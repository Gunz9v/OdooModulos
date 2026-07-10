from odoo import fields, models


class SireApiTicket(models.Model):
    _name = "sire.api.ticket"
    _description = "Ticket API SUNAT SIRE"
    _order = "requested_at desc, id desc"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    period_id = fields.Many2one("sire.period", string="Periodo", ondelete="cascade", index=True)
    proposal_id = fields.Many2one(
        "sire.sunat.proposal",
        string="Propuesta SUNAT",
        ondelete="set null",
        index=True,
    )
    process_type = fields.Selection(
        [
            ("get_token", "Obtener token"),
            ("check_periods", "Consultar periodos RVIE"),
            ("request_proposal", "Solicitar propuesta"),
            ("check_ticket", "Consultar ticket"),
            ("download_proposal", "Descargar propuesta"),
            ("parse_proposal", "Procesar propuesta"),
            ("run_reconciliation", "Ejecutar conciliacion"),
            ("submit_acceptance", "Aceptar propuesta"),
            ("submit_complement", "Complementar propuesta"),
            ("submit_replacement", "Reemplazar propuesta"),
            ("download_result", "Descargar resultado"),
        ],
        string="Proceso",
        required=True,
        index=True,
    )
    ticket_number = fields.Char(string="Ticket SUNAT", index=True)
    requested_at = fields.Datetime(string="Solicitado el", default=fields.Datetime.now, required=True)
    last_check_at = fields.Datetime(string="Ultima consulta")
    next_check_at = fields.Datetime(string="Proxima consulta")
    status_code = fields.Char(string="Codigo estado")
    status_description = fields.Char(string="Descripcion estado")
    attempt_count = fields.Integer(string="Intentos", default=0)
    request_url = fields.Char(string="URL")
    request_method = fields.Char(string="Metodo")
    request_payload = fields.Text(string="Request")
    response_payload = fields.Text(string="Response")
    result_filename = fields.Char(string="Archivo resultado")
    result_content_filename = fields.Char(string="Archivo contenido")
    result_file_type = fields.Char(string="Tipo archivo resultado")
    result_file = fields.Binary(string="Resultado", attachment=True)
    validated_row_count = fields.Integer(string="Filas validadas")
    error_document_count = fields.Integer(string="CP con error")
    informed_document_count = fields.Integer(string="CP informados")
    error_code = fields.Char(string="Codigo error")
    error_message = fields.Text(string="Mensaje error")
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("sent", "Enviado"),
            ("done", "Completado"),
            ("error", "Error"),
        ],
        string="Estado",
        default="draft",
        required=True,
        index=True,
    )

    def action_check_ticket_status(self):
        self.ensure_one()
        self.env["sire.api.client"].check_ticket_status(self)
        return True

    def action_download_ticket_file(self):
        self.ensure_one()
        self.env["sire.api.client"].download_ticket_file(self)
        return True
