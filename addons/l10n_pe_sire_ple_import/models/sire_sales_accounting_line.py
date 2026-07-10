from odoo import fields, models


class SireSalesAccountingLine(models.Model):
    _name = "sire.sales.accounting.line"
    _inherit = "sire.imported.line.mixin"
    _description = "Linea contable RVIE importada"
    _order = "period_id desc, source_line_number"

    customer_document_type = fields.Char(string="Tipo doc. cliente", index=True)
    customer_document_number = fields.Char(string="Numero doc. cliente", index=True)
    customer_name = fields.Char(string="Cliente")
    original_document_date = fields.Date(string="Fecha comprobante original")
    original_document_type = fields.Char(string="Tipo comprobante original")
    original_document_series = fields.Char(string="Serie original")
    original_document_number = fields.Char(string="Numero original")
