import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation


BOOK_HANDLERS = {
    "080100": "purchase",
    "080400": "purchase",
    "140100": "sales",
    "140400": "sales",
}

FILENAME_RE = re.compile(
    r"^LE(?P<ruc>\d{11})(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?P<book>\d{6}).*(?:\.txt)?$",
    re.IGNORECASE,
)


@dataclass
class PleParsedName:
    ruc: str
    year: int
    month: str
    period_code: str
    book_code: str
    registry_kind: str


@dataclass
class PleLineIssue:
    line_number: int
    level: str
    code: str
    message: str
    raw_text: str = ""


@dataclass
class PleParsedLine:
    line_number: int
    raw_text: str
    values: list[str]
    normalized: dict
    issues: list[PleLineIssue] = field(default_factory=list)

    @property
    def has_errors(self):
        return any(issue.level == "error" for issue in self.issues)

    @property
    def has_warnings(self):
        return any(issue.level == "warning" for issue in self.issues)


@dataclass
class PleParsedFile:
    filename_info: PleParsedName
    encoding: str
    file_hash: str
    lines: list[PleParsedLine]
    issues: list[PleLineIssue]

    @property
    def valid_lines(self):
        return [line for line in self.lines if not line.has_errors]


class PleParserError(ValueError):
    pass


def parse_filename(filename):
    match = FILENAME_RE.match(filename or "")
    if not match:
        raise PleParserError("El nombre del archivo PLE no tiene una estructura valida.")
    book_code = match.group("book")
    registry_kind = BOOK_HANDLERS.get(book_code)
    if not registry_kind:
        raise PleParserError("No existe importador para el libro %s." % book_code)
    year = int(match.group("year"))
    month = match.group("month")
    return PleParsedName(
        ruc=match.group("ruc"),
        year=year,
        month=month,
        period_code="%04d-%s" % (year, month),
        book_code=book_code,
        registry_kind=registry_kind,
    )


def normalize_period_code(value):
    value = normalize_empty(value)
    match = re.match(r"^(?P<year>\d{4})(?P<month>\d{2})", value)
    if not match:
        return ""
    return "%s-%s" % (match.group("year"), match.group("month"))


def detect_encoding(content):
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            content.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"


def normalize_empty(value):
    value = (value or "").strip()
    if value == "-":
        return ""
    return value


def parse_decimal(value):
    value = normalize_empty(value)
    if not value:
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise PleParserError("Importe no valido: %s" % value)


def parse_date(value):
    value = normalize_empty(value)
    if not value or value == "01/01/0001":
        return False
    match = re.match(r"^(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})$", value)
    if not match:
        raise PleParserError("Fecha no valida: %s" % value)
    parsed = date(
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
    )
    return parsed.isoformat()


def normalize_series(value):
    return normalize_empty(value).upper()


def normalize_currency(value):
    return normalize_empty(value).upper()


def normalize_document_number_for_key(value):
    value = normalize_empty(value)
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def normalize_purchase_year_for_key(value):
    value = normalize_document_number_for_key(value)
    return "" if value in ("", "0") else value


def build_sales_key(values):
    return build_sales_key_from_parts(
        values[9],
        values[10],
        values[5],
        values[6],
        values[7],
        values[34],
        values[24],
    )


def build_sales_key_from_parts(
    customer_document_type,
    customer_document_number,
    document_type,
    series,
    number,
    record_state=None,
    total_amount=None,
):
    document_type = normalize_empty(document_type)
    customer_document_type = normalize_empty(customer_document_type)
    customer_document_number = normalize_empty(customer_document_number)
    record_state = normalize_empty(record_state)
    total_amount = parse_decimal(str(total_amount)) if total_amount is not None else Decimal("0")
    if document_type == "03" or (record_state == "2" and total_amount == Decimal("0")):
        customer_document_type = ""
        customer_document_number = ""
    return "|".join(
        [
            customer_document_type,
            customer_document_number,
            document_type,
            normalize_series(series),
            normalize_document_number_for_key(number),
        ]
    )


def build_purchase_key(values):
    return build_purchase_key_from_parts(
        values[10],
        values[11],
        values[5],
        values[6],
        values[7],
        values[8],
    )


def build_purchase_key_from_parts(supplier_document_type, supplier_document_number, document_type, series, year, number):
    return "|".join(
        [
            normalize_empty(supplier_document_type),
            normalize_empty(supplier_document_number),
            normalize_empty(document_type),
            normalize_series(series),
            normalize_purchase_year_for_key(year),
            normalize_document_number_for_key(number),
        ]
    )


def first_nonzero_decimal(*values):
    for value in values:
        parsed = parse_decimal(value)
        if parsed:
            return parsed
    return Decimal("0")


