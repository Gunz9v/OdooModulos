from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sire_ruc = fields.Char(string="RUC SIRE")
    sire_sol_user = fields.Char(string="Usuario SOL")
    sire_sol_password = fields.Char(string="Clave SOL", groups="l10n_pe_sire_core.group_sire_manager")
    sire_client_id = fields.Char(string="Client ID SUNAT")
    sire_client_secret = fields.Char(
        string="Client Secret SUNAT",
        groups="l10n_pe_sire_core.group_sire_manager",
    )
    sire_oauth_token_url = fields.Char(
        string="URL token OAuth",
        default="https://api-seguridad.sunat.gob.pe/v1/clientessol/%(client_id)s/oauth2/token/",
    )
    sire_oauth_scope = fields.Char(
        string="Scope OAuth",
        default="https://api-sire.sunat.gob.pe",
    )
    sire_api_base_url = fields.Char(
        string="URL base API SIRE",
        default="https://api-sire.sunat.gob.pe",
    )
    sire_access_token = fields.Text(
        string="Token de acceso",
        copy=False,
        groups="l10n_pe_sire_core.group_sire_manager",
    )
    sire_token_expiration = fields.Datetime(string="Expiracion token", copy=False)
    sire_connection_state = fields.Selection(
        [
            ("not_configured", "Sin configurar"),
            ("token_ok", "Token obtenido"),
            ("error", "Error"),
        ],
        string="Estado conexion SIRE",
        default="not_configured",
        copy=False,
    )
    sire_last_connection_error = fields.Text(string="Ultimo error SIRE", copy=False)

    def action_sire_get_token(self):
        self.ensure_one()
        token_data = self.env["sire.api.client"].get_token(self)
        message = "Token SUNAT obtenido correctamente."
        if token_data.get("expires_in"):
            message += " Expira en %s segundos." % token_data["expires_in"]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Conexion SIRE",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    def action_sire_check_rvie_periods(self):
        self.ensure_one()
        data = self.env["sire.api.client"].get_rvie_periods(self)
        records = data if isinstance(data, list) else data.get("lisPeriodos") or data.get("registros") or []
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Conexion SIRE",
                "message": "Consulta RVIE autorizada. Registros recibidos: %s." % len(records),
                "type": "success",
                "sticky": False,
            },
        }
