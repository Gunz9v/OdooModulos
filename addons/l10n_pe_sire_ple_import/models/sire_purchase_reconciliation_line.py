from odoo import fields, models


class SirePurchaseReconciliationLine(models.Model):
    _name = "sire.purchase.reconciliation.line"
    _description = "Conciliacion RCE compras"
    _order = "period_id desc, status, normalized_key, id"

    period_id = fields.Many2one("sire.period", string="Periodo", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_id.company_id", string="Empresa", store=True, index=True)
    accounting_line_id = fields.Many2one(
        "sire.purchase.accounting.line",
        string="Linea contable",
        ondelete="cascade",
        index=True,
    )
    sunat_line_id = fields.Many2one(
        "sire.purchase.sunat.line",
        string="Linea SUNAT",
        ondelete="cascade",
        index=True,
    )
    normalized_key = fields.Char(string="Clave normalizada", index=True)
    status = fields.Selection(
        [
            ("matched", "Coincidente"),
            ("difference", "Con diferencias"),
            ("system_only", "Solo sistema"),
            ("sunat_only", "Solo SUNAT"),
        ],
        string="Estado",
        required=True,
        index=True,
    )

    accounting_car_sunat = fields.Char(related="accounting_line_id.car_sunat", string="CAR contable")
    sunat_car_sunat = fields.Char(related="sunat_line_id.car_sunat", string="CAR SUNAT")
    accounting_record_state = fields.Char(related="accounting_line_id.record_state", string="Estado contable")
    sunat_record_state = fields.Char(related="sunat_line_id.record_state", string="Estado SUNAT")
    accounting_issue_date = fields.Date(related="accounting_line_id.issue_date", string="Fecha contable")
    sunat_issue_date = fields.Date(related="sunat_line_id.issue_date", string="Fecha SUNAT")
    accounting_document_type = fields.Char(related="accounting_line_id.document_type", string="Tipo CP contable")
    sunat_document_type = fields.Char(related="sunat_line_id.document_type", string="Tipo CP SUNAT")
    accounting_series = fields.Char(related="accounting_line_id.series", string="Serie contable")
    sunat_series = fields.Char(related="sunat_line_id.series", string="Serie SUNAT")
    accounting_purchase_year = fields.Char(related="accounting_line_id.purchase_year", string="Año DUA contable")
    sunat_purchase_year = fields.Char(related="sunat_line_id.purchase_year", string="Año DUA")
    accounting_number = fields.Char(related="accounting_line_id.number", string="Numero contable")
    sunat_number = fields.Char(related="sunat_line_id.number", string="Numero SUNAT")
    accounting_supplier_document_number = fields.Char(
        related="accounting_line_id.supplier_document_number",
        string="Doc. proveedor contable",
    )
    sunat_supplier_document_number = fields.Char(
        related="sunat_line_id.supplier_document_number",
        string="Doc. proveedor SUNAT",
    )
    accounting_supplier_name = fields.Char(related="accounting_line_id.supplier_name", string="Proveedor contable")
    sunat_supplier_name = fields.Char(related="sunat_line_id.supplier_name", string="Proveedor SUNAT")
    accounting_currency_code = fields.Char(related="accounting_line_id.currency_code", string="Moneda contable")
    sunat_currency_code = fields.Char(related="sunat_line_id.currency_code", string="Moneda SUNAT")
    accounting_exchange_rate = fields.Float(
        related="accounting_line_id.exchange_rate",
        string="TC contable",
        digits=(12, 3),
    )
    sunat_exchange_rate = fields.Float(
        related="sunat_line_id.exchange_rate",
        string="TC SUNAT",
        digits=(12, 3),
    )

    accounting_taxable_base_dg = fields.Monetary(
        related="accounting_line_id.taxable_base_dg",
        string="BI DG contable",
        currency_field="company_currency_id",
    )
    sunat_taxable_base_dg = fields.Monetary(
        related="sunat_line_id.taxable_base_dg",
        string="BI DG SUNAT",
        currency_field="company_currency_id",
    )
    accounting_igv_dg = fields.Monetary(
        related="accounting_line_id.igv_dg",
        string="IGV DG contable",
        currency_field="company_currency_id",
    )
    sunat_igv_dg = fields.Monetary(
        related="sunat_line_id.igv_dg",
        string="IGV DG SUNAT",
        currency_field="company_currency_id",
    )
    accounting_taxable_base_dgng = fields.Monetary(
        related="accounting_line_id.taxable_base_dgng",
        string="BI DGNG contable",
        currency_field="company_currency_id",
    )
    sunat_taxable_base_dgng = fields.Monetary(
        related="sunat_line_id.taxable_base_dgng",
        string="BI DGNG SUNAT",
        currency_field="company_currency_id",
    )
    accounting_igv_dgng = fields.Monetary(
        related="accounting_line_id.igv_dgng",
        string="IGV DGNG contable",
        currency_field="company_currency_id",
    )
    sunat_igv_dgng = fields.Monetary(
        related="sunat_line_id.igv_dgng",
        string="IGV DGNG SUNAT",
        currency_field="company_currency_id",
    )
    accounting_taxable_base_dng = fields.Monetary(
        related="accounting_line_id.taxable_base_dng",
        string="BI DNG contable",
        currency_field="company_currency_id",
    )
    sunat_taxable_base_dng = fields.Monetary(
        related="sunat_line_id.taxable_base_dng",
        string="BI DNG SUNAT",
        currency_field="company_currency_id",
    )
    accounting_igv_dng = fields.Monetary(
        related="accounting_line_id.igv_dng",
        string="IGV DNG contable",
        currency_field="company_currency_id",
    )
    sunat_igv_dng = fields.Monetary(
        related="sunat_line_id.igv_dng",
        string="IGV DNG SUNAT",
        currency_field="company_currency_id",
    )
    accounting_non_taxed_amount = fields.Monetary(
        related="accounting_line_id.non_taxed_amount",
        string="Valor NG contable",
        currency_field="company_currency_id",
    )
    sunat_non_taxed_amount = fields.Monetary(
        related="sunat_line_id.non_taxed_amount",
        string="Valor NG SUNAT",
        currency_field="company_currency_id",
    )
    accounting_isc_amount = fields.Monetary(
        related="accounting_line_id.isc_amount",
        string="ISC contable",
        currency_field="company_currency_id",
    )
    sunat_isc_amount = fields.Monetary(
        related="sunat_line_id.isc_amount",
        string="ISC SUNAT",
        currency_field="company_currency_id",
    )
    accounting_icbper_amount = fields.Monetary(
        related="accounting_line_id.icbper_amount",
        string="ICBPER contable",
        currency_field="company_currency_id",
    )
    sunat_icbper_amount = fields.Monetary(
        related="sunat_line_id.icbper_amount",
        string="ICBPER SUNAT",
        currency_field="company_currency_id",
    )
    accounting_other_tax_amount = fields.Monetary(
        related="accounting_line_id.other_tax_amount",
        string="Otros contable",
        currency_field="company_currency_id",
    )
    sunat_other_tax_amount = fields.Monetary(
        related="sunat_line_id.other_tax_amount",
        string="Otros SUNAT",
        currency_field="company_currency_id",
    )
    accounting_total_amount = fields.Monetary(
        related="accounting_line_id.total_amount",
        string="Total contable",
        currency_field="company_currency_id",
    )
    sunat_total_amount = fields.Monetary(
        related="sunat_line_id.total_amount",
        string="Total SUNAT",
        currency_field="company_currency_id",
    )

    difference_summary = fields.Text(string="Resumen de diferencias")
    issue_date_diff = fields.Boolean(string="Fecha diferente")
    currency_diff = fields.Boolean(string="Moneda diferente")
    taxable_base_dg_has_diff = fields.Boolean(string="BI DG con diferencia")
    igv_dg_has_diff = fields.Boolean(string="IGV DG con diferencia")
    taxable_base_dgng_has_diff = fields.Boolean(string="BI DGNG con diferencia")
    igv_dgng_has_diff = fields.Boolean(string="IGV DGNG con diferencia")
    taxable_base_dng_has_diff = fields.Boolean(string="BI DNG con diferencia")
    igv_dng_has_diff = fields.Boolean(string="IGV DNG con diferencia")
    non_taxed_has_diff = fields.Boolean(string="Valor NG con diferencia")
    isc_has_diff = fields.Boolean(string="ISC con diferencia")
    icbper_has_diff = fields.Boolean(string="ICBPER con diferencia")
    other_tax_has_diff = fields.Boolean(string="Otros con diferencia")
    total_has_diff = fields.Boolean(string="Total con diferencia")

    taxable_base_dg_diff = fields.Monetary(string="Diferencia BI DG", currency_field="company_currency_id")
    igv_dg_diff = fields.Monetary(string="Diferencia IGV DG", currency_field="company_currency_id")
    taxable_base_dgng_diff = fields.Monetary(string="Diferencia BI DGNG", currency_field="company_currency_id")
    igv_dgng_diff = fields.Monetary(string="Diferencia IGV DGNG", currency_field="company_currency_id")
    taxable_base_dng_diff = fields.Monetary(string="Diferencia BI DNG", currency_field="company_currency_id")
    igv_dng_diff = fields.Monetary(string="Diferencia IGV DNG", currency_field="company_currency_id")
    non_taxed_diff = fields.Monetary(string="Diferencia valor NG", currency_field="company_currency_id")
    isc_diff = fields.Monetary(string="Diferencia ISC", currency_field="company_currency_id")
    icbper_diff = fields.Monetary(string="Diferencia ICBPER", currency_field="company_currency_id")
    other_tax_diff = fields.Monetary(string="Diferencia otros", currency_field="company_currency_id")
    total_diff = fields.Monetary(string="Diferencia total", currency_field="company_currency_id")
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Moneda de compania", readonly=True)
