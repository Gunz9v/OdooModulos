from enum import Enum
import re

from odoo import _
from odoo.exceptions import UserError


CAMPOS_BASE_ANEXO_8 = tuple(range(1, 38))
CAMPOS_CLU_ANEXO_8 = tuple(range(42, 81))
RCE_COMPLEMENT_ALLOWED_CP_TYPES = {
    "00",
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "10",
    "12",
    "13",
    "14",
    "15",
    "16",
    "18",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "30",
    "32",
    "34",
    "35",
    "36",
    "37",
    "42",
    "43",
    "45",
    "46",
    "48",
    "49",
    "50",
    "51",
    "52",
    "53",
    "54",
    "55",
    "56",
    "87",
    "88",
}
RCE_COMPLEMENT_FORBIDDEN_CP_TYPES = {"91", "97", "98"}
RCE_COMPLEMENT_NOTE_TYPES = {"07", "08", "87", "88"}


class RceComplementFileType(Enum):
    CP = "CP"
    RCECOM = "RCECOM"
    RCEINEX = "RCEINEX"
    RCETCA = "RCETCA"


class RceComplementFileNameBuilder:
    @classmethod
    def build(cls, file_type, ruc, period, correlativo=1):
        cls._validate_common_name_values(ruc, period, correlativo)
        return "%s-%s-%s-%02d.txt" % (ruc, file_type.value, period, int(correlativo))

    @classmethod
    def _validate_common_name_values(cls, ruc, period, correlativo):
        if not re.fullmatch(r"\d{11}", ruc or ""):
            raise UserError(_("El RUC debe tener exactamente 11 digitos."))
        if not re.fullmatch(r"\d{6}", period or ""):
            raise UserError(_("El periodo debe tener formato AAAAMM."))
        month = int(period[4:6])
        if month < 1 or month > 12:
            raise UserError(_("El mes del periodo debe estar entre 01 y 12."))
        if int(correlativo or 0) < 1 or int(correlativo or 0) > 99:
            raise UserError(_("El correlativo debe estar entre 01 y 99."))


