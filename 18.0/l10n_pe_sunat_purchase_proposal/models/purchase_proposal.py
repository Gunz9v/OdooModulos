from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SunatPurchaseProposal(models.Model):
    _name = "sunat.purchase.proposal"
    _description = "Propuesta de compras SUNAT"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period desc, id desc"

    name = fields.Char(required=True, copy=False, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    period = fields.Char(required=True, index=True, tracking=True)
    state = fields.Selection(
        [
            ("imported", "Importada"),
            ("compared", "Comparada"),
            ("processed", "Procesada"),
            ("error", "Con errores"),
        ],
        required=True,
        default="imported",
        tracking=True,
    )
    source_filename = fields.Char(required=True, readonly=True)
    source_file = fields.Binary(attachment=True, readonly=True)
    source_hash = fields.Char(required=True, index=True, readonly=True)
    imported_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    line_ids = fields.One2many(
        "sunat.purchase.proposal.line",
        "proposal_id",
        string="Comprobantes",
    )
    line_count = fields.Integer(compute="_compute_counts")
    matched_count = fields.Integer(compute="_compute_counts")
    difference_count = fields.Integer(compute="_compute_counts")
    missing_count = fields.Integer(compute="_compute_counts")
    ambiguous_count = fields.Integer(compute="_compute_counts")
    generated_count = fields.Integer(compute="_compute_counts")
    invalid_count = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        (
            "company_source_hash_unique",
            "unique(company_id, source_hash)",
            "Este archivo ya fue importado para la empresa.",
        ),
    ]

    @api.depends("line_ids.match_state")
    def _compute_counts(self):
        for proposal in self:
            proposal.line_count = len(proposal.line_ids)
            counts = {key: 0 for key in ("matched", "difference", "missing", "ambiguous", "generated", "invalid")}
            for line in proposal.line_ids:
                if line.match_state in counts:
                    counts[line.match_state] += 1
            for key, value in counts.items():
                setattr(proposal, "%s_count" % key, value)

    def action_compare(self):
        for proposal in self:
            proposal.line_ids._compare_with_moves()
            proposal.state = "processed" if proposal.line_ids and all(
                line.match_state in ("matched", "difference", "generated", "invalid")
                for line in proposal.line_ids
            ) else "compared"
        return self.action_open_lines()

    def action_open_lines(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "l10n_pe_sunat_purchase_proposal.action_sunat_purchase_proposal_line"
        )
        action["domain"] = [("proposal_id", "=", self.id)]
        action["context"] = {
            "default_proposal_id": self.id,
            "search_default_group_match_state": 1,
        }
        return action

    def action_open_missing_lines(self):
        self.ensure_one()
        action = self.action_open_lines()
        action["domain"] = [
            ("proposal_id", "=", self.id),
            ("match_state", "=", "missing"),
        ]
        return action

    def unlink(self):
        if any(proposal.generated_count for proposal in self):
            raise UserError(_("No puede eliminar una propuesta que ya genero facturas."))
        return super().unlink()

