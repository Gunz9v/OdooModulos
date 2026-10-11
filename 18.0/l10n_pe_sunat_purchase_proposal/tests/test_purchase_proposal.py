from odoo.tests.common import TransactionCase

from odoo.addons.l10n_pe_sunat_purchase_proposal.models.utils import build_document_key
from odoo.addons.l10n_pe_sunat_purchase_proposal.wizards.proposal_parser import PurchaseProposalParser


class TestPurchaseProposal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        values = [""] * 41
        values[0:14] = [
            "20100080932",
            "EMPRESA",
            "202605",
            "CAR001",
            "04/05/2026",
            "03/06/2026",
            "01",
            "F250",
            "",
            "5699",
            "",
            "6",
            "20332839200",
            "FGA INGENIEROS SA",
        ]
        values[14] = "1866.38"
        values[15] = "335.94"
        values[24] = "2202.32"
        values[25] = "USD"
        values[26] = "3.521"
        values[39] = "1"
        cls.line = "|".join(values) + "|"

    def test_parser_reads_purchase_proposal(self):
        rows, issues = PurchaseProposalParser().parse(self.line.encode("utf-8"))
        self.assertFalse(issues)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["period"], "2026-05")
        self.assertEqual(rows[0]["normalized_key"], "20332839200|01|F250|5699")
        self.assertEqual(float(rows[0]["total_amount"]), 2202.32)

    def test_document_key_normalizes_number(self):
        self.assertEqual(
            build_document_key("20-332839200", "01", "f250", "00005699"),
            "20332839200|01|F250|5699",
        )
