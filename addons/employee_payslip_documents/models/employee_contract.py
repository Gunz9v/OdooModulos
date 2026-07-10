import base64
import hashlib
import html
import json
import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EmployeeContractTemplate(models.Model):
    _name = "employee.contract.template"
    _description = "Plantilla de Contrato de Empleado"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "contract_kind, name"

    name = fields.Char(string="Nombre", required=True, tracking=True)
    active = fields.Boolean(string="Activo", default=True)
    contract_kind = fields.Selection(
        selection=[
            ("payroll", "Planilla"),
            ("service", "Locacion de servicios"),
            ("internship", "Practicas"),
            ("fixed_term", "Plazo fijo"),
            ("other", "Otro"),
        ],
        default="payroll",
        required=True,
        tracking=True,
        string="Tipo de contrato",
    )
    body_html = fields.Html(
        string="Documento firmable",
        sanitize=False,
        required=True,
        default="""
<div style="padding: 28px; border: 1px solid #111; background: #fff; min-height: 760px; font-family: Arial, sans-serif; color: #111;">
    <h2 style="text-align: center; margin-bottom: 28px;">CONTRATO DE TRABAJO</h2>
    <p><strong>Referencia:</strong> {{contract_name}}</p>
    <p><strong>Empleado:</strong> {{employee_name}}</p>
    <p><strong>Documento:</strong> {{employee_identification}}</p>
    <p><strong>Cargo:</strong> {{job_name}}</p>
    <p><strong>Departamento:</strong> {{department_name}}</p>
    <p><strong>Fecha de inicio:</strong> {{date_start}}</p>
    <p><strong>Fecha de fin:</strong> {{date_end}}</p>
    <p><strong>Remuneracion mensual:</strong> {{wage}}</p>
    <p style="margin-top: 24px;">
        Las partes declaran su conformidad con las condiciones laborales indicadas en este documento.
    </p>
    <div style="height: 220px;"></div>
    <p style="border-top: 1px solid #111; width: 260px; text-align: center; padding-top: 8px;">
        Firma del trabajador
    </p>
</div>
""",
    )
    source_file_data = fields.Binary(
        string="Archivo base referencial",
        attachment=True,
        help="Archivo original de referencia. Para poder firmar con datos dinamicos, copie su contenido al documento HTML firmable.",
    )
    source_file_name = fields.Char(string="Nombre del archivo")
    placeholder_preview = fields.Text(string="Marcadores detectados", compute="_compute_placeholder_preview")

    @api.depends("body_html")
    def _compute_placeholder_preview(self):
        pattern = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
        for template in self:
            placeholders = sorted(set(pattern.findall(template.body_html or "")))
            template.placeholder_preview = "\n".join(placeholders)

    def render_template(self, values):
        self.ensure_one()
        body = self.body_html or ""

        def replace(match):
            key = match.group(1).strip()
            value = values.get(key, "")
            if value is None:
                return ""
            return str(value)

        return Markup(re.sub(r"{{\s*([a-zA-Z0-9_]+)\s*}}", replace, body))


