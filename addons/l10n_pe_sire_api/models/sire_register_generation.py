from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SireRegisterGeneration(models.Model):
    _name = "sire.register.generation"
    _description = "Generacion de registros SIRE"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_code desc, company_id"
    _rec_name = "period_code"

    company_id = fields.Many2one("res.company", string="Empresa", required=True, index=True)
    period_code = fields.Char(string="Periodo", required=True, index=True)
    year = fields.Integer(string="Anio", required=True)
    month = fields.Selection(
        [(str(number).zfill(2), str(number).zfill(2)) for number in range(1, 13)],
        string="Mes",
        required=True,
    )
    line_ids = fields.One2many(
        "sire.register.generation.line",
        "generation_id",
        string="Registros",
    )
    has_pending_generation = fields.Boolean(
        string="Pendiente de generacion",
        compute="_compute_has_pending_generation",
        store=True,
    )

    _sql_constraints = [
        (
            "company_period_unique",
            "unique(company_id, period_code)",
            "Ya existe una generacion de registros para esta empresa y periodo.",
        )
    ]

    @api.depends("line_ids.generation_state")
    def _compute_has_pending_generation(self):
        for generation in self:
            generation.has_pending_generation = any(
                line.generation_state != "generated" for line in generation.line_ids
            )

    def action_generate_records(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.selected and line.generation_state != "generated")
        if not lines:
            lines = self.line_ids.filtered(lambda line: line.generation_state != "generated")
        if not lines:
            raise UserError(_("No hay registros pendientes para generar."))
        missing_preliminary = lines.filtered(lambda line: line.preliminary_state != "registered")
        if missing_preliminary:
            raise UserError(_("Todos los registros seleccionados deben tener preliminar registrado."))

        ticket = self.env["sire.api.client"].generate_records(self)
        lines.write(
            {
                "generation_state": "generated",
                "selected": False,
                "last_ticket_id": ticket.id,
            }
        )
        self.message_post(
            body=_("Solicitud de generacion de registros enviada a SUNAT. Ticket: %s")
            % (ticket.ticket_number or ticket.id)
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Ticket SUNAT"),
            "res_model": "sire.api.ticket",
            "view_mode": "form",
            "res_id": ticket.id,
        }

    @api.model
    def sync_period_after_acceptance(self, period, ticket=False):
        generation = self.search(
            [
                ("company_id", "=", period.company_id.id),
                ("period_code", "=", period.period_code),
            ],
            limit=1,
        )
        if not generation:
            generation = self.create(
                {
                    "company_id": period.company_id.id,
                    "period_code": period.period_code,
                    "year": period.year,
                    "month": period.month,
                }
            )
        line = self.env["sire.register.generation.line"].search(
            [
                ("generation_id", "=", generation.id),
                ("period_id", "=", period.id),
                ("registry_type", "=", period.registry_type),
            ],
            limit=1,
        )
        values = {
            "generation_id": generation.id,
            "period_id": period.id,
            "company_id": period.company_id.id,
            "registry_type": period.registry_type,
            "period_code": period.period_code,
            "content_indicator": "with_info"
            if (period.total_sunat_records or period.total_accounting_records)
            else "without_info",
            "preliminary_state": "registered",
            "update_state": "updated",
            "generation_state": "not_generated",
            "last_ticket_id": ticket.id if ticket else False,
        }
        if line:
            line.write(values)
        else:
            line = self.env["sire.register.generation.line"].create(values)
        return line


class SireRegisterGenerationLine(models.Model):
    _name = "sire.register.generation.line"
    _description = "Linea de generacion de registros SIRE"
    _order = "registry_type, id"

    generation_id = fields.Many2one(
        "sire.register.generation",
        string="Generacion",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one("res.company", string="Empresa", required=True, index=True)
    period_id = fields.Many2one("sire.period", string="Periodo SIRE", required=True, ondelete="cascade")
    period_code = fields.Char(string="Periodo", required=True, index=True)
    registry_type = fields.Selection(
        [
            ("rce", "Registro de compras"),
            ("rvie", "Registro de Ventas e Ingresos"),
        ],
        string="Registro",
        required=True,
        index=True,
    )
    content_indicator = fields.Selection(
        [
            ("with_info", "Con Informacion"),
            ("without_info", "Sin Informacion"),
        ],
        string="Indicador de contenido",
        default="with_info",
        required=True,
    )
    preliminary_state = fields.Selection(
        [
            ("not_registered", "No Registrado"),
            ("registered", "Registrado"),
        ],
        string="Detalle del preliminar",
        default="not_registered",
        required=True,
    )
    preliminary_deletion_state = fields.Selection(
        [
            ("available", "Disponible"),
            ("not_available", "No disponible"),
        ],
        string="Eliminacion del preliminar",
        default="not_available",
        required=True,
    )
    update_state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("updated", "Actualizado"),
        ],
        string="Estado de actualizacion",
        default="updated",
        required=True,
    )
    generation_state = fields.Selection(
        [
            ("not_generated", "No Generado"),
            ("generated", "Generado"),
        ],
        string="Estado de generacion",
        default="not_generated",
        required=True,
    )
    selected = fields.Boolean(string="Seleccionar")
    last_ticket_id = fields.Many2one("sire.api.ticket", string="Ultimo ticket", readonly=True)

    def action_open_period(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Periodo SIRE"),
            "res_model": "sire.period",
            "view_mode": "form",
            "res_id": self.period_id.id,
        }
