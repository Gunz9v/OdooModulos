from odoo import fields, models


class SireSalesReconciliationLine(models.Model):
    _name = "sire.sales.reconciliation.line"
    _description = "Conciliacion RVIE ventas"
    _order = "period_id desc, status, normalized_key, id"

    period_id = fields.Many2one(
        "sire.period",
        string="Periodo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="period_id.company_id",
        string="Empresa",
        store=True,
        index=True,
    )
    accounting_line_id = fields.Many2one(
        "sire.sales.accounting.line",
        string="Linea contable",
        ondelete="cascade",
        index=True,
    )
    sunat_line_id = fields.Many2one(
        "sire.sales.sunat.line",
        string="Linea SUNAT",
        ondelete="cascade",
        index=True,
    )
    normalized_key = fields.Char(string="Clave normalizada", index=True)
    accounting_car_sunat = fields.Char(
        related="accounting_line_id.car_sunat",
        string="CAR contable",
    )
    sunat_car_sunat = fields.Char(
        related="sunat_line_id.car_sunat",
        string="CAR SUNAT",
    )
    accounting_record_state = fields.Char(
        related="accounting_line_id.record_state",
        string="Estado contable",
    )
    sunat_record_state = fields.Char(
        related="sunat_line_id.record_state",
        string="Estado SUNAT",
    )
    accounting_issue_date = fields.Date(
        related="accounting_line_id.issue_date",
        string="Fecha contable",
    )
    sunat_issue_date = fields.Date(
        related="sunat_line_id.issue_date",
        string="Fecha SUNAT",
    )
    accounting_document_type = fields.Char(
        related="accounting_line_id.document_type",
        string="Tipo CP contable",
    )
    sunat_document_type = fields.Char(
        related="sunat_line_id.document_type",
        string="Tipo CP SUNAT",
    )
    accounting_series = fields.Char(
        related="accounting_line_id.series",
        string="Serie contable",
    )
    sunat_series = fields.Char(
        related="sunat_line_id.series",
        string="Serie SUNAT",
    )
    accounting_number = fields.Char(
        related="accounting_line_id.number",
        string="Numero contable",
    )
    sunat_number = fields.Char(
        related="sunat_line_id.number",
        string="Numero SUNAT",
    )
    accounting_customer_document_number = fields.Char(
        related="accounting_line_id.customer_document_number",
        string="Doc. cliente contable",
    )
    sunat_customer_document_number = fields.Char(
        related="sunat_line_id.customer_document_number",
        string="Doc. cliente SUNAT",
    )
    accounting_customer_name = fields.Char(
        related="accounting_line_id.customer_name",
        string="Cliente contable",
    )
    sunat_customer_name = fields.Char(
        related="sunat_line_id.customer_name",
        string="Cliente SUNAT",
    )
    accounting_currency_code = fields.Char(
        related="accounting_line_id.currency_code",
        string="Moneda contable",
    )
    sunat_currency_code = fields.Char(
        related="sunat_line_id.currency_code",
        string="Moneda SUNAT",
    )
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
    accounting_taxable_base = fields.Monetary(
        related="accounting_line_id.taxable_base",
        string="Base contable",
        currency_field="company_currency_id",
    )
    sunat_taxable_base = fields.Monetary(
        related="sunat_line_id.taxable_base",
        string="Base SUNAT",
        currency_field="company_currency_id",
    )
    accounting_export_amount = fields.Monetary(
        related="accounting_line_id.export_amount",
        string="Exportacion contable",
        currency_field="company_currency_id",
    )
    sunat_export_amount = fields.Monetary(
        related="sunat_line_id.export_amount",
        string="Exportacion SUNAT",
        currency_field="company_currency_id",
    )
    accounting_exempt_amount = fields.Monetary(
        related="accounting_line_id.exempt_amount",
        string="Exonerada contable",
        currency_field="company_currency_id",
    )
    sunat_exempt_amount = fields.Monetary(
        related="sunat_line_id.exempt_amount",
        string="Exonerada SUNAT",
        currency_field="company_currency_id",
    )
    accounting_unaffected_amount = fields.Monetary(
        related="accounting_line_id.unaffected_amount",
        string="Inafecta contable",
        currency_field="company_currency_id",
    )
    sunat_unaffected_amount = fields.Monetary(
        related="sunat_line_id.unaffected_amount",
        string="Inafecta SUNAT",
        currency_field="company_currency_id",
    )
    accounting_igv_amount = fields.Monetary(
        related="accounting_line_id.igv_amount",
        string="IGV contable",
        currency_field="company_currency_id",
    )
    sunat_igv_amount = fields.Monetary(
        related="sunat_line_id.igv_amount",
        string="IGV SUNAT",
        currency_field="company_currency_id",
    )
    accounting_total_amount = fields.Monetary(
        related="accounting_line_id.total_amount",
        string="Importe contable",
        currency_field="company_currency_id",
    )
    sunat_total_amount = fields.Monetary(
        related="sunat_line_id.total_amount",
        string="Importe SUNAT",
        currency_field="company_currency_id",
    )
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
    difference_summary = fields.Text(string="Resumen de diferencias")
    issue_date_diff = fields.Boolean(string="Fecha diferente")
    currency_diff = fields.Boolean(string="Moneda diferente")
    export_has_diff = fields.Boolean(string="Exportacion con diferencia")
    taxable_base_has_diff = fields.Boolean(string="Base con diferencia")
    exempt_has_diff = fields.Boolean(string="Exonerada con diferencia")
    unaffected_has_diff = fields.Boolean(string="Inafecta con diferencia")
    igv_has_diff = fields.Boolean(string="IGV con diferencia")
    total_has_diff = fields.Boolean(string="Total con diferencia")
    export_diff = fields.Monetary(
        string="Diferencia exportacion",
        currency_field="company_currency_id",
    )
    taxable_base_diff = fields.Monetary(
        string="Diferencia base",
        currency_field="company_currency_id",
    )
    exempt_diff = fields.Monetary(
        string="Diferencia exonerada",
        currency_field="company_currency_id",
    )
    unaffected_diff = fields.Monetary(
        string="Diferencia inafecta",
        currency_field="company_currency_id",
    )
    igv_diff = fields.Monetary(string="Diferencia IGV", currency_field="company_currency_id")
    total_diff = fields.Monetary(string="Diferencia total", currency_field="company_currency_id")
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda de compania",
        readonly=True,
    )
