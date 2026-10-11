from odoo import api, fields, models


class SireImportBatch(models.Model):
    _inherit = "sire.import.batch"

    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda de compania",
        readonly=True,
    )
    registry_type = fields.Selection(
        related="period_id.registry_type",
        string="Tipo de registro",
        readonly=True,
    )
    total_export_amount = fields.Monetary(
        string="Total exportacion",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_taxable_base = fields.Monetary(
        string="Total BI",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_taxable_base_discount = fields.Monetary(
        string="Total dscto BI",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_exempt_amount = fields.Monetary(
        string="Total exonerado",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_unaffected_amount = fields.Monetary(
        string="Total inafecto",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_igv_amount = fields.Monetary(
        string="Total IGV",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_igv_discount = fields.Monetary(
        string="Total dscto IGV",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_taxable_base_dg = fields.Monetary(
        string="Total BI DG",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_igv_dg = fields.Monetary(
        string="Total IGV DG",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_taxable_base_dgng = fields.Monetary(
        string="Total BI DGNG",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_igv_dgng = fields.Monetary(
        string="Total IGV DGNG",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_taxable_base_dng = fields.Monetary(
        string="Total BI DNG",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_igv_dng = fields.Monetary(
        string="Total IGV DNG",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_non_taxed_amount = fields.Monetary(
        string="Total adq. NG",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_isc_amount = fields.Monetary(
        string="Total ISC",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_icbper_amount = fields.Monetary(
        string="Total ICBPER",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_other_tax_amount = fields.Monetary(
        string="Total otros trib.",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )
    total_document_amount = fields.Monetary(
        string="Total CP",
        currency_field="company_currency_id",
        compute="_compute_amount_totals",
    )

    @api.depends("line_model")
    def _compute_amount_totals(self):
        amount_fields = self._amount_total_fields()
        for batch in self:
            totals = dict.fromkeys(amount_fields, 0.0)
            line_model = batch.line_model
            if line_model and line_model in self.env.registry:
                for line in self.env[line_model].search([("batch_id", "=", batch.id)]):
                    for target_field, source_field in amount_fields.items():
                        if source_field in line._fields:
                            totals[target_field] += line[source_field] or 0.0
            for field_name, value in totals.items():
                batch[field_name] = value

    def _amount_total_fields(self):
        return {
            "total_export_amount": "export_amount",
            "total_taxable_base": "taxable_base",
            "total_taxable_base_discount": "taxable_base_discount",
            "total_exempt_amount": "exempt_amount",
            "total_unaffected_amount": "unaffected_amount",
            "total_igv_amount": "igv_amount",
            "total_igv_discount": "igv_discount",
            "total_taxable_base_dg": "taxable_base_dg",
            "total_igv_dg": "igv_dg",
            "total_taxable_base_dgng": "taxable_base_dgng",
            "total_igv_dgng": "igv_dgng",
            "total_taxable_base_dng": "taxable_base_dng",
            "total_igv_dng": "igv_dng",
            "total_non_taxed_amount": "non_taxed_amount",
            "total_isc_amount": "isc_amount",
            "total_icbper_amount": "icbper_amount",
            "total_other_tax_amount": "other_tax_amount",
            "total_document_amount": "total_amount",
        }

    def unlink(self):
        cleanup_data = []
        for batch in self:
            period = batch.period_id
            import_kind = self._get_import_kind(batch)
            proposals = self._get_batch_sunat_proposals(batch) if import_kind == "sunat" else self.env["sire.sunat.proposal"]
            cleanup_data.append((period, import_kind, proposals))
            if proposals:
                proposals.unlink()

        result = super().unlink()

        for period, import_kind, _proposals in cleanup_data:
            if period.exists():
                period._reset_after_import_batch_delete(import_kind)
        return result

    def _get_import_kind(self, batch):
        line_model = batch.line_model or ""
        if "accounting.line" in line_model:
            return "accounting"
        if "sunat.line" in line_model:
            return "sunat"
        if batch.format_version in ("14.1", "8.1"):
            return "accounting"
        if batch.format_version in ("14.4", "8.4"):
            return "sunat"
        return "unknown"

    def _get_batch_sunat_proposals(self, batch):
        if batch.line_model not in ("sire.sales.sunat.line", "sire.purchase.sunat.line"):
            return self.env["sire.sunat.proposal"]
        lines = self.env[batch.line_model].search([("batch_id", "=", batch.id)])
        proposals = lines.mapped("proposal_id")
        if batch.period_id.sunat_proposal_id and not proposals:
            proposals = batch.period_id.sunat_proposal_id
        return proposals
