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
    signature_required = fields.Boolean(string="Requiere firma", default=True, tracking=True)
    signature_state = fields.Selection(
        selection=[
            ("unsigned", "Pendiente"),
            ("signed", "Firmado"),
        ],
        default="unsigned",
        required=True,
        tracking=True,
        string="Estado de firma",
    )
    signed_date = fields.Datetime(string="Fecha firma", readonly=True, tracking=True)
    signed_by_id = fields.Many2one("res.users", string="Firmado por", readonly=True)
    signed_partner_id = fields.Many2one("res.partner", string="Contacto firmante", readonly=True)
    signature_name = fields.Char(string="Nombre del firmante", readonly=True)
    signature_ip = fields.Char(string="IP de firma", readonly=True)
    signature_user_agent = fields.Char(string="Navegador de firma", readonly=True)
    signature_hash = fields.Char(string="Hash de firma", readonly=True, copy=False)
    signature_image = fields.Text(string="Trazo de firma", readonly=True, copy=False)
    signature_preview_html = fields.Html(
        string="Vista de firma",
        compute="_compute_signature_preview_html",
        sanitize=False,
    )
    signed_document_preview_html = fields.Html(
        string="Documento firmado",
        compute="_compute_signed_document_preview_html",
        sanitize=False,
    )
    signature_position_x = fields.Float(string="Posicion firma X (%)", default=68.0, readonly=True)
    signature_position_y = fields.Float(string="Posicion firma Y (%)", default=78.0, readonly=True)
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
        template_values.update(
            {
                "public_pdf_url": self.get_public_pdf_url(),
                "qr_image_url": self.get_qr_image_url(),
            }
        )
        return template_values

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
                        Firma pendiente.
                    </div>
                """
                continue

            signer_name = html.escape(document.signature_name or "")
            signed_date = html.escape(str(document.signed_date or ""))
            signature_hash = html.escape(document.signature_hash or "")
            if document.signature_image:
                signature_block = """
                    <img src="%s" style="display: block; max-width: 360px; max-height: 130px; object-fit: contain; margin-bottom: 8px;"/>
                """ % document.signature_image
            else:
                signature_block = """
                    <div style="font-family: 'Brush Script MT', 'Segoe Script', cursive; font-size: 36px; line-height: 1.2; color: #111827; margin-bottom: 8px;">
                        %s
                    </div>
                """ % signer_name

            document.signature_preview_html = """
                <div style="max-width: 560px; padding: 14px; border: 1px solid #198754; border-radius: 8px; background: #fff;">
                    %s
                    <div style="font-size: 13px; color: #212529;">
                        <strong>Firmante:</strong> %s<br/>
                        <strong>Fecha:</strong> %s<br/>
                        <strong>Hash:</strong>
                        <code style="word-break: break-all;">%s</code>
                    </div>
                </div>
            """ % (signature_block, signer_name, signed_date, signature_hash)

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
            rendered_html = document.rendered_html or ""
            if document.signature_state != "signed":
                document.signed_document_preview_html = rendered_html
                continue

            document.signed_document_preview_html = """
                <div style="position: relative;">
                    %s
                    %s
                </div>
            """ % (rendered_html, document._get_signature_frame_html())

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
            raise UserError(_("Debe ingresar su nombre completo para firmar."))

        for document in self:
            document._check_can_sign(user)
            signed_date = fields.Datetime.now()
            position_x = document._normalize_signature_position(signature_position_x, document.signature_position_x)
            position_y = document._normalize_signature_position(signature_position_y, document.signature_position_y)
            signature_image = document._normalize_signature_image(signature_image)
            signature_values = {
                "signature_state": "signed",
                "signed_date": signed_date,
                "signed_by_id": user.id,
                "signed_partner_id": user.partner_id.id,
                "signature_name": signer_name,
                "signature_ip": ip_address,
                "signature_user_agent": user_agent,
                "signature_image": signature_image,
                "signature_position_x": position_x,
                "signature_position_y": position_y,
                "signature_hash": document._build_signature_hash(
                    signer_name,
                    user,
                    signed_date,
                    ip_address,
                    user_agent,
                    position_x,
                    position_y,
                    signature_image,
                ),
            }
            document.sudo().write(signature_values)
            document.sudo().message_post(
                body=_("Documento firmado electronicamente por %s.") % signer_name
            )
            document.sudo()._sync_legajo_document()
        return True

    def _check_can_sign(self, user):
        self.ensure_one()
        if self.state != "published":
            raise UserError(_("Solo se pueden firmar boletas publicadas."))
        if not self.signature_required:
            raise UserError(_("Esta boleta no requiere firma."))
        if self.signature_state == "signed":
            raise UserError(_("Esta boleta ya fue firmada."))
        if user.has_group("hr.group_hr_user"):
            return True
        if self.employee_user_id == user or self.employee_partner_id == user.partner_id:
            return True
        raise UserError(_("No tiene permisos para firmar esta boleta."))

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
            "signature_position_x": signature_position_x,
            "signature_position_y": signature_position_y,
            "signature_image": signature_image or "",
        }
        serialized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _sync_legajo_document(self):
        self.ensure_one()
        document_type = self.env.ref(
            "employee_payslip_documents.document_type_payslip",
            raise_if_not_found=False,
        )
        if not document_type:
            return False

        pdf_content, _content_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "employee_payslip_documents.action_report_payslip_document",
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
            }
        )
        return legajo
