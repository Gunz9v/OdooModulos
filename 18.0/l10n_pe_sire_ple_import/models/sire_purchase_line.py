from odoo import fields, models


class SirePurchaseLineMixin(models.AbstractModel):
    _name = "sire.purchase.line.mixin"
    _inherit = "sire.imported.line.mixin"
    _description = "Linea RCE SIRE"

    purchase_year = fields.Char(string="Anio DUA/DSI")
    final_number = fields.Char(string="Numero final")
    supplier_document_type = fields.Char(string="Tipo doc. proveedor", index=True)
    supplier_document_number = fields.Char(string="Numero doc. proveedor", index=True)
    supplier_name = fields.Char(string="Proveedor")
    original_document_date = fields.Date(string="Fecha comprobante original")
    original_document_type = fields.Char(string="Tipo comprobante original")
    original_document_series = fields.Char(string="Serie original")
    original_document_number = fields.Char(string="Numero original")
    taxable_base_dg = fields.Monetary(string="BI Gravado DG", currency_field="company_currency_id")
    igv_dg = fields.Monetary(string="IGV/IPM DG", currency_field="company_currency_id")
    taxable_base_dgng = fields.Monetary(string="BI Gravado DGNG", currency_field="company_currency_id")
    igv_dgng = fields.Monetary(string="IGV/IPM DGNG", currency_field="company_currency_id")
    taxable_base_dng = fields.Monetary(string="BI Gravado DNG", currency_field="company_currency_id")
    igv_dng = fields.Monetary(string="IGV/IPM DNG", currency_field="company_currency_id")
    non_taxed_amount = fields.Monetary(string="Valor adq. NG", currency_field="company_currency_id")
    icbper_amount = fields.Monetary(string="ICBPER", currency_field="company_currency_id")
    deduction_amount = fields.Monetary(string="Detraccion", currency_field="company_currency_id")
    classification = fields.Char(string="Clasif. bienes/servicios")
    car_original_indicator = fields.Char(string="CAR orig/ind E o I")
    deduction_indicator = fields.Char(string="Indicador detraccion")
    note_type = fields.Char(string="Tipo de nota")
    inconsistency = fields.Char(string="Incal")


class SirePurchaseAccountingLine(models.Model):
    _name = "sire.purchase.accounting.line"
    _inherit = "sire.purchase.line.mixin"
    _description = "Linea contable RCE importada"
    _order = "period_id desc, source_line_number"


class SirePurchaseSunatLine(models.Model):
    _name = "sire.purchase.sunat.line"
    _inherit = "sire.purchase.line.mixin"
    _description = "Linea SUNAT RCE importada"
    _order = "period_id desc, source_line_number"

    proposal_id = fields.Many2one(
        "sire.sunat.proposal",
        string="Propuesta SUNAT",
        ondelete="cascade",
        index=True,
    )
