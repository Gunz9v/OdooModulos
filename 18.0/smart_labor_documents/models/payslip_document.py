import base64
import hashlib
import html
import json
import secrets
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PayslipDocument(models.Model):
    _name = "employee.payslip.document"
    _description = "Boleta de Empleado"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period desc, employee_id"

    name = fields.Char(string="Nombre", required=True, tracking=True)
    template_id = fields.Many2one(
        "employee.payslip.document.template",
        string="Plantilla",
        required=True,
        ondelete="restrict",
    )
    batch_id = fields.Many2one(
        "employee.payslip.document.batch",
        string="Envio Masivo",
        ondelete="set null",
    )
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, ondelete="restrict", index=True)
    employee_user_id = fields.Many2one(string="Usuario del empleado", related="employee_id.user_id", store=True, index=True)
    employee_partner_id = fields.Many2one(string="Contacto del empleado", related="employee_id.user_id.partner_id", store=True, index=True)
    period = fields.Char(string="Periodo", required=True, tracking=True)
    access_token = fields.Char(copy=False, readonly=True, index=True)
    values_json = fields.Json(string="Valores importados", default=dict)
    rendered_html = fields.Html(string="Documento renderizado", sanitize=False)
    is_read = fields.Boolean(string="Leido", default=False, tracking=True)
    read_date = fields.Datetime(string="Fecha Lectura", readonly=True)
    signature_required = fields.Boolean(string="Requiere acuse de recepcion", default=True, tracking=True)
    digital_signer_user_id = fields.Many2one(
        "res.users",
        string="Usuario encargado de firma digital",
        tracking=True,
        help="Usuario cuyo certificado digital se usara para firmar el PDF cuando se envie al legajo.",
    )
    signature_state = fields.Selection(
        selection=[
            ("unsigned", "Pendiente"),
            ("signed", "Confirmado"),
        ],
        default="unsigned",
        required=True,
        tracking=True,
        string="Estado de acuse",
    )
    signed_date = fields.Datetime(string="Fecha acuse", readonly=True, tracking=True)
    signed_by_id = fields.Many2one("res.users", string="Confirmado por", readonly=True)
    signed_partner_id = fields.Many2one("res.partner", string="Contacto que confirma", readonly=True)
    signature_name = fields.Char(string="Nombre del trabajador", readonly=True)
    signature_ip = fields.Char(string="IP de acuse", readonly=True)
    signature_user_agent = fields.Char(string="Navegador de acuse", readonly=True)
    signature_hash = fields.Char(string="Hash de evidencia", readonly=True, copy=False)
    signature_image = fields.Text(string="Trazo de firma obsoleto", readonly=True, copy=False)
    signature_preview_html = fields.Html(
        string="Acuse de recepcion",
        compute="_compute_signature_preview_html",
        sanitize=False,
    )
    signed_document_preview_html = fields.Html(
        string="Documento",
        compute="_compute_signed_document_preview_html",
        sanitize=False,
    )
    signature_position_x = fields.Float(string="Posicion firma X obsoleta (%)", default=68.0, readonly=True)
    signature_position_y = fields.Float(string="Posicion firma Y obsoleta (%)", default=78.0, readonly=True)
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("published", "Publicado"),
        ],
        default="published",
        required=True,
        tracking=True,
        string="Estado",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("access_token", secrets.token_urlsafe(32))
            if vals.get("template_id") and not vals.get("digital_signer_user_id"):
                template = self.env["employee.payslip.document.template"].browse(vals["template_id"])
                vals["digital_signer_user_id"] = template.digital_signer_user_id.id
        return super().create(vals_list)

    def _get_base_url(self):
        return self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")

    def get_public_pdf_url(self):
        self.ensure_one()
        if not self.access_token:
            self.sudo().access_token = secrets.token_urlsafe(32)
        return "%s/payslip/document/%s/%s/pdf" % (
            self._get_base_url(),
            self.id,
            self.access_token,
        )

    def get_qr_image_url(self):
        self.ensure_one()
        return "/report/barcode/?barcode_type=QR&value=%s&width=180&height=180" % quote(
            self.get_public_pdf_url(),
            safe="",
        )

    def _get_template_values(self, values=None):
        self.ensure_one()
        template_values = dict(values or self.values_json or {})
        digital_signed_date = self.env.context.get("digital_signature_signed_date")
        template_values.update(
            {
                "public_pdf_url": self.get_public_pdf_url(),
                "qr_image_url": self.get_qr_image_url(),
            }
        )
        template_values.update(self._get_digital_signer_template_values(digital_signed_date))
        return template_values

    def _get_digital_signer_template_values(self, signed_date=None):
        self.ensure_one()
        signer = self.digital_signer_user_id.sudo()
        signer_name = signer.digital_signature_name or signer.name or ""
        signer_employee = self.env["hr.employee"].sudo().search([("user_id", "=", signer.id)], limit=1)
        signer_position = (
            signer.digital_signature_position
            or signer.digital_signature_job_id.name
            or signer_employee.job_id.name
            or ""
        )
        signature_image = signer.digital_signature_image or ""
        if isinstance(signature_image, bytes):
            signature_image = signature_image.decode("ascii")
        signed_date_text = ""
        if signed_date:
            signed_date_text = fields.Datetime.context_timestamp(self, signed_date).strftime("%d/%m/%Y %H:%M:%S")
        reason = signer.digital_signature_reason or "BOLETA DE PAGO"
        return {
            "manager_name": signer_name,
            "manager_position": signer_position,
            "digital_signer_name": signer_name,
            "digital_signer_position": signer_position,
            "digital_signer_signature_image": (
                "data:image/png;base64,%s" % signature_image
                if signature_image
                else "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
            ),
            "digital_signature_signed_by": signer_name,
            "digital_signature_date": signed_date_text,
            "digital_signature_reason": reason,
        }

    def action_render_template(self):
        for document in self:
            values = document._get_template_values()
            document.rendered_html = document.template_id.render_template(values)

    def action_publish(self):
        self.write({"state": "published"})

    def action_set_draft(self):
        self.write({"state": "draft"})

    def action_sync_legajo_document(self):
        for document in self:
            document._sync_legajo_document()

    def action_mark_read(self):
        self.filtered(lambda document: not document.is_read).sudo().write(
            {
                "is_read": True,
                "read_date": fields.Datetime.now(),
            }
        )

    @api.depends("signature_state", "signature_name", "signature_image", "signed_date", "signature_hash")
    def _compute_signature_preview_html(self):
        for document in self:
            if document.signature_state != "signed":
                document.signature_preview_html = """
                    <div style="padding: 12px; border: 1px dashed #adb5bd; border-radius: 6px; color: #6c757d;">
                        Acuse de recepcion pendiente.
                    </div>
                """
                continue

            signer_name = html.escape(document.signature_name or "")
            signed_date = html.escape(str(document.signed_date or ""))
            signature_hash = html.escape(document.signature_hash or "")
            document.signature_preview_html = """
                <div style="max-width: 560px; padding: 14px; border: 1px solid #198754; border-radius: 8px; background: #fff;">
                    <div style="font-size: 13px; color: #212529;">
                        <strong>Trabajador:</strong> %s<br/>
                        <strong>Fecha de acuse:</strong> %s<br/>
                        <strong>Hash de evidencia:</strong>
                        <code style="word-break: break-all;">%s</code>
                    </div>
                </div>
            """ % (signer_name, signed_date, signature_hash)

    @api.depends(
        "rendered_html",
        "signature_state",
        "signature_name",
        "signature_image",
        "signature_position_x",
        "signature_position_y",
        "signed_date",
    )
    def _compute_signed_document_preview_html(self):
        for document in self:
            document.signed_document_preview_html = document.rendered_html or ""

    def _get_signature_frame_html(self):
        self.ensure_one()
        signer_name = html.escape(self.signature_name or "")
        signed_date = html.escape(str(self.signed_date or ""))
        if self.signature_image:
            signature_block = """
                <img src="%s" style="display: block; max-width: 190px; max-height: 42px; object-fit: contain;"/>
            """ % self.signature_image
        else:
            signature_block = """
                <span style="display: block; font-family: 'Brush Script MT', 'Segoe Script', cursive; font-size: 24px; line-height: 1.1; color: #111827;">
                    %s
                </span>
            """ % signer_name

        return """
            <div style="position: absolute; left: %s%%; top: %s%%; width: 220px; min-height: 72px; padding: 8px 10px; border: 2px solid #198754; border-radius: 6px; background: rgba(255, 255, 255, 0.94); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16); font-size: 11px; z-index: 5;">
                %s
                <span style="display: block; margin-top: 4px; color: #495057;">
                    Firma electronica - %s
                </span>
            </div>
        """ % (
            self.signature_position_x or 0.0,
            self.signature_position_y or 0.0,
            signature_block,
            signed_date,
        )

    def action_reset_signature(self):
        self.write(
            {
                "signature_state": "unsigned",
                "signed_date": False,
                "signed_by_id": False,
                "signed_partner_id": False,
                "signature_name": False,
                "signature_ip": False,
                "signature_user_agent": False,
                "signature_hash": False,
                "signature_image": False,
                "signature_position_x": 68.0,
                "signature_position_y": 78.0,
            }
        )

    def action_sign_document(
        self,
        signer_name,
        user=None,
        ip_address=None,
        user_agent=None,
        signature_position_x=None,
        signature_position_y=None,
        signature_image=None,
    ):
        user = user or self.env.user
        signer_name = (signer_name or "").strip()
        if not signer_name:
            raise UserError(_("Debe ingresar su nombre completo para confirmar la recepcion."))

        for document in self:
            document._check_can_sign(user)
            signed_date = fields.Datetime.now()
            signature_values = {
                "signature_state": "signed",
                "signed_date": signed_date,
                "signed_by_id": user.id,
                "signed_partner_id": user.partner_id.id,
                "signature_name": signer_name,
                "signature_ip": ip_address,
                "signature_user_agent": user_agent,
                "signature_hash": document._build_signature_hash(
                    signer_name,
                    user,
                    signed_date,
                    ip_address,
                    user_agent,
                ),
            }
            document.sudo().write(signature_values)
            document.sudo().message_post(
                body=_("Recepcion y conformidad registradas por %s.") % signer_name
            )
            document.sudo()._sync_legajo_receipt_metadata()
        return True

    def _check_can_sign(self, user):
        self.ensure_one()
        if self.state != "published":
            raise UserError(_("Solo se puede confirmar la recepcion de boletas publicadas."))
        if not self.signature_required:
            raise UserError(_("Esta boleta no requiere acuse de recepcion."))
        if self.signature_state == "signed":
            raise UserError(_("La recepcion de esta boleta ya fue confirmada."))
        if user.has_group("hr.group_hr_user"):
            return True
        if self.employee_user_id == user or self.employee_partner_id == user.partner_id:
            return True
        raise UserError(_("No tiene permisos para confirmar la recepcion de esta boleta."))

    @staticmethod
    def _normalize_signature_position(value, fallback):
        try:
            position = float(value)
        except (TypeError, ValueError):
            position = fallback
        return min(max(position, 0.0), 100.0)

    @staticmethod
    def _normalize_signature_image(value):
        value = (value or "").strip()
        if not value or value == "empty":
            return False
        if not value.startswith("data:image/png;base64,"):
            return False
        return value

    def _build_signature_hash(
        self,
        signer_name,
        user,
        signed_date,
        ip_address=None,
        user_agent=None,
        signature_position_x=None,
        signature_position_y=None,
        signature_image=None,
    ):
        self.ensure_one()
        payload = {
            "document_id": self.id,
            "document_name": self.name,
            "employee_id": self.employee_id.id,
            "period": self.period,
            "rendered_html": self.rendered_html or "",
            "values_json": self.values_json or {},
            "signer_name": signer_name,
            "signed_date": signed_date,
            "user_id": user.id,
            "partner_id": user.partner_id.id,
            "ip_address": ip_address or "",
            "user_agent": user_agent or "",
            "acknowledgement": "worker_receipt",
        }
        serialized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _sync_legajo_receipt_metadata(self):
        document_type = self.env.ref(
            "employee_legajo_documents.document_type_payslip",
            raise_if_not_found=False,
        )
        if not document_type:
            return False

        for document in self:
            metadata_values = {
                "worker_signature_required": document.signature_required,
                "worker_signature_state": "signed" if document.signature_state == "signed" else (
                    "unsigned" if document.signature_required else "not_required"
                ),
                "worker_signed_date": document.signed_date,
                "worker_signed_by_id": document.signed_by_id.id,
                "worker_signed_partner_id": document.signed_partner_id.id,
                "worker_signature_name": document.signature_name,
                "worker_signature_hash": document.signature_hash,
            }
            legajo = self.env["employee.document.file"].sudo().search(
                [
                    ("employee_id", "=", document.employee_id.id),
                    ("document_type_id", "=", document_type.id),
                ],
                limit=1,
            )
            if not legajo:
                document._sync_legajo_document()
                continue
            legajo.with_context(skip_document_history=True).sudo().write(metadata_values)
            history = self.env["employee.document.history"].sudo().search(
                [
                    ("source_model", "=", document._name),
                    ("source_res_id", "=", document.id),
                ],
                limit=1,
            )
            if history:
                history.sudo().write(metadata_values)
        return True

    def _get_certified_legajo_history(self):
        self.ensure_one()
        return self.env["employee.document.history"].sudo().search(
            [
                ("source_model", "=", self._name),
                ("source_res_id", "=", self.id),
                ("file_data", "!=", False),
                ("signature_state", "=", "signed"),
            ],
            limit=1,
        )

    def _get_portal_pdf_content(self):
        self.ensure_one()
        history = self._get_certified_legajo_history()
        if history:
            return base64.b64decode(history.file_data or b""), history.file_name or ("%s.pdf" % self.name)
        digital_signed_date = fields.Datetime.now() if self.digital_signer_user_id else False
        if self.digital_signer_user_id:
            self.with_context(digital_signature_signed_date=digital_signed_date).action_render_template()

        pdf_content, _content_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "smart_labor_documents.action_report_payslip_document",
            [self.id],
        )
        return pdf_content, "%s.pdf" % self.name

    def _sync_legajo_document(self):
        self.ensure_one()
        document_type = self.env.ref(
            "employee_legajo_documents.document_type_payslip",
            raise_if_not_found=False,
        )
        if not document_type:
            return False

        digital_signed_date = fields.Datetime.now() if self.digital_signer_user_id else False
        if self.digital_signer_user_id:
            self.with_context(digital_signature_signed_date=digital_signed_date).action_render_template()

        pdf_content, _content_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "smart_labor_documents.action_report_payslip_document",
            [self.id],
        )
        file_name = "%s.pdf" % self.name
        legajo_values = {
            "name": self.name,
            "employee_id": self.employee_id.id,
            "document_type_id": document_type.id,
            "document_date": fields.Date.context_today(self),
                "state": "validated" if self.state == "published" else "uploaded",
                "notes": "Generado automaticamente desde Boletas de Pago.",
                "worker_signature_required": self.signature_required,
                "worker_signature_state": "signed" if self.signature_state == "signed" else ("unsigned" if self.signature_required else "not_required"),
                "worker_signed_date": self.signed_date,
                "worker_signed_by_id": self.signed_by_id.id,
                "worker_signed_partner_id": self.signed_partner_id.id,
                "worker_signature_name": self.signature_name,
                "worker_signature_hash": self.signature_hash,
                "signature_required": bool(self.digital_signer_user_id),
                "signature_state": "unsigned" if self.digital_signer_user_id else "not_required",
            }
        legajo = self.env["employee.document.file"].sudo().search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("document_type_id", "=", document_type.id),
            ],
            limit=1,
        )
        if legajo:
            legajo.write(legajo_values)
        else:
            legajo = self.env["employee.document.file"].sudo().create(legajo_values)
        legajo._create_history_from_payload(
            {
                "name": self.name,
                "period": self.period,
                "document_date": fields.Date.context_today(self),
                "file_data": base64.b64encode(pdf_content),
                "file_name": file_name,
                "state": "validated" if self.state == "published" else "uploaded",
                "notes": "Generado automaticamente desde Boletas de Pago.",
                "source_model": self._name,
                "source_res_id": self.id,
                "worker_signature_required": self.signature_required,
                "worker_signature_state": "signed" if self.signature_state == "signed" else ("unsigned" if self.signature_required else "not_required"),
                "worker_signed_date": self.signed_date,
                "worker_signed_by_id": self.signed_by_id.id,
                "worker_signed_partner_id": self.signed_partner_id.id,
                "worker_signature_name": self.signature_name,
                "worker_signature_hash": self.signature_hash,
                "signature_required": bool(self.digital_signer_user_id),
                "signature_state": "unsigned" if self.digital_signer_user_id else "not_required",
            }
        )
        self._sign_legajo_with_digital_signer(legajo, signed_date=digital_signed_date)
        return legajo

    def _sign_legajo_with_digital_signer(self, legajo, signed_date=None):
        self.ensure_one()
        signer = self.digital_signer_user_id
        if not signer:
            return False
        try:
            legajo.with_context(
                allow_designated_digital_signer=True,
                forced_digital_signed_date=signed_date,
                digital_signature_reason=signer.digital_signature_reason or "BOLETA DE PAGO",
            ).sudo().action_sign_pdf_with_user_certificate(
                signer.digital_signature_name or signer.name,
                user=signer,
            )
        except UserError as error:
            legajo.sudo().message_post(
                body=_("No se pudo aplicar la firma digital del usuario encargado %s: %s") % (signer.name, error)
            )
            return False
        return True
