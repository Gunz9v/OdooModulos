import base64
import calendar
import hashlib
import json
import re
from datetime import timedelta
from urllib.parse import urlencode

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


class SireApiClient(models.AbstractModel):
    _name = "sire.api.client"
    _description = "Cliente API SUNAT SIRE"

    def get_token(self, company):
        self._validate_token_config(company)
        url = self._render_token_url(company)
        payload = {
            "grant_type": "password",
            "scope": company.sire_oauth_scope or "",
            "client_id": company.sire_client_id,
            "client_secret": company.sire_client_secret,
            "username": "%s%s" % (company.sire_ruc or "", company.sire_sol_user or ""),
            "password": company.sire_sol_password,
        }
        ticket = self._create_ticket(company, "get_token", "POST", url, self._safe_payload(payload))
        try:
            response = requests.post(url, data=payload, timeout=30)
        except requests.RequestException as error:
            self._mark_error(ticket, company, "request_error", str(error))
            raise UserError(_("No se pudo conectar con SUNAT: %s") % error) from error

        response_text = response.text or ""
        ticket.write(
            {
                "status_code": str(response.status_code),
                "response_payload": response_text[:10000],
                "attempt_count": ticket.attempt_count + 1,
            }
        )
        if response.status_code >= 400:
            self._mark_error(ticket, company, str(response.status_code), response_text[:2000])
            raise UserError(_("SUNAT rechazo la solicitud de token: %s") % response_text[:500])

        try:
            data = response.json()
        except ValueError as error:
            self._mark_error(ticket, company, "invalid_json", response_text[:2000])
            raise UserError(_("SUNAT devolvio una respuesta de token no valida.")) from error

        access_token = data.get("access_token")
        if not access_token:
            self._mark_error(ticket, company, "missing_token", response_text[:2000])
            raise UserError(_("La respuesta de SUNAT no contiene access_token."))

        expires_in = int(data.get("expires_in") or 0)
        expiration = False
        if expires_in:
            expiration = fields.Datetime.now() + timedelta(seconds=max(expires_in - 60, 0))
        company.write(
            {
                "sire_access_token": access_token,
                "sire_token_expiration": expiration,
                "sire_connection_state": "token_ok",
                "sire_last_connection_error": False,
            }
        )
        ticket.write(
            {
                "state": "done",
                "status_description": "Token obtenido",
            }
        )
        return data

    def request_proposal(self, period):
        period.ensure_one()
        if period.registry_type not in ("rvie", "rce"):
            raise UserError(_("La descarga de propuesta SUNAT corresponde a RVIE o RCE."))
        company = period.company_id
        self._ensure_token(company)
        per_tributario = self._format_period(period)
        path, params = self._proposal_request_endpoint(period, per_tributario)
        url = self._build_url(company, path, params)
        proposal = self._create_proposal(period)
        ticket = self._create_ticket(
            company,
            "request_proposal",
            "GET",
            url,
            {
                "period": per_tributario,
                "registry_type": period.registry_type,
                "params": params,
            },
            period=period,
            proposal=proposal,
        )
        data = self._request_json(ticket, "GET", url, company)
        num_ticket = data.get("numTicket")
        if not num_ticket:
            self._mark_error(ticket, company, "missing_ticket", json.dumps(data, ensure_ascii=True))
            raise UserError(_("SUNAT no devolvio numTicket para la propuesta."))
        ticket.write(
            {
                "ticket_number": num_ticket,
                "status_code": "01",
                "status_description": "Propuesta solicitada",
                "state": "sent",
            }
        )
        proposal.write({"ticket_number": num_ticket, "state": "requested"})
        period.write({"state": "proposal_requested", "sunat_proposal_id": proposal.id})
        period.message_post(body=_("Solicitud de propuesta SUNAT enviada. Ticket: %s") % num_ticket)
        return ticket

    def get_rvie_periods(self, company):
        self._ensure_token(company)
        url = self._build_url(
            company,
            "/v1/contribuyente/migeigv/libros/rvierce/padron/web/omisos/140000/periodos",
        )
        ticket = self._create_ticket(
            company,
            "check_periods",
            "GET",
            url,
            {"codLibro": "140000"},
        )
        data = self._request_json(ticket, "GET", url, company)
        ticket.write(
            {
                "state": "done",
                "status_description": "Periodos RVIE consultados",
            }
        )
        return data

    def check_ticket_status(self, ticket):
        ticket.ensure_one()
        company = ticket.company_id
        self._ensure_token(company)
        per_tributario = self._format_period(ticket.period_id)
        params = {
            "perIni": per_tributario,
            "perFin": per_tributario,
            "page": "1",
            "perPage": "20",
            "numTicket": ticket.ticket_number or "",
        }
        url = self._build_url(
            company,
            "/v1/contribuyente/migeigv/libros/rvierce/gestionprocesosmasivos/web/masivo/consultaestadotickets",
            params,
        )
        ticket.write(
            {
                "request_method": "GET",
                "request_url": url,
                "request_payload": json.dumps(params, ensure_ascii=True, indent=2),
            }
        )
        data = self._request_json(ticket, "GET", url, company)
        record = self._find_ticket_record(data, ticket.ticket_number)
        if not record:
            ticket.write(
                {
                    "status_code": "not_found",
                    "status_description": "Ticket no encontrado en respuesta SUNAT",
                    "state": "sent",
                }
            )
            return data

        file_info = self._first_file_info(record)
        detail = record.get("detalleTicket") or {}
        values = {
            "last_check_at": fields.Datetime.now(),
            "status_code": record.get("codEstadoProceso") or record.get("codEstadoEnvio"),
            "status_description": record.get("desEstadoProceso") or record.get("desEstadoEnvio"),
            "state": "done" if (record.get("codEstadoProceso") or record.get("codEstadoEnvio")) == "06" else "sent",
            "validated_row_count": int(detail.get("cntFilasvalidada") or 0),
            "error_document_count": int(detail.get("cntCPError") or 0),
            "informed_document_count": int(detail.get("cntCPInformados") or 0),
        }
        if file_info:
            values.update(
                {
                    "result_filename": file_info.get("nomArchivoReporte"),
                    "result_content_filename": file_info.get("nomArchivoContenido"),
                    "result_file_type": file_info.get("codTipoAchivoReporte")
                    or file_info.get("codTipoArchivoReporte")
                    or "null",
                }
            )
        ticket.write(values)
        return data

    def download_ticket_file(self, ticket):
        ticket.ensure_one()
        if not ticket.result_filename:
            raise UserError(_("Primero consulta el ticket hasta obtener el nombre del archivo."))
        company = ticket.company_id
        self._ensure_token(company)
        response, used_file_type, used_filename = self._download_ticket_file_response(ticket, company)
        if not response:
            return False
        file_data = response.content
        encoded = base64.b64encode(file_data)
        values = {
            "result_file": encoded,
            "result_file_type": used_file_type,
            "state": "done",
            "status_description": "Archivo descargado",
        }
        ticket.write(values)
        if ticket.proposal_id:
            ticket.proposal_id.write(
                {
                    "downloaded_at": fields.Datetime.now(),
                    "source_filename": used_filename,
                    "zip_file": encoded,
                    "file_hash": hashlib.sha256(file_data).hexdigest(),
                    "state": "downloaded",
                }
            )
            ticket.period_id.write({"state": "proposal_downloaded"})
        return response

    def _download_ticket_file_response(self, ticket, company):
        last_error = False
        for filename in self._filename_candidates(ticket):
            for cod_libro in self._cod_libro_candidates(ticket, filename):
                for type_param in self._file_type_param_candidates():
                    for file_type in self._file_type_candidates(ticket.result_file_type):
                        params = {
                            "nomArchivoReporte": filename,
                            type_param: file_type,
                            "perTributario": self._format_period(ticket.period_id),
                            "codProceso": "10",
                            "numTicket": ticket.ticket_number or "",
                            "codLibro": cod_libro,
                        }
                        url = self._build_url(
                            company,
                            "/v1/contribuyente/migeigv/libros/rvierce/gestionprocesosmasivos/web/masivo/archivoreporte",
                            params,
                        )
                        ticket.write(
                            {
                                "request_method": "GET",
                                "request_url": url,
                                "request_payload": json.dumps(params, ensure_ascii=True, indent=2),
                            }
                        )
                        try:
                            return self._request_binary(ticket, "GET", url, company), file_type, filename
                        except UserError as error:
                            last_error = error
                            if not self._is_missing_file_error(ticket.response_payload):
                                raise
        if last_error:
            if ticket.informed_document_count == 0:
                message = _(
                    "SUNAT termino el ticket, pero reporto 0 comprobantes informados y no publico un archivo descargable."
                )
                ticket.write(
                    {
                        "state": "done",
                        "status_description": "Sin archivo por propuesta vacia",
                        "error_code": "2244",
                        "error_message": message,
                    }
                )
                if ticket.proposal_id:
                    ticket.proposal_id.write(
                        {
                            "downloaded_at": fields.Datetime.now(),
                            "source_filename": ticket.result_filename,
                            "record_count": 0,
                            "state": "empty",
                        }
                    )
                    ticket.period_id.write(
                        {
                            "state": "proposal_downloaded",
                            "total_sunat_records": 0,
                        }
                    )
                return False, ticket.result_file_type or "00", ticket.result_filename
            raise last_error
        raise UserError(_("No se pudo construir la solicitud de descarga del archivo SUNAT."))

    def _filename_candidates(self, ticket):
        candidates = []
        for filename in (ticket.result_filename, ticket.result_content_filename):
            if filename and filename not in candidates:
                candidates.append(filename)
        if ticket.response_payload and not ticket.result_content_filename:
            try:
                data = json.loads(ticket.response_payload)
            except ValueError:
                data = {}
            record = self._find_ticket_record(data, ticket.ticket_number)
            file_info = self._first_file_info(record or {})
            for filename in (
                file_info.get("nomArchivoReporte") if file_info else False,
                file_info.get("nomArchivoContenido") if file_info else False,
            ):
                if filename and filename not in candidates:
                    candidates.append(filename)
        return candidates

    def _file_type_param_candidates(self):
        return ["codTipoArchivoReporte", "codTipoAchivoReporte"]

    def _cod_libro_candidates(self, ticket, filename):
        candidates = []
        if ticket.period_id.registry_type == "rce":
            candidates.append("080000")
        else:
            match = re.search(r"14\d{4}", filename or "")
            if match:
                candidates.append(match.group(0))
            if "140000" not in candidates:
                candidates.append("140000")
        return candidates

    def _proposal_request_endpoint(self, period, per_tributario):
        if period.registry_type == "rce":
            return (
                "/v1/contribuyente/migeigv/libros/rce/propuesta/web/propuesta/%s/exportacioncomprobantepropuesta"
                % per_tributario,
                {
                    "codTipoArchivo": "0",
                    "codOrigenEnvio": "2",
                },
            )
        return (
            "/v1/contribuyente/migeigv/libros/rvie/propuesta/web/propuesta/%s/exportapropuesta"
            % per_tributario,
            {
                "fecDocumentoDesde": self._period_start_date(period),
                "fecDocumentoHasta": self._period_end_date(period),
                "codTipoArchivo": "0",
            },
        )

    def _validate_token_config(self, company):
        missing = []
        for field_name, label in [
            ("sire_ruc", "RUC SIRE"),
            ("sire_sol_user", "Usuario SOL"),
            ("sire_sol_password", "Clave SOL"),
            ("sire_client_id", "Client ID"),
            ("sire_client_secret", "Client Secret"),
            ("sire_oauth_token_url", "URL token OAuth"),
        ]:
            if not company[field_name]:
                missing.append(label)
        if missing:
            raise UserError(_("Faltan datos de configuracion SUNAT: %s") % ", ".join(missing))

    def _render_token_url(self, company):
        url_template = company.sire_oauth_token_url or ""
        try:
            return url_template % {"client_id": company.sire_client_id}
        except (KeyError, TypeError, ValueError):
            return url_template

    def _ensure_token(self, company):
        if not company.sire_access_token or self._token_is_expired(company):
            self.get_token(company)

    def _token_is_expired(self, company):
        return bool(company.sire_token_expiration and company.sire_token_expiration <= fields.Datetime.now())

    def _create_ticket(self, company, process_type, method, url, payload, period=False, proposal=False):
        return self.env["sire.api.ticket"].create(
            {
                "company_id": company.id,
                "period_id": period.id if period else False,
                "proposal_id": proposal.id if proposal else False,
                "process_type": process_type,
                "request_method": method,
                "request_url": url,
                "request_payload": json.dumps(payload or {}, ensure_ascii=True, indent=2),
                "state": "sent",
            }
        )

    def _create_proposal(self, period):
        last = self.env["sire.sunat.proposal"].search(
            [("period_id", "=", period.id)],
            order="proposal_version desc",
            limit=1,
        )
        return self.env["sire.sunat.proposal"].create(
            {
                "period_id": period.id,
                "proposal_version": (last.proposal_version or 0) + 1,
                "requested_at": fields.Datetime.now(),
                "state": "draft",
            }
        )

    def _request_json(self, ticket, method, url, company):
        response = self._request(ticket, method, url, company, retry_auth=True)
        try:
            return response.json()
        except ValueError as error:
            self._mark_error(ticket, company, "invalid_json", (response.text or "")[:2000])
            raise UserError(_("SUNAT devolvio una respuesta JSON no valida.")) from error

    def _request_binary(self, ticket, method, url, company):
        return self._request(ticket, method, url, company, retry_auth=True)

    def _request(self, ticket, method, url, company, retry_auth=False):
        try:
            response = requests.request(method, url, headers=self._headers(company), timeout=60)
        except requests.RequestException as error:
            self._mark_error(ticket, company, "request_error", str(error))
            raise UserError(_("No se pudo conectar con SUNAT: %s") % error) from error
        if response.status_code == 401 and retry_auth:
            company.write({"sire_access_token": False, "sire_token_expiration": False})
            self.get_token(company)
            try:
                response = requests.request(method, url, headers=self._headers(company), timeout=60)
            except requests.RequestException as error:
                self._mark_error(ticket, company, "request_error", str(error))
                raise UserError(_("No se pudo conectar con SUNAT: %s") % error) from error
        ticket.write(
            {
                "status_code": str(response.status_code),
                "response_payload": self._response_payload(response),
                "attempt_count": ticket.attempt_count + 1,
            }
        )
        if response.status_code >= 400:
            self._mark_error(ticket, company, str(response.status_code), self._response_payload(response))
            if response.status_code == 401:
                raise UserError(
                    _(
                        "SUNAT rechazo la solicitud con 401 Authorization Required aun despues de renovar el token. "
                        "Verifica que el usuario SOL, Client ID/Secret y permisos API tengan acceso a SIRE/RVIE."
                    )
                )
            raise UserError(_("SUNAT rechazo la solicitud: %s") % self._response_payload(response)[:500])
        return response

    def _headers(self, company):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer %s" % company.sire_access_token,
        }

    def _response_payload(self, response):
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type or "text/" in content_type:
            return (response.text or "")[:10000]
        return "Binary response: %s bytes; content-type=%s" % (len(response.content or b""), content_type)

    def _build_url(self, company, path, params=False):
        base_url = (company.sire_api_base_url or "https://api-sire.sunat.gob.pe").rstrip("/")
        url = "%s%s" % (base_url, path)
        if params:
            url = "%s?%s" % (url, urlencode(params))
        return url

    def _format_period(self, period):
        return (period.period_code or "").replace("-", "")

    def _period_start_date(self, period):
        return "01/%s/%04d" % (period.month, period.year)

    def _period_end_date(self, period):
        last_day = calendar.monthrange(period.year, int(period.month))[1]
        return "%02d/%s/%04d" % (last_day, period.month, period.year)

    def _find_ticket_record(self, data, ticket_number):
        records = data.get("registros") or []
        if ticket_number:
            for record in records:
                if record.get("numTicket") == ticket_number:
                    return record
                detail = record.get("detalleTicket") or {}
                if detail.get("numTicket") == ticket_number:
                    return record
        return records[0] if records else False

    def _first_file_info(self, record):
        files = record.get("archivoReporte") or []
        if files:
            return files[0]
        detail = record.get("detalleTicket") or {}
        if detail.get("nomArchivoReporte"):
            return detail
        return False

    def _file_type_candidates(self, file_type):
        first = file_type or "null"
        candidates = [first]
        if isinstance(first, str) and first.isdigit():
            normalized = str(int(first))
            if normalized not in candidates:
                candidates.append(normalized)
        if "null" not in candidates:
            candidates.append("null")
        return candidates

    def _is_missing_file_error(self, payload):
        payload = payload or ""
        return '"cod":2244' in payload or "El archivo solicitado no existe" in payload

    def _mark_error(self, ticket, company, code, message):
        ticket.write(
            {
                "state": "error",
                "error_code": code,
                "error_message": message,
                "status_description": "Error",
            }
        )
        company.write(
            {
                "sire_connection_state": "error",
                "sire_last_connection_error": message,
            }
        )

    def _safe_payload(self, payload):
        safe = dict(payload or {})
        for key in ("client_secret", "password"):
            if safe.get(key):
                safe[key] = "***"
        return safe
