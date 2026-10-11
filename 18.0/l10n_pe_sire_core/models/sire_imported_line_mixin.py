from odoo import fields, models


class SireImportedLineMixin(models.AbstractModel):
    _name = "sire.imported.line.mixin"
    _description = "Linea importada SIRE"

    period_id = fields.Many2one(
        "sire.period",
        string="Periodo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    batch_id = fields.Many2one(
        "sire.import.batch",
        string="Lote",
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
    source_line_number = fields.Integer(string="Linea origen", required=True)
    source_raw_text = fields.Text(string="Texto original", required=True)
    source_hash = fields.Char(string="Hash de linea", index=True)
    cuo = fields.Char(string="CUO")
    entry_sequence = fields.Char(string="Correlativo")
    issue_date = fields.Date(string="Fecha de emision")
    due_date = fields.Date(string="Fecha de vencimiento")
    document_type = fields.Char(string="Tipo de comprobante", index=True)
    series = fields.Char(string="Serie", index=True)
    number = fields.Char(string="Numero", index=True)
    currency_code = fields.Char(string="Moneda")
    exchange_rate = fields.Float(
        string="Tipo de cambio",
        digits=(12, 3),
    )
    taxable_base = fields.Monetary(
        string="Base imponible",
        currency_field="company_currency_id",
    )
    export_amount = fields.Monetary(
        string="Valor facturado exportacion",
        currency_field="company_currency_id",
    )
    exempt_amount = fields.Monetary(
        string="Operacion exonerada",
        currency_field="company_currency_id",
    )
    unaffected_amount = fields.Monetary(
        string="Operacion inafecta",
        currency_field="company_currency_id",
    )
    igv_amount = fields.Monetary(string="IGV", currency_field="company_currency_id")
    non_taxable_amount = fields.Monetary(
        string="No gravado",
        currency_field="company_currency_id",
    )
    isc_amount = fields.Monetary(string="ISC", currency_field="company_currency_id")
    other_tax_amount = fields.Monetary(
        string="Otros tributos",
        currency_field="company_currency_id",
    )
    total_amount = fields.Monetary(string="Total", currency_field="company_currency_id")
    normalized_key = fields.Char(string="Clave normalizada", index=True)
    record_state = fields.Char(string="Estado PLE")
    validation_state = fields.Selection(
        [
            ("valid", "Valido"),
            ("warning", "Con advertencias"),
            ("invalid", "Invalido"),
        ],
        string="Estado de validacion",
        default="valid",
        required=True,
    )
    validation_messages = fields.Text(string="Mensajes de validacion")
    car_sunat = fields.Char(string="CAR SUNAT")
    car_original = fields.Char(string="CAR original")
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda de compania",
        readonly=True,
    )
