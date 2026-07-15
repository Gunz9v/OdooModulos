import base64
import io
import zipfile
from collections import defaultdict
from decimal import Decimal

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.addons.l10n_pe_sire_ple_import.models.rce_complement import (
    RceComplementService,
)
from odoo.addons.l10n_pe_sire_ple_import.models.ple_parser import (
    build_purchase_key_from_parts,
    build_sales_key_from_parts,
    first_nonzero_decimal,
    parse_decimal,
)


class SirePeriod(models.Model):
    _inherit = "sire.period"

    sales_reconciliation_line_ids = fields.One2many(
        "sire.sales.reconciliation.line",
        "period_id",
        string="Conciliacion RVIE",
    )
    purchase_reconciliation_line_ids = fields.One2many(
        "sire.purchase.reconciliation.line",
        "period_id",
        string="Conciliacion RCE",
    )
    sire_generated_txt_filename = fields.Char(string="TXT SIRE generado", copy=False)
    sire_generated_zip_filename = fields.Char(string="ZIP SIRE generado", copy=False)
    sire_generated_zip = fields.Binary(string="Archivo ZIP SIRE", attachment=True, copy=False)
    sire_generated_at = fields.Datetime(string="Generado el", copy=False)
    sire_replace_txt_filename = fields.Char(string="TXT reemplazo", copy=False)
    sire_replace_txt = fields.Binary(string="TXT reemplazo", attachment=True, copy=False)
    sire_replace_zip_filename = fields.Char(string="ZIP reemplazo", copy=False)
    sire_replace_zip = fields.Binary(string="Reemplazo", attachment=True, copy=False)
    sire_replace_count = fields.Integer(string="Registros reemplazo", copy=False)
    sire_complement_txt_filename = fields.Char(string="TXT complemento", copy=False)
    sire_complement_txt = fields.Binary(string="TXT complemento", attachment=True, copy=False)
    sire_complement_zip_filename = fields.Char(string="ZIP complemento", copy=False)
    sire_complement_zip = fields.Binary(string="Complemento", attachment=True, copy=False)
    sire_complement_count = fields.Integer(string="Registros complemento", copy=False)
    sire_non_domiciled_zip_filename = fields.Char(string="ZIP no domiciliados", copy=False)
    sire_non_domiciled_zip = fields.Binary(string="No domiciliados", attachment=True, copy=False)
    sire_non_domiciled_count = fields.Integer(string="Registros no domiciliados", copy=False)
    sire_adjustment_zip_filename = fields.Char(string="ZIP ajuste posterior", copy=False)
    sire_adjustment_zip = fields.Binary(string="Ajuste posterior", attachment=True, copy=False)
    sire_adjustment_count = fields.Integer(string="Registros ajuste posterior", copy=False)
    rce_cp_txt_filename = fields.Char(string="TXT CP", copy=False)
    rce_cp_txt = fields.Binary(string="Nuevos comprobantes CP", attachment=True, copy=False)
    rce_cp_count = fields.Integer(string="Registros CP", copy=False)
    rce_cp_duplicate_count = fields.Integer(string="Duplicados CP omitidos", copy=False)
    rce_cp_duplicate_summary = fields.Text(string="Detalle duplicados CP", copy=False)
    rcecom_txt_filename = fields.Char(string="TXT RCECOM", copy=False)
    rcecom_txt = fields.Binary(string="Complemento RCECOM", attachment=True, copy=False)
    rcecom_count = fields.Integer(string="Registros RCECOM", copy=False)
    rceinex_txt_filename = fields.Char(string="TXT RCEINEX", copy=False)
    rceinex_txt = fields.Binary(string="Inclusion/exclusion RCEINEX", attachment=True, copy=False)
    rceinex_count = fields.Integer(string="Registros RCEINEX", copy=False)
    rcetca_txt_filename = fields.Char(string="TXT RCETCA", copy=False)
    rcetca_txt = fields.Binary(string="Tipo de cambio RCETCA", attachment=True, copy=False)
    rcetca_count = fields.Integer(string="Registros RCETCA", copy=False)

    def action_open_sunat_proposal_import_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Importar propuesta SUNAT",
            "res_model": "sire.sunat.proposal.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_period_id": self.id},
        }

    def _reset_after_import_batch_delete(self, import_kind):
        for period in self:
            period._clear_reconciliation_and_generated_files()
            values = {
                "matched_count": 0,
                "difference_count": 0,
                "sunat_only_count": 0,
                "system_only_count": 0,
                "preliminary_generated": False,
                "final_generation_date": False,
            }
            if import_kind == "accounting":
                values.update(
                    {
                        "accounting_batch_id": False,
                        "total_accounting_records": 0,
                    }
                )
            elif import_kind == "sunat":
                values.update(
                    {
                        "sunat_proposal_id": False,
                        "total_sunat_records": 0,
                    }
                )
            values["state"] = period._state_after_import_delete(values)
            period.write(values)
            period.message_post(body=_("Importacion eliminada. Se limpiaron conciliacion y estructuras generadas."))

    def _clear_reconciliation_and_generated_files(self):
        self.ensure_one()
        self.sales_reconciliation_line_ids.unlink()
        self.purchase_reconciliation_line_ids.unlink()
        self.write(
            {
                "sire_generated_txt_filename": False,
                "sire_generated_zip_filename": False,
                "sire_generated_zip": False,
                "sire_generated_at": False,
                "sire_replace_txt_filename": False,
                "sire_replace_txt": False,
                "sire_replace_zip_filename": False,
                "sire_replace_zip": False,
                "sire_replace_count": 0,
                "sire_complement_txt_filename": False,
                "sire_complement_txt": False,
                "sire_complement_zip_filename": False,
                "sire_complement_zip": False,
                "sire_complement_count": 0,
                "sire_non_domiciled_zip_filename": False,
                "sire_non_domiciled_zip": False,
                "sire_non_domiciled_count": 0,
                "sire_adjustment_zip_filename": False,
                "sire_adjustment_zip": False,
                "sire_adjustment_count": 0,
                "rce_cp_txt_filename": False,
                "rce_cp_txt": False,
                "rce_cp_count": 0,
                "rce_cp_duplicate_count": 0,
                "rce_cp_duplicate_summary": False,
                "rcecom_txt_filename": False,
                "rcecom_txt": False,
                "rcecom_count": 0,
                "rceinex_txt_filename": False,
                "rceinex_txt": False,
                "rceinex_count": 0,
                "rcetca_txt_filename": False,
                "rcetca_txt": False,
                "rcetca_count": 0,
            }
        )

    def _state_after_import_delete(self, pending_values):
        self.ensure_one()
        accounting_batch = pending_values.get("accounting_batch_id", self.accounting_batch_id)
        sunat_proposal = pending_values.get("sunat_proposal_id", self.sunat_proposal_id)
        if accounting_batch and sunat_proposal:
            return "proposal_downloaded"
        if accounting_batch:
            return "file_imported"
        if sunat_proposal:
            return "proposal_downloaded"
        return "draft"

    def action_generate_sire_files(self):
        return self.action_generate_structures()

    def action_generate_structures(self):
        self.ensure_one()
        updates, counts = self._prepare_sire_file_updates()
        if self.registry_type == "rce":
            complement_updates, complement_counts = self._prepare_rce_complement_txt_updates(raise_if_empty=False)
            updates.update(complement_updates)
            counts.update(complement_counts)
        self.write(updates)
        self.message_post(
            body=_(
                "Estructuras SIRE generadas: reemplazo %(replace)s, complemento %(complement)s, "
                "CP %(cp)s, RCECOM %(rcecom)s, RCEINEX %(rceinex)s, duplicados CP omitidos %(duplicates)s."
            )
            % {
                "replace": counts.get("replace", 0),
                "complement": counts.get("complement", 0),
                "cp": counts.get("cp", 0),
                "rcecom": counts.get("rcecom", 0),
                "rceinex": counts.get("rceinex", 0),
                "duplicates": counts.get("cp_duplicates", 0),
            }
        )
        if updates.get("rce_cp_duplicate_summary"):
            self.message_post(
                body=_("Comprobantes duplicados omitidos del CP:\n%s") % updates["rce_cp_duplicate_summary"]
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Estructuras generadas"),
                "message": _("Los archivos disponibles quedaron actualizados en la seccion Archivos generados."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def _prepare_sire_file_updates(self):
        replacement_lines = self._get_replacement_source_lines()
        if not replacement_lines:
            raise UserError(_("Primero importa el archivo contable del periodo."))

        generated_at = fields.Datetime.now()
        replacement = self._build_sire_zip_payload(replacement_lines, "replace")
        complement_lines = self._get_complement_source_lines()
        complement = self._build_sire_zip_payload(complement_lines, "complement") if complement_lines else {}
        updates = {
            "sire_replace_txt_filename": replacement["txt_filename"],
            "sire_replace_txt": replacement["txt_data"],
            "sire_replace_zip_filename": replacement["zip_filename"],
            "sire_replace_zip": replacement["zip_data"],
            "sire_replace_count": len(replacement_lines),
            "sire_generated_txt_filename": replacement["txt_filename"],
            "sire_generated_zip_filename": replacement["zip_filename"],
            "sire_generated_zip": replacement["zip_data"],
            "sire_generated_at": generated_at,
            "sire_complement_txt_filename": False,
            "sire_complement_txt": False,
            "sire_complement_zip_filename": False,
            "sire_complement_zip": False,
            "sire_complement_count": 0,
            "sire_non_domiciled_zip_filename": False,
            "sire_non_domiciled_zip": False,
            "sire_non_domiciled_count": 0,
            "sire_adjustment_zip_filename": False,
            "sire_adjustment_zip": False,
            "sire_adjustment_count": 0,
            "preliminary_generated": True,
            "final_generation_date": generated_at,
            "state": "ready_to_submit",
        }
        if complement:
            updates.update(
                {
                    "sire_complement_txt_filename": complement["txt_filename"],
                    "sire_complement_txt": complement["txt_data"],
                    "sire_complement_zip_filename": complement["zip_filename"],
                    "sire_complement_zip": complement["zip_data"],
                    "sire_complement_count": len(complement_lines),
                }
            )
        return updates, {"replace": len(replacement_lines), "complement": len(complement_lines)}

    def action_generate_sire_replacement_zip(self):
        return self.action_generate_structures()

    def action_generate_rce_complement_txt_files(self):
        self.ensure_one()
        if self.registry_type != "rce":
            raise UserError(_("Los archivos CP/RCECOM/RCEINEX/RCETCA corresponden al RCE."))

        updates, counts = self._prepare_rce_complement_txt_updates(raise_if_empty=True)
        self.write(updates)
        self.message_post(
            body=_(
                "TXT complemento RCE generados: CP %(cp)s, RCECOM %(rcecom)s, RCEINEX %(rceinex)s, "
                "duplicados CP omitidos %(duplicates)s."
            )
            % {
                "cp": counts["cp"],
                "rcecom": counts["rcecom"],
                "rceinex": counts["rceinex"],
                "duplicates": counts.get("cp_duplicates", 0),
            }
        )
        if updates.get("rce_cp_duplicate_summary"):
            self.message_post(
                body=_("Comprobantes duplicados omitidos del CP:\n%s") % updates["rce_cp_duplicate_summary"]
            )
        if self.rce_cp_txt:
            return self.action_download_rce_cp_txt()
        if self.rcecom_txt:
            return self.action_download_rcecom_txt()
        return self.action_download_rceinex_txt()

    def _prepare_rce_complement_txt_updates(self, raise_if_empty=True):
        service = self._get_rce_complement_service()
        cp_rows, cp_duplicates = self._get_rce_cp_rows_and_duplicates()
        rcecom_rows = self._get_rcecom_rows()
        rceinex_rows, rceinex_document_types = self._get_rceinex_rows()
        updates = {
            "rce_cp_txt_filename": False,
            "rce_cp_txt": False,
            "rce_cp_count": 0,
            "rce_cp_duplicate_count": len(cp_duplicates),
            "rce_cp_duplicate_summary": self._build_rce_cp_duplicate_summary(cp_duplicates),
            "rcecom_txt_filename": False,
            "rcecom_txt": False,
            "rcecom_count": 0,
            "rceinex_txt_filename": False,
            "rceinex_txt": False,
            "rceinex_count": 0,
            "rcetca_txt_filename": False,
            "rcetca_txt": False,
            "rcetca_count": 0,
            "sire_generated_at": fields.Datetime.now(),
        }
        if cp_rows:
            payload = service.generate_cp(cp_rows)
            updates.update(
                {
                    "rce_cp_txt_filename": payload["filename"],
                    "rce_cp_txt": base64.b64encode(payload["content"].encode("latin-1")),
                    "rce_cp_count": len(cp_rows),
                }
            )
        if rcecom_rows:
            payload = service.generate_rcecom(rcecom_rows)
            updates.update(
                {
                    "rcecom_txt_filename": payload["filename"],
                    "rcecom_txt": base64.b64encode(payload["content"].encode("latin-1")),
                    "rcecom_count": len(rcecom_rows),
                }
            )
        if rceinex_rows:
            payload = service.generate_rceinex(rceinex_rows, document_types=rceinex_document_types)
            updates.update(
                {
                    "rceinex_txt_filename": payload["filename"],
                    "rceinex_txt": base64.b64encode(payload["content"].encode("latin-1")),
                    "rceinex_count": len(rceinex_rows),
                }
            )
        if not cp_rows and not rcecom_rows and not rceinex_rows:
            if raise_if_empty:
                raise UserError(_("No hay registros de conciliacion RCE para generar CP, RCECOM o RCEINEX."))
        return updates, {
            "cp": len(cp_rows),
            "cp_duplicates": len(cp_duplicates),
            "rcecom": len(rcecom_rows),
            "rceinex": len(rceinex_rows),
        }

    def _build_sire_zip_payload(self, lines, decision_key):
        txt_filename = self._build_sire_replacement_filename("TXT", decision_key=decision_key)
        zip_filename = self._build_sire_replacement_filename("", decision_key=decision_key)
        line_texts = [self._build_sire_line_text(line) for line in lines]
        if any(text.lower().startswith("ruc|") for text in line_texts):
            raise UserError(_("El TXT SIRE no debe contener cabecera."))
        txt_content = "\r\n".join(line_texts) + "\r\n"
        try:
            txt_bytes = txt_content.encode("latin-1")
        except UnicodeEncodeError as error:
            raise UserError(_("El archivo contiene caracteres que no se pueden codificar en latin-1: %s") % error) from error

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(txt_filename, txt_bytes)
        zip_data = zip_buffer.getvalue()
        return {
            "txt_filename": txt_filename,
            "txt_data": base64.b64encode(txt_bytes),
            "zip_filename": zip_filename,
            "zip_data": base64.b64encode(zip_data),
        }

    def _build_sire_line_text(self, line):
        if self.registry_type == "rvie":
            return self._build_rvie_replacement_line_text(line)
        return self._build_rce_replacement_line_text(line)

    def _split_source_values(self, line, expected_columns):
        values = (line.source_raw_text or "").rstrip("\r\n").split("|")
        if values and values[-1] == "":
            values = values[:-1]
        while len(values) < expected_columns:
            values.append("")
        return values

    def _build_rvie_replacement_line_text(self, line):
        values = self._split_source_values(line, 35)
        company_name = (self.company_id.name or "").strip()
        if not company_name:
            raise UserError(_("La razon social de la empresa es obligatoria para generar el reemplazo RVIE."))
        document_type = (values[5] or "").strip()
        if document_type in ("07", "08", "87", "88"):
            modified_document_values = [values[27], values[28], values[29], values[30]]
        else:
            modified_document_values = ["", "", "", ""]
        taxable_base = values[13]
        taxable_discount = values[14]
        igv_amount = values[15]
        igv_discount = values[16]
        modified_date_in_period = self._date_text_is_in_period(values[27])
        modified_document_type = (values[28] or "").strip()
        if document_type == "07" and modified_document_type == "03" and not modified_date_in_period:
            taxable_base = "0.00"
            taxable_discount = first_nonzero_decimal(values[13], values[14])
            igv_amount = "0.00"
            igv_discount = first_nonzero_decimal(values[15], values[16])
        elif document_type == "07" and (
            (modified_document_type == "03" and modified_date_in_period)
            or (modified_document_type == "01" and not modified_date_in_period)
        ):
            taxable_base = "0.00"
            taxable_discount = "0.00"
            igv_amount = "0.00"
            igv_discount = "0.00"
        currency_code = (values[25] or "").strip().upper()
        exchange_rate = "" if currency_code == "PEN" else values[26]
        base_values = [
            (self.company_id.vat or "").strip(),
            company_name,
            "%04d%s" % (self.year, self.month),
            "",
            values[3],
            values[4],
            values[5],
            values[6],
            values[7],
            values[8],
            values[9],
            values[10],
            values[11],
            values[12],
            taxable_base,
            taxable_discount,
            igv_amount,
            igv_discount,
            values[17],
            values[18],
            values[19],
            values[20],
            values[21],
            values[22],
            values[23],
            values[24],
            values[25],
            exchange_rate,
            *modified_document_values,
            values[31],
        ]
        clu_values = self._get_rvie_clu_values(values)
        output_values = self._build_rvie_output_values(base_values, clu_values)
        self._validate_rvie_replacement_values(output_values, document_type)
        return "|".join(output_values) + "|"

    def _get_rvie_clu_values(self, values):
        clu_values = list(values[35:52])
        while len(clu_values) < 17:
            clu_values.append("")
        return clu_values[:17]

    def _date_text_is_in_period(self, value):
        date_text = (value or "").strip()
        parts = date_text.split("/")
        return (
            len(parts) == 3
            and parts[1] == self.month
            and parts[2] == str(self.year)
        )

    def _build_rvie_output_values(self, base_values, clu_values):
        output_values = [str(value or "").strip() for value in base_values]
        normalized_clu = [str(value or "").strip() for value in clu_values]
        last_clu_index = -1
        for index, value in enumerate(normalized_clu):
            if value:
                last_clu_index = index
        if last_clu_index >= 0:
            output_values.extend(normalized_clu[: last_clu_index + 1])
        return output_values

    def _validate_rvie_replacement_values(self, values, document_type):
        if any("|" in value or "\r" in value or "\n" in value for value in values):
            raise UserError(_("Los valores del TXT SIRE no pueden contener palotes ni saltos de linea."))
        if values and values[0].strip().lower() == "ruc":
            raise UserError(_("El TXT SIRE no debe contener cabecera."))
        has_clu = len(values) > 33
        if not has_clu and len(values) != 33:
            raise UserError(_("Una fila RVIE sin CLU debe tener 33 campos logicos."))
        if has_clu and len(values) > 50:
            raise UserError(_("Una fila RVIE con CLU no puede tener mas de 50 campos logicos."))
        if len(values) < 2 or not values[1]:
            raise UserError(_("El campo 2 del reemplazo RVIE debe contener la razon social."))
        if document_type not in ("07", "08", "87", "88") and any(values[28:32]):
            raise UserError(_("Los campos 29 al 32 solo deben informarse para notas 07, 08, 87 u 88."))

    def _build_rce_replacement_line_text(self, line):
        values = self._split_source_values(line, 42)
        document_type = (values[5] or "").strip()
        purchase_year = "" if (values[7] or "").strip(" 0") == "" else values[7]
        series = (values[6] or "").strip().upper()
        if series == "-":
            series = ""
        currency_code = (values[24] or "").strip().upper()
        exchange_rate = "" if currency_code == "PEN" or (values[25] or "").strip() == "0.000" else values[25]
        if document_type in ("07", "08", "87", "88"):
            modified_document_values = [values[26], values[27], values[28], values[29], values[30]]
        else:
            modified_document_values = ["", "", "", "", ""]
        classification = (values[41] or "").strip()
        if classification not in ("1", "2", "3", "4", "5"):
            classification = ""
        amount_values = values[13:24]
        clu_values = self._get_rce_clu_values(values)
        if document_type in ("02", "03"):
            clu_values = amount_values + clu_values
            amount_values = [""] * 11
        base_values = [
            (self.company_id.vat or "").strip(),
            self.company_id.name or "",
            "%04d%s" % (self.year, self.month),
            "",
            values[3],
            values[4],
            values[5],
            series,
            purchase_year,
            values[8],
            values[9],
            values[10],
            values[11],
            values[12],
            *amount_values,
            values[24],
            exchange_rate,
            *modified_document_values,
            classification,
            values[33],
            values[34],
            values[35],
            "",
            "",
            "",
            "",
            "",
        ]
        output_values = self._build_rce_output_values(base_values, clu_values)
        self._validate_rce_replacement_values(output_values)
        return "|".join(output_values) + "|"

    def _get_rce_clu_values(self, values):
        clu_values = list(values[42:81])
        while len(clu_values) < 39:
            clu_values.append("")
        return clu_values[:39]

    def _build_rce_output_values(self, base_values, clu_values):
        output_values = [str(value or "").strip() for value in base_values]
        normalized_clu = [str(value or "").strip() for value in clu_values]
        last_clu_index = -1
        for index, value in enumerate(normalized_clu):
            if value:
                last_clu_index = index
        if last_clu_index >= 0:
            output_values.extend(normalized_clu[: last_clu_index + 1])
        return output_values

    def _validate_rce_replacement_values(self, values):
        if any("|" in value or "\r" in value or "\n" in value for value in values):
            raise UserError(_("Los valores del TXT RCE no pueden contener palotes ni saltos de linea."))
        has_clu = len(values) > 41
        if not has_clu and len(values) != 41:
            raise UserError(_("Una fila RCE sin CLU debe tener 41 campos logicos."))
        if has_clu and len(values) > 80:
            raise UserError(_("Una fila RCE con CLU no puede tener mas de 80 campos logicos."))
        if len(values) < 2 or not values[1]:
            raise UserError(_("El campo 2 del reemplazo RCE debe contener la razon social."))
        if len(values) >= 37 and values[36]:
            raise UserError(_("El campo 37 CAR original debe ir vacio para reemplazo RCE."))

    def action_download_sire_replacement_zip(self):
        self.ensure_one()
        if not self.sire_generated_zip:
            raise UserError(_("Primero genera el ZIP SIRE."))
        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": "/web/content/sire.period/%s/sire_generated_zip/%s?download=true"
            % (self.id, self.sire_generated_zip_filename),
        }

    def action_download_sire_replace_zip(self):
        self.ensure_one()
        if not self.sire_replace_zip:
            raise UserError(_("Primero genera los archivos SIRE."))
        return self._download_generated_zip("sire_replace_zip", self.sire_replace_zip_filename)

    def action_download_sire_replace_txt(self):
        self.ensure_one()
        if not self.sire_replace_txt:
            raise UserError(_("Primero genera los archivos SIRE."))
        return self._download_generated_zip("sire_replace_txt", self.sire_replace_txt_filename)

    def action_download_sire_complement_zip(self):
        self.ensure_one()
        if not self.sire_complement_zip:
            raise UserError(_("No se genero complemento porque no hay lineas solo en sistema contable."))
        return self._download_generated_zip("sire_complement_zip", self.sire_complement_zip_filename)

    def action_download_sire_complement_txt(self):
        self.ensure_one()
        if not self.sire_complement_txt:
            raise UserError(_("No se genero complemento porque no hay lineas solo en sistema contable."))
        return self._download_generated_zip("sire_complement_txt", self.sire_complement_txt_filename)

    def action_download_sire_non_domiciled_zip(self):
        self.ensure_one()
        if not self.sire_non_domiciled_zip:
            raise UserError(_("Aun no hay archivo de no domiciliados generado para este periodo."))
        return self._download_generated_zip("sire_non_domiciled_zip", self.sire_non_domiciled_zip_filename)

    def action_download_sire_adjustment_zip(self):
        self.ensure_one()
        if not self.sire_adjustment_zip:
            raise UserError(_("Aun no hay archivo de ajuste posterior generado para este periodo."))
        return self._download_generated_zip("sire_adjustment_zip", self.sire_adjustment_zip_filename)

    def action_download_rce_cp_txt(self):
        self.ensure_one()
        if not self.rce_cp_txt:
            raise UserError(_("Aun no hay archivo CP generado para este periodo."))
        return self._download_generated_zip("rce_cp_txt", self.rce_cp_txt_filename)

    def action_download_rcecom_txt(self):
        self.ensure_one()
        if not self.rcecom_txt:
            raise UserError(_("Aun no hay archivo RCECOM generado para este periodo."))
        return self._download_generated_zip("rcecom_txt", self.rcecom_txt_filename)

    def action_download_rceinex_txt(self):
        self.ensure_one()
        if not self.rceinex_txt:
            raise UserError(_("Aun no hay archivo RCEINEX generado para este periodo."))
        return self._download_generated_zip("rceinex_txt", self.rceinex_txt_filename)

    def action_download_rcetca_txt(self):
        self.ensure_one()
        if not self.rcetca_txt:
            raise UserError(_("Aun no hay archivo RCETCA generado para este periodo."))
        return self._download_generated_zip("rcetca_txt", self.rcetca_txt_filename)

    def action_submit_sire_replace(self):
        self.ensure_one()
        if not self.sire_replace_zip:
            raise UserError(_("Primero genera el archivo de reemplazo."))
        return self._submit_generated_sire_file("replacement", self.sire_replace_zip, self.sire_replace_zip_filename)

    def action_submit_sire_complement(self):
        self.ensure_one()
        if not self.sire_complement_zip:
            raise UserError(_("No hay archivo de complemento generado para enviar."))
        return self._submit_generated_sire_file("complement", self.sire_complement_zip, self.sire_complement_zip_filename)

    def action_submit_rce_cp(self):
        self.ensure_one()
        if not self.rce_cp_txt:
            raise UserError(_("No hay TXT 8.1 generado para enviar."))
        file_data, filename = self._zip_generated_text_file(self.rce_cp_txt, self.rce_cp_txt_filename)
        return self._submit_generated_sire_file("rce_cp", file_data, filename)

    def action_submit_rcecom(self):
        self.ensure_one()
        if not self.rcecom_txt:
            raise UserError(_("No hay TXT 8.2 generado para enviar."))
        file_data, filename = self._zip_generated_text_file(self.rcecom_txt, self.rcecom_txt_filename)
        return self._submit_generated_sire_file("rcecom", file_data, filename)

    def action_submit_rceinex(self):
        self.ensure_one()
        if not self.rceinex_txt:
            raise UserError(_("No hay TXT 8.3 generado para enviar."))
        file_data, filename = self._zip_generated_text_file(self.rceinex_txt, self.rceinex_txt_filename)
        return self._submit_generated_sire_file("rceinex", file_data, filename)

    def action_submit_rcetca(self):
        self.ensure_one()
        if not self.rcetca_txt:
            raise UserError(_("No hay TXT tipo de cambio generado para enviar."))
        file_data, filename = self._zip_generated_text_file(self.rcetca_txt, self.rcetca_txt_filename)
        return self._submit_generated_sire_file("rcetca", file_data, filename)

    def _submit_generated_sire_file(self, submission_type, file_data, filename):
        ticket = self.env["sire.api.client"].submit_generated_file_and_download_result(
            self,
            submission_type,
            file_data,
            filename,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Ticket SUNAT"),
            "res_model": "sire.api.ticket",
            "view_mode": "form",
            "res_id": ticket.id,
            "target": "current",
        }

    def _zip_generated_text_file(self, file_data, filename):
        raw = base64.b64decode(file_data or b"")
        if raw.startswith(b"PK"):
            return file_data, filename
        txt_filename = (filename or "sire.txt").strip()
        zip_filename = txt_filename.rsplit(".", 1)[0] + ".zip"
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(txt_filename, raw)
        return base64.b64encode(zip_buffer.getvalue()), zip_filename

    def _download_generated_zip(self, field_name, filename):
        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": "/web/content/sire.period/%s/%s/%s?download=true"
            % (self.id, field_name, filename),
        }

    def _get_rce_complement_service(self):
        return RceComplementService(
            (self.company_id.vat or "").strip(),
            "%04d%s" % (self.year, self.month),
            correlativo=1,
        )

    def _get_rce_cp_rows(self):
        rows, _duplicates = self._get_rce_cp_rows_and_duplicates()
        return rows

    def _get_rce_cp_rows_and_duplicates(self):
        reconciliation_lines = self.purchase_reconciliation_line_ids.filtered(
            lambda line: line.status == "system_only" and line.accounting_line_id
        )
        rows = []
        seen = {}
        duplicates = []
        for line in reconciliation_lines.sorted(key=lambda item: (item.accounting_line_id.source_line_number, item.id)):
            row = self._build_rce_cp_row(line.accounting_line_id)
            duplicate_key = (row[12], row[6], row[7], row[9])
            if duplicate_key in seen:
                duplicates.append(
                    {
                        "duplicate_line": line.accounting_line_id,
                        "original_line": seen[duplicate_key],
                        "supplier_document_number": row[12],
                        "document_type": row[6],
                        "series": row[7],
                        "number": row[9],
                    }
                )
                continue
            seen[duplicate_key] = line.accounting_line_id
            rows.append(row)
        return rows, duplicates

    def _build_rce_cp_duplicate_summary(self, duplicates):
        if not duplicates:
            return False
        lines = []
        for duplicate in duplicates[:100]:
            original = duplicate["original_line"]
            repeated = duplicate["duplicate_line"]
            lines.append(
                _(
                    "Linea %(repeated)s duplicada de linea %(original)s: proveedor %(supplier)s, "
                    "tipo %(type)s, serie %(series)s, numero %(number)s"
                )
                % {
                    "repeated": repeated.source_line_number,
                    "original": original.source_line_number,
                    "supplier": duplicate["supplier_document_number"] or "-",
                    "type": duplicate["document_type"] or "-",
                    "series": duplicate["series"] or "-",
                    "number": duplicate["number"] or "-",
                }
            )
        if len(duplicates) > len(lines):
            lines.append(_("... %s duplicados adicionales omitidos del resumen.") % (len(duplicates) - len(lines)))
        return "\n".join(lines)

    def _get_rcecom_rows(self):
        reconciliation_lines = self.purchase_reconciliation_line_ids.filtered(
            lambda line: line.status == "difference" and line.sunat_car_sunat and line.accounting_line_id
        )
        rows = []
        for line in reconciliation_lines.sorted(key=lambda item: (item.accounting_line_id.source_line_number, item.id)):
            row = self._build_rcecom_row(line)
            if any(row[index] for index in (14, 15, 16, 17, 18, 19, 21, 26, 32, 33, 34, 35)):
                rows.append(row)
        return rows

    def _get_rceinex_rows(self):
        reconciliation_lines = self.purchase_reconciliation_line_ids.filtered(
            lambda line: line.status == "sunat_only" and line.sunat_car_sunat
        )
        rows = []
        document_types = {}
        for line in reconciliation_lines.sorted(key=lambda item: (item.sunat_line_id.source_line_number, item.id)):
            if line.sunat_document_type in ("07", "87"):
                continue
            row = [""] * 37
            row[3] = line.sunat_car_sunat
            row[36] = "1"
            rows.append(row)
            document_types[line.sunat_car_sunat] = line.sunat_document_type
        return rows, document_types

    def _build_rce_cp_row(self, line):
        values = self._split_source_values(line, 42)
        document_type = (values[5] or "").strip()
        series = (values[6] or "").strip().upper()
        purchase_year = "" if (values[7] or "").strip(" 0") == "" else values[7]
        currency_code = (values[24] or "").strip().upper()
        exchange_rate = "" if currency_code == "PEN" or (values[25] or "").strip() == "0.000" else values[25]
        if document_type in ("07", "08", "87", "88"):
            modified_values = [values[26], values[27], values[28], values[29], values[30]]
        else:
            modified_values = ["", "", "", "", ""]
        classification = (values[41] or "").strip()
        if classification not in ("1", "2", "3", "4", "5"):
            classification = ""
        return [
            (self.company_id.vat or "").strip(),
            self.company_id.name or "",
            "%04d%s" % (self.year, self.month),
            "",
            values[3],
            values[4],
            document_type,
            "" if series == "-" else series,
            purchase_year,
            values[8],
            values[9],
            values[10],
            values[11],
            values[12],
            *values[13:24],
            values[24],
            exchange_rate,
            *modified_values,
            classification,
            values[33],
            values[34],
            values[35],
            "",
            *self._get_rce_complement_clu_values(values),
        ]

    def _build_rcecom_row(self, reconciliation_line):
        accounting_values = self._split_source_values(reconciliation_line.accounting_line_id, 42)
        row = [""] * 37
        row[3] = reconciliation_line.sunat_car_sunat
        row[14] = accounting_values[13] if reconciliation_line.taxable_base_dg_has_diff else ""
        row[15] = accounting_values[14] if reconciliation_line.igv_dg_has_diff else ""
        row[16] = accounting_values[15] if reconciliation_line.taxable_base_dgng_has_diff else ""
        row[17] = accounting_values[16] if reconciliation_line.igv_dgng_has_diff else ""
        row[18] = accounting_values[17] if reconciliation_line.taxable_base_dng_has_diff else ""
        row[19] = accounting_values[18] if reconciliation_line.igv_dng_has_diff else ""
        row[21] = accounting_values[20] if reconciliation_line.isc_has_diff else ""
        accounting_currency = (accounting_values[24] or "").strip().upper()
        accounting_exchange_rate = (accounting_values[25] or "").strip()
        row[26] = (
            accounting_exchange_rate
            if reconciliation_line.currency_diff and accounting_currency != "PEN" and accounting_exchange_rate != "0.000"
            else ""
        )
        classification = (accounting_values[41] or "").strip()
        row[32] = classification if classification in ("1", "2", "3", "4", "5") else ""
        row[33] = accounting_values[33]
        row[34] = accounting_values[34]
        row[35] = accounting_values[35]
        return row + self._get_rce_complement_clu_values(accounting_values)

    def _get_rce_complement_clu_values(self, values):
        clu_values = list(values[42:81])
        while len(clu_values) < 39:
            clu_values.append("")
        return clu_values[:39]

    def _get_replacement_source_lines(self):
        model_name = (
            "sire.purchase.accounting.line"
            if self.registry_type == "rce"
            else "sire.sales.accounting.line"
        )
        return self.env[model_name].search(
            [
                ("period_id", "=", self.id),
                ("validation_state", "!=", "invalid"),
            ],
            order="source_line_number, id",
        )

    def _get_complement_source_lines(self):
        if self.registry_type == "rce":
            reconciliation_lines = self.purchase_reconciliation_line_ids.filtered(
                lambda line: line.status == "system_only" and line.accounting_line_id
            )
            return reconciliation_lines.mapped("accounting_line_id").sorted(
                key=lambda line: (line.source_line_number, line.id)
            )
        reconciliation_lines = self.sales_reconciliation_line_ids.filtered(
            lambda line: line.status == "system_only" and line.accounting_line_id
        )
        return reconciliation_lines.mapped("accounting_line_id").sorted(
            key=lambda line: (line.source_line_number, line.id)
        )

    def _build_sire_replacement_filename(self, extension, decision_key=None):
        extension = (extension or "").upper()
        filename = self._build_sire_replacement_filename_base(decision_key=decision_key)
        return "%s.%s" % (filename, extension) if extension else filename

    def _build_sire_replacement_filename_base(self, decision_key=None):
        ruc = (self.company_id.vat or "").strip()
        if len(ruc) != 11 or not ruc.isdigit():
            raise UserError(_("Configura un RUC valido de 11 digitos en la empresa."))
        book_code = "080400" if self.registry_type == "rce" else "140400"
        opportunity_codes = {
            "replace": "02",
            "complement": "03",
            "non_domiciled": "04",
            "adjustment": "05",
        }
        opportunity_code = opportunity_codes.get(decision_key or "replace", "02")
        operation_indicator = "1"
        content_indicator = "1"
        currency_indicator = "1"
        sire_generation_indicator = "2"
        presentation_code = (
            opportunity_code
            + operation_indicator
            + content_indicator
            + currency_indicator
            + sire_generation_indicator
        )
        return "LE%s%04d%s00%s%s" % (
            ruc,
            self.year,
            self.month,
            book_code,
            presentation_code,
        )

    def action_run_purchase_reconciliation(self):
        self.ensure_one()
        if self.registry_type != "rce":
            raise UserError(_("La conciliacion de compras corresponde a RCE."))

        accounting_lines = self.env["sire.purchase.accounting.line"].search(
            [("period_id", "=", self.id), ("validation_state", "!=", "invalid")]
        )
        sunat_lines = self.env["sire.purchase.sunat.line"].search(
            [("period_id", "=", self.id), ("validation_state", "!=", "invalid")]
        )
        if not accounting_lines:
            raise UserError(_("Primero importa el archivo contable RCE."))
        if not sunat_lines:
            raise UserError(_("Primero importa la propuesta SUNAT RCE."))

        self._refresh_purchase_normalized_keys(accounting_lines)
        self._refresh_purchase_normalized_keys(sunat_lines)
        self.purchase_reconciliation_line_ids.unlink()
        accounting_by_key = self._group_sales_lines(accounting_lines)
        sunat_by_key = self._group_sales_lines(sunat_lines)
        values = []
        for key in sorted(set(accounting_by_key) | set(sunat_by_key)):
            accountings = accounting_by_key.get(key, [])
            sunats = sunat_by_key.get(key, [])
            pair_count = min(len(accountings), len(sunats))
            for index in range(pair_count):
                values.append(self._build_purchase_reconciliation_values(key, accountings[index], sunats[index]))
            for line in accountings[pair_count:]:
                values.append(
                    {
                        "period_id": self.id,
                        "accounting_line_id": line.id,
                        "normalized_key": key,
                        "status": "system_only",
                        "difference_summary": self._missing_purchase_line_summary(line, "sunat"),
                    }
                )
            for line in sunats[pair_count:]:
                values.append(
                    {
                        "period_id": self.id,
                        "sunat_line_id": line.id,
                        "normalized_key": key,
                        "status": "sunat_only",
                        "difference_summary": self._missing_purchase_line_summary(line, "system"),
                    }
                )
        if values:
            self.env["sire.purchase.reconciliation.line"].create(values)

        counts = self.env["sire.purchase.reconciliation.line"].read_group(
            [("period_id", "=", self.id)],
            ["status"],
            ["status"],
        )
        count_by_status = {row["status"]: row["status_count"] for row in counts}
        self.write(
            {
                "matched_count": count_by_status.get("matched", 0),
                "difference_count": count_by_status.get("difference", 0),
                "system_only_count": count_by_status.get("system_only", 0),
                "sunat_only_count": count_by_status.get("sunat_only", 0),
                "state": "reconciled",
            }
        )
        self.message_post(
            body=_(
                "Conciliacion RCE ejecutada: %s coincidentes, %s con diferencias, %s solo sistema, %s solo SUNAT."
            )
            % (
                self.matched_count,
                self.difference_count,
                self.system_only_count,
                self.sunat_only_count,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Periodo SIRE"),
            "res_model": "sire.period",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_open_purchase_reconciliation(self):
        self.ensure_one()
        if self.registry_type != "rce":
            raise UserError(_("La conciliacion de compras corresponde a RCE."))
        return {
            "type": "ir.actions.act_window",
            "name": "Conciliacion RCE",
            "res_model": "sire.purchase.reconciliation.line",
            "view_mode": "list,form",
            "domain": [("period_id", "=", self.id)],
            "context": {
                "search_default_review_pending": 1,
                "search_default_period_id": self.id,
            },
        }

    def action_run_sales_reconciliation(self):
        self.ensure_one()
        if self.registry_type != "rvie":
            raise UserError(_("La conciliacion implementada corresponde a RVIE."))

        accounting_lines = self.env["sire.sales.accounting.line"].search(
            [("period_id", "=", self.id), ("validation_state", "!=", "invalid")]
        )
        sunat_lines = self.env["sire.sales.sunat.line"].search(
            [("period_id", "=", self.id), ("validation_state", "!=", "invalid")]
        )
        if not accounting_lines:
            raise UserError(_("Primero importa el archivo contable RVIE."))
        if not sunat_lines:
            raise UserError(_("Primero importa la propuesta SUNAT."))

        self._refresh_sales_amount_breakdowns(accounting_lines)
        self._refresh_sales_amount_breakdowns(sunat_lines)
        self._refresh_sunat_record_states(sunat_lines)
        self._refresh_sales_normalized_keys(accounting_lines)
        self._refresh_sales_normalized_keys(sunat_lines)
        self._refresh_sunat_credit_note_amounts(sunat_lines)
        self.sales_reconciliation_line_ids.unlink()
        accounting_by_key = self._group_sales_lines(accounting_lines)
        sunat_by_key = self._group_sales_lines(sunat_lines)
        values = []
        for key in sorted(set(accounting_by_key) | set(sunat_by_key)):
            accountings = accounting_by_key.get(key, [])
            sunats = sunat_by_key.get(key, [])
            pair_count = min(len(accountings), len(sunats))
            for index in range(pair_count):
                values.append(self._build_reconciliation_values(key, accountings[index], sunats[index]))
            for line in accountings[pair_count:]:
                values.append(
                    {
                        "period_id": self.id,
                        "accounting_line_id": line.id,
                        "normalized_key": key,
                        "status": "system_only",
                        "difference_summary": self._missing_line_summary(line, "sunat"),
                    }
                )
            for line in sunats[pair_count:]:
                values.append(
                    {
                        "period_id": self.id,
                        "sunat_line_id": line.id,
                        "normalized_key": key,
                        "status": "sunat_only",
                        "difference_summary": self._missing_line_summary(line, "system"),
                    }
                )
        if values:
            self.env["sire.sales.reconciliation.line"].create(values)

        counts = self.env["sire.sales.reconciliation.line"].read_group(
            [("period_id", "=", self.id)],
            ["status"],
            ["status"],
        )
        count_by_status = {row["status"]: row["status_count"] for row in counts}
        self.write(
            {
                "matched_count": count_by_status.get("matched", 0),
                "difference_count": count_by_status.get("difference", 0),
                "system_only_count": count_by_status.get("system_only", 0),
                "sunat_only_count": count_by_status.get("sunat_only", 0),
                "state": "reconciled",
            }
        )
        self.message_post(
            body=_(
                "Conciliacion RVIE ejecutada: %s coincidentes, %s con diferencias, %s solo sistema, %s solo SUNAT."
            )
            % (
                self.matched_count,
                self.difference_count,
                self.system_only_count,
                self.sunat_only_count,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Periodo SIRE"),
            "res_model": "sire.period",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_open_sales_reconciliation(self):
        self.ensure_one()
        if self.registry_type != "rvie":
            raise UserError(_("La conciliacion implementada corresponde a RVIE."))
        return {
            "type": "ir.actions.act_window",
            "name": "Conciliacion RVIE",
            "res_model": "sire.sales.reconciliation.line",
            "view_mode": "list,form",
            "domain": [("period_id", "=", self.id)],
            "context": {
                "search_default_review_pending": 1,
                "search_default_period_id": self.id,
            },
        }

    def _group_sales_lines(self, lines):
        grouped = defaultdict(list)
        for line in lines:
            grouped[line.normalized_key or ""].append(line)
        for key in grouped:
            grouped[key].sort(key=lambda item: (item.issue_date or fields.Date.today(), item.id))
        return grouped

    def _refresh_sales_normalized_keys(self, lines):
        for line in lines:
            key = build_sales_key_from_parts(
                line.customer_document_type,
                line.customer_document_number,
                line.document_type,
                line.series,
                line.number,
                line.record_state,
                line.total_amount,
            )
            if line.normalized_key != key:
                line.normalized_key = key

    def _refresh_purchase_normalized_keys(self, lines):
        for line in lines:
            key = build_purchase_key_from_parts(
                line.supplier_document_type,
                line.supplier_document_number,
                line.document_type,
                line.series,
                line.purchase_year,
                line.number,
            )
            if line.normalized_key != key:
                line.normalized_key = key

    def _refresh_sunat_record_states(self, lines):
        for line in lines.filtered(lambda item: item.source_raw_text):
            values = line.source_raw_text.rstrip("\r\n").split("|")
            if values and values[-1] == "":
                values = values[:-1]
            if len(values) == 39:
                values.append("")
            if len(values) != 40:
                continue
            record_state = values[34].strip()
            if line.record_state != record_state:
                line.record_state = record_state

    def _refresh_sales_amount_breakdowns(self, lines):
        for line in lines.filtered(lambda item: item.source_raw_text):
            values = line.source_raw_text.rstrip("\r\n").split("|")
            if values and values[-1] == "":
                values = values[:-1]
            updates = {}
            if line._name == "sire.sales.accounting.line" and len(values) == 35:
                updates = {
                    "export_amount": parse_decimal(values[12]),
                    "taxable_base": parse_decimal(values[13]),
                    "igv_amount": parse_decimal(values[15]),
                    "exempt_amount": parse_decimal(values[17]),
                    "unaffected_amount": parse_decimal(values[18]),
                    "non_taxable_amount": parse_decimal(values[18]),
                    "total_amount": parse_decimal(values[24]),
                }
            elif line._name == "sire.sales.sunat.line":
                if len(values) == 39:
                    values.append("")
                if len(values) == 40:
                    updates = {
                        "export_amount": parse_decimal(values[13]),
                        "taxable_base": (
                            first_nonzero_decimal(values[14], values[15])
                            if line.document_type == "07"
                            else parse_decimal(values[14])
                        ),
                        "igv_amount": (
                            first_nonzero_decimal(values[16], values[17])
                            if line.document_type == "07"
                            else parse_decimal(values[16])
                        ),
                        "exempt_amount": parse_decimal(values[18]),
                        "unaffected_amount": parse_decimal(values[19]),
                        "non_taxable_amount": parse_decimal(values[19]),
                        "total_amount": parse_decimal(values[25]),
                    }
            if not updates:
                continue
            changed = {
                field_name: value
                for field_name, value in updates.items()
                if self._decimal(line[field_name]) != value
            }
            if changed:
                line.write(changed)

    def _refresh_sunat_credit_note_amounts(self, lines):
        for line in lines.filtered(lambda item: item.document_type == "07" and item.source_raw_text):
            values = line.source_raw_text.rstrip("\r\n").split("|")
            if values and values[-1] == "":
                values = values[:-1]
            if len(values) == 39:
                values.append("")
            if len(values) != 40:
                continue
            taxable_base = first_nonzero_decimal(values[14], values[15])
            igv_amount = first_nonzero_decimal(values[16], values[17])
            total_amount = parse_decimal(values[25])
            updates = {}
            if self._decimal(line.taxable_base) != taxable_base:
                updates["taxable_base"] = taxable_base
            if self._decimal(line.igv_amount) != igv_amount:
                updates["igv_amount"] = igv_amount
            if self._decimal(line.total_amount) != total_amount:
                updates["total_amount"] = total_amount
            if updates:
                line.write(updates)

    def _build_reconciliation_values(self, key, accounting_line, sunat_line):
        amount_fields = [
            ("export_amount", "Valor facturado de exportacion", "export"),
            ("taxable_base", "Base imponible", "taxable_base"),
            ("exempt_amount", "Operacion exonerada", "exempt"),
            ("unaffected_amount", "Operacion inafecta", "unaffected"),
            ("igv_amount", "IGV", "igv"),
            ("total_amount", "Total", "total"),
        ]
        differences = []
        values = {
            "period_id": self.id,
            "accounting_line_id": accounting_line.id,
            "sunat_line_id": sunat_line.id,
            "normalized_key": key,
        }
        if accounting_line.issue_date != sunat_line.issue_date:
            values["issue_date_diff"] = True
            differences.append(_("Fecha contable %s vs SUNAT %s") % (accounting_line.issue_date, sunat_line.issue_date))
        if (
            (accounting_line.currency_code or "") != (sunat_line.currency_code or "")
            and not self._should_ignore_cancelled_zero_currency(accounting_line, sunat_line)
        ):
            values["currency_diff"] = True
            differences.append(
                _("Moneda contable %s vs SUNAT %s")
                % (accounting_line.currency_code or "-", sunat_line.currency_code or "-")
            )
        for field_name, label, diff_key in amount_fields:
            diff = self._decimal(accounting_line[field_name]) - self._decimal(sunat_line[field_name])
            diff_field = "%s_diff" % diff_key
            if field_name == "igv_amount" and self._should_ignore_free_boleta_igv(accounting_line, sunat_line):
                values[diff_field] = Decimal("0")
                continue
            values[diff_field] = diff
            if abs(diff) > Decimal("0.01"):
                flag_field = "%s_has_diff" % diff_key
                values[flag_field] = True
                differences.append(_("%s contable %s vs SUNAT %s") % (label, accounting_line[field_name], sunat_line[field_name]))
        values["status"] = "difference" if differences else "matched"
        values["difference_summary"] = "\n".join(differences) if differences else False
        return values

    def _build_purchase_reconciliation_values(self, key, accounting_line, sunat_line):
        amount_fields = [
            ("taxable_base_dg", "BI Gravado DG", "taxable_base_dg"),
            ("igv_dg", "IGV/IPM DG", "igv_dg"),
            ("taxable_base_dgng", "BI Gravado DGNG", "taxable_base_dgng"),
            ("igv_dgng", "IGV/IPM DGNG", "igv_dgng"),
            ("taxable_base_dng", "BI Gravado DNG", "taxable_base_dng"),
            ("igv_dng", "IGV/IPM DNG", "igv_dng"),
            ("non_taxed_amount", "Valor adquisicion no gravada", "non_taxed"),
            ("isc_amount", "ISC", "isc"),
            ("icbper_amount", "ICBPER", "icbper"),
            ("other_tax_amount", "Otros tributos/cargos", "other_tax"),
            ("total_amount", "Total", "total"),
        ]
        differences = []
        values = {
            "period_id": self.id,
            "accounting_line_id": accounting_line.id,
            "sunat_line_id": sunat_line.id,
            "normalized_key": key,
        }
        if accounting_line.issue_date != sunat_line.issue_date:
            values["issue_date_diff"] = True
            differences.append(_("Fecha contable %s vs SUNAT %s") % (accounting_line.issue_date, sunat_line.issue_date))
        if (accounting_line.currency_code or "") != (sunat_line.currency_code or ""):
            values["currency_diff"] = True
            differences.append(
                _("Moneda contable %s vs SUNAT %s")
                % (accounting_line.currency_code or "-", sunat_line.currency_code or "-")
            )
        for field_name, label, diff_key in amount_fields:
            diff = self._decimal(accounting_line[field_name]) - self._decimal(sunat_line[field_name])
            values["%s_diff" % diff_key] = diff
            if abs(diff) > Decimal("0.01"):
                values["%s_has_diff" % diff_key] = True
                differences.append(_("%s contable %s vs SUNAT %s") % (label, accounting_line[field_name], sunat_line[field_name]))
        values["status"] = "difference" if differences else "matched"
        values["difference_summary"] = "\n".join(differences) if differences else False
        return values

    def _decimal(self, value):
        return Decimal(str(value or "0"))

    def _is_zero_amount(self, value):
        return abs(self._decimal(value)) <= Decimal("0.01")

    def _should_ignore_free_boleta_igv(self, accounting_line, sunat_line):
        if (accounting_line.document_type or sunat_line.document_type or "") != "03":
            return False
        return (
            self._is_zero_amount(accounting_line.taxable_base)
            and self._is_zero_amount(sunat_line.taxable_base)
            and self._is_zero_amount(accounting_line.total_amount)
            and self._is_zero_amount(sunat_line.total_amount)
        )

    def _should_ignore_cancelled_zero_currency(self, accounting_line, sunat_line):
        return (
            (accounting_line.record_state or sunat_line.record_state or "") == "2"
            and self._is_zero_amount(accounting_line.total_amount)
            and self._is_zero_amount(sunat_line.total_amount)
        )

    def _missing_line_summary(self, line, missing_side):
        target = _("propuesta SUNAT") if missing_side == "sunat" else _("archivo contable")
        return _(
            "El comprobante %(document_type)s %(series)s-%(number)s del cliente %(customer)s "
            "no existe en %(target)s. Importe: %(amount)s %(currency)s. Tipo de cambio: %(rate)s."
        ) % {
            "document_type": line.document_type or "-",
            "series": line.series or "-",
            "number": line.number or "-",
            "customer": line.customer_document_number or line.customer_name or "-",
            "target": target,
            "amount": line.total_amount,
            "currency": line.currency_code or "-",
            "rate": line.exchange_rate,
        }

    def _missing_purchase_line_summary(self, line, missing_side):
        target = _("propuesta SUNAT") if missing_side == "sunat" else _("archivo contable")
        return _(
            "El comprobante %(document_type)s %(series)s-%(number)s del proveedor %(supplier)s "
            "no existe en %(target)s. Importe: %(amount)s %(currency)s. Tipo de cambio: %(rate)s."
        ) % {
            "document_type": line.document_type or "-",
            "series": line.series or "-",
            "number": line.number or "-",
            "supplier": line.supplier_document_number or line.supplier_name or "-",
            "target": target,
            "amount": line.total_amount,
            "currency": line.currency_code or "-",
            "rate": line.exchange_rate,
        }