class Format141Parser:
    expected_columns = 35

    def parse_line(self, line_number, raw_text):
        values = raw_text.rstrip("\r\n").split("|")
        if values and values[-1] == "":
            values = values[:-1]

        issues = []
        if len(values) != self.expected_columns:
            issues.append(
                PleLineIssue(
                    line_number=line_number,
                    level="error",
                    code="column_count",
                    message="La linea tiene %s columnas; se esperaban %s."
                    % (len(values), self.expected_columns),
                    raw_text=raw_text,
                )
            )
            return PleParsedLine(line_number, raw_text, values, {}, issues)

        normalized = {}
        checks = [
            ("issue_date", parse_date, values[3]),
            ("due_date", parse_date, values[4]),
            ("export_amount", parse_decimal, values[12]),
            ("taxable_base", parse_decimal, values[13]),
            ("taxable_base_discount", parse_decimal, values[14]),
            ("igv_amount", parse_decimal, values[15]),
            ("igv_discount", parse_decimal, values[16]),
            ("exempt_amount", parse_decimal, values[17]),
            ("unaffected_amount", parse_decimal, values[18]),
            ("isc_amount", parse_decimal, values[19]),
            ("other_tax_amount", parse_decimal, values[22]),
            ("total_amount", parse_decimal, values[24]),
            ("exchange_rate", parse_decimal, values[26]),
        ]
        for field_name, parser, raw_value in checks:
            try:
                normalized[field_name] = parser(raw_value)
            except PleParserError as error:
                issues.append(
                    PleLineIssue(
                        line_number=line_number,
                        level="error",
                        code=field_name,
                        message=str(error),
                        raw_text=raw_text,
                    )
                )

        normalized.update(
            {
                "period_code": normalize_period_code(values[0]),
                "cuo": normalize_empty(values[1]),
                "entry_sequence": normalize_empty(values[2]),
                "document_type": normalize_empty(values[5]),
                "series": normalize_series(values[6]),
                "number": normalize_empty(values[7]),
                "customer_document_type": normalize_empty(values[9]),
                "customer_document_number": normalize_empty(values[10]),
                "customer_name": normalize_empty(values[11]),
                "currency_code": normalize_currency(values[25]),
                "non_taxable_amount": normalized.get("unaffected_amount", Decimal("0")),
                "original_document_date": parse_date(values[27]),
                "original_document_type": normalize_empty(values[28]),
                "original_document_series": normalize_series(values[29]),
                "original_document_number": normalize_empty(values[30]),
                "record_state": normalize_empty(values[34]),
                "normalized_key": build_sales_key(values),
                "source_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            }
        )

        if normalized["document_type"] == "07" and normalized.get("total_amount", Decimal("0")) > 0:
            issues.append(
                PleLineIssue(
                    line_number=line_number,
                    level="warning",
                    code="credit_note_sign",
                    message="La nota de credito tiene total positivo; revisar signos.",
                    raw_text=raw_text,
                )
            )

        return PleParsedLine(line_number, raw_text, values, normalized, issues)


class Format81Parser:
    expected_columns = 42

    def parse_line(self, line_number, raw_text):
        values = raw_text.rstrip("\r\n").split("|")
        if values and values[-1] == "":
            values = values[:-1]

        issues = []
        if len(values) != self.expected_columns:
            issues.append(
                PleLineIssue(
                    line_number=line_number,
                    level="error",
                    code="column_count",
                    message="La linea tiene %s columnas; se esperaban %s."
                    % (len(values), self.expected_columns),
                    raw_text=raw_text,
                )
            )
            return PleParsedLine(line_number, raw_text, values, {}, issues)

        normalized = {}
        checks = [
            ("issue_date", parse_date, values[3]),
            ("due_date", parse_date, values[4]),
            ("taxable_base_dg", parse_decimal, values[13]),
            ("igv_dg", parse_decimal, values[14]),
            ("taxable_base_dgng", parse_decimal, values[15]),
            ("igv_dgng", parse_decimal, values[16]),
            ("taxable_base_dng", parse_decimal, values[17]),
            ("igv_dng", parse_decimal, values[18]),
            ("non_taxed_amount", parse_decimal, values[19]),
            ("isc_amount", parse_decimal, values[20]),
            ("icbper_amount", parse_decimal, values[21]),
            ("other_tax_amount", parse_decimal, values[22]),
            ("total_amount", parse_decimal, values[23]),
            ("exchange_rate", parse_decimal, values[25]),
            ("original_document_date", parse_date, values[26]),
        ]
        for field_name, parser, raw_value in checks:
            try:
                normalized[field_name] = parser(raw_value)
            except PleParserError as error:
                issues.append(
                    PleLineIssue(
                        line_number=line_number,
                        level="error",
                        code=field_name,
                        message=str(error),
                        raw_text=raw_text,
                    )
                )

        normalized.update(
            {
                "period_code": normalize_period_code(values[0]),
                "cuo": normalize_empty(values[1]),
                "entry_sequence": normalize_empty(values[2]),
                "document_type": normalize_empty(values[5]),
                "series": normalize_series(values[6]),
                "purchase_year": normalize_empty(values[7]),
                "number": normalize_empty(values[8]),
                "final_number": normalize_empty(values[9]),
                "supplier_document_type": normalize_empty(values[10]),
                "supplier_document_number": normalize_empty(values[11]),
                "supplier_name": normalize_empty(values[12]),
                "currency_code": normalize_currency(values[24]),
                "taxable_base": normalized.get("taxable_base_dg", Decimal("0")),
                "igv_amount": normalized.get("igv_dg", Decimal("0")),
                "non_taxable_amount": normalized.get("non_taxed_amount", Decimal("0")),
                "original_document_type": normalize_empty(values[27]),
                "original_document_series": normalize_series(values[28]),
                "original_document_number": normalize_empty(values[30]),
                "record_state": normalize_empty(values[41]),
                "normalized_key": build_purchase_key(values),
                "source_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            }
        )
        return PleParsedLine(line_number, raw_text, values, normalized, issues)


class SunatProposalPurchaseParser:
    minimum_columns = 41

    def parse_line(self, line_number, raw_text):
        values = raw_text.rstrip("\r\n").split("|")
        if values and values[-1] == "":
            values = values[:-1]

        issues = []
        if values and values[0].strip().lower() == "ruc":
            return PleParsedLine(line_number, raw_text, values, {}, issues)
        if len(values) < self.minimum_columns:
            issues.append(
                PleLineIssue(
                    line_number=line_number,
                    level="error",
                    code="column_count",
                    message="La linea tiene %s columnas; se esperaban al menos %s."
                    % (len(values), self.minimum_columns),
                    raw_text=raw_text,
                )
            )
            return PleParsedLine(line_number, raw_text, values, {}, issues)

        normalized = {}
        checks = [
            ("issue_date", parse_date, values[4]),
            ("due_date", parse_date, values[5]),
            ("taxable_base_dg", parse_decimal, values[14]),
            ("igv_dg", parse_decimal, values[15]),
            ("taxable_base_dgng", parse_decimal, values[16]),
            ("igv_dgng", parse_decimal, values[17]),
            ("taxable_base_dng", parse_decimal, values[18]),
            ("igv_dng", parse_decimal, values[19]),
            ("non_taxed_amount", parse_decimal, values[20]),
            ("isc_amount", parse_decimal, values[21]),
            ("icbper_amount", parse_decimal, values[22]),
            ("other_tax_amount", parse_decimal, values[23]),
            ("total_amount", parse_decimal, values[24]),
            ("exchange_rate", parse_decimal, values[26]),
            ("original_document_date", parse_date, values[27]),
            ("deduction_amount", parse_decimal, values[35]),
        ]
        for field_name, parser, raw_value in checks:
            try:
                normalized[field_name] = parser(raw_value)
            except PleParserError as error:
                issues.append(
                    PleLineIssue(
                        line_number=line_number,
                        level="error",
                        code=field_name,
                        message=str(error),
                        raw_text=raw_text,
                    )
                )

        document_type = normalize_empty(values[6])
        series = normalize_series(values[7])
        purchase_year = normalize_empty(values[8])
        number = normalize_empty(values[9])
        supplier_document_type = normalize_empty(values[11])
        supplier_document_number = normalize_empty(values[12])
        normalized.update(
            {
                "period_code": normalize_period_code(values[2]),
                "cuo": normalize_empty(values[3]),
                "entry_sequence": normalize_empty(values[3]),
                "car_sunat": normalize_empty(values[3]),
                "document_type": document_type,
                "series": series,
                "purchase_year": purchase_year,
                "number": number,
                "final_number": normalize_empty(values[10]),
                "supplier_document_type": supplier_document_type,
                "supplier_document_number": supplier_document_number,
                "supplier_name": normalize_empty(values[13]),
                "currency_code": normalize_currency(values[25]),
                "taxable_base": normalized.get("taxable_base_dg", Decimal("0")),
                "igv_amount": normalized.get("igv_dg", Decimal("0")),
                "non_taxable_amount": normalized.get("non_taxed_amount", Decimal("0")),
                "original_document_type": normalize_empty(values[28]),
                "original_document_series": normalize_series(values[29]),
                "original_document_number": normalize_empty(values[31]),
                "classification": normalize_empty(values[32]),
                "car_original_indicator": normalize_empty(values[36]),
                "deduction_indicator": normalize_empty(values[37]),
                "note_type": normalize_empty(values[38]),
                "record_state": normalize_empty(values[39]),
                "inconsistency": normalize_empty(values[40]),
                "normalized_key": build_purchase_key_from_parts(
                    supplier_document_type,
                    supplier_document_number,
                    document_type,
                    series,
                    purchase_year,
                    number,
                ),
                "source_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            }
        )
        return PleParsedLine(line_number, raw_text, values, normalized, issues)


class SunatProposalSalesParser:
    expected_columns = 40

    def parse_line(self, line_number, raw_text):
        values = raw_text.rstrip("\r\n").split("|")
        if values and values[-1] == "":
            values = values[:-1]

        issues = []
        if values and values[0].strip().lower() == "ruc":
            return PleParsedLine(line_number, raw_text, values, {}, issues)
        if len(values) == self.expected_columns - 1:
            values.append("")
        if len(values) != self.expected_columns:
            issues.append(
                PleLineIssue(
                    line_number=line_number,
                    level="error",
                    code="column_count",
                    message="La linea tiene %s columnas; se esperaban %s."
                    % (len(values), self.expected_columns),
                    raw_text=raw_text,
                )
            )
            return PleParsedLine(line_number, raw_text, values, {}, issues)

        document_type = normalize_empty(values[6])
        normalized = {}
        checks = [
            ("issue_date", parse_date, values[4]),
            ("due_date", parse_date, values[5]),
            ("export_amount", parse_decimal, values[13]),
            ("exempt_amount", parse_decimal, values[18]),
            ("unaffected_amount", parse_decimal, values[19]),
            ("isc_amount", parse_decimal, values[20]),
            ("other_tax_amount", parse_decimal, values[24]),
            ("total_amount", parse_decimal, values[25]),
            ("exchange_rate", parse_decimal, values[27]),
            ("original_document_date", parse_date, values[28]),
        ]
        for field_name, parser, raw_value in checks:
            try:
                normalized[field_name] = parser(raw_value)
            except PleParserError as error:
                issues.append(
                    PleLineIssue(
                        line_number=line_number,
                        level="error",
                        code=field_name,
                        message=str(error),
                        raw_text=raw_text,
                    )
                )

        try:
            normalized["taxable_base"] = parse_decimal(values[14])
            normalized["taxable_base_discount"] = parse_decimal(values[15])
            normalized["igv_amount"] = parse_decimal(values[16])
            normalized["igv_discount"] = parse_decimal(values[17])
        except PleParserError as error:
            issues.append(
                PleLineIssue(
                    line_number=line_number,
                    level="error",
                    code="credit_note_amount",
                    message=str(error),
                    raw_text=raw_text,
                )
            )

        series = normalize_series(values[7])
        number = normalize_empty(values[8])
        customer_document_type = normalize_empty(values[10])
        customer_document_number = normalize_empty(values[11])

        normalized.update(
            {
                "period_code": normalize_period_code(values[2]),
                "cuo": normalize_empty(values[3]),
                "entry_sequence": normalize_empty(values[3]),
                "car_sunat": normalize_empty(values[3]),
                "document_type": document_type,
                "series": series,
                "number": number,
                "customer_document_type": customer_document_type,
                "customer_document_number": customer_document_number,
                "customer_name": normalize_empty(values[12]),
                "currency_code": normalize_currency(values[26]),
                "non_taxable_amount": normalized.get("unaffected_amount", Decimal("0")),
                "original_document_type": normalize_empty(values[29]),
                "original_document_series": normalize_series(values[30]),
                "original_document_number": normalize_empty(values[31]),
                "record_state": normalize_empty(values[34]),
                "normalized_key": build_sales_key_from_parts(
                    customer_document_type,
                    customer_document_number,
                    document_type,
                    series,
                    number,
                    values[34],
                    values[25],
                ),
                "source_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            }
        )
        return PleParsedLine(line_number, raw_text, values, normalized, issues)


class PleFileParser:
    def __init__(self):
        self._format_handlers = {
            "080100": Format81Parser(),
            "080400": SunatProposalPurchaseParser(),
            "140100": Format141Parser(),
            "140400": SunatProposalSalesParser(),
        }

    def parse(self, filename, content):
        filename_info = parse_filename(filename)
        handler = self._format_handlers.get(filename_info.book_code)
        if not handler:
            raise PleParserError("No existe parser para el libro %s." % filename_info.book_code)

        encoding = detect_encoding(content)
        text = content.decode(encoding)
        file_hash = hashlib.sha256(content).hexdigest()
        lines = []
        issues = []
        for line_number, raw_text in enumerate(text.splitlines(), start=1):
            if not raw_text.strip():
                continue
            parsed_line = handler.parse_line(line_number, raw_text)
            if not parsed_line.normalized and not parsed_line.has_errors:
                continue
            lines.append(parsed_line)
            issues.extend(parsed_line.issues)
        return PleParsedFile(filename_info, encoding, file_hash, lines, issues)
