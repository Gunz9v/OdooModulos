import base64
import calendar
import hashlib
import json
import re
import time
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
        try:
            data = self._request_json(ticket, "GET", url, company)
        except UserError as error:
            existing_ticket_number = self._existing_process_ticket_number(ticket.response_payload)
            if not existing_ticket_number:
                raise
            ticket.write(
                {
                    "ticket_number": existing_ticket_number,
                    "status_code": "01",
                    "status_description": "Propuesta solicitada en otro ambiente",
                    "state": "sent",
                    "sunat_process_code": "10",
                    "sunat_book_code": "080000" if period.registry_type == "rce" else "140000",
                    "error_code": False,
                    "error_message": False,
                }
            )
            proposal.write({"ticket_number": existing_ticket_number, "state": "requested"})
            period.write({"state": "proposal_requested", "sunat_proposal_id": proposal.id})
            period.message_post(
                body=_("SUNAT ya tenia una solicitud de propuesta en curso. Se registro el ticket existente: %s")
                % existing_ticket_number
            )
            return ticket
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
                "sunat_process_code": "10",
                "sunat_book_code": "080000" if period.registry_type == "rce" else "140000",
            }
        )
        proposal.write({"ticket_number": num_ticket, "state": "requested"})
        period.write({"state": "proposal_requested", "sunat_proposal_id": proposal.id})
        period.message_post(body=_("Solicitud de propuesta SUNAT enviada. Ticket: %s") % num_ticket)
        return ticket

    def accept_proposal(self, period):
        period.ensure_one()
        if period.registry_type not in ("rvie", "rce"):
            raise UserError(_("La aceptacion de propuesta SUNAT corresponde a RVIE o RCE."))
        company = period.company_id
        self._ensure_token(company)
        per_tributario = self._format_period(period)
        path = self._accept_proposal_endpoint(period, per_tributario)
        url = self._build_url(company, path)
        ticket = self._create_ticket(
            company,
            "submit_acceptance",
            "POST",
            url,
            {
                "period": per_tributario,
                "registry_type": period.registry_type,
            },
            period=period,
            proposal=period.sunat_proposal_id,
        )
        data = self._request_json(ticket, "POST", url, company)
        num_ticket = data.get("numTicket")
        if not num_ticket:
            self._mark_error(ticket, company, "missing_ticket", json.dumps(data, ensure_ascii=True))
            raise UserError(_("SUNAT no devolvio numTicket para la aceptacion de propuesta."))
        ticket.write(
            {
                "ticket_number": num_ticket,
                "status_code": "01",
                "status_description": "Aceptacion de propuesta enviada",
                "state": "sent",
                "sunat_process_code": "2",
                "sunat_book_code": "080000" if period.registry_type == "rce" else "140000",
            }
        )
        period.write({"state": "pending_sunat_confirmation"})
        period.message_post(body=_("Aceptacion de propuesta SUNAT enviada. Ticket: %s") % num_ticket)
        return ticket

    def generate_records(self, generation):
        generation.ensure_one()
        company = generation.company_id
        self._ensure_token(company)
        per_tributario = (generation.period_code or "").replace("-", "")
        path = "/v1/contribuyente/migeigv/libros/rvierce/gestionlibro/web/registroslibros/%s/registrapreliminar" % per_tributario
        url = self._build_url(company, path)
        ticket = self._create_ticket(
            company,
            "generate_records",
            "POST",
            url,
            {"period": per_tributario},
        )
        self._request(ticket, "POST", url, company, retry_auth=True)
        ticket.write(
            {
                "state": "done",
                "status_description": "Registros generados",
                "sunat_process_code": "5",
                "sunat_book_code": "080000/140000",
            }
        )
        return ticket

    def delete_registered_preliminary(self, generation_line):
        generation_line.ensure_one()
        period = generation_line.period_id
        company = generation_line.company_id
        self._ensure_token(company)
        per_tributario = self._format_period(period)
        cod_libro = "080000" if generation_line.registry_type == "rce" else "140000"
        payload = {
            "id": "",
            "codTipoRegistro": "08" if generation_line.registry_type == "rce" else "14",
        }
        url = self._build_url(
            company,
            "/v1/contribuyente/migeigv/libros/rvierce/gestionlibro/web/registroslibros/%s/eliminapreliminar"
            % per_tributario,
            {"codLibro": cod_libro},
        )
        ticket = self._create_ticket(
            company,
            "delete_preliminary",
            "PUT",
            url,
            payload,
            period=period,
        )
        self._request(ticket, "PUT", url, company, retry_auth=True, payload=payload)
        ticket.write(
            {
                "state": "done",
                "status_description": "Preliminar eliminado",
                "sunat_process_code": "delete_preliminary",
                "sunat_book_code": cod_libro,
            }
        )
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
        if (
            ticket.state == "done"
            and ticket.status_code == "06"
            and ticket.process_type == "submit_acceptance"
            and ticket.period_id
        ):
            self.env["sire.register.generation"].sync_period_after_acceptance(ticket.period_id, ticket=ticket)
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

    def request_rvie_cp_inconsistencies(self, source_ticket):
        source_ticket.ensure_one()
        period = source_ticket.period_id
        if not period or period.registry_type != "rvie":
            raise UserError(_("Las inconsistencias por CP corresponden al RVIE."))
        company = source_ticket.company_id
        self._ensure_token(company)
        per_tributario = self._format_period(period)
        last_day = calendar.monthrange(period.year, int(period.month))[1]
        params = {
            "codTipoArchivo": "0",
            "fecEmisionIni": "01/%s/%04d" % (period.month, period.year),
            "fecEmisionFin": "%02d/%s/%04d" % (last_day, period.month, period.year),
            "codInconsistencia": "",
            "numDocAdquiriente": "",
            "codTipoCDP": "",
            "numSerieCDP": "",
            "numCDP": "",
            "s": "",
            "ord": "",
        }
        url = self._build_url(
            company,
            "/v1/contribuyente/migeigv/libros/rvie/inconsistencias/web/periodoinconsistencias/%s/exporta"
            % per_tributario,
            params,
        )
        ticket = self._create_ticket(
            company,
            "request_cp_inconsistencies",
            "GET",
            url,
            params,
            period=period,
        )
        data = self._request_json(ticket, "GET", url, company)
        num_ticket = data.get("numTicket") if isinstance(data, dict) else False
        if not num_ticket:
            raise UserError(_("SUNAT no devolvio numTicket para el reporte de inconsistencias CP."))
        ticket.write(
            {
                "ticket_number": num_ticket,
                "state": "sent",
                "status_description": "Solicitud de inconsistencias CP enviada",
                "sunat_process_code": "13",
                "sunat_book_code": "140000",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Ticket inconsistencias CP"),
            "res_model": "sire.api.ticket",
            "view_mode": "form",
            "res_id": ticket.id,
        }

    def submit_generated_file(self, period, submission_type, file_data, filename):
        period.ensure_one()
        company = period.company_id
        self._ensure_token(company)
        raw_file = base64.b64decode(file_data or b"")
        if not raw_file:
            raise UserError(_("El archivo a enviar esta vacio."))
        upload_filename = self._normalize_upload_filename(filename)
        submission = self._submission_metadata(period, submission_type, upload_filename)
        url = self._build_url(company, submission["path"])
        ticket = self._create_ticket(
            company,
            submission["process_type"],
            "TUS",
            url,
            {
                "filename": upload_filename,
                "period": self._format_period(period),
                "submission_type": submission_type,
                "metadata": submission["metadata"],
            },
            period=period,
        )
        ticket.write(
            {
                "submitted_filename": upload_filename,
                "submitted_file": base64.b64encode(raw_file),
                "submitted_file_hash": hashlib.sha256(raw_file).hexdigest(),
                "sunat_process_code": submission["metadata"]["codProceso"],
                "sunat_book_code": submission["metadata"]["codLibro"],
            }
        )
        num_ticket = self._tus_upload(ticket, company, url, raw_file, upload_filename, submission["metadata"])
        ticket.write(
            {
                "ticket_number": num_ticket,
                "status_code": "01",
                "status_description": "Archivo enviado a SUNAT",
                "state": "sent",
            }
        )
        period.message_post(
            body=_("Archivo SIRE enviado a SUNAT: %(file)s. Ticket: %(ticket)s")
            % {"file": upload_filename, "ticket": num_ticket}
        )
        return ticket

    def submit_generated_file_and_download_result(self, period, submission_type, file_data, filename):
        ticket = self.submit_generated_file(period, submission_type, file_data, filename)
        max_checks = int(self.env.context.get("sire_submit_max_checks", 8))
        sleep_seconds = int(self.env.context.get("sire_submit_sleep_seconds", 2))
        for attempt in range(max(max_checks, 1)):
            self.check_ticket_status(ticket)
            if ticket.state == "done" and ticket.status_code == "06":
                break
            if attempt < max_checks - 1 and sleep_seconds:
                time.sleep(sleep_seconds)
        if ticket.state == "done" and ticket.status_code == "06":
            if ticket.result_filename:
                self.download_ticket_file(ticket)
            self.download_receipt_file(ticket, raise_if_missing=False)
        return ticket

    def download_receipt_file(self, ticket, raise_if_missing=True):
        ticket.ensure_one()
        company = ticket.company_id
        self._ensure_token(company)
        last_error = False
        for filename in self._receipt_filename_candidates(ticket):
            params = {"nomArchivo": filename}
            url = self._build_url(
                company,
                "/v1/contribuyente/migeigv/libros/rvierce/gestionlibro/web/registroslibros/constancia/archivo",
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
                response = self._request_json(ticket, "GET", url, company)
            except UserError as error:
                last_error = error
                continue
            encoded_pdf = response.get("archivoPdf") if isinstance(response, dict) else False
            if not encoded_pdf:
                last_error = UserError(_("SUNAT no devolvio archivoPdf para la constancia."))
                continue
            ticket.write(
                {
                    "receipt_filename": filename,
                    "receipt_file": encoded_pdf,
                    "state": "done",
                    "status_description": "Constancia descargada",
                }
            )
            return True
        if raise_if_missing and last_error:
            raise last_error
        return False

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
                            "codProceso": ticket.sunat_process_code or "10",
                            "numTicket": ticket.ticket_number or "",
                            "codLibro": ticket.sunat_book_code or cod_libro,
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
        if ticket.sunat_book_code:
            candidates.append(ticket.sunat_book_code)
        if ticket.period_id.registry_type == "rce":
            if "080000" not in candidates:
                candidates.append("080000")
        else:
            match = re.search(r"14\d{4}", filename or "")
            if match:
                candidates.append(match.group(0))
            if "140000" not in candidates:
                candidates.append("140000")
        return candidates

    def _submission_metadata(self, period, submission_type, filename):
        per_tributario = self._format_period(period)
        book_code = "080000" if period.registry_type == "rce" else "140000"
        metadata = {
            "filename": filename,
            "filetype": "application/zip",
            "numRuc": (period.company_id.sire_ruc or period.company_id.vat or "").strip(),
            "perTributario": per_tributario,
            "codOrigenEnvio": "2",
            "codProceso": self._submission_process_code(period, submission_type),
            "codTipoCorrelativo": "01",
            "nomArchivoImportacion": filename,
            "codLibro": book_code,
        }
        return {
            "path": self._submission_upload_path(period, submission_type),
            "metadata": metadata,
            "process_type": self._submission_process_type(submission_type),
        }

    def _submission_process_code(self, period, submission_type):
        if submission_type == "replacement":
            return "3"
        if submission_type in ("complement", "rce_cp"):
            return "1"
        if submission_type in ("rcecom", "rcetca"):
            return "1"
        if submission_type == "rceinex":
            return "1"
        raise UserError(_("Tipo de envio SIRE no soportado: %s") % submission_type)

    def _submission_process_type(self, submission_type):
        if submission_type == "replacement":
            return "submit_replacement"
        if submission_type in ("complement", "rce_cp", "rcecom", "rceinex", "rcetca"):
            return "submit_complement"
        return "submit_replacement"

    def _submission_upload_path(self, period, submission_type):
        return "/v1/contribuyente/migeigv/libros/rvierce/receptorpropuesta/web/propuesta/upload"

    def _normalize_upload_filename(self, filename):
        filename = (filename or "").strip()
        if not filename:
            raise UserError(_("El archivo a enviar no tiene nombre."))
        if not filename.lower().endswith(".zip"):
            filename = "%s.zip" % filename
        return filename

    def _tus_upload(self, ticket, company, url, file_content, filename, metadata):
        headers = {
            "Authorization": "Bearer %s" % company.sire_access_token,
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(len(file_content)),
            "Upload-Metadata": self._tus_metadata_header(metadata),
        }
        try:
            create_response = requests.post(url, headers=headers, timeout=60)
        except requests.RequestException as error:
            self._mark_error(ticket, company, "request_error", str(error))
            raise UserError(_("No se pudo crear la carga TUS en SUNAT: %s") % error) from error
        ticket.write(
            {
                "status_code": str(create_response.status_code),
                "response_payload": self._response_payload(create_response),
                "attempt_count": ticket.attempt_count + 1,
            }
        )
        if create_response.status_code == 401:
            company.write({"sire_access_token": False, "sire_token_expiration": False})
            self.get_token(company)
            return self._tus_upload(ticket, company, url, file_content, filename, metadata)
        if create_response.status_code >= 400:
            self._mark_error(ticket, company, str(create_response.status_code), self._response_payload(create_response))
            raise UserError(_("SUNAT rechazo la creacion de carga TUS: %s") % self._response_payload(create_response)[:500])
        upload_url = create_response.headers.get("Location")
        if not upload_url:
            self._mark_error(ticket, company, "missing_location", self._response_payload(create_response))
            raise UserError(_("SUNAT no devolvio la URL Location para la carga TUS."))
        if upload_url.startswith("/"):
            upload_url = "%s%s" % ((company.sire_api_base_url or "https://api-sire.sunat.gob.pe").rstrip("/"), upload_url)

        patch_headers = {
            "Authorization": "Bearer %s" % company.sire_access_token,
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
            "Accept": "application/json",
        }
        ticket.write(
            {
                "request_method": "PATCH",
                "request_url": upload_url,
                "request_payload": json.dumps(
                    {"filename": filename, "bytes": len(file_content), "metadata": metadata},
                    ensure_ascii=True,
                    indent=2,
                ),
            }
        )
        try:
            upload_response = requests.patch(upload_url, headers=patch_headers, data=file_content, timeout=300)
        except requests.RequestException as error:
            self._mark_error(ticket, company, "request_error", str(error))
            raise UserError(_("No se pudo subir el archivo a SUNAT: %s") % error) from error
        ticket.write(
            {
                "status_code": str(upload_response.status_code),
                "response_payload": self._response_payload(upload_response),
                "attempt_count": ticket.attempt_count + 1,
            }
        )
        if upload_response.status_code >= 400:
            self._mark_error(ticket, company, str(upload_response.status_code), self._response_payload(upload_response))
            raise UserError(_("SUNAT rechazo la carga del archivo: %s") % self._response_payload(upload_response)[:500])
        num_ticket = self._extract_ticket_number_from_response(upload_response)
        if not num_ticket:
            self._mark_error(ticket, company, "missing_ticket", self._response_payload(upload_response))
            raise UserError(_("SUNAT recibio el archivo, pero no devolvio numTicket."))
        return num_ticket

    def _tus_metadata_header(self, metadata):
        parts = []
        for key, value in metadata.items():
            raw_value = str(value or "").encode("utf-8")
            parts.append("%s %s" % (key, base64.b64encode(raw_value).decode("ascii")))
        return ",".join(parts)

    def _extract_ticket_number_from_response(self, response):
        payload = response.text or ""
        try:
            data = response.json()
        except ValueError:
            data = {}
        if isinstance(data, dict):
            for key in ("numTicket", "ticket", "numeroTicket"):
                if data.get(key):
                    return data[key]
        match = re.search(r"\b\d{12,14}\b", payload)
        return match.group(0) if match else False

    def _receipt_filename_candidates(self, ticket):
        candidates = []
        for filename in (ticket.receipt_filename, ticket.result_filename, ticket.result_content_filename):
            if filename and filename.lower().endswith(".pdf") and filename not in candidates:
                candidates.append(filename)
        base = ticket.submitted_filename or ""
        if base:
            pdf_name = re.sub(r"\.zip$", ".pdf", base, flags=re.IGNORECASE)
            if pdf_name not in candidates:
                candidates.append(pdf_name)
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
                "codTipoArchivo": "0",
            },
        )

    def _accept_proposal_endpoint(self, period, per_tributario):
        if period.registry_type == "rce":
            return "/v1/contribuyente/migeigv/libros/rce/propuesta/web/registroslibros/%s/aceptarpropuesta" % per_tributario
        return "/v1/contribuyente/migeigv/libros/rvie/propuesta/web/propuesta/%s/aceptapropuesta" % per_tributario

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

    def _request(self, ticket, method, url, company, retry_auth=False, payload=False):
        request_kwargs = {"headers": self._headers(company), "timeout": 60}
        if payload is not False:
            request_kwargs["json"] = payload
        try:
            response = requests.request(method, url, **request_kwargs)
        except requests.RequestException as error:
            self._mark_error(ticket, company, "request_error", str(error))
            raise UserError(_("No se pudo conectar con SUNAT: %s") % error) from error
        if response.status_code == 401 and retry_auth:
            company.write({"sire_access_token": False, "sire_token_expiration": False})
            self.get_token(company)
            request_kwargs["headers"] = self._headers(company)
            try:
                response = requests.request(method, url, **request_kwargs)
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

    def _existing_process_ticket_number(self, payload):
        payload = payload or ""
        if '"cod":42209' not in payload and "aun tiene un proceso" not in payload:
            return False
        match = re.search(r"Ticket:\s*(?P<ticket>\d{12,14})", payload)
        if match:
            return match.group("ticket")
        match = re.search(r"\b(?P<ticket>\d{12,14})\b", payload)
        return match.group("ticket") if match else False

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
