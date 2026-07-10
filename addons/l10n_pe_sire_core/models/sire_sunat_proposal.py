from odoo import fields, models


class SireSunatProposal(models.Model):
    _name = "sire.sunat.proposal"
    _description = "Propuesta SUNAT SIRE"
    _order = "period_id desc, proposal_version desc, id desc"

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
    proposal_version = fields.Integer(string="Version", required=True, default=1)
    requested_at = fields.Datetime(string="Solicitada el")
    downloaded_at = fields.Datetime(string="Descargada el")
    ticket_number = fields.Char(string="Ticket")
    source_filename = fields.Char(string="Archivo origen")
    zip_file = fields.Binary(string="ZIP SUNAT", attachment=True)
    txt_file = fields.Binary(string="TXT SUNAT", attachment=True)
    file_hash = fields.Char(string="SHA-256", index=True)
    record_count = fields.Integer(string="Registros")
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("requested", "Solicitada"),
            ("downloaded", "Descargada"),
            ("empty", "Sin registros"),
            ("parsed", "Procesada"),
            ("error", "Error"),
        ],
        string="Estado",
        default="draft",
        required=True,
    )
