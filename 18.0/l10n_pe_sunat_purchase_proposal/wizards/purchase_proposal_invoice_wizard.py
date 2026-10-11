from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.utils import normalize_vat


class SunatPurchaseProposalInvoiceWizard(models.TransientModel):
    _name = "sunat.purchase.proposal.invoice.wizard"
    _description = "Generar facturas desde propuesta SUNAT"

    company_id = fields.Many2one("res.company", required=True)
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    product_id = fields.Many2one(
        "product.product",
        required=True,
        check_company=True,
        help="Se usara en una linea resumida sin impuestos automaticos.",
    )
    line_ids = fields.Many2many(
        "sunat.purchase.proposal.line",
        "sunat_purchase_invoice_wizard_line_rel",
        "wizard_id",
        "line_id",
        string="Comprobantes",
        required=True,
    )
    line_count = fields.Integer(compute="_compute_line_count")

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        company = self.env["res.company"].browse(values.get("company_id")) or self.env.company
        values.setdefault("journal_id", company.sunat_purchase_journal_id.id)
        values.setdefault("product_id", company.sunat_purchase_product_id.id)
        return values

    @api.depends("line_ids")
    def _compute_line_count(self):
        for wizard in self:
            wizard.line_count = len(wizard.line_ids)

    def action_create_invoices(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.match_state == "missing" and not line.generated_move_id)
        if not lines:
            raise UserError(_("No hay comprobantes faltantes disponibles para generar."))
        moves = self.env["account.move"]
        errors = []
        for line in lines:
            try:
                with self.env.cr.savepoint():
                    moves |= self._create_invoice(line)
            except UserError as error:
                errors.append("%s-%s: %s" % (line.series, line.number, error))
        if errors:
            raise UserError(_("No se pudieron generar todas las facturas:\n%s") % "\n".join(errors))
        lines.mapped("proposal_id").write({"state": "processed"})
        return {
            "type": "ir.actions.act_window",
            "name": _("Facturas generadas"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", moves.ids)],
        }

    def _create_invoice(self, line):
        partner = self._find_partner(line)
        document_type = self.env["l10n_latam.document.type"].search(
            [("country_id.code", "=", "PE"), ("code", "=", line.document_type_code)],
            limit=1,
        )
        if not document_type:
            raise UserError(_("No existe el tipo de comprobante SUNAT %s.") % line.document_type_code)
        currency = self.env["res.currency"].search([("name", "=", line.currency_code or "PEN")], limit=1)
        if not currency:
            raise UserError(_("No existe la moneda %s.") % line.currency_code)
        move_type = "in_refund" if line.document_type_code == "07" or line.total_amount < 0 else "in_invoice"
        document_number = "%s-%s" % (line.series, line.number)
        move = self.env["account.move"].with_company(line.company_id).create(
            {
                "move_type": move_type,
                "company_id": line.company_id.id,
                "journal_id": self.journal_id.id,
                "partner_id": partner.id,
                "invoice_date": line.issue_date,
                "invoice_date_due": line.due_date or line.issue_date,
                "currency_id": currency.id,
                "l10n_latam_document_type_id": document_type.id,
                "l10n_latam_document_number": document_number,
                "ref": document_number,
                "sunat_purchase_proposal_line_id": line.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_id.id,
                            "name": _("Compra importada de propuesta SUNAT %s") % line.car_sunat,
                            "quantity": 1,
                            "price_unit": abs(line.total_amount),
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        line.write(
            {
                "generated_move_id": move.id,
                "matched_move_id": move.id,
                "match_state": "generated",
                "difference_summary": _("Factura borrador generada. Revisar detalle contable e impuestos antes de publicar."),
            }
        )
        return move

    def _find_partner(self, line):
        vat = normalize_vat(line.supplier_document_number)
        partners = self.env["res.partner"].search(
            [("vat", "!=", False), ("company_id", "in", (False, line.company_id.id))]
        ).filtered(lambda partner: normalize_vat(partner.vat) == vat)
        commercial = partners.mapped("commercial_partner_id")
        if len(commercial) != 1:
            if not commercial:
                raise UserError(_("No se encontro proveedor con documento %s.") % vat)
            raise UserError(_("Existe mas de un proveedor con documento %s.") % vat)
        return commercial
