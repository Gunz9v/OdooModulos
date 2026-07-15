import base64
import io
import zipfile
from decimal import Decimal

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_pe_sire_ple_import.models.rce_complement import (
    RceComplementFileNameBuilder,
    RceComplementFileType,
    RceComplementSerializer,
    RceComplementService,
)
from odoo.addons.l10n_pe_sire_ple_import.models.ple_parser import PleFileParser


class TestPleImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.vat = "20123456789"
        cls.filename = "LE2012345678920260500140100001111.txt"
        cls.line = (
            "20260500|CUO001|M0001|15/05/2026||01|f001|00001234| |6|"
            "10456789123|CLIENTE DEMO SAC|0.00|100.00|0.00|18.00|"
            "0.00|0.00|0.00|0.00|0.00|0.00|0.00|0.00|118.00|"
            "pen|3.700|01/01/0001|00|-|-||||1|"
        )
        cls.content = (cls.line + "\n").encode("latin-1")
        cls.sunat_header = (
            "Ruc|Razon Social|Periodo|CAR SUNAT|Fecha de emisión|Fecha Vcto/Pago|Tipo CP/Doc.|"
            "Serie del CDP|Nro CP o Doc. Nro Inicial (Rango)|Nro Final (Rango)|Tipo Doc Identidad|"
            "Nro Doc Identidad|Apellidos Nombres/ Razón Social|Valor Facturado Exportación|BI Gravada|"
            "Dscto BI|IGV / IPM|Dscto IGV / IPM|Mto Exonerado|Mto Inafecto|ISC|BI Grav IVAP|IVAP|"
            "ICBPER|Otros Tributos|Total CP|Moneda|Tipo Cambio|Fecha Emisión Doc Modificado|"
            "Tipo CP Modificado|Serie CP Modificado|Nro CP Modificado|ID Proyecto Operadores Atribución|"
            "Tipo de Nota|Est. Comp|Valor FOB Embarcado|Valor OP Gratuitas|Tipo Operación|DAM / CP|CLU"
        )
        cls.sunat_line = (
            "20100080932|YOHERSA YOSHIMOTO HERMANOS S.A.C.|202605|2010008093201F2500000005699|"
            "04/05/2026|03/06/2026|01|F250|5699||6|20332839200|FGA INGENIEROS SA|0|1866.38|"
            "0|335.94|0|0|0|0|0|0|0|0|2202.32|USD|3.521|||||||1|0|0|0101|||"
        )
        cls.sunat_content = ("%s\n%s\n" % (cls.sunat_header, cls.sunat_line)).encode("latin-1")

    def _ple_filename(self, year, month, ruc="20123456789"):
        return "LE%s%s%s00140100001111.txt" % (ruc, year, month)

    def _ple_content(self, year, month):
        return self.content.replace(b"20260500", ("%s%s00" % (year, month)).encode("ascii"))

    def _sunat_filename(self, year, month):
        return "LE20100080932%s%s00140400001EXP2.txt" % (year, month)

    def _sunat_content(self, year, month):
        return self.sunat_content.replace(b"|202605|", ("|%s%s|" % (year, month)).encode("ascii"))

    def test_parser_detects_name_encoding_and_normalizes_141(self):
        parsed = PleFileParser().parse(self.filename, self.content)

        self.assertEqual(parsed.filename_info.ruc, "20123456789")
        self.assertEqual(parsed.filename_info.period_code, "2026-05")
        self.assertEqual(parsed.filename_info.book_code, "140100")
        self.assertEqual(parsed.encoding, "utf-8-sig")
        self.assertEqual(len(parsed.lines), 1)
        normalized = parsed.lines[0].normalized
        self.assertEqual(normalized["series"], "F001")
        self.assertEqual(normalized["currency_code"], "PEN")
        self.assertEqual(normalized["taxable_base"], Decimal("100.00"))
        self.assertEqual(normalized["igv_amount"], Decimal("18.00"))
        self.assertEqual(normalized["total_amount"], Decimal("118.00"))
        self.assertFalse(normalized["original_document_date"])
        self.assertEqual(normalized["normalized_key"], "6|10456789123|01|F001|1234")

    def test_parser_accepts_filename_without_txt_extension(self):
        parsed = PleFileParser().parse("LE2010008093220260500140100001111", self.content)

        self.assertEqual(parsed.filename_info.ruc, "20100080932")
        self.assertEqual(parsed.filename_info.period_code, "2026-05")
        self.assertEqual(parsed.filename_info.book_code, "140100")

    def test_parser_accepts_sunat_proposal_book_140400(self):
        parsed = PleFileParser().parse("LE2010008093220260700140400001EXP2.txt", self.sunat_content)

        self.assertEqual(parsed.filename_info.ruc, "20100080932")
        self.assertEqual(parsed.filename_info.period_code, "2026-07")
        self.assertEqual(parsed.filename_info.book_code, "140400")
        self.assertEqual(len(parsed.lines), 1)
        normalized = parsed.lines[0].normalized
        self.assertEqual(normalized["car_sunat"], "2010008093201F2500000005699")
        self.assertEqual(normalized["series"], "F250")
        self.assertEqual(normalized["number"], "5699")
        self.assertEqual(normalized["taxable_base"], Decimal("1866.38"))
        self.assertEqual(normalized["igv_amount"], Decimal("335.94"))
        self.assertEqual(normalized["total_amount"], Decimal("2202.32"))
        self.assertEqual(normalized["normalized_key"], "6|20332839200|01|F250|5699")

    def test_normalized_key_ignores_document_number_leading_zeroes(self):
        sunat_content = (
            self.sunat_header
            + "\n"
            + "20100080932|YOHERSA YOSHIMOTO HERMANOS S.A.C.|202605|2010008093203B2510000084420|"
            + "28/05/2026||03|B251|84420||1|03370678|-|0|202.54|0|36.46|0|0|0|0|0|0|0|0|239|"
            + "PEN|1.000|||||||1|0|0|||\n"
        ).encode("latin-1")
        ple_content = (
            "20260500|1202605062055119|M055119|28/05/2026||03|B251|084420| |1|"
            "03370678|ISMAEL RAMIREZ PALACIOS|       0.00|     202.54|       0.00|"
            "      36.46|       0.00|       0.00|       0.00|       0.00|       0.00|"
            "       0.00|       0.00|       0.00|     239.00|PEN|1.000|01/01/0001|"
            "00|-|-||||1|\n"
        ).encode("latin-1")

        sunat = PleFileParser().parse("LE2010008093220260500140400001EXP2.txt", sunat_content)
        ple = PleFileParser().parse("LE2010008093220260500140100001111.txt", ple_content)

        self.assertEqual(sunat.valid_lines[0].normalized["number"], "84420")
        self.assertEqual(ple.valid_lines[0].normalized["number"], "084420")
        self.assertEqual(sunat.valid_lines[0].normalized["normalized_key"], "||03|B251|84420")
        self.assertEqual(ple.valid_lines[0].normalized["normalized_key"], "||03|B251|84420")

    def test_boleta_key_ignores_customer_identity_placeholders(self):
        sunat_content = (
            self.sunat_header
            + "\n"
            + "20100080932|YOHERSA YOSHIMOTO HERMANOS S.A.C.|202605|2010008093203B2510000084042|"
            + "07/05/2026||03|B251|84042||-|11111111|-|0|9.91|0|1.78|0|0|0|0|0|0|0|0|"
            + "11.69|PEN|1.000|||||||1|0|0|||\n"
        ).encode("latin-1")
        ple_content = (
            "20260500|1202605062052954|M052954|07/05/2026||03|B251|084042| |||CESAR|"
            "       0.00|       9.91|       0.00|       1.78|       0.00|       0.00|"
            "       0.00|       0.00|       0.00|       0.00|       0.00|       0.00|"
            "      11.69|PEN|1.000|01/01/0001|00|-|-||||1|\n"
        ).encode("latin-1")

        sunat = PleFileParser().parse("LE2010008093220260500140400001EXP2.txt", sunat_content)
        ple = PleFileParser().parse("LE2010008093220260500140100001111.txt", ple_content)

        self.assertEqual(sunat.valid_lines[0].normalized["normalized_key"], "||03|B251|84042")
        self.assertEqual(ple.valid_lines[0].normalized["normalized_key"], "||03|B251|84042")

    def test_cancelled_zero_amount_invoice_key_ignores_customer_identity(self):
        sunat_content = (
            self.sunat_header
            + "\n"
            + "20100080932||202605|2010008093201F2520000181211|13/05/2026||01|F252|181211|||||"
            + "0|0|0|0|0|0|0|0|0|0|0|0|0|||||||||2|0|0|||\n"
        ).encode("latin-1")
        ple_content = (
            "20260500|1202605062054179|M054179|13/05/2026||01|F252|181211| |6|"
            "20251433705|-|       0.00|       0.00|       0.00|       0.00|"
            "       0.00|       0.00|       0.00|       0.00|       0.00|"
            "       0.00|       0.00|       0.00|       0.00|PEN|1.000|01/01/0001|"
            "00|-|-||||2|\n"
        ).encode("latin-1")

        sunat = PleFileParser().parse("LE2010008093220260500140400001EXP2.txt", sunat_content)
        ple = PleFileParser().parse("LE2010008093220260500140100001111.txt", ple_content)

        self.assertEqual(sunat.valid_lines[0].normalized["normalized_key"], "||01|F252|181211")
        self.assertEqual(ple.valid_lines[0].normalized["normalized_key"], "||01|F252|181211")

    def test_sunat_proposal_reads_record_state_from_est_comp_column(self):
        sunat_content = (
            self.sunat_header
            + "\n"
            + "20100080932|YOHERSA YOSHIMOTO HERMANOS S.A.C.|202605|2010008093201F4520000076692|"
            + "14/05/2026|15/05/2026|01|F452|76692||6|20221368283|EMPRESA MINERA EMILIO MIGUEL "
            + "SOCIEDAD COMERCIAL DE RESPONSABILIDAD LIMITADA|0|0|0|0|0|0|0|0|0|0|0|0|0|PEN|"
            + "0.000|||||||2|0|0|0101||\n"
        ).encode("latin-1")
        ple_content = (
            "20260500|1202605062054829|M054829|14/05/2026||01|F452|076692| |6|"
            "20221368283|-|       0.00|       0.00|       0.00|       0.00|"
            "       0.00|       0.00|       0.00|       0.00|       0.00|"
            "       0.00|       0.00|       0.00|       0.00|PEN|1.000|01/01/0001|"
            "00|-|-||||2|\n"
        ).encode("latin-1")

        sunat = PleFileParser().parse("LE2010008093220260500140400001EXP2.txt", sunat_content)
        ple = PleFileParser().parse("LE2010008093220260500140100001111.txt", ple_content)

        self.assertEqual(sunat.valid_lines[0].normalized["record_state"], "2")
        self.assertEqual(sunat.valid_lines[0].normalized["normalized_key"], "||01|F452|76692")
        self.assertEqual(ple.valid_lines[0].normalized["normalized_key"], "||01|F452|76692")

    def test_reconciliation_ignores_free_boleta_reference_igv(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "04",
            }
        )
        accounting_batch = self.env["sire.import.batch"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "filename": "accounting-free-boleta.txt",
                "file_data": base64.b64encode(b"accounting-free-boleta"),
                "file_hash": "accounting-free-boleta",
                "book_code": "140100",
                "state": "imported",
            }
        )
        sunat_batch = self.env["sire.import.batch"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "filename": "sunat-free-boleta.txt",
                "file_data": base64.b64encode(b"sunat-free-boleta"),
                "file_hash": "sunat-free-boleta",
                "book_code": "140400",
                "state": "imported",
            }
        )
        self.env["sire.sales.accounting.line"].create(
            {
                "period_id": period.id,
                "batch_id": accounting_batch.id,
                "source_line_number": 1,
                "source_raw_text": "PLE free boleta",
                "validation_state": "valid",
                "issue_date": "2026-05-12",
                "document_type": "03",
                "series": "B251",
                "number": "084145",
                "customer_name": "ATENCION A PERSONAL",
                "currency_code": "PEN",
                "exchange_rate": 1.0,
                "taxable_base": 0.0,
                "igv_amount": 67.36,
                "total_amount": 0.0,
            }
        )
        self.env["sire.sales.sunat.line"].create(
            {
                "period_id": period.id,
                "batch_id": sunat_batch.id,
                "source_line_number": 1,
                "source_raw_text": "SUNAT free boleta",
                "validation_state": "valid",
                "issue_date": "2026-05-12",
                "document_type": "03",
                "series": "B251",
                "number": "84145",
                "customer_document_type": "-",
                "customer_document_number": "11111111",
                "customer_name": "-",
                "currency_code": "PEN",
                "exchange_rate": 1.0,
                "taxable_base": 0.0,
                "igv_amount": 0.0,
                "total_amount": 0.0,
            }
        )

        period.action_run_sales_reconciliation()
        reconciliation = self.env["sire.sales.reconciliation.line"].search([("period_id", "=", period.id)])

        self.assertEqual(len(reconciliation), 1)
        self.assertEqual(reconciliation.status, "matched")
        self.assertFalse(reconciliation.igv_has_diff)
        self.assertEqual(reconciliation.igv_diff, 0.0)
        self.assertEqual(period.matched_count, 1)

    def test_reconciliation_matches_cancelled_zero_amount_invoice_without_customer_on_sunat(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "05",
            }
        )
        accounting_batch = self.env["sire.import.batch"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "filename": "accounting-cancelled-invoice.txt",
                "file_data": base64.b64encode(b"accounting-cancelled-invoice"),
                "file_hash": "accounting-cancelled-invoice",
                "book_code": "140100",
                "state": "imported",
            }
        )
        sunat_batch = self.env["sire.import.batch"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "filename": "sunat-cancelled-invoice.txt",
                "file_data": base64.b64encode(b"sunat-cancelled-invoice"),
                "file_hash": "sunat-cancelled-invoice",
                "book_code": "140400",
                "state": "imported",
            }
        )
        self.env["sire.sales.accounting.line"].create(
            {
                "period_id": period.id,
                "batch_id": accounting_batch.id,
                "source_line_number": 1,
                "source_raw_text": "PLE cancelled invoice",
                "validation_state": "valid",
                "issue_date": "2026-05-13",
                "document_type": "01",
                "series": "F252",
                "number": "181211",
                "customer_document_type": "6",
                "customer_document_number": "20251433705",
                "customer_name": "-",
                "currency_code": "PEN",
                "exchange_rate": 1.0,
                "total_amount": 0.0,
                "record_state": "2",
            }
        )
        self.env["sire.sales.sunat.line"].create(
            {
                "period_id": period.id,
                "batch_id": sunat_batch.id,
                "source_line_number": 1,
                "source_raw_text": (
                    "20100080932||202605|2010008093201F2520000181211|13/05/2026||01|F252|"
                    "181211|||||0|0|0|0|0|0|0|0|0|0|0|0|0|||||||||2|0|0|||"
                ),
                "validation_state": "valid",
                "issue_date": "2026-05-13",
                "document_type": "01",
                "series": "F252",
                "number": "181211",
                "currency_code": "",
                "total_amount": 0.0,
                "record_state": "0",
            }
        )

        period.action_run_sales_reconciliation()
        reconciliation = self.env["sire.sales.reconciliation.line"].search([("period_id", "=", period.id)])

        self.assertEqual(len(reconciliation), 1)
        self.assertEqual(reconciliation.status, "matched")
        self.assertEqual(reconciliation.sunat_line_id.record_state, "2")
        self.assertFalse(reconciliation.sunat_line_id.customer_document_number)
        self.assertEqual(period.sunat_only_count, 0)
        self.assertEqual(period.system_only_count, 0)

    def test_sunat_credit_note_uses_discount_columns_as_negative_amounts(self):
        sunat_content = (
            self.sunat_header
            + "\n"
            + "20100080932|YOHERSA YOSHIMOTO HERMANOS S.A.C.|202605|2010008093207B3580000000058|"
            + "05/05/2026||07|B358|58||1|44217879|-|0|0|-176.99|0|-31.85|0|0|0|0|0|0|0|"
            + "-208.84|PEN|1.000|11/02/2026|03|B351|21097|||1|0|0|||\n"
        ).encode("latin-1")
        ple_content = (
            "20260500|1202605062053485|M053485|05/05/2026||07|B358|000058| |1|"
            "44217879|SAMUEL ABAT ALHUA|       0.00|    -176.99|       0.00|"
            "     -31.85|       0.00|       0.00|       0.00|       0.00|       0.00|"
            "       0.00|       0.00|       0.00|    -208.84|PEN|1.000|11/02/2026|"
            "03|B351|021097||||1|\n"
        ).encode("latin-1")

        sunat = PleFileParser().parse("LE2010008093220260500140400001EXP2.txt", sunat_content)
        ple = PleFileParser().parse("LE2010008093220260500140100001111.txt", ple_content)

        self.assertEqual(sunat.valid_lines[0].normalized["normalized_key"], "1|44217879|07|B358|58")
        self.assertEqual(ple.valid_lines[0].normalized["normalized_key"], "1|44217879|07|B358|58")
        self.assertEqual(sunat.valid_lines[0].normalized["taxable_base"], Decimal("-176.99"))
        self.assertEqual(sunat.valid_lines[0].normalized["igv_amount"], Decimal("-31.85"))
        self.assertEqual(sunat.valid_lines[0].normalized["total_amount"], Decimal("-208.84"))
        self.assertEqual(sunat.valid_lines[0].normalized["taxable_base"], ple.valid_lines[0].normalized["taxable_base"])
        self.assertEqual(sunat.valid_lines[0].normalized["igv_amount"], ple.valid_lines[0].normalized["igv_amount"])
        self.assertEqual(sunat.valid_lines[0].normalized["total_amount"], ple.valid_lines[0].normalized["total_amount"])

    def test_wizard_imports_141_and_preserves_traceability(self):
        content = self._ple_content("2098", "01")
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "01",
            }
        )
        wizard = self.env["sire.ple.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": self._ple_filename("2098", "01"),
                "file_data": base64.b64encode(content),
            }
        )

        action = wizard.action_import_file()
        batch = self.env["sire.import.batch"].browse(action["res_id"])
        line = self.env["sire.sales.accounting.line"].search([("batch_id", "=", batch.id)])

        self.assertEqual(batch.total_rows, 1)
        self.assertEqual(batch.valid_rows, 1)
        self.assertEqual(batch.book_code, "140100")
        self.assertEqual(batch.file_data, base64.b64encode(content))
        self.assertEqual(period.state, "file_imported")
        self.assertEqual(period.total_accounting_records, 1)
        self.assertTrue(line.source_raw_text.startswith("20980100|"))
        self.assertEqual(line.series, "F001")
        self.assertEqual(line.total_amount, 118.00)

    def test_import_requires_deleting_existing_accounting_batch_before_reimport(self):
        content = self._ple_content("2098", "11")
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "11",
            }
        )
        first_wizard = self.env["sire.ple.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": self._ple_filename("2098", "11"),
                "file_data": base64.b64encode(content),
            }
        )
        first_action = first_wizard.action_import_file()

        second_wizard = self.env["sire.ple.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": self._ple_filename("2098", "11"),
                "file_data": base64.b64encode(content),
            }
        )
        with self.assertRaises(UserError):
            second_wizard.action_import_file()

        batch = self.env["sire.import.batch"].browse(first_action["res_id"])
        batch.action_delete_import_batch()

        self.assertFalse(period.accounting_batch_id)
        self.assertEqual(period.total_accounting_records, 0)
        self.assertEqual(period.state, "draft")
        self.assertFalse(self.env["sire.sales.accounting.line"].search([("period_id", "=", period.id)]))

        third_wizard = self.env["sire.ple.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": self._ple_filename("2098", "11"),
                "file_data": base64.b64encode(content),
            }
        )
        third_action = third_wizard.action_import_file()
        self.assertTrue(third_action["res_id"])

    def test_wizard_does_not_require_company_ruc_match(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "02",
            }
        )
        wizard = self.env["sire.ple.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": self._ple_filename("2098", "02", ruc="20100080932"),
                "file_data": base64.b64encode(self._ple_content("2098", "02")),
            }
        )

        action = wizard.action_import_file()

        self.assertTrue(action["res_id"])

    def test_accounting_import_rejects_file_from_other_period(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "04",
            }
        )
        wizard = self.env["sire.ple.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": self.filename,
                "file_data": base64.b64encode(self.content),
            }
        )

        with self.assertRaises(UserError):
            wizard.action_import_file()

    def test_sunat_proposal_wizard_imports_zip(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "03",
            }
        )
        txt_name = self._sunat_filename("2098", "03")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(txt_name, self._sunat_content("2098", "03"))
        zip_content = zip_buffer.getvalue()
        wizard = self.env["sire.sunat.proposal.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": "LE2010008093220980300140400001EXP2.zip",
                "file_data": base64.b64encode(zip_content),
            }
        )

        action = wizard.action_import_file()
        proposal = self.env["sire.sunat.proposal"].browse(action["res_id"])
        line = self.env["sire.sales.sunat.line"].search([("proposal_id", "=", proposal.id)])

        self.assertEqual(proposal.state, "parsed")
        self.assertEqual(proposal.record_count, 1)
        self.assertEqual(period.sunat_proposal_id, proposal)
        self.assertEqual(period.total_sunat_records, 1)
        self.assertEqual(line.car_sunat, "2010008093201F2500000005699")
        self.assertEqual(line.series, "F250")
        self.assertEqual(line.total_amount, 2202.32)

    def test_sunat_proposal_import_rejects_content_from_other_period_even_with_generated_zip_name(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "06",
            }
        )
        txt_name = self._sunat_filename("2098", "12")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(txt_name, self._sunat_content("2098", "12"))
        wizard = self.env["sire.sunat.proposal.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": "20100080932-20260710-111148-propuesta.zip",
                "file_data": base64.b64encode(zip_buffer.getvalue()),
            }
        )

        with self.assertRaises(UserError):
            wizard.action_import_file()

    def test_sunat_proposal_import_uses_content_period_over_generated_filename(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "06",
            }
        )
        txt_name = self._sunat_filename("2098", "07")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(txt_name, self._sunat_content("2098", "06"))
        wizard = self.env["sire.sunat.proposal.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": "20100080932-20980710-111148-propuesta.zip",
                "file_data": base64.b64encode(zip_buffer.getvalue()),
            }
        )

        action = wizard.action_import_file()

        proposal = self.env["sire.sunat.proposal"].browse(action["res_id"])
        self.assertEqual(proposal.period_id, period)
        self.assertEqual(period.total_sunat_records, 1)

    def test_delete_sunat_import_clears_proposal_lines_and_reconciliation(self):
        period = self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2098,
                "month": "12",
            }
        )
        txt_name = self._sunat_filename("2098", "12")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(txt_name, self._sunat_content("2098", "12"))
        zip_content = zip_buffer.getvalue()
        wizard = self.env["sire.sunat.proposal.import.wizard"].create(
            {
                "period_id": period.id,
                "filename": "LE2010008093220981200140400001EXP2.zip",
                "file_data": base64.b64encode(zip_content),
            }
        )
        wizard.action_import_file()
        batch = self.env["sire.import.batch"].search(
            [("period_id", "=", period.id), ("line_model", "=", "sire.sales.sunat.line")],
            limit=1,
        )
        self.env["sire.sales.reconciliation.line"].create(
            {
                "period_id": period.id,
                "status": "sunat_only",
                "normalized_key": "sunat-only",
            }
        )
        period.write(
            {
                "matched_count": 1,
                "sire_replace_zip_filename": "dummy.zip",
                "sire_replace_zip": base64.b64encode(b"dummy"),
            }
        )

        with self.assertRaises(UserError):
            self.env["sire.sunat.proposal.import.wizard"].create(
                {
                    "period_id": period.id,
                    "filename": "LE2010008093220981200140400001EXP2-v2.zip",
                    "file_data": base64.b64encode(zip_content),
                }
            ).action_import_file()

        batch.action_delete_import_batch()

        self.assertFalse(period.sunat_proposal_id)
        self.assertEqual(period.total_sunat_records, 0)
        self.assertEqual(period.matched_count, 0)
        self.assertFalse(period.sire_replace_zip)
        self.assertFalse(self.env["sire.sales.sunat.line"].search([("period_id", "=", period.id)]))
        self.assertFalse(self.env["sire.sales.reconciliation.line"].search([("period_id", "=", period.id)]))

    def test_invalid_column_count_records_line_error(self):
        parsed = PleFileParser().parse(self.filename, b"20260500|CUO001|M0001|\n")

        self.assertEqual(len(parsed.lines), 1)
        self.assertTrue(parsed.lines[0].has_errors)
        self.assertEqual(parsed.issues[0].code, "column_count")

    def _create_rvie_generation_period(self):
        self.company.vat = "20100080932"
        self.company.name = "YOHERSA YOSHIMOTO HERMANOS S.A.C."
        return self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rvie",
                "year": 2026,
                "month": "05",
            }
        )

    def _create_rvie_generation_line(self, period, source_values):
        batch = self.env["sire.import.batch"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "filename": "LE2010008093220260500140100001111.txt",
                "file_data": base64.b64encode(b"data"),
                "file_hash": "%s-%s" % (period.id, source_values[5]),
                "book_code": "140100",
                "format_version": "14.1",
            }
        )
        return self.env["sire.sales.accounting.line"].create(
            {
                "period_id": period.id,
                "batch_id": batch.id,
                "source_line_number": 1,
                "source_raw_text": "|".join(source_values) + "|",
            }
        )

    def _rvie_source_values(self, document_type="01", modified=None, clu_values=None):
        values = [
            "20260500",
            "CUO001",
            "M0001",
            "15/05/2026",
            "",
            document_type,
            "F001" if document_type != "03" else "B001",
            "00001234",
            "",
            "6",
            "10456789123",
            "CLIENTE DEMO SAC",
            "0.00",
            "100.00",
            "0.00",
            "18.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "118.00",
            "PEN",
            "1.000",
            "01/01/0001",
            "00",
            "-",
            "-",
            "",
            "",
            "",
            "1",
        ]
        if modified:
            values[27:31] = modified
        if clu_values:
            values.extend(clu_values)
        return values

    def _create_rce_generation_period(self):
        self.company.vat = "20100080932"
        self.company.name = "YOHERSA YOSHIMOTO HERMANOS S.A.C."
        return self.env["sire.period"].create(
            {
                "company_id": self.company.id,
                "registry_type": "rce",
                "year": 2026,
                "month": "05",
            }
        )

    def _create_rce_generation_line(self, period, clu_values=None, overrides=None):
        values = [
            "20260500",
            "CUO001",
            "M0001",
            "24/04/2026",
            "11/05/2026",
            "14",
            "S107",
            "0",
            "6572147",
            "",
            "6",
            "20100152356",
            "SERV AGUA POTAB Y ALCANT DE LIMA-SEDAPAL",
            "6.30",
            "1.13",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "-0.03",
            "0.00",
            "0.00",
            "0.00",
            "7.40",
            "PEN",
            "0.000",
            "01/01/0001",
            "00",
            "-",
            "",
            "-",
            "01/01/0001",
            "0",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "6",
        ]
        while len(values) < 42:
            values.append("")
        if overrides:
            for index, value in overrides.items():
                values[index] = value
        if clu_values:
            values.extend(clu_values)
        batch = self.env["sire.import.batch"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "filename": "LE2010008093220260500080100001111.txt",
                "file_data": base64.b64encode(b"data"),
                "file_hash": "%s-rce" % period.id,
                "book_code": "080100",
                "format_version": "8.1",
            }
        )
        return self.env["sire.purchase.accounting.line"].create(
            {
                "period_id": period.id,
                "batch_id": batch.id,
                "source_line_number": 1,
                "source_raw_text": "|".join(values) + "|",
            }
        )

    def _logical_fields(self, line_text):
        fields = line_text.split("|")
        if fields and fields[-1] == "":
            fields = fields[:-1]
        return fields

    def test_rvie_replacement_invoice_without_clu_has_33_fields_and_no_modified_document(self):
        period = self._create_rvie_generation_period()
        line = self._create_rvie_generation_line(period, self._rvie_source_values("01"))

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(len(fields), 33)
        self.assertEqual(fields[1], "YOHERSA YOSHIMOTO HERMANOS S.A.C.")
        self.assertEqual(fields[27], "")
        self.assertEqual(fields[28:32], ["", "", "", ""])

    def test_rvie_replacement_receipt_without_clu_has_33_fields_and_no_modified_document(self):
        period = self._create_rvie_generation_period()
        line = self._create_rvie_generation_line(period, self._rvie_source_values("03"))

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(len(fields), 33)
        self.assertEqual(fields[28:32], ["", "", "", ""])

    def test_rvie_replacement_credit_note_keeps_modified_document_fields(self):
        period = self._create_rvie_generation_period()
        modified = ["11/02/2026", "03", "B351", "21097"]
        line = self._create_rvie_generation_line(
            period,
            self._rvie_source_values("07", modified=modified),
        )

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(len(fields), 33)
        self.assertEqual(fields[28:32], modified)

    def test_rvie_replacement_credit_note_for_previous_period_receipt_uses_discount_columns(self):
        period = self._create_rvie_generation_period()
        values = self._rvie_source_values(
            "07",
            modified=["11/02/2026", "03", "B351", "21097"],
        )
        values[13] = "-176.99"
        values[14] = "0.00"
        values[15] = "-31.85"
        values[16] = "0.00"
        line = self._create_rvie_generation_line(period, values)

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(fields[14:18], ["0.00", "-176.99", "0.00", "-31.85"])

    def test_rvie_replacement_credit_note_for_current_period_receipt_has_zero_tax_fields(self):
        period = self._create_rvie_generation_period()
        values = self._rvie_source_values(
            "07",
            modified=["16/05/2026", "03", "B351", "21573"],
        )
        values[13] = "-28.96"
        values[14] = "0.00"
        values[15] = "-5.21"
        values[16] = "0.00"
        line = self._create_rvie_generation_line(period, values)

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(fields[14:18], ["0.00", "0.00", "0.00", "0.00"])

    def test_rvie_replacement_credit_note_for_previous_period_invoice_has_zero_tax_fields(self):
        period = self._create_rvie_generation_period()
        values = self._rvie_source_values(
            "07",
            modified=["28/04/2026", "01", "F352", "104346"],
        )
        values[13] = "-386.66"
        values[14] = "0.00"
        values[15] = "-69.60"
        values[16] = "0.00"
        line = self._create_rvie_generation_line(period, values)

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(fields[14:18], ["0.00", "0.00", "0.00", "0.00"])

    def test_rvie_replacement_with_only_clu_41_has_34_fields(self):
        period = self._create_rvie_generation_period()
        line = self._create_rvie_generation_line(
            period,
            self._rvie_source_values("01", clu_values=["CLU41"]),
        )

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(len(fields), 34)
        self.assertEqual(fields[33], "CLU41")

    def test_rvie_replacement_with_later_clu_keeps_intermediate_empty_clu_only(self):
        period = self._create_rvie_generation_period()
        line = self._create_rvie_generation_line(
            period,
            self._rvie_source_values("01", clu_values=["", "", "CLU43", "", ""]),
        )

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertEqual(len(fields), 36)
        self.assertEqual(fields[33:36], ["", "", "CLU43"])

    def test_rvie_replacement_never_outputs_fields_34_to_40_gap(self):
        period = self._create_rvie_generation_period()
        line = self._create_rvie_generation_line(
            period,
            self._rvie_source_values("01", clu_values=["CLU41"]),
        )

        fields = self._logical_fields(period._build_rvie_replacement_line_text(line))

        self.assertNotEqual(len(fields), 57)
        self.assertEqual(fields[33], "CLU41")

    def test_rce_replacement_filename_uses_080400_and_uppercase_extension(self):
        period = self._create_rce_generation_period()

        self.assertEqual(
            period._build_sire_replacement_filename("TXT", decision_key="replace"),
            "LE2010008093220260500080400021112.TXT",
        )
        self.assertEqual(
            period._build_sire_replacement_filename("ZIP", decision_key="replace"),
            "LE2010008093220260500080400021112.ZIP",
        )
        self.assertEqual(
            period._build_sire_replacement_filename("", decision_key="replace"),
            "LE2010008093220260500080400021112",
        )

    def test_rce_replacement_line_uses_purchase_structure_not_rvie(self):
        period = self._create_rce_generation_period()
        line = self._create_rce_generation_line(period)

        fields = self._logical_fields(period._build_rce_replacement_line_text(line))

        self.assertEqual(len(fields), 41)
        self.assertEqual(fields[0], "20100080932")
        self.assertEqual(fields[2], "202605")
        self.assertEqual(fields[6], "14")
        self.assertEqual(fields[8], "")
        self.assertEqual(fields[11], "6")
        self.assertEqual(fields[12], "20100152356")
        self.assertEqual(fields[24], "7.40")
        self.assertEqual(fields[26], "")
        self.assertEqual(fields[27:32], ["", "", "", "", ""])
        self.assertEqual(fields[32], "")
        self.assertEqual(fields[36:41], ["", "", "", "", ""])

    def test_rce_replacement_normalizes_series(self):
        period = self._create_rce_generation_period()
        line = self._create_rce_generation_line(period, overrides={6: "s114"})

        fields = self._logical_fields(period._build_rce_replacement_line_text(line))

        self.assertEqual(fields[7], "S114")

    def test_rce_replacement_clears_dash_series(self):
        period = self._create_rce_generation_period()
        line = self._create_rce_generation_line(period, overrides={5: "27", 6: "-"})

        fields = self._logical_fields(period._build_rce_replacement_line_text(line))

        self.assertEqual(fields[7], "")

    def test_rce_replacement_non_credit_document_moves_amounts_to_clu(self):
        period = self._create_rce_generation_period()
        line = self._create_rce_generation_line(
            period,
            overrides={5: "02", 13: "0.00", 14: "0.00", 23: "10566.00", 24: "USD", 25: "3.522"},
        )

        fields = self._logical_fields(period._build_rce_replacement_line_text(line))

        self.assertEqual(fields[14:25], [""] * 11)
        self.assertEqual(fields[25], "USD")
        self.assertEqual(fields[26], "3.522")
        self.assertEqual(fields[41:52], ["0.00", "0.00", "0.00", "0.00", "0.00", "0.00", "-0.03", "0.00", "0.00", "0.00", "10566.00"])

    def test_rce_replacement_with_only_clu_42_has_42_fields(self):
        period = self._create_rce_generation_period()
        line = self._create_rce_generation_line(period, clu_values=["CLU42"])

        fields = self._logical_fields(period._build_rce_replacement_line_text(line))

        self.assertEqual(len(fields), 42)
        self.assertEqual(fields[41], "CLU42")

    def test_rce_replacement_with_later_clu_keeps_intermediate_empty_clu_only(self):
        period = self._create_rce_generation_period()
        line = self._create_rce_generation_line(period, clu_values=["", "", "CLU44", "", ""])

        fields = self._logical_fields(period._build_rce_replacement_line_text(line))

        self.assertEqual(len(fields), 44)
        self.assertEqual(fields[41:44], ["", "", "CLU44"])

    def test_rce_replacement_zip_contains_txt_with_same_base_name(self):
        period = self._create_rce_generation_period()
        line = self._create_rce_generation_line(period)

        payload = period._build_sire_zip_payload(line, "replace")
        zip_content = base64.b64decode(payload["zip_data"])
        with zipfile.ZipFile(io.BytesIO(zip_content)) as archive:
            names = archive.namelist()

        self.assertEqual(payload["zip_filename"], "LE2010008093220260500080400021112")
        self.assertEqual(payload["txt_filename"], "LE2010008093220260500080400021112.TXT")
        self.assertEqual(names, ["LE2010008093220260500080400021112.TXT"])

    def _rce_anexo8_base(self):
        return [
            "20100080932",
            "YOHERSA YOSHIMOTO HERMANOS S.A.C.",
            "202605",
            "",
            "15/05/2026",
            "",
            "01",
            "F001",
            "",
            "123",
            "",
            "6",
            "20100152356",
            "PROVEEDOR SAC",
            "100.00",
            "18.00",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "118.00",
            "PEN",
            "",
            "",
            "",
            "",
            "",
            "",
            "1",
            "",
            "",
            "",
            "",
        ]

    def test_rce_complement_names(self):
        self.assertEqual(
            RceComplementFileNameBuilder.build(RceComplementFileType.CP, "20100080932", "202605", 1),
            "20100080932-CP-202605-01.txt",
        )
        self.assertEqual(
            RceComplementFileNameBuilder.build(RceComplementFileType.RCECOM, "20100080932", "202605", 1),
            "20100080932-RCECOM-202605-01.txt",
        )
        self.assertEqual(
            RceComplementFileNameBuilder.build(RceComplementFileType.RCEINEX, "20100080932", "202605", 1),
            "20100080932-RCEINEX-202605-01.txt",
        )
        self.assertEqual(
            RceComplementFileNameBuilder.build(RceComplementFileType.RCETCA, "20100080932", "202605", 1),
            "20100080932-RCETCA-202605-01.txt",
        )

    def test_rce_complement_name_validations(self):
        with self.assertRaises(UserError):
            RceComplementFileNameBuilder.build(RceComplementFileType.CP, "201", "202605", 1)
        with self.assertRaises(UserError):
            RceComplementFileNameBuilder.build(RceComplementFileType.CP, "20100080932", "202613", 1)
        with self.assertRaises(UserError):
            RceComplementFileNameBuilder.build(RceComplementFileType.CP, "20100080932", "202605", 100)

    def test_rce_anexo8_without_clu_has_37_physical_fields(self):
        line = RceComplementSerializer.serialize_anexo8(self._rce_anexo8_base())

        fields = self._logical_fields(line)

        self.assertEqual(len(fields), 37)
        self.assertEqual(line.count("|"), 37)

    def test_rce_anexo8_with_clu42_has_38_physical_fields(self):
        line = RceComplementSerializer.serialize_anexo8(self._rce_anexo8_base(), ["CLU42"])

        fields = self._logical_fields(line)

        self.assertEqual(len(fields), 38)
        self.assertEqual(fields[37], "CLU42")

    def test_rce_anexo8_with_clu45_keeps_intermediate_empty_fields(self):
        line = RceComplementSerializer.serialize_anexo8(self._rce_anexo8_base(), ["", "", "", "CLU45", ""])

        fields = self._logical_fields(line)

        self.assertEqual(len(fields), 41)
        self.assertEqual(fields[37:41], ["", "", "", "CLU45"])

    def test_rce_anexo8_with_all_clu_has_76_fields(self):
        line = RceComplementSerializer.serialize_anexo8(self._rce_anexo8_base(), ["X%s" % index for index in range(39)])

        fields = self._logical_fields(line)

        self.assertEqual(len(fields), 76)

    def test_rce_cp_payload_uses_anexo8_and_validates_notes(self):
        service = RceComplementService("20100080932", "202605", 1)
        row = self._rce_anexo8_base()

        payload = service.generate_cp([row])
        fields = self._logical_fields(payload["content"].splitlines()[0])

        self.assertEqual(payload["filename"], "20100080932-CP-202605-01.txt")
        self.assertEqual(fields[0:4], ["20100080932", "YOHERSA YOSHIMOTO HERMANOS S.A.C.", "202605", ""])
        self.assertEqual(fields[27:32], ["", "", "", "", ""])
        self.assertEqual(fields[36], "")

    def test_rce_cp_credit_note_allows_modified_document_fields(self):
        service = RceComplementService("20100080932", "202605", 1)
        row = self._rce_anexo8_base()
        row[6] = "07"
        row[27:32] = ["01/04/2026", "01", "F001", "", "123"]

        payload = service.generate_cp([row])
        fields = self._logical_fields(payload["content"].splitlines()[0])

        self.assertEqual(fields[27:32], ["01/04/2026", "01", "F001", "", "123"])

    def test_rce_cp_rejects_forbidden_type_and_duplicates(self):
        service = RceComplementService("20100080932", "202605", 1)
        row = self._rce_anexo8_base()
        row[6] = "91"
        with self.assertRaises(UserError):
            service.generate_cp([row])

        first = self._rce_anexo8_base()
        second = list(first)
        with self.assertRaises(UserError):
            service.generate_cp([first, second])

    def test_rcecom_only_uses_car_and_complementable_fields(self):
        service = RceComplementService("20100080932", "202605", 1)
        row = [""] * 37
        row[3] = "A12345678901234567890123456"
        row[32] = "1"

        payload = service.generate_rcecom([row])
        fields = self._logical_fields(payload["content"].splitlines()[0])

        self.assertEqual(payload["filename"], "20100080932-RCECOM-202605-01.txt")
        self.assertEqual(fields[0:3], ["", "", ""])
        self.assertEqual(fields[3], "A12345678901234567890123456")
        self.assertEqual(fields[4:14], [""] * 10)
        self.assertEqual(fields[32], "1")
        self.assertEqual(fields[36], "")

    def test_rcecom_accepts_car_with_letter_e_without_scientific_notation_error(self):
        service = RceComplementService("20100080932", "202605", 1)
        row = [""] * 37
        row[3] = "2010008093201E0010000001027"
        row[32] = "1"

        payload = service.generate_rcecom([row])
        fields = self._logical_fields(payload["content"].splitlines()[0])

        self.assertEqual(fields[3], "2010008093201E0010000001027")

    def test_rcecom_rejects_identifying_changes_and_car_only(self):
        service = RceComplementService("20100080932", "202605", 1)
        car_only = [""] * 37
        car_only[3] = "A12345678901234567890123456"
        with self.assertRaises(UserError):
            service.generate_rcecom([car_only])

        invalid = list(car_only)
        invalid[7] = "F001"
        invalid[32] = "1"
        with self.assertRaises(UserError):
            service.generate_rcecom([invalid])

    def test_rceinex_exclusion_and_inclusion_have_37_fields(self):
        service = RceComplementService("20100080932", "202605", 1)
        exclude = RceComplementSerializer.serialize_rceinex("A12345678901234567890123456", "1")
        include = RceComplementSerializer.serialize_rceinex("B12345678901234567890123456", "2")

        payload = service.generate_rceinex(
            [
                self._logical_fields(exclude),
                self._logical_fields(include),
            ]
        )
        first_fields = self._logical_fields(payload["content"].splitlines()[0])

        self.assertEqual(payload["filename"], "20100080932-RCEINEX-202605-01.txt")
        self.assertEqual(len(first_fields), 37)
        self.assertEqual(first_fields[3], "A12345678901234567890123456")
        self.assertEqual(first_fields[36], "1")
        self.assertFalse(any(first_fields[index] for index in range(37) if index not in (3, 36)))

    def test_rceinex_rejects_invalid_indicator_car_and_note_exclusion(self):
        service = RceComplementService("20100080932", "202605", 1)
        invalid_indicator = [""] * 37
        invalid_indicator[3] = "A12345678901234567890123456"
        invalid_indicator[36] = "3"
        with self.assertRaises(UserError):
            service.generate_rceinex([invalid_indicator])

        invalid_car = [""] * 37
        invalid_car[3] = "123"
        invalid_car[36] = "1"
        with self.assertRaises(UserError):
            service.generate_rceinex([invalid_car])

        note_exclusion = [""] * 37
        note_exclusion[3] = "A12345678901234567890123456"
        note_exclusion[36] = "1"
        with self.assertRaises(UserError):
            service.generate_rceinex([note_exclusion], document_types={"A12345678901234567890123456": "07"})

    def test_period_rceinex_generation_skips_sunat_only_credit_notes(self):
        period = self._create_rce_generation_period()
        batch = self.env["sire.import.batch"].create(
            {
                "company_id": self.company.id,
                "period_id": period.id,
                "filename": "LE201000809322026070008040001EXP2.txt",
                "file_data": base64.b64encode(b"data"),
                "file_hash": "%s-rce-sunat" % period.id,
                "book_code": "080400",
                "format_version": "rce",
            }
        )
        credit_note = self.env["sire.purchase.sunat.line"].create(
            {
                "period_id": period.id,
                "batch_id": batch.id,
                "source_line_number": 1,
                "source_raw_text": "raw",
                "car_sunat": "A12345678901234567890123456",
                "document_type": "07",
            }
        )
        invoice = self.env["sire.purchase.sunat.line"].create(
            {
                "period_id": period.id,
                "batch_id": batch.id,
                "source_line_number": 2,
                "source_raw_text": "raw",
                "car_sunat": "B12345678901234567890123456",
                "document_type": "01",
            }
        )
        self.env["sire.purchase.reconciliation.line"].create(
            {
                "period_id": period.id,
                "sunat_line_id": credit_note.id,
                "status": "sunat_only",
                "normalized_key": "credit-note",
            }
        )
        self.env["sire.purchase.reconciliation.line"].create(
            {
                "period_id": period.id,
                "sunat_line_id": invoice.id,
                "status": "sunat_only",
                "normalized_key": "invoice",
            }
        )

        rows, document_types = period._get_rceinex_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], "B12345678901234567890123456")
        self.assertEqual(document_types, {"B12345678901234567890123456": "01"})

    def test_period_cp_generation_skips_duplicate_system_only_documents(self):
        period = self._create_rce_generation_period()
        first_line = self._create_rce_generation_line(period)
        second_line = self.env["sire.purchase.accounting.line"].create(
            {
                "period_id": period.id,
                "batch_id": first_line.batch_id.id,
                "source_line_number": first_line.source_line_number + 1,
                "source_raw_text": first_line.source_raw_text,
            }
        )
        self.env["sire.purchase.reconciliation.line"].create(
            {
                "period_id": period.id,
                "accounting_line_id": first_line.id,
                "status": "system_only",
                "normalized_key": "duplicate-1",
            }
        )
        self.env["sire.purchase.reconciliation.line"].create(
            {
                "period_id": period.id,
                "accounting_line_id": second_line.id,
                "status": "system_only",
                "normalized_key": "duplicate-2",
            }
        )

        rows, duplicates = period._get_rce_cp_rows_and_duplicates()
        summary = period._build_rce_cp_duplicate_summary(duplicates)

        self.assertEqual(len(rows), 1)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual((rows[0][12], rows[0][6], rows[0][7], rows[0][9]), ("20100152356", "14", "S107", "6572147"))
        self.assertIn("Linea 2 duplicada de linea 1", summary)
        self.assertIn("proveedor 20100152356", summary)

    def test_rcetca_for_soles_keeps_five_fields_with_empty_field_5(self):
        service = RceComplementService("20100080932", "202605", 1)

        payload = service.generate_rcetca(
            [{"period": "202605", "issue_date": "15/05/2026", "currency": "EUR", "exchange_rate_pen": "3.842"}]
        )
        fields = self._logical_fields(payload["content"].splitlines()[0])

        self.assertEqual(payload["filename"], "20100080932-RCETCA-202605-01.txt")
        self.assertEqual(fields, ["202605", "15/05/2026", "EUR", "3.842", ""])

    def test_rcetca_for_foreign_accounting_requires_field_5(self):
        service = RceComplementService("20100080932", "202605", 1)

        payload = service.generate_rcetca(
            [
                {
                    "period": "202605",
                    "issue_date": "15/05/2026",
                    "currency": "EUR",
                    "exchange_rate_pen": "3.842",
                    "exchange_rate_usd": "0.267",
                }
            ],
            accounting_in_foreign_currency=True,
        )
        fields = self._logical_fields(payload["content"].splitlines()[0])

        self.assertEqual(fields, ["202605", "15/05/2026", "EUR", "3.842", "0.267"])

    def test_rcetca_rejects_invalid_values_and_duplicates(self):
        service = RceComplementService("20100080932", "202605", 1)
        with self.assertRaises(UserError):
            service.generate_rcetca(
                [{"period": "202605", "issue_date": "15/05/2026", "currency": "EU", "exchange_rate_pen": "3.842"}]
            )
        with self.assertRaises(UserError):
            service.generate_rcetca(
                [{"period": "202605", "issue_date": "15/05/2026", "currency": "EUR", "exchange_rate_pen": "0"}]
            )
        with self.assertRaises(UserError):
            service.generate_rcetca(
                [
                    {"period": "202605", "issue_date": "15/05/2026", "currency": "EUR", "exchange_rate_pen": "3.842"},
                    {"period": "202605", "issue_date": "15/05/2026", "currency": "EUR", "exchange_rate_pen": "3.843"},
                ]
            )
