from odoo import fields, models


class SireImportError(models.Model):
    _name = "sire.import.error"
    _description = "Error de importacion SIRE"
    _order = "batch_id desc, line_number, id"

    batch_id = fields.Many2one(
        "sire.import.batch",
        string="Lote",
        required=True,
        ondelete="cascade",
        index=True,
    )
    period_id = fields.Many2one(
        related="batch_id.period_id",
        string="Periodo",
        store=True,
        index=True,
    )
    line_number = fields.Integer(string="Linea", index=True)
    level = fields.Selection(
        [
            ("error", "Error"),
            ("warning", "Advertencia"),
            ("information", "Informacion"),
        ],
        string="Nivel",
        required=True,
        default="error",
    )
    code = fields.Char(string="Codigo")
    message = fields.Text(string="Mensaje", required=True)
    raw_text = fields.Text(string="Texto original")
