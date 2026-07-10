import time

from odoo import _, fields, models
from odoo.exceptions import UserError


class SirePeriod(models.Model):
    _inherit = "sire.period"

    api_ticket_ids = fields.One2many("sire.api.ticket", "period_id", string="Tickets SUNAT")

    def action_sync_sunat_proposal(self):
        self.ensure_one()
        client = self.env["sire.api.client"]
        ticket = client.request_proposal(self)
        max_checks = int(self.env.context.get("sire_auto_sync_max_checks", 8))
        sleep_seconds = int(self.env.context.get("sire_auto_sync_sleep_seconds", 2))
        for attempt in range(max(max_checks, 1)):
            client.check_ticket_status(ticket)
            if ticket.state == "done" and ticket.status_code == "06":
                break
            if attempt < max_checks - 1 and sleep_seconds:
                time.sleep(sleep_seconds)

        if ticket.state == "done" and ticket.status_code == "06":
            response = client.download_ticket_file(ticket)
            if response and ticket.result_file:
                proposal = self._import_downloaded_sunat_proposal(ticket)
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Propuesta SUNAT"),
                    "res_model": "sire.sunat.proposal",
                    "view_mode": "form",
                    "res_id": proposal.id,
                }
            if ticket.proposal_id and ticket.proposal_id.state == "empty":
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Propuesta SUNAT"),
                    "res_model": "sire.sunat.proposal",
                    "view_mode": "form",
                    "res_id": ticket.proposal_id.id,
                }

        return {
            "type": "ir.actions.act_window",
            "name": "Ticket SUNAT",
            "res_model": "sire.api.ticket",
            "view_mode": "form",
            "res_id": ticket.id,
        }

    def _import_downloaded_sunat_proposal(self, ticket):
        if "sire.sunat.proposal.import.wizard" not in self.env.registry:
            raise UserError(_("El modulo de importacion PLE SIRE no esta instalado."))
        wizard = self.env["sire.sunat.proposal.import.wizard"].create(
            {
                "period_id": self.id,
                "file_data": ticket.result_file,
                "filename": ticket.result_filename,
            }
        )
        return wizard.action_import_downloaded_proposal(ticket.proposal_id)
