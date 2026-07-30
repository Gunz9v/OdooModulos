import hashlib
import re
from datetime import datetime

from odoo import _

from ..models.utils import build_document_key, clean_text, normalize_series, parse_decimal


class ProposalParserError(ValueError):
    pass


def parse_date(value):
    value = clean_text(value)
    if not value or value == "01/01/0001":
        return False
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as error:
        raise ProposalParserError(_("Fecha no valida: %s") % value) from error


class PurchaseProposalParser:
    minimum_columns = 41

    def parse(self, content):
        encoding = self._detect_encoding(content)
        text = content.decode(encoding)
        rows = []
        issues = []
        for line_number, raw_text in enumerate(text.splitlines(), 1):
            if not raw_text.strip():
                continue
            values = raw_text.rstrip("\r\n").split("|")
            if values and values[-1] == "":
                values.pop()
            if values and values[0].strip().lower() == "ruc":
                continue
            if len(values) < self.minimum_columns:
                issues.append(_("Linea %s: tiene %s columnas; se esperaban al menos %s.") % (
                    line_number, len(values), self.minimum_columns
                ))
                continue
            try:
                row = self._parse_values(line_number, raw_text, values)
            except (ProposalParserError, ValueError) as error:
                issues.append(_("Linea %s: %s") % (line_number, error))
                continue
            rows.append(row)
        if not rows:
            raise ProposalParserError(
                _("El archivo no contiene comprobantes validos.%s")
                % (("\n" + "\n".join(issues[:10])) if issues else "")
            )
        return rows, issues

    def _parse_values(self, line_number, raw_text, values):
        period_raw = clean_text(values[2])
        match = re.match(r"^(\d{4})(\d{2})", period_raw)
        if not match:
            raise ProposalParserError(_("Periodo no valido: %s") % period_raw)
        document_type = clean_text(values[6])
        series = normalize_series(values[7])
        number = clean_text(values[9])
        supplier_vat = clean_text(values[12])
        return {
            "source_line_number": line_number,
            "source_raw_text": raw_text,
            "source_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "period": "%s-%s" % (match.group(1), match.group(2)),
            "car_sunat": clean_text(values[3]),
            "issue_date": parse_date(values[4]),
            "due_date": parse_date(values[5]),
            "document_type_code": document_type,
            "series": series,
            "purchase_year": clean_text(values[8]),
            "number": number,
            "final_number": clean_text(values[10]),
            "supplier_document_type": clean_text(values[11]),
            "supplier_document_number": supplier_vat,
            "supplier_name": clean_text(values[13]),
            "taxable_base_dg": parse_decimal(values[14]),
            "igv_dg": parse_decimal(values[15]),
            "taxable_base_dgng": parse_decimal(values[16]),
            "igv_dgng": parse_decimal(values[17]),
            "taxable_base_dng": parse_decimal(values[18]),
            "igv_dng": parse_decimal(values[19]),
            "non_taxed_amount": parse_decimal(values[20]),
            "isc_amount": parse_decimal(values[21]),
            "icbper_amount": parse_decimal(values[22]),
            "other_tax_amount": parse_decimal(values[23]),
            "total_amount": parse_decimal(values[24]),
            "currency_code": clean_text(values[25]).upper(),
            "exchange_rate": parse_decimal(values[26]),
            "original_document_date": parse_date(values[27]),
            "original_document_type": clean_text(values[28]),
            "original_document_series": normalize_series(values[29]),
            "original_document_number": clean_text(values[31]),
            "classification": clean_text(values[32]),
            "record_state": clean_text(values[39]),
            "inconsistency": clean_text(values[40]),
            "normalized_key": build_document_key(supplier_vat, document_type, series, number),
        }

    @staticmethod
    def _detect_encoding(content):
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                content.decode(encoding)
                return encoding
            except UnicodeDecodeError:
                continue
        return "latin-1"