class RceComplementSerializer:
    @classmethod
    def serialize_anexo8(cls, base_values, clu_values=None, row_number=1):
        if len(base_values) != 37:
            raise UserError(_("Fila %(row)s: el Anexo 8 debe recibir 37 campos base.") % {"row": row_number})
        output_values = cls._clean_values(base_values, row_number)
        normalized_clu = cls._clean_values(clu_values or [], row_number, start_field=42)
        if len(normalized_clu) > 39:
            raise UserError(_("Fila %(row)s: el Anexo 8 permite como maximo 39 campos CLU.") % {"row": row_number})
        last_clu_index = -1
        for index, value in enumerate(normalized_clu):
            if value:
                last_clu_index = index
        if last_clu_index >= 0:
            output_values.extend(normalized_clu[: last_clu_index + 1])
        if len(output_values) > 76:
            raise UserError(_("Fila %(row)s: el Anexo 8 permite como maximo 76 campos fisicos.") % {"row": row_number})
        return "|".join(output_values) + "|"

    @classmethod
    def serialize_rceinex(cls, car_sunat, indicator, row_number=1):
        base_values = [""] * 37
        base_values[3] = car_sunat
        base_values[36] = indicator
        return cls.serialize_anexo8(base_values, [], row_number=row_number)

    @classmethod
    def serialize_anexo10(cls, rows, accounting_in_foreign_currency=False):
        if not rows:
            raise UserError(_("Debe existir al menos un registro para generar RCETCA."))
        output = []
        seen = set()
        for row_number, row in enumerate(rows, start=1):
            period = str(row.get("period") or "").strip()
            issue_date = str(row.get("issue_date") or "").strip()
            currency = str(row.get("currency") or "").strip().upper()
            exchange_rate_pen = str(row.get("exchange_rate_pen") or "").strip()
            exchange_rate_usd = str(row.get("exchange_rate_usd") or "").strip()
            key = (period, issue_date, currency)
            if key in seen:
                raise UserError(_("Fila %(row)s: periodo, fecha y moneda duplicados.") % {"row": row_number})
            seen.add(key)
            if not re.fullmatch(r"\d{6}", period):
                raise UserError(_("Fila %(row)s campo 1: periodo invalido.") % {"row": row_number})
            cls._validate_date(issue_date, row_number, 2)
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise UserError(_("Fila %(row)s campo 3: la moneda debe tener tres caracteres.") % {"row": row_number})
            cls._validate_exchange_rate(exchange_rate_pen, row_number, 4)
            if accounting_in_foreign_currency:
                cls._validate_exchange_rate(exchange_rate_usd, row_number, 5)
            elif exchange_rate_usd:
                cls._validate_exchange_rate(exchange_rate_usd, row_number, 5)
            values = [period, issue_date, currency, exchange_rate_pen, exchange_rate_usd]
            output.append("|".join(cls._clean_values(values, row_number)) + "|")
        return "\r\n".join(output) + "\r\n"

    @classmethod
    def _clean_values(cls, values, row_number, start_field=1):
        normalized = []
        for index, value in enumerate(values, start=start_field):
            text = "" if value is None else str(value).strip()
            if text in ("null", "None", "undefined", "N/A", "01/01/0001", "-"):
                text = ""
            if "|" in text or "\r" in text or "\n" in text:
                raise UserError(
                    _("Fila %(row)s campo %(field)s: el valor contiene palotes o saltos de linea.")
                    % {"row": row_number, "field": index}
                )
            if "," in text and re.fullmatch(r"-?\d{1,3}(,\d{3})*(\.\d+)?|-?\d+,\d+", text):
                raise UserError(
                    _("Fila %(row)s campo %(field)s: no use comas ni separadores de miles.")
                    % {"row": row_number, "field": index}
                )
            if re.fullmatch(r"-?\d+(\.\d+)?[eE][+-]?\d+", text) and not (index == 4 and len(text) == 27):
                raise UserError(
                    _("Fila %(row)s campo %(field)s: no use notacion cientifica.")
                    % {"row": row_number, "field": index}
                )
            normalized.append(text)
        return normalized

    @classmethod
    def _validate_date(cls, value, row_number, field_number):
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value or ""):
            raise UserError(_("Fila %(row)s campo %(field)s: fecha invalida.") % {"row": row_number, "field": field_number})

    @classmethod
    def _validate_exchange_rate(cls, value, row_number, field_number):
        if not re.fullmatch(r"\d+(\.\d{1,3})?", value or "") or float(value) <= 0:
            raise UserError(
                _("Fila %(row)s campo %(field)s: tipo de cambio invalido.")
                % {"row": row_number, "field": field_number}
            )