class HrContract(models.Model):
    _inherit = "hr.contract"

    contract_template_id = fields.Many2one(
        "employee.contract.template",
        string="Plantilla de contrato",
        domain=[("active", "=", True)],
        ondelete="set null",
    )
    contract_kind = fields.Selection(
        related="contract_template_id.contract_kind",
        string="Tipo de contrato para firma",
        readonly=True,
        store=True,
    )
    contract_document_html = fields.Html(string="Documento del contrato", sanitize=False)
    contract_signature_required = fields.Boolean(string="Requiere firma", default=True, tracking=True)
    contract_signature_state = fields.Selection(
        selection=[
            ("unsigned", "Pendiente"),
            ("signed", "Firmado"),
        ],
        default="unsigned",
        required=True,
        tracking=True,
        string="Estado de firma",
    )
    contract_signed_date = fields.Datetime(string="Fecha firma", readonly=True, tracking=True)
    contract_signed_by_id = fields.Many2one("res.users", string="Firmado por", readonly=True)
    contract_signed_partner_id = fields.Many2one("res.partner", string="Contacto firmante", readonly=True)
    contract_signature_name = fields.Char(string="Nombre del firmante", readonly=True)
    contract_signature_ip = fields.Char(string="IP de firma", readonly=True)
    contract_signature_user_agent = fields.Char(string="Navegador de firma", readonly=True)
    contract_signature_hash = fields.Char(string="Hash de firma", readonly=True, copy=False)
    contract_signature_image = fields.Text(string="Trazo de firma", readonly=True, copy=False)
    contract_signature_position_x = fields.Float(string="Posicion firma X (%)", default=68.0, readonly=True)
    contract_signature_position_y = fields.Float(string="Posicion firma Y (%)", default=78.0, readonly=True)
    contract_signature_preview_html = fields.Html(
        string="Vista de firma",
        compute="_compute_contract_signature_preview_html",
        sanitize=False,
    )
    signed_contract_preview_html = fields.Html(
        string="Contrato firmado",
        compute="_compute_signed_contract_preview_html",
        sanitize=False,
    )

    def action_prepare_contract_document(self):
        for contract in self:
            if contract.contract_template_id:
                contract.contract_document_html = contract.contract_template_id.render_template(contract._get_contract_template_values())
            else:
                contract.contract_document_html = contract._get_default_contract_html()

    def action_apply_contract_template(self):
        self.action_prepare_contract_document()

    def action_reset_contract_signature(self):
        self.write(
            {
                "contract_signature_state": "unsigned",
                "contract_signed_date": False,
                "contract_signed_by_id": False,
                "contract_signed_partner_id": False,
                "contract_signature_name": False,
                "contract_signature_ip": False,
                "contract_signature_user_agent": False,
                "contract_signature_hash": False,
                "contract_signature_image": False,
                "contract_signature_position_x": 68.0,
                "contract_signature_position_y": 78.0,
            }
        )

    def action_sync_contract_legajo_document(self):
        for contract in self:
            contract._sync_contract_legajo_document()

    def action_sign_contract(
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

        for contract in self:
            contract._check_can_sign_contract(user)
            signed_date = fields.Datetime.now()
            position_x = contract._normalize_signature_position(signature_position_x, contract.contract_signature_position_x)
            position_y = contract._normalize_signature_position(signature_position_y, contract.contract_signature_position_y)
            signature_image = contract._normalize_signature_image(signature_image)
            contract.sudo().write(
                {
                    "contract_signature_state": "signed",
                    "contract_signed_date": signed_date,
                    "contract_signed_by_id": user.id,
                    "contract_signed_partner_id": user.partner_id.id,
                    "contract_signature_name": signer_name,
                    "contract_signature_ip": ip_address,
                    "contract_signature_user_agent": user_agent,
                    "contract_signature_image": signature_image,
                    "contract_signature_position_x": position_x,
                    "contract_signature_position_y": position_y,
                    "contract_signature_hash": contract._build_contract_signature_hash(
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
            )
            contract.sudo().message_post(body=_("Contrato firmado electronicamente por %s.") % signer_name)
            contract.sudo()._sync_contract_legajo_document()
        return True

    def _check_can_sign_contract(self, user):
        self.ensure_one()
        if not self.contract_signature_required:
            raise UserError(_("Este contrato no requiere firma."))
        if self.contract_signature_state == "signed":
            raise UserError(_("Este contrato ya fue firmado."))
        if not self.contract_document_html:
            raise UserError(_("El contrato no tiene documento para firmar."))
        if user.has_group("hr.group_hr_user") or user.has_group("hr_contract.group_hr_contract_manager"):
            return True
        employee = self.employee_id
        if employee.user_id == user or employee.user_id.partner_id == user.partner_id:
            return True
        raise UserError(_("No tiene permisos para firmar este contrato."))

    def _can_user_access_contract_portal(self, user):
        self.ensure_one()
        employee = self.employee_id
        return employee and (employee.user_id == user or employee.user_id.partner_id == user.partner_id)

    @api.depends("contract_signature_state", "contract_signature_name", "contract_signature_image", "contract_signed_date", "contract_signature_hash")
    def _compute_contract_signature_preview_html(self):
        for contract in self:
            if contract.contract_signature_state != "signed":
                contract.contract_signature_preview_html = """
                    <div style="padding: 12px; border: 1px dashed #adb5bd; border-radius: 6px; color: #6c757d;">
                        Firma pendiente.
                    </div>
                """
                continue

            signer_name = html.escape(contract.contract_signature_name or "")
            signed_date = html.escape(str(contract.contract_signed_date or ""))
            signature_hash = html.escape(contract.contract_signature_hash or "")
            signature_block = contract._get_contract_signature_content_html(360, 130, 36)
            contract.contract_signature_preview_html = """
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
        "contract_document_html",
        "contract_signature_state",
        "contract_signature_name",
        "contract_signature_image",
        "contract_signature_position_x",
        "contract_signature_position_y",
        "contract_signed_date",
    )
    def _compute_signed_contract_preview_html(self):
        for contract in self:
            document_html = contract.contract_document_html or contract._get_default_contract_html()
            if contract.contract_signature_state != "signed":
                contract.signed_contract_preview_html = document_html
                continue
            contract.signed_contract_preview_html = """
                <div style="position: relative;">
                    %s
                    %s
                </div>
            """ % (document_html, contract._get_contract_signature_frame_html())

    def _get_contract_signature_content_html(self, max_width=190, max_height=42, font_size=24):
        self.ensure_one()
        signer_name = html.escape(self.contract_signature_name or "")
        if self.contract_signature_image:
            return """
                <img src="%s" style="display: block; max-width: %spx; max-height: %spx; object-fit: contain;"/>
            """ % (self.contract_signature_image, max_width, max_height)
        return """
            <span style="display: block; font-family: 'Brush Script MT', 'Segoe Script', cursive; font-size: %spx; line-height: 1.1; color: #111827;">
                %s
            </span>
        """ % (font_size, signer_name)

    def _get_contract_signature_frame_html(self):
        self.ensure_one()
        signed_date = html.escape(str(self.contract_signed_date or ""))
        return """
            <div style="position: absolute; left: %s%%; top: %s%%; width: 220px; min-height: 72px; padding: 8px 10px; border: 2px solid #198754; border-radius: 6px; background: rgba(255, 255, 255, 0.94); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16); font-size: 11px; z-index: 5;">
                %s
                <span style="display: block; margin-top: 4px; color: #495057;">
                    Firma electronica - %s
                </span>
            </div>
        """ % (
            self.contract_signature_position_x or 0.0,
            self.contract_signature_position_y or 0.0,
            self._get_contract_signature_content_html(),
            signed_date,
        )

    def _build_contract_signature_hash(
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
            "contract_id": self.id,
            "contract_name": self.name,
            "employee_id": self.employee_id.id,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "contract_document_html": self.contract_document_html or "",
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

    def _get_default_contract_html(self):
        self.ensure_one()
        values = self._get_contract_template_values()
        return """
            <div style="padding: 28px; border: 1px solid #111; background: #fff; min-height: 760px; font-family: Arial, sans-serif; color: #111;">
                <h2 style="text-align: center; margin-bottom: 28px;">CONTRATO DE TRABAJO</h2>
                <p><strong>Referencia:</strong> %(contract_name)s</p>
                <p><strong>Empleado:</strong> %(employee_name)s</p>
                <p><strong>Documento:</strong> %(employee_identification)s</p>
                <p><strong>Cargo:</strong> %(job_name)s</p>
                <p><strong>Departamento:</strong> %(department_name)s</p>
                <p><strong>Fecha de inicio:</strong> %(date_start)s</p>
                <p><strong>Fecha de fin:</strong> %(date_end)s</p>
                <p><strong>Remuneracion mensual:</strong> %(wage)s</p>
                <p style="margin-top: 24px;">
                    Las partes declaran su conformidad con las condiciones laborales indicadas en este documento,
                    sin perjuicio de las clausulas adicionales pactadas por escrito.
                </p>
                <div style="height: 220px;"></div>
                <p style="border-top: 1px solid #111; width: 260px; text-align: center; padding-top: 8px;">
                    Firma del trabajador
                </p>
            </div>
        """ % {key: html.escape(str(value or "")) for key, value in values.items()}

    def _get_contract_template_values(self):
        self.ensure_one()
        employee_name = html.escape(self.employee_id.name or "")
        job_name = html.escape(self.job_id.name or "")
        department_name = html.escape(self.department_id.name or "")
        contract_name = html.escape(self.name or "")
        date_start = html.escape(str(self.date_start or ""))
        date_end = html.escape(str(self.date_end or "Indefinido"))
        wage = html.escape(str(self.wage or ""))
        return {
            "contract_name": contract_name,
            "contract_type": html.escape(self.contract_type_id.name or ""),
            "contract_kind": html.escape(self.contract_kind or ""),
            "employee_name": employee_name,
            "employee_identification": html.escape(self.employee_id.identification_id or ""),
            "employee_email": html.escape(self.employee_id.work_email or self.employee_id.user_id.email or ""),
            "job_name": job_name,
            "department_name": department_name,
            "date_start": date_start,
            "date_end": date_end,
            "wage": wage,
            "company_name": html.escape(self.company_id.name or ""),
        }

    def _sync_contract_legajo_document(self):
        self.ensure_one()
        document_type = self.env.ref("employee_payslip_documents.document_type_contract", raise_if_not_found=False)
        if not document_type or not self.employee_id:
            return False

        pdf_content, _content_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "employee_payslip_documents.action_report_employee_contract",
            [self.id],
        )
        file_name = "%s.pdf" % self.name
        legajo_values = {
            "name": self.name,
            "employee_id": self.employee_id.id,
            "document_type_id": document_type.id,
            "document_date": self.date_start or fields.Date.context_today(self),
            "state": "validated" if self.contract_signature_state == "signed" else "uploaded",
            "notes": "Generado automaticamente desde Contratos.",
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
                "document_date": self.date_start or fields.Date.context_today(self),
                "file_data": base64.b64encode(pdf_content),
                "file_name": file_name,
                "state": "validated" if self.contract_signature_state == "signed" else "uploaded",
                "notes": "Generado automaticamente desde Contratos.",
                "source_model": self._name,
                "source_res_id": self.id,
            }
        )
        return legajo
