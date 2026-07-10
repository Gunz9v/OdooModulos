from odoo import fields, models


class SireImportBatch(models.Model):
    _name = "sire.import.batch"
    _description = "Lote de importacion SIRE"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "imported_at desc, id desc"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    period_id = fields.Many2one(
        "sire.period",
        string="Periodo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    filename = fields.Char(string="Archivo", required=True)
    file_data = fields.Binary(string="Archivo original", required=True, attachment=True)
    file_hash = fields.Char(string="SHA-256", required=True, index=True, copy=False)
    file_encoding = fields.Char(string="Codificacion")
    book_code = fields.Char(string="Codigo de libro", index=True)
    format_version = fields.Char(string="Formato")
    imported_by = fields.Many2one(
        "res.users",
        string="Importado por",
        default=lambda self: self.env.user,
        readonly=True,
    )
    imported_at = fields.Datetime(
        string="Importado el",
        default=fields.Datetime.now,
        readonly=True,
    )
    total_rows = fields.Integer(string="Filas totales", copy=False)
    valid_rows = fields.Integer(string="Filas validas", copy=False)
    warning_rows = fields.Integer(string="Filas con advertencias", copy=False)
    invalid_rows = fields.Integer(string="Filas invalidas", copy=False)
    duplicate_rows = fields.Integer(string="Filas duplicadas", copy=False)
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("imported", "Importado"),
            ("imported_with_warnings", "Importado con advertencias"),
            ("error", "Error"),
        ],
        string="Estado",
        default="draft",
        required=True,
        tracking=True,
    )
    error_summary = fields.Text(string="Resumen de errores", copy=False)
    line_model = fields.Char(string="Modelo de lineas", readonly=True)
    error_ids = fields.One2many(
        "sire.import.error",
        "batch_id",
        string="Errores y advertencias",
    )

    _sql_constraints = [
        (
            "company_file_hash_unique",
            "unique(company_id, file_hash)",
            "Este archivo ya fue importado para la empresa.",
        )
    ]
