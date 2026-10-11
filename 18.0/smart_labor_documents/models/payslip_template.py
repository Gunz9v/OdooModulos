import re

from markupsafe import Markup

from odoo import api, fields, models


class PayslipDocumentTemplate(models.Model):
    _name = "employee.payslip.document.template"
    _description = "Plantilla de Boleta"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Nombre", required=True, tracking=True)
    active = fields.Boolean(string="Activo", default=True)
    employee_lookup_field = fields.Selection(
        selection=[
            ("work_email", "Correo de trabajo"),
            ("barcode", "Codigo de empleado"),
            ("identification_id", "Numero de identificacion"),
            ("name", "Nombre del empleado"),
        ],
        default="work_email",
        required=True,
        tracking=True,
        string="Campo de busqueda del empleado",
    )
    employee_lookup_column = fields.Char(
        string="Columna de busqueda en Excel",
        default="employee_email",
        required=True,
        help="Columna del Excel usada para encontrar al empleado.",
    )
    digital_signer_user_id = fields.Many2one(
        "res.users",
        string="Usuario encargado de firma digital",
        tracking=True,
        help="Usuario cuyo certificado digital se usara para firmar el PDF generado al enviarlo al legajo.",
    )
    body_html = fields.Html(
        string="Cuerpo de la plantilla",
        sanitize=False,
        required=True,
        default="""
<h2>Boleta de Pago</h2>
<p><strong>Empleado:</strong> {{employee_name}}</p>
<p><strong>Periodo:</strong> {{period}}</p>
<table class="table table-sm">
    <tr><td>Sueldo basico</td><td>{{basic_salary}}</td></tr>
    <tr><td>Bonos</td><td>{{bonus}}</td></tr>
    <tr><td>Descuentos</td><td>{{discount}}</td></tr>
    <tr><td>Neto a pagar</td><td>{{net_amount}}</td></tr>
</table>
""",
    )
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
