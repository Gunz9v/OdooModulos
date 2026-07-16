from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


SIRE_PERIOD_STATES = [
    ("draft", "Borrador"),
    ("file_imported", "Archivo importado"),
    ("proposal_requested", "Propuesta solicitada"),
    ("proposal_downloaded", "Propuesta descargada"),
    ("reconciled", "Conciliado"),
    ("under_review", "En revision"),
    ("ready_to_submit", "Listo para enviar"),
    ("preliminary_generated", "Preliminar generado"),
    ("pending_sunat_confirmation", "Pendiente SUNAT"),
    ("closed", "Cerrado"),
    ("error", "Error"),
]


class SirePeriod(models.Model):
    _name = "sire.period"
    _description = "Periodo SIRE"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "period_code"
    _order = "period_code desc, registry_type, company_id"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    registry_type = fields.Selection(
        [
            ("rce", "RCE - Compras"),
            ("rvie", "RVIE - Ventas e Ingresos"),
        ],
        string="Tipo de registro",
        required=True,
        default="rce",
        tracking=True,
    )
    year = fields.Integer(string="Anio", required=True, tracking=True)
    month = fields.Selection(
        [(str(number).zfill(2), str(number).zfill(2)) for number in range(1, 13)],
        string="Mes",
        required=True,
        tracking=True,
    )
    period_code = fields.Char(
        string="Periodo",
        compute="_compute_period_code",
        store=True,
        readonly=False,
        tracking=True,
    )
    state = fields.Selection(
        SIRE_PERIOD_STATES,
        string="Estado",
        default="draft",
        required=True,
        tracking=True,
    )
    state_before_validation = fields.Selection(
        SIRE_PERIOD_STATES,
        string="Estado anterior de validacion",
        copy=False,
    )
    decision_type = fields.Selection(
        [
            ("accept", "Aceptar propuesta"),
            ("complement", "Complementar propuesta"),
            ("replace", "Reemplazar propuesta"),
            ("non_domiciled", "No domiciliados"),
            ("adjustment", "Ajuste posterior"),
        ],
        string="Decision tributaria",
        tracking=True,
    )
    accounting_batch_id = fields.Many2one(
        "sire.import.batch",
        string="Lote contable activo",
        copy=False,
    )
    sunat_proposal_id = fields.Many2one(
        "sire.sunat.proposal",
        string="Propuesta SUNAT",
        copy=False,
    )
    total_accounting_records = fields.Integer(string="Registros contables", copy=False)
    total_sunat_records = fields.Integer(string="Registros SUNAT", copy=False)
    matched_count = fields.Integer(string="Coincidentes", copy=False)
    difference_count = fields.Integer(string="Con diferencias", copy=False)
    sunat_only_count = fields.Integer(string="Solo SUNAT", copy=False)
    system_only_count = fields.Integer(string="Solo sistema", copy=False)
    preliminary_generated = fields.Boolean(string="Preliminar generado", copy=False)
    final_generation_date = fields.Datetime(string="Fecha generacion final", copy=False)
    closed_by = fields.Many2one("res.users", string="Cerrado por", copy=False)
    closed_at = fields.Datetime(string="Cerrado el", copy=False)
    import_batch_ids = fields.One2many(
        "sire.import.batch",
        "period_id",
        string="Importaciones",
    )

    _sql_constraints = [
        (
            "company_period_registry_unique",
            "unique(company_id, period_code, registry_type)",
            "Ya existe un periodo SIRE para esta empresa, periodo y tipo de registro.",
        )
    ]

    @api.depends("year", "month")
    def _compute_period_code(self):
        for period in self:
            period.period_code = "%04d-%s" % (period.year or 0, period.month or "00")

    @api.constrains("year")
    def _check_year(self):
        for period in self:
            if period.year and (period.year < 2000 or period.year > 2100):
                raise ValidationError("El anio del periodo SIRE no es valido.")

    def unlink(self):
        locked_periods = self.filtered(lambda period: period.state in ("closed", "error"))
        if locked_periods:
            names = ", ".join(locked_periods.mapped("period_code"))
            raise UserError(
                _("No se puede eliminar un periodo SIRE en estado Cerrado o Error: %s.") % names
            )
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._check_decision_type_write(values)
        return super().create(vals_list)

    def write(self, values):
        self._check_decision_type_write(values)
        if values and not self.env.context.get("allow_sire_closed_write"):
            allowed_fields = {
                "message_follower_ids",
                "message_ids",
                "activity_ids",
            }
            protected_values = set(values) - allowed_fields
            closed_periods = self.filtered(lambda period: period.state == "closed")
            if closed_periods and protected_values:
                names = ", ".join(closed_periods.mapped("period_code"))
                raise UserError(
                    _("No se puede modificar un periodo SIRE cerrado: %s. Elimina el preliminar desde Registros para reabrirlo.")
                    % names
                )
        return super().write(values)

    def _check_decision_type_write(self, values):
        if not values or self.env.context.get("allow_sire_decision_type_write"):
            return
        if "decision_type" in values:
            raise UserError(
                _(
                    "La decision tributaria no se selecciona manualmente. "
                    "Se asigna automaticamente al usar el boton correspondiente."
                )
            )

    def action_server_set_closed_or_error(self):
        for period in self:
            next_state = "error" if period.state == "closed" else "closed"
            values = {"state": next_state}
            if period.state not in ("closed", "error"):
                values["state_before_validation"] = period.state
            if next_state == "closed":
                values.update(
                    {
                        "closed_by": self.env.user.id,
                        "closed_at": fields.Datetime.now(),
                    }
                )
            period.with_context(allow_sire_closed_write=True).write(values)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Validacion aplicada"),
                "message": _("Los periodos seleccionados fueron enviados a Cerrado/Error."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_server_restore_previous_state(self):
        missing_previous = self.filtered(lambda period: not period.state_before_validation)
        if missing_previous:
            names = ", ".join(missing_previous.mapped("period_code"))
            raise UserError(_("No hay estado anterior guardado para: %s.") % names)
        for period in self:
            period.with_context(allow_sire_closed_write=True).write(
                {
                    "state": period.state_before_validation,
                    "state_before_validation": False,
                    "closed_by": False,
                    "closed_at": False,
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Estado restaurado"),
                "message": _("Los periodos seleccionados volvieron a su estado anterior."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_import_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Importar archivo contable",
            "res_model": "sire.ple.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_period_id": self.id},
        }
