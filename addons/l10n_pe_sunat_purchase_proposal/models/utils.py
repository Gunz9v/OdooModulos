import re
from decimal import Decimal, InvalidOperation


def clean_text(value):
    value = (value or "").strip()
    return "" if value == "-" else value


def normalize_vat(value):
    return re.sub(r"[^0-9A-Z]", "", clean_text(value).upper())


def normalize_series(value):
    return re.sub(r"\s+", "", clean_text(value).upper())


def normalize_number(value):
    value = clean_text(value).upper()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def split_document_number(value):
    value = clean_text(value).upper()
    if " " in value:
        value = value.rsplit(" ", 1)[-1]
    match = re.match(r"^\s*([A-Z0-9]+)\s*[-/]\s*([A-Z0-9]+)\s*$", value)
    if match:
        return normalize_series(match.group(1)), normalize_number(match.group(2))
    return "", normalize_number(value)


def build_document_key(vat, document_type, series, number):
    return "|".join(
        (
            normalize_vat(vat),
            clean_text(document_type),
            normalize_series(series),
            normalize_number(number),
        )
    )


def parse_decimal(value):
    value = clean_text(value)
    if not value:
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Importe no valido: %s" % value) from error

