from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    sunat_purchase_proposal_line_id = fields.Many2one(
        "sunat.purchase.proposal.line",
        string="Linea de propuesta SUNAT",
        copy=False,
        index=True,
        readonly=True,
    )
    sunat_purchase_car = fields.Char(
        related="sunat_purchase_proposal_line_id.car_sunat",
        string="CAR SUNAT",
        store=True,
    )