class RceComplementValidator:
    @classmethod
    def validate_cp(cls, rows):
        cls._validate_rows(rows)
        seen = set()
        for row_number, row in enumerate(rows, start=1):
            document_type = row[6]
            if document_type in RCE_COMPLEMENT_FORBIDDEN_CP_TYPES:
                raise UserError(_("Fila %(row)s campo 7: tipo de comprobante no permitido en CP.") % {"row": row_number})
            if document_type not in RCE_COMPLEMENT_ALLOWED_CP_TYPES:
                raise UserError(_("Fila %(row)s campo 7: tipo de comprobante fuera de Tabla 11.") % {"row": row_number})
            if row[3]:
                raise UserError(_("Fila %(row)s campo 4: CAR SUNAT debe estar vacio para CP.") % {"row": row_number})
            if row[36]:
                raise UserError(_("Fila %(row)s campo 37: debe estar vacio para CP.") % {"row": row_number})
            if document_type not in RCE_COMPLEMENT_NOTE_TYPES and any(row[27:32]):
                raise UserError(_("Fila %(row)s campos 28-32: solo aplican para notas.") % {"row": row_number})
            duplicate_key = (row[12], document_type, row[7], row[9])
            if duplicate_key in seen:
                raise UserError(_("Fila %(row)s: comprobante duplicado dentro del archivo CP.") % {"row": row_number})
            seen.add(duplicate_key)

    @classmethod
    def validate_rcecom(cls, rows):
        cls._validate_rows(rows)
        complement_indexes = [14, 15, 16, 17, 18, 19, 21, 26, 32, 33, 34, 35]
        for row_number, row in enumerate(rows, start=1):
            cls._validate_car(row[3], row_number)
            if any(row[0:3]):
                raise UserError(_("Fila %(row)s campos 1-3: deben estar vacios para RCECOM.") % {"row": row_number})
            if any(row[4:14]):
                raise UserError(_("Fila %(row)s campos 5-14: deben estar vacios para RCECOM.") % {"row": row_number})
            forbidden_indexes = set(range(37)) - {3, *complement_indexes}
            if any(row[index] for index in forbidden_indexes):
                raise UserError(_("Fila %(row)s: RCECOM contiene campos no modificables.") % {"row": row_number})
            if not any(row[index] for index in complement_indexes):
                raise UserError(_("Fila %(row)s: RCECOM debe informar al menos un campo complementable.") % {"row": row_number})
            if row[32] and row[32] not in ("1", "2", "3", "4", "5"):
                raise UserError(_("Fila %(row)s campo 33: clasificacion invalida.") % {"row": row_number})

    @classmethod
    def validate_rceinex(cls, rows, document_types=None):
        cls._validate_rows(rows)
        seen = {}
        document_types = document_types or {}
        for row_number, row in enumerate(rows, start=1):
            car_sunat = row[3]
            indicator = row[36]
            cls._validate_car(car_sunat, row_number)
            if indicator not in ("1", "2"):
                raise UserError(_("Fila %(row)s campo 37: indicador invalido.") % {"row": row_number})
            if any(row[index] for index in range(37) if index not in (3, 36)):
                raise UserError(_("Fila %(row)s: solo campos 4 y 37 pueden estar informados.") % {"row": row_number})
            if document_types.get(car_sunat) in ("07", "87") and indicator == "1":
                raise UserError(_("Fila %(row)s: no se permite excluir comprobantes tipo 07 o 87.") % {"row": row_number})
            if car_sunat in seen and seen[car_sunat] != indicator:
                raise UserError(_("Fila %(row)s: CAR duplicado con acciones contradictorias.") % {"row": row_number})
            seen[car_sunat] = indicator

    @classmethod
    def _validate_rows(cls, rows):
        if not rows:
            raise UserError(_("Debe existir al menos un registro para generar el archivo."))

    @classmethod
    def _validate_car(cls, car_sunat, row_number):
        if not re.fullmatch(r"[A-Za-z0-9]{27}", car_sunat or ""):
            raise UserError(_("Fila %(row)s campo 4: CAR SUNAT debe tener 27 caracteres alfanumericos.") % {"row": row_number})


class RceComplementService:
    def __init__(self, ruc, period, correlativo=1):
        RceComplementFileNameBuilder._validate_common_name_values(ruc, period, correlativo)
        self.ruc = ruc
        self.period = period
        self.correlativo = correlativo

    def generate_cp(self, rows):
        RceComplementValidator.validate_cp(rows)
        return self._build_payload(RceComplementFileType.CP, rows)

    def generate_rcecom(self, rows):
        RceComplementValidator.validate_rcecom(rows)
        return self._build_payload(RceComplementFileType.RCECOM, rows)

    def generate_rceinex(self, rows, document_types=None):
        RceComplementValidator.validate_rceinex(rows, document_types=document_types)
        return self._build_payload(RceComplementFileType.RCEINEX, rows)

    def generate_rcetca(self, rows, accounting_in_foreign_currency=False):
        filename = RceComplementFileNameBuilder.build(
            RceComplementFileType.RCETCA,
            self.ruc,
            self.period,
            self.correlativo,
        )
        txt_content = RceComplementSerializer.serialize_anexo10(
            rows,
            accounting_in_foreign_currency=accounting_in_foreign_currency,
        )
        return {"filename": filename, "content": txt_content}

    def _build_payload(self, file_type, rows):
        filename = RceComplementFileNameBuilder.build(file_type, self.ruc, self.period, self.correlativo)
        line_texts = [
            RceComplementSerializer.serialize_anexo8(row[:37], row[37:] if len(row) > 37 else [], row_number=index)
            for index, row in enumerate(rows, start=1)
        ]
        txt_content = "\r\n".join(line_texts) + "\r\n"
        return {"filename": filename, "content": txt_content}
