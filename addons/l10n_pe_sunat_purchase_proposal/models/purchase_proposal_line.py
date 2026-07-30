from collections import defaultdict

from odoo import api, fields, models, _
from odoo.tools import float_compare

from .utils import build_document_key, normalize_number, normalize_series, normalize_vat, split_document_number


class SunatPurchaseProposalLine(models.Model):
    _name = "sunat.purchase.proposal.line"
    _description = "Comprobante de propuesta de compras SUNAT"
    _order = "proposal_id desc, source_line_number, id"

    proposal_id = fields.Many2one(
        "sunat.purchase.proposal",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="proposal_id.company_id", store=True, index=True)
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    source_line_number = fields.Integer(required=True)
    source_raw_text = fields.Text(required=True)
    source_hash = fields.Char(index=True)
    car_sunat = fields.Char(string="CAR SUNAT", index=True)
    issue_date = fields.Date(string="Fecha de emision")
    due_date = fields.Date(string="Fecha de vencimiento")
    document_type_code = fields.Char(string="Tipo CP", index=True)
    series = fields.Char(index=True)
    purchase_year = fields.Char(string="Anio DUA/DSI")
    number = fields.Char(string="Numero", index=True)
    final_number = fields.Char(string="Numero final")
    supplier_document_type = fields.Char(string="Tipo doc. proveedor")
    supplier_document_number = fields.Char(string="Documento proveedor", index=True)
    supplier_name = fields.Char(string="Proveedor")
    currency_code = fields.Char(string="Moneda")
    exchange_rate = fields.Float(string="Tipo de cambio", digits=(12, 3))
    taxable_base_dg = fields.Monetary(string="BI Gravada DG", currency_field="company_currency_id")
    igv_dg = fields.Monetary(string="IGV DG", currency_field="company_currency_id")
    taxable_base_dgng = fields.Monetary(string="BI Gravada DGNG", currency_field="company_currency_id")
    igv_dgng = fields.Monetary(string="IGV DGNG", currency_field="company_currency_id")
    taxable_base_dng = fields.Monetary(string="BI Gravada DNG", currency_field="company_currency_id")
    igv_dng = fields.Monetary(string="IGV DNG", currency_field="company_currency_id")
    non_taxed_amount = fields.Monetary(string="No gravado", currency_field="company_currency_id")
    isc_amount = fields.Monetary(string="ISC", currency_field="company_currency_id")
    icbper_amount = fields.Monetary(string="ICBPER", currency_field="company_currency_id")
    other_tax_amount = fields.Monetary(string="Otros tributos", currency_field="company_currency_id")
    total_amount = fields.Monetary(string="Total", currency_field="company_currency_id")
    original_document_date = fields.Date(string="Fecha documento original")
    original_document_type = fields.Char(string="Tipo documento original")
    original_document_series = fields.Char(string="Serie documento original")
    original_document_number = fields.Char(string="Numero documento original")
    classification = fields.Char(string="Clasificacion")
    record_state = fields.Char(string="Estado SUNAT")
    inconsistency = fields.Char(string="Inconsistencia")
    normalized_key = fields.Char(index=True)
    validation_state = fields.Selection(
        [("valid", "Valida"), ("warning", "Con advertencias"), ("invalid", "Invalida")],
        required=True,
        default="valid",
    )
    validation_messages = fields.Text()
    match_state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("matched", "Registrada"),
            ("difference", "Con diferencias"),
            ("missing", "No registrada"),
            ("ambiguous", "Coincidencia ambigua"),
            ("generated", "Factura generada"),
            ("invalid", "No procesable"),
        ],
        required=True,
        default="pending",
        index=True,
    )
    matched_move_id = fields.Many2one("account.move", string="Factura encontrada", index=True)
    generated_move_id = fields.Many2one("account.move", string="Factura generada", index=True, copy=False)
    difference_summary = fields.Text(string="Resultado de comparacion")

    _sql_constraints = [
        (
            "proposal_source_line_unique",
            "unique(proposal_id, source_line_number)",
            "La linea de origen ya existe en esta propuesta.",
        ),
    ]

    def _compare_with_moves(self):
        proposals = self.mapped("proposal_id")
        for proposal in proposals:
            lines = self.filtered(lambda item: item.proposal_id == proposal and not item.generated_move_id)
            moves = self.env["account.move"].search(
                [
                    ("company_id", "=", proposal.company_id.id),
                    ("move_type", "in", ("in_invoice", "in_refund")),
                    ("state", "!=", "cancel"),
                ]
            )
            moves_by_key = defaultdict(lambda: self.env["account.move"])
            for move in moves:
                key = self._move_key(move)
                if key:
                    moves_by_key[key] |= move
            for line in lines:
                if line.validation_state == "invalid" or line.record_state == "2":
                    line.write(
                        {
                            "match_state": "invalid",
                            "matched_move_id": False,
                            "difference_summary": _("Linea invalida o comprobante SUNAT anulado."),
                        }
                    )
                    continue
                candidates = moves_by_key.get(line.normalized_key, self.env["account.move"])
                if not candidates:
                    line.write(
                        {
                            "match_state": "missing",
                            "matched_move_id": False,
                            "difference_summary": _("No se encontro una factura con la misma clave documental."),
                        }
                    )
                elif len(candidates) > 1:
                    line.write(
                        {
                            "match_state": "ambiguous",
                            "matched_move_id": False,
                            "difference_summary": _("Se encontraron varias facturas: %s") % ", ".join(candidates.mapped("display_name")),
                        }
                    )
                else:
                    differences = line._get_move_differences(candidates)
                    line.write(
                        {
                            "match_state": "difference" if differences else "matched",
                            "matched_move_id": candidates.id,
                            "difference_summary": "\n".join(differences) if differences else _("Coincidencia exacta."),
                        }
                    )

    @api.model
    def _move_key(self, move):
        vat = normalize_vat(move.commercial_partner_id.vat or move.partner_id.vat)
        document_type = move.l10n_latam_document_type_id.code or ""
        raw_number = move.l10n_latam_document_number or move.ref or move.name
        series, number = split_document_number(raw_number)
        if not series and move.ref:
            series, number = split_document_number(move.ref)
        if not vat or not document_type or not series or not number:
            return False
        return build_document_key(vat, document_type, series, number)

    def _get_move_differences(self, move):
        self.ensure_one()
        differences = []
        if self.issue_date and move.invoice_date and self.issue_date != move.invoice_date:
            differences.append(_("Fecha: SUNAT %s / Odoo %s") % (self.issue_date, move.invoice_date))
        expected_currency = self.currency_code or self.company_id.currency_id.name
        if expected_currency and move.currency_id.name != expected_currency:
            differences.append(_("Moneda: SUNAT %s / Odoo %s") % (expected_currency, move.currency_id.name))
        precision = move.currency_id.decimal_places
        expected_total = abs(self.total_amount)
        if float_compare(expected_total, move.amount_total, precision_digits=precision):
            differences.append(_("Total: SUNAT %.2f / Odoo %.2f") % (expected_total, move.amount_total))
        return differences

    def action_open_invoice_creation_wizard(self):
        eligible = self.filtered(lambda line: line.match_state == "missing" and not line.generated_move_id)
        return {
            "type": "ir.actions.act_window",
            "name": _("Generar facturas faltantes"),
            "res_model": "sunat.purchase.proposal.invoice.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_line_ids": [(6, 0, eligible.ids)],
                "default_company_id": eligible[:1].company_id.id or self.env.company.id,
            },
        }

    def action_open_related_move(self):
        self.ensure_one()
        move = self.generated_move_id or self.matched_move_id
        return {
            "type": "ir.actions.act_window",
            "name": _("Factura"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
        }

