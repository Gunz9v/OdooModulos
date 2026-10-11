import hmac
import base64
from datetime import date, timedelta

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class PayslipDocumentPortal(CustomerPortal):
    def _get_current_employee(self):
        return request.env["hr.employee"].sudo().search(
            [
                "|",
                ("user_id", "=", request.env.user.id),
                ("user_id.partner_id", "=", request.env.user.partner_id.id),
            ],
            limit=1,
        )

    def _get_upcoming_birthdays(self, days=45, limit=8):
        today = date.today()
        deadline = today + timedelta(days=days)
        employees = request.env["hr.employee"].sudo().search(
            [("active", "=", True), ("birthday", "!=", False)],
            order="name asc",
        )
        birthdays = []
        for employee in employees:
            next_birthday = self._next_birthday(employee.birthday, today)
            if today <= next_birthday <= deadline:
                birthdays.append(
                    {
                        "employee": employee,
                        "date": next_birthday,
                        "days_until": (next_birthday - today).days,
                    }
                )
        birthdays.sort(key=lambda item: (item["date"], item["employee"].name or ""))
        return birthdays[:limit]

    @staticmethod
    def _next_birthday(birthday, today):
        try:
            next_birthday = birthday.replace(year=today.year)
        except ValueError:
            next_birthday = date(today.year, 3, 1)
        if next_birthday < today:
            try:
                next_birthday = birthday.replace(year=today.year + 1)
            except ValueError:
                next_birthday = date(today.year + 1, 3, 1)
        return next_birthday

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "payslip_document_count" in counters:
            values["payslip_document_count"] = request.env["employee.payslip.document"].search_count(
                [("state", "=", "published")]
            )
        if "announcement_count" in counters:
            values["announcement_count"] = request.env["employee.announcement.recipient"].search_count(
                [("state", "=", "published")]
            )
        if "employee_portal_event_count" in counters:
            values["employee_portal_event_count"] = request.env["employee.portal.event"].search_count(
                [("state", "=", "published"), ("event_date", ">=", date.today())]
            )
        if "employee_contract_count" in counters:
            values["employee_contract_count"] = request.env["hr.contract"].sudo().search_count(
                [
                    ("contract_signature_required", "=", True),
                    "|",
                    ("employee_id.user_id", "=", request.env.user.id),
                    ("employee_id.user_id.partner_id", "=", request.env.user.partner_id.id),
                ]
            )
        return values

    def _prepare_employee_dashboard_values(self):
        values = self._prepare_portal_layout_values()
        today = date.today()
        current_employee = self._get_current_employee()
        recipients = request.env["employee.announcement.recipient"].search(
            [("state", "=", "published")],
            order="sent_date desc, id desc",
            limit=6,
        )
        unread_recipients = recipients.filtered(lambda recipient: not recipient.is_read)
        documents = request.env["employee.payslip.document"].search(
            [("state", "=", "published")],
            order="period desc, id desc",
            limit=5,
        )
        pending_documents = documents.filtered(
            lambda document: document.signature_required and document.signature_state != "signed"
        )
        contracts = request.env["hr.contract"].sudo().search(
            [
                ("contract_signature_required", "=", True),
                "|",
                ("employee_id.user_id", "=", request.env.user.id),
                ("employee_id.user_id.partner_id", "=", request.env.user.partner_id.id),
            ],
            order="date_start desc, id desc",
            limit=5,
        )
        pending_contracts = contracts.filtered(lambda contract: contract.contract_signature_state != "signed")
        events = request.env["employee.portal.event"].search(
            [("state", "=", "published"), ("event_date", ">=", today)],
            order="event_date asc, id asc",
            limit=8,
        )
        values.update(
            {
                "page_name": "employee_dashboard",
                "employee": current_employee,
                "recipients": recipients,
                "unread_recipients": unread_recipients,
                "unread_count": len(unread_recipients),
                "documents": documents,
                "pending_documents": pending_documents,
                "pending_document_count": len(pending_documents),
                "contracts": contracts,
                "pending_contracts": pending_contracts,
                "pending_contract_count": len(pending_contracts),
                "birthdays": self._get_upcoming_birthdays(),
                "events": events,
            }
        )
        return values

    @http.route(["/my", "/my/home"], type="http", auth="user", website=True)
    def home(self, **kw):
        return request.render("smart_labor_documents.portal_employee_dashboard", self._prepare_employee_dashboard_values())

    @http.route(["/my/inicio"], type="http", auth="user", website=True)
    def portal_employee_dashboard(self, **kw):
        values = self._prepare_employee_dashboard_values()
        return request.render("smart_labor_documents.portal_employee_dashboard", values)

    @http.route(["/my/payslip-documents"], type="http", auth="user", website=True)
    def portal_my_payslip_documents(self, **kw):
        values = self._prepare_portal_layout_values()
        documents = request.env["employee.payslip.document"].search(
            [("state", "=", "published")],
            order="period desc, id desc",
        )
        values.update(
            {
                "documents": documents,
                "page_name": "payslip_documents",
            }
        )
        return request.render("smart_labor_documents.portal_my_payslip_documents", values)

    @http.route(["/my/employee-contracts"], type="http", auth="user", website=True)
    def portal_my_employee_contracts(self, **kw):
        values = self._prepare_portal_layout_values()
        contracts = request.env["hr.contract"].sudo().search(
            [
                ("contract_signature_required", "=", True),
                "|",
                ("employee_id.user_id", "=", request.env.user.id),
                ("employee_id.user_id.partner_id", "=", request.env.user.partner_id.id),
            ],
            order="date_start desc, id desc",
        )
        values.update(
            {
                "contracts": contracts,
                "page_name": "employee_contracts",
            }
        )
        return request.render("smart_labor_documents.portal_my_employee_contracts", values)

    @http.route(["/my/employee-contracts/<int:contract_id>"], type="http", auth="user", website=True)
    def portal_my_employee_contract_detail(self, contract_id, **kw):
        contract = request.env["hr.contract"].sudo().browse(contract_id)
        if not contract.exists() or not contract._can_user_access_contract_portal(request.env.user):
            return request.not_found()
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "contract": contract,
                "contract_signature_error": request.session.pop("contract_signature_error", False),
                "contract_signature_success": request.session.pop("contract_signature_success", False),
                "page_name": "employee_contracts",
            }
        )
        return request.render("smart_labor_documents.portal_my_employee_contract_detail", values)

    @http.route(["/my/employee-contracts/<int:contract_id>/sign"], type="http", auth="user", website=True, methods=["POST"])
    def portal_my_employee_contract_sign(self, contract_id, signer_name=None, **kw):
        contract = request.env["hr.contract"].sudo().browse(contract_id)
        if not contract.exists() or not contract._can_user_access_contract_portal(request.env.user):
            return request.not_found()

        forwarded_for = request.httprequest.headers.get("X-Forwarded-For", "")
        ip_address = (forwarded_for.split(",")[0].strip() if forwarded_for else request.httprequest.remote_addr) or ""
        user_agent = request.httprequest.headers.get("User-Agent", "")
        try:
            contract.action_sign_contract(
                signer_name,
                user=request.env.user,
                ip_address=ip_address,
                user_agent=user_agent,
                signature_position_x=kw.get("signature_position_x"),
                signature_position_y=kw.get("signature_position_y"),
                signature_image=kw.get("signature_image"),
            )
            request.session["contract_signature_success"] = "Contrato firmado correctamente."
        except UserError as error:
            request.session["contract_signature_error"] = str(error)
        return request.redirect("/my/employee-contracts/%s" % contract.id)

    @http.route(["/my/employee-contracts/<int:contract_id>/pdf"], type="http", auth="user", website=True)
    def portal_my_employee_contract_pdf(self, contract_id, **kw):
        contract = request.env["hr.contract"].sudo().browse(contract_id)
        if not contract.exists() or not contract._can_user_access_contract_portal(request.env.user):
            return request.not_found()
        pdf_content, _content_type = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "smart_labor_documents.action_report_employee_contract",
            [contract.id],
        )
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf_content)),
            ("Content-Disposition", 'attachment; filename="%s.pdf"' % contract.name.replace('"', "")),
        ]
        return request.make_response(pdf_content, headers=headers)

    @http.route(["/my/payslip-documents/<int:document_id>"], type="http", auth="user", website=True)
    def portal_my_payslip_document_detail(self, document_id, **kw):
        document = request.env["employee.payslip.document"].search(
            [("id", "=", document_id), ("state", "=", "published")],
            limit=1,
        )
        if not document:
            return request.not_found()
        document.action_mark_read()
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "document": document,
                "signature_error": request.session.pop("payslip_signature_error", False),
                "signature_success": request.session.pop("payslip_signature_success", False),
                "page_name": "payslip_documents",
            }
        )
        return request.render("smart_labor_documents.portal_my_payslip_document_detail", values)

    @http.route(["/my/payslip-documents/<int:document_id>/sign"], type="http", auth="user", website=True, methods=["POST"])
    def portal_my_payslip_document_sign(self, document_id, signer_name=None, **kw):
        document = request.env["employee.payslip.document"].search(
            [("id", "=", document_id), ("state", "=", "published")],
            limit=1,
        )
        if not document:
            return request.not_found()

        forwarded_for = request.httprequest.headers.get("X-Forwarded-For", "")
        ip_address = (forwarded_for.split(",")[0].strip() if forwarded_for else request.httprequest.remote_addr) or ""
        user_agent = request.httprequest.headers.get("User-Agent", "")
        try:
            document.sudo().action_sign_document(
                signer_name,
                user=request.env.user,
                ip_address=ip_address,
                user_agent=user_agent,
                signature_position_x=kw.get("signature_position_x"),
                signature_position_y=kw.get("signature_position_y"),
                signature_image=kw.get("signature_image"),
            )
            request.session["payslip_signature_success"] = "Recepcion de boleta confirmada correctamente."
        except UserError as error:
            request.session["payslip_signature_error"] = str(error)
        return request.redirect("/my/payslip-documents/%s" % document.id)

    @http.route(["/my/payslip-documents/<int:document_id>/pdf"], type="http", auth="user", website=True)
    def portal_my_payslip_document_pdf(self, document_id, **kw):
        document = request.env["employee.payslip.document"].search(
            [("id", "=", document_id), ("state", "=", "published")],
            limit=1,
        )
        if not document:
            return request.not_found()
        document.action_mark_read()

        pdf_content, file_name = document.sudo()._get_portal_pdf_content()
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf_content)),
            ("Content-Disposition", 'attachment; filename="%s"' % file_name.replace('"', "")),
        ]
        return request.make_response(pdf_content, headers=headers)

    @http.route(["/my/announcements"], type="http", auth="user", website=True)
    def portal_my_announcements(self, **kw):
        values = self._prepare_portal_layout_values()
        recipients = request.env["employee.announcement.recipient"].search(
            [("state", "=", "published")],
            order="sent_date desc, id desc",
        )
        values.update(
            {
                "recipients": recipients,
                "page_name": "announcements",
            }
        )
        return request.render("smart_labor_documents.portal_my_announcements", values)

    @http.route(["/my/announcements/<int:announcement_id>"], type="http", auth="user", website=True)
    def portal_my_announcement_detail(self, announcement_id, **kw):
        recipient = request.env["employee.announcement.recipient"].search(
            [("announcement_id", "=", announcement_id), ("state", "=", "published")],
            limit=1,
        )
        if not recipient:
            return request.not_found()
        recipient.action_mark_read()
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "recipient": recipient,
                "announcement": recipient.announcement_id,
                "page_name": "announcements",
            }
        )
        return request.render("smart_labor_documents.portal_my_announcement_detail", values)

    @http.route(["/my/announcements/<int:announcement_id>/pdf"], type="http", auth="user", website=True)
    def portal_my_announcement_pdf(self, announcement_id, **kw):
        recipient = request.env["employee.announcement.recipient"].search(
            [("announcement_id", "=", announcement_id), ("state", "=", "published")],
            limit=1,
        )
        if not recipient:
            return request.not_found()
        recipient.action_mark_read()
        announcement = recipient.announcement_id
        pdf_content = base64.b64decode(announcement.file_data or b"")
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf_content)),
            ("Content-Disposition", 'inline; filename="%s"' % (announcement.file_name or (announcement.name + ".pdf")).replace('"', "")),
        ]
        return request.make_response(pdf_content, headers=headers)

    @http.route(
        ["/payslip/document/<int:document_id>/<string:access_token>/pdf"],
        type="http",
        auth="public",
        website=False,
    )
    def public_payslip_document_pdf(self, document_id, access_token, **kw):
        document = request.env["employee.payslip.document"].sudo().browse(document_id)
        if (
            not document.exists()
            or not document.access_token
            or not hmac.compare_digest(document.access_token, access_token)
            or document.state != "published"
        ):
            return request.not_found()

        pdf_content, file_name = document.sudo()._get_portal_pdf_content()
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf_content)),
            ("Content-Disposition", 'inline; filename="%s"' % file_name.replace('"', "")),
        ]
        return request.make_response(pdf_content, headers=headers)
