from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SirePeriod(models.Model):
    _name = "sire.period"
    _description = "Periodo SIRE"
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
        [
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
        ],
        string="Estado",
        default="draft",
        required=True,
        tracking=True,
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
