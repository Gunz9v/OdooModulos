import base64
from unittest.mock import Mock, patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSireApi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "sire_ruc": "20100080932",
                "sire_sol_user": "MODDATOS",
                "sire_sol_password": "secret",
                "sire_client_id": "client-id",
                "sire_client_secret": "client-secret",
                "sire_oauth_token_url": "https://example.test/%(client_id)s/token",
                "sire_oauth_scope": "scope",
            }
        )

    def test_get_token_stores_token_and_ticket(self):
        response = Mock()
        response.status_code = 200
        response.text = '{"access_token":"abc","expires_in":3600}'
        response.json.return_value = {"access_token": "abc", "expires_in": 3600}

        with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.post", return_value=response) as post:
            data = self.env["sire.api.client"].get_token(self.company)

        self.assertEqual(data["access_token"], "abc")
        self.assertEqual(self.company.sire_access_token, "abc")
        self.assertEqual(self.company.sire_connection_state, "token_ok")
        self.assertTrue(post.called)
        ticket = self.env["sire.api.ticket"].search([("process_type", "=", "get_token")], limit=1)
        self.assertEqual(ticket.state, "done")
        self.assertIn("***", ticket.request_payload)
        self.assertNotIn('"password": "secret"', ticket.request_payload)
        self.assertNotIn('"client_secret": "client-secret"', ticket.request_payload)

    def test_missing_token_config_raises_user_error(self):
        self.company.sire_client_secret = False

        with self.assertRaises(UserError):
            self.env["sire.api.client"].get_token(self.company)

    def test_request_proposal_creates_pending_ticket(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "05",
            }
        )
        response = Mock()
        response.status_code = 200
        response.text = '{"numTicket":"20230300000001"}'
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"numTicket": "20230300000001"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=response,
        ) as request:
            ticket = self.env["sire.api.client"].request_proposal(period)

        self.assertEqual(ticket.process_type, "request_proposal")
        self.assertEqual(ticket.ticket_number, "20230300000001")
        self.assertEqual(period.state, "proposal_requested")
        self.assertIn("/v1/contribuyente/migeigv/libros/rvie/propuesta/web/propuesta/209705/exportapropuesta", request.call_args[0][1])
        self.assertIn("codTipoArchivo=0", request.call_args[0][1])
        self.assertNotIn("fecDocumentoDesde", request.call_args[0][1])
        self.assertNotIn("fecDocumentoHasta", request.call_args[0][1])

    def test_request_rvie_proposal_adopts_existing_ticket_from_sunat_42209(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "06",
            }
        )
        response = Mock()
        response.status_code = 422
        response.text = (
            '{"cod":422,"msg":"Unprocessable Entity","errors":[{"cod":42209,'
            '"msg":"Estimado contribuyente aun tiene un proceso de \\"Generar archivo exportar propuesta\\" '
            'en curso con Ticket: 20260300004478 y Fecha Envio: 14/07/2026 11:27:36"}]}'
        )
        response.content = response.text.encode()
        response.headers = {"Content-Type": "application/json"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=response,
        ):
            ticket = self.env["sire.api.client"].request_proposal(period)

        self.assertEqual(ticket.ticket_number, "20260300004478")
        self.assertEqual(ticket.process_type, "request_proposal")
        self.assertEqual(ticket.sunat_process_code, "10")
        self.assertEqual(ticket.sunat_book_code, "140000")
        self.assertEqual(ticket.state, "sent")
        self.assertEqual(period.sunat_proposal_id.ticket_number, "20260300004478")

    def test_request_rce_proposal_uses_purchase_endpoint(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rce",
                "year": 2097,
                "month": "05",
            }
        )
        response = Mock()
        response.status_code = 200
        response.text = '{"numTicket":"20260300004317"}'
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"numTicket": "20260300004317"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=response,
        ) as request:
            ticket = self.env["sire.api.client"].request_proposal(period)

        self.assertEqual(ticket.ticket_number, "20260300004317")
        self.assertIn("/v1/contribuyente/migeigv/libros/rce/propuesta/web/propuesta/209705/exportacioncomprobantepropuesta", request.call_args[0][1])
        self.assertIn("codTipoArchivo=0", request.call_args[0][1])
        self.assertIn("codOrigenEnvio=2", request.call_args[0][1])
        self.assertNotIn("fecDocumentoDesde", request.call_args[0][1])

    def test_accept_rvie_proposal_creates_ticket(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "05",
                "decision_type": "accept",
            }
        )
        response = Mock()
        response.status_code = 200
        response.text = '{"numTicket":"20260300004500"}'
        response.content = response.text.encode()
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"numTicket": "20260300004500"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=response,
        ) as request:
            ticket = self.env["sire.api.client"].accept_proposal(period)

        self.assertEqual(ticket.process_type, "submit_acceptance")
        self.assertEqual(ticket.ticket_number, "20260300004500")
        self.assertEqual(ticket.sunat_process_code, "2")
        self.assertEqual(ticket.sunat_book_code, "140000")
        self.assertEqual(period.state, "pending_sunat_confirmation")
        self.assertEqual(request.call_args[0][0], "POST")
        self.assertIn("/v1/contribuyente/migeigv/libros/rvie/propuesta/web/propuesta/209705/aceptapropuesta", request.call_args[0][1])

    def test_accept_rce_proposal_creates_ticket(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rce",
                "year": 2097,
                "month": "05",
                "decision_type": "accept",
            }
        )
        response = Mock()
        response.status_code = 200
        response.text = '{"numTicket":"20260300004501"}'
        response.content = response.text.encode()
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"numTicket": "20260300004501"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=response,
        ) as request:
            ticket = self.env["sire.api.client"].accept_proposal(period)

        self.assertEqual(ticket.process_type, "submit_acceptance")
        self.assertEqual(ticket.ticket_number, "20260300004501")
        self.assertEqual(ticket.sunat_process_code, "2")
        self.assertEqual(ticket.sunat_book_code, "080000")
        self.assertEqual(request.call_args[0][0], "POST")
        self.assertIn("/v1/contribuyente/migeigv/libros/rce/propuesta/web/registroslibros/209705/aceptarpropuesta", request.call_args[0][1])

    def test_sync_sunat_proposal_downloads_and_imports_when_ticket_finishes(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rce",
                "year": 2097,
                "month": "05",
            }
        )
        proposal = self.env["sire.sunat.proposal"].create({"period_id": period.id})
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "proposal_id": proposal.id,
                "process_type": "request_proposal",
                "ticket_number": "20260300004317",
            }
        )

        def check_ticket(ticket_record):
            ticket_record.write({"state": "done", "status_code": "06", "status_description": "Terminado"})

        def download_file(ticket_record):
            ticket_record.write(
                {
                    "result_filename": "PROP.zip",
                    "result_file": base64.b64encode(b"zip-bytes"),
                }
            )
            return True

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.SireApiClient.request_proposal",
            return_value=ticket,
        ), patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.SireApiClient.check_ticket_status",
            side_effect=check_ticket,
        ), patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.SireApiClient.download_ticket_file",
            side_effect=download_file,
        ), patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_period.SirePeriod._import_downloaded_sunat_proposal",
            return_value=proposal,
        ) as importer:
            action = period.with_context(sire_auto_sync_max_checks=1, sire_auto_sync_sleep_seconds=0).action_sync_sunat_proposal()

        importer.assert_called_once()
        self.assertEqual(action["res_model"], "sire.sunat.proposal")
        self.assertEqual(action["res_id"], proposal.id)

    def test_sync_sunat_proposal_opens_ticket_when_still_processing(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rce",
                "year": 2097,
                "month": "05",
            }
        )
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "process_type": "request_proposal",
                "ticket_number": "20260300004318",
                "state": "sent",
                "status_code": "01",
            }
        )

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.SireApiClient.request_proposal",
            return_value=ticket,
        ), patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.SireApiClient.check_ticket_status",
            return_value={},
        ):
            action = period.with_context(sire_auto_sync_max_checks=1, sire_auto_sync_sleep_seconds=0).action_sync_sunat_proposal()

        self.assertEqual(action["res_model"], "sire.api.ticket")
        self.assertEqual(action["res_id"], ticket.id)

    def test_request_proposal_refreshes_token_after_401(self):
        self.company.write(
            {
                "sire_access_token": "old-token",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "07",
            }
        )
        unauthorized = Mock()
        unauthorized.status_code = 401
        unauthorized.text = "<html>401 Authorization Required</html>"
        unauthorized.content = unauthorized.text.encode()
        unauthorized.headers = {"Content-Type": "text/html"}
        ok = Mock()
        ok.status_code = 200
        ok.text = '{"numTicket":"20230300000002"}'
        ok.content = ok.text.encode()
        ok.headers = {"Content-Type": "application/json"}
        ok.json.return_value = {"numTicket": "20230300000002"}
        token_response = Mock()
        token_response.status_code = 200
        token_response.text = '{"access_token":"new-token","expires_in":3600}'
        token_response.json.return_value = {"access_token": "new-token", "expires_in": 3600}

        with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.post", return_value=token_response):
            with patch(
                "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
                side_effect=[unauthorized, ok],
            ):
                ticket = self.env["sire.api.client"].request_proposal(period)

        self.assertEqual(self.company.sire_access_token, "new-token")
        self.assertEqual(ticket.ticket_number, "20230300000002")

    def test_get_rvie_periods_uses_migeigv_scope_endpoint(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        response = Mock()
        response.status_code = 200
        response.text = '{"lisPeriodos":[{"perTributario":"202605"}]}'
        response.content = response.text.encode()
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"lisPeriodos": [{"perTributario": "202605"}]}

        with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request", return_value=response) as request:
            data = self.env["sire.api.client"].get_rvie_periods(self.company)

        self.assertEqual(data["lisPeriodos"][0]["perTributario"], "202605")
        self.assertIn("/v1/contribuyente/migeigv/libros/rvierce/padron/web/omisos/140000/periodos", request.call_args[0][1])
        ticket = self.env["sire.api.ticket"].search([("process_type", "=", "check_periods")], limit=1)
        self.assertEqual(ticket.state, "done")

    def test_check_ticket_status_and_download_file(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "06",
            }
        )
        proposal = self.env["sire.sunat.proposal"].create({"period_id": period.id})
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "proposal_id": proposal.id,
                "process_type": "request_proposal",
                "ticket_number": "20230300000001",
            }
        )
        status_response = Mock()
        status_response.status_code = 200
        status_response.text = '{"registros":[{"numTicket":"20230300000001","codEstadoProceso":"06","desEstadoProceso":"Terminado","archivoReporte":[{"codTipoAchivoReporte":"01","nomArchivoReporte":"PROP.zip"}]}]}'
        status_response.headers = {"Content-Type": "application/json"}
        status_response.json.return_value = {
            "registros": [
                {
                    "numTicket": "20230300000001",
                    "codEstadoProceso": "06",
                    "desEstadoProceso": "Terminado",
                    "archivoReporte": [
                        {"codTipoAchivoReporte": "01", "nomArchivoReporte": "PROP.zip"}
                    ],
                }
            ]
        }
        file_response = Mock()
        file_response.status_code = 200
        file_response.content = b"zip-bytes"
        file_response.text = ""
        file_response.headers = {"Content-Type": "application/zip"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            side_effect=[status_response, file_response],
        ):
            self.env["sire.api.client"].check_ticket_status(ticket)
            self.env["sire.api.client"].download_ticket_file(ticket)

        self.assertEqual(ticket.result_filename, "PROP.zip")
        self.assertFalse(ticket.result_content_filename)
        self.assertEqual(ticket.result_file_type, "01")
        self.assertEqual(ticket.informed_document_count, 0)
        self.assertEqual(proposal.state, "downloaded")
        self.assertEqual(period.state, "proposal_downloaded")

    def test_download_file_retries_normalized_file_type_after_missing_file(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "08",
            }
        )
        proposal = self.env["sire.sunat.proposal"].create({"period_id": period.id})
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "proposal_id": proposal.id,
                "process_type": "request_proposal",
                "ticket_number": "20230300000003",
                "result_filename": "PROP.zip",
                "result_file_type": "00",
            }
        )
        missing = Mock()
        missing.status_code = 422
        missing.text = '{"cod":2244,"msg":"El archivo solicitado no existe."}'
        missing.content = missing.text.encode()
        missing.headers = {"Content-Type": "application/json"}
        ok = Mock()
        ok.status_code = 200
        ok.content = b"zip-bytes"
        ok.text = ""
        ok.headers = {"Content-Type": "application/zip"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            side_effect=[missing, ok],
        ) as request:
            self.env["sire.api.client"].download_ticket_file(ticket)

        self.assertEqual(request.call_count, 2)
        self.assertIn("codTipoArchivoReporte=0", request.call_args[0][1])
        self.assertEqual(ticket.result_file_type, "0")
        self.assertEqual(proposal.state, "downloaded")

    def test_download_file_tries_content_filename_after_missing_report(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "09",
            }
        )
        proposal = self.env["sire.sunat.proposal"].create({"period_id": period.id})
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "proposal_id": proposal.id,
                "process_type": "request_proposal",
                "ticket_number": "20230300000004",
                "result_filename": "REPORT.zip",
                "result_content_filename": "CONTENT.txt",
                "result_file_type": "00",
            }
        )
        missing = Mock()
        missing.status_code = 422
        missing.text = '{"cod":2244,"msg":"El archivo solicitado no existe."}'
        missing.content = missing.text.encode()
        missing.headers = {"Content-Type": "application/json"}
        ok = Mock()
        ok.status_code = 200
        ok.content = b"txt-bytes"
        ok.text = ""
        ok.headers = {"Content-Type": "application/octet-stream"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            side_effect=[missing, missing, missing, missing, missing, missing, ok],
        ):
            self.env["sire.api.client"].download_ticket_file(ticket)

        self.assertEqual(ticket.result_filename, "REPORT.zip")
        self.assertEqual(proposal.source_filename, "CONTENT.txt")
        self.assertEqual(proposal.state, "downloaded")

    def test_missing_file_with_zero_informed_documents_marks_empty_proposal(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "10",
            }
        )
        proposal = self.env["sire.sunat.proposal"].create({"period_id": period.id})
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "proposal_id": proposal.id,
                "process_type": "request_proposal",
                "ticket_number": "20230300000005",
                "result_filename": "REPORT.zip",
                "result_file_type": "00",
                "informed_document_count": 0,
            }
        )
        missing = Mock()
        missing.status_code = 422
        missing.text = '{"cod":2244,"msg":"El archivo solicitado no existe."}'
        missing.content = missing.text.encode()
        missing.headers = {"Content-Type": "application/json"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=missing,
        ):
            self.env["sire.api.client"].download_ticket_file(ticket)

        self.assertEqual(proposal.state, "empty")
        self.assertEqual(period.total_sunat_records, 0)
        self.assertEqual(ticket.error_code, "2244")

    def test_download_file_uses_book_code_from_sunat_filename(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "11",
            }
        )
        proposal = self.env["sire.sunat.proposal"].create({"period_id": period.id})
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "proposal_id": proposal.id,
                "process_type": "request_proposal",
                "ticket_number": "20230300000006",
                "result_filename": "LE2010008093220260700014040001EXP2.zip",
                "result_file_type": "00",
            }
        )
        ok = Mock()
        ok.status_code = 200
        ok.content = b"zip-bytes"
        ok.text = ""
        ok.headers = {"Content-Type": "application/zip"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=ok,
        ) as request:
            self.env["sire.api.client"].download_ticket_file(ticket)

        self.assertIn("codLibro=140400", request.call_args[0][1])
        self.assertEqual(proposal.state, "downloaded")

    def test_download_rce_file_uses_080000_and_ticket_params(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rce",
                "year": 2097,
                "month": "12",
            }
        )
        proposal = self.env["sire.sunat.proposal"].create({"period_id": period.id})
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "proposal_id": proposal.id,
                "process_type": "request_proposal",
                "ticket_number": "20260300004317",
                "result_filename": "20100080932-20260709-105151-propuesta.zip",
                "result_file_type": "00",
            }
        )
        ok = Mock()
        ok.status_code = 200
        ok.content = b"zip-bytes"
        ok.text = ""
        ok.headers = {"Content-Type": "application/zip"}

        with patch(
            "odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request",
            return_value=ok,
        ) as request:
            self.env["sire.api.client"].download_ticket_file(ticket)

        url = request.call_args[0][1]
        self.assertIn("nomArchivoReporte=20100080932-20260709-105151-propuesta.zip", url)
        self.assertIn("codTipoArchivoReporte=00", url)
        self.assertIn("perTributario=209712", url)
        self.assertIn("codProceso=10", url)
        self.assertIn("numTicket=20260300004317", url)
        self.assertIn("codLibro=080000", url)
        self.assertEqual(proposal.state, "downloaded")

    def test_submit_generated_file_uploads_with_tus_metadata(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "05",
            }
        )
        create_response = Mock()
        create_response.status_code = 201
        create_response.text = ""
        create_response.content = b""
        create_response.headers = {"Location": "/upload/123"}
        upload_response = Mock()
        upload_response.status_code = 204
        upload_response.text = '{"numTicket":"20260300004444"}'
        upload_response.content = upload_response.text.encode()
        upload_response.headers = {"Content-Type": "application/json"}
        upload_response.json.return_value = {"numTicket": "20260300004444"}

        with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.post", return_value=create_response) as post:
            with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.patch", return_value=upload_response) as patch_request:
                ticket = self.env["sire.api.client"].submit_generated_file(
                    period,
                    "replacement",
                    base64.b64encode(b"zip-bytes"),
                    "LE2010008093220970500140400021112",
                )

        self.assertEqual(ticket.ticket_number, "20260300004444")
        self.assertEqual(ticket.process_type, "submit_replacement")
        self.assertEqual(ticket.sunat_process_code, "3")
        self.assertEqual(ticket.sunat_book_code, "140000")
        self.assertEqual(ticket.submitted_filename, "LE2010008093220970500140400021112.zip")
        headers = post.call_args[1]["headers"]
        self.assertEqual(headers["Tus-Resumable"], "1.0.0")
        self.assertIn("codProceso Mw==", headers["Upload-Metadata"])
        self.assertIn("codLibro MTQwMDAw", headers["Upload-Metadata"])
        self.assertEqual(patch_request.call_args[1]["data"], b"zip-bytes")

    def test_submit_rce_generated_file_uses_purchase_book_code(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rce",
                "year": 2097,
                "month": "05",
            }
        )
        create_response = Mock()
        create_response.status_code = 201
        create_response.text = ""
        create_response.content = b""
        create_response.headers = {"Location": "https://api-sire.sunat.gob.pe/upload/456"}
        upload_response = Mock()
        upload_response.status_code = 200
        upload_response.text = '{"numTicket":"20260300004445"}'
        upload_response.content = upload_response.text.encode()
        upload_response.headers = {"Content-Type": "application/json"}
        upload_response.json.return_value = {"numTicket": "20260300004445"}

        with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.post", return_value=create_response) as post:
            with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.patch", return_value=upload_response):
                ticket = self.env["sire.api.client"].submit_generated_file(
                    period,
                    "rce_cp",
                    base64.b64encode(b"zip-bytes"),
                    "LE2010008093220970500080400021112.zip",
                )

        self.assertEqual(ticket.process_type, "submit_complement")
        self.assertEqual(ticket.sunat_process_code, "1")
        self.assertEqual(ticket.sunat_book_code, "080000")
        self.assertIn("codLibro MDgwMDAw", post.call_args[1]["headers"]["Upload-Metadata"])

    def test_download_submitted_result_uses_ticket_process_code(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "05",
            }
        )
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "process_type": "submit_replacement",
                "ticket_number": "20260300004444",
                "result_filename": "RESULT.zip",
                "result_file_type": "00",
                "sunat_process_code": "3",
                "sunat_book_code": "140000",
            }
        )
        ok = Mock()
        ok.status_code = 200
        ok.content = b"zip-bytes"
        ok.text = ""
        ok.headers = {"Content-Type": "application/zip"}

        with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request", return_value=ok) as request:
            self.env["sire.api.client"].download_ticket_file(ticket)

        url = request.call_args[0][1]
        self.assertIn("codProceso=3", url)
        self.assertIn("codLibro=140000", url)

    def test_download_receipt_file_stores_pdf(self):
        self.company.write(
            {
                "sire_access_token": "abc",
                "sire_token_expiration": False,
            }
        )
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2097,
                "month": "05",
            }
        )
        ticket = self.env["sire.api.ticket"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "process_type": "submit_replacement",
                "ticket_number": "20260300004444",
                "submitted_filename": "LE2010008093220970500140400021112.zip",
            }
        )
        response = Mock()
        response.status_code = 200
        response.text = '{"archivoPdf":"cGRmLWJ5dGVz"}'
        response.content = response.text.encode()
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"archivoPdf": "cGRmLWJ5dGVz"}

        with patch("odoo.addons.l10n_pe_sire_api.models.sire_api_client.requests.request", return_value=response) as request:
            self.env["sire.api.client"].download_receipt_file(ticket)

        self.assertEqual(ticket.receipt_filename, "LE2010008093220970500140400021112.pdf")
        self.assertEqual(ticket.receipt_file, b"cGRmLWJ5dGVz")
        self.assertIn("constancia/archivo", request.call_args[0][1])
