from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sunat_purchase_journal_id = fields.Many2one(
        "account.journal",
        string="Diario para propuestas SUNAT",
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        check_company=True,
    )
    sunat_purchase_product_id = fields.Many2one(
        "product.product",
        string="Producto para propuestas SUNAT",
        check_company=True,
        help="Producto usado en la linea resumida de las facturas generadas.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sunat_purchase_journal_id = fields.Many2one(
        related="company_id.sunat_purchase_journal_id",
        readonly=False,
    )
    sunat_purchase_product_id = fields.Many2one(
        related="company_id.sunat_purchase_product_id",
        readonly=False,
    )

