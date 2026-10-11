from odoo import fields, models


class SireSalesSunatLine(models.Model):
    _name = "sire.sales.sunat.line"
    _inherit = "sire.imported.line.mixin"
    _description = "Linea SUNAT RVIE importada"
    _order = "period_id desc, source_line_number"

    proposal_id = fields.Many2one(
        "sire.sunat.proposal",
        string="Propuesta SUNAT",
        ondelete="cascade",
        index=True,
    )
    customer_document_type = fields.Char(string="Tipo doc. cliente", index=True)
    customer_document_number = fields.Char(string="Numero doc. cliente", index=True)
    customer_name = fields.Char(string="Cliente")
    original_document_date = fields.Date(string="Fecha comprobante original")
    original_document_type = fields.Char(string="Tipo comprobante original")
    original_document_series = fields.Char(string="Serie original")
    original_document_number = fields.Char(string="Numero original")
    taxable_base_discount = fields.Monetary(string="Dscto BI", currency_field="company_currency_id")
    igv_discount = fields.Monetary(string="Dscto IGV", currency_field="company_currency_id")
