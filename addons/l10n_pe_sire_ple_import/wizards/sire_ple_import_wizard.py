import base64
from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.l10n_pe_sire_ple_import.models.ple_parser import (
    PleFileParser,
    PleParserError,
)


class SirePleImportWizard(models.TransientModel):
    _name = "sire.ple.import.wizard"
    _description = "Importar archivo PLE SIRE"

    period_id = fields.Many2one("sire.period", string="Periodo", required=True)
    file_data = fields.Binary(string="Archivo TXT", required=True)
    filename = fields.Char(string="Nombre de archivo", required=True)

    def action_import_file(self):
        self.ensure_one()
        content = base64.b64decode(self.file_data or b"")
        try:
            parsed_file = PleFileParser().parse(self.filename, content)
        except PleParserError as error:
            raise UserError(str(error)) from error

        self._validate_file_context(parsed_file)
        self._validate_no_active_accounting_import()
        existing = self.env["sire.import.batch"].search(
            [
                ("company_id", "=", self.period_id.company_id.id),
                ("file_hash", "=", parsed_file.file_hash),
            ],
            limit=1,
        )
        if existing:
            raise UserError(_("Este archivo ya fue importado en el lote %s.") % existing.display_name)

        with self.env.cr.savepoint():
            batch = self._create_batch(parsed_file)
            self._create_errors(batch, parsed_file.issues)
            if parsed_file.filename_info.registry_kind == "purchase":
                self._create_purchase_lines(batch, parsed_file)
            else:
                self._create_sales_lines(batch, parsed_file)
            self._finalize_period(batch, parsed_file)
        return {
            "type": "ir.actions.act_window",
            "res_model": "sire.import.batch",
            "view_mode": "form",
            "res_id": batch.id,
        }

    def _validate_file_context(self, parsed_file):
        if parsed_file.filename_info.registry_kind == "sales" and self.period_id.registry_type != "rvie":
            raise ValidationError(_("El archivo 14.1 corresponde a RVIE, no a RCE."))
        if parsed_file.filename_info.registry_kind == "purchase" and self.period_id.registry_type != "rce":
            raise ValidationError(_("El archivo 8.1 corresponde a RCE, no a RVIE."))
        self._validate_file_period(parsed_file)

    def _validate_file_period(self, parsed_file):
        expected_period = self.period_id.period_code
        found_periods = {parsed_file.filename_info.period_code}
        found_periods.update(
            line.normalized.get("period_code")
            for line in parsed_file.valid_lines
            if line.normalized.get("period_code")
        )
        found_periods.discard("")
        if found_periods and found_periods != {expected_period}:
            raise ValidationError(
                _(
                    "El archivo corresponde al periodo %(file_period)s, pero el periodo seleccionado es %(period)s. "
                    "Adjunta el archivo del mismo anio y mes."
                )
                % {
                    "file_period": ", ".join(sorted(found_periods)),
                    "period": expected_period,
                }
            )

    def _validate_no_active_accounting_import(self):
        existing = self.period_id.accounting_batch_id
        if not existing:
            existing = self.env["sire.import.batch"].search(
                [
                    ("period_id", "=", self.period_id.id),
                    ("line_model", "in", ("sire.sales.accounting.line", "sire.purchase.accounting.line")),
                ],
                limit=1,
            )
        if existing:
            raise UserError(
                _(
                    "Ya existe un archivo contable importado para este periodo: %s. "
                    "Eliminalo desde la pestana Importaciones antes de adjuntar uno nuevo."
                )
                % existing.filename
            )

    def _create_batch(self, parsed_file):
        invalid_rows = len([line for line in parsed_file.lines if line.has_errors])
        warning_rows = len([line for line in parsed_file.lines if line.has_warnings and not line.has_errors])
        state = "imported"
        if invalid_rows:
            state = "imported_with_warnings"
        elif warning_rows:
            state = "imported_with_warnings"
        return self.env["sire.import.batch"].create(
            {
                "company_id": self.period_id.company_id.id,
                "period_id": self.period_id.id,
                "filename": self.filename,
                "file_data": self.file_data,
                "file_hash": parsed_file.file_hash,
                "file_encoding": parsed_file.encoding,
                "book_code": parsed_file.filename_info.book_code,
                "format_version": "14.1" if parsed_file.filename_info.book_code == "140100" else "8.1",
                "total_rows": len(parsed_file.lines),
                "valid_rows": len(parsed_file.valid_lines),
                "warning_rows": warning_rows,
                "invalid_rows": invalid_rows,
                "state": state,
                "line_model": (
                    "sire.purchase.accounting.line"
                    if parsed_file.filename_info.registry_kind == "purchase"
                    else "sire.sales.accounting.line"
                ),
                "error_summary": self._build_error_summary(parsed_file.issues),
            }
        )

    def _create_errors(self, batch, issues):
        values = [
            {
                "batch_id": batch.id,
                "line_number": issue.line_number,
                "level": issue.level,
                "code": issue.code,
                "message": issue.message,
                "raw_text": issue.raw_text,
            }
            for issue in issues
        ]
        if values:
            self.env["sire.import.error"].create(values)

    def _create_sales_lines(self, batch, parsed_file):
        values = []
        for line in parsed_file.valid_lines:
            validation_messages = "\n".join(issue.message for issue in line.issues)
            normalized = line.normalized
            values.append(
                {
                    "period_id": self.period_id.id,
                    "batch_id": batch.id,
                    "source_line_number": line.line_number,
                    "source_raw_text": line.raw_text,
                    "source_hash": normalized.get("source_hash"),
                    "cuo": normalized.get("cuo"),
                    "entry_sequence": normalized.get("entry_sequence"),
                    "issue_date": normalized.get("issue_date") or False,
                    "due_date": normalized.get("due_date") or False,
                    "document_type": normalized.get("document_type"),
                    "series": normalized.get("series"),
                    "number": normalized.get("number"),
                    "customer_document_type": normalized.get("customer_document_type"),
                    "customer_document_number": normalized.get("customer_document_number"),
                    "customer_name": normalized.get("customer_name"),
                    "currency_code": normalized.get("currency_code"),
                    "exchange_rate": normalized.get("exchange_rate"),
                    "export_amount": normalized.get("export_amount"),
                    "taxable_base": normalized.get("taxable_base"),
                    "exempt_amount": normalized.get("exempt_amount"),
                    "unaffected_amount": normalized.get("unaffected_amount"),
                    "igv_amount": normalized.get("igv_amount"),
                    "non_taxable_amount": normalized.get("non_taxable_amount"),
                    "isc_amount": normalized.get("isc_amount"),
                    "other_tax_amount": normalized.get("other_tax_amount"),
                    "total_amount": normalized.get("total_amount"),
                    "original_document_date": normalized.get("original_document_date") or False,
                    "original_document_type": normalized.get("original_document_type"),
                    "original_document_series": normalized.get("original_document_series"),
                    "original_document_number": normalized.get("original_document_number"),
                    "normalized_key": normalized.get("normalized_key"),
                    "record_state": normalized.get("record_state"),
                    "validation_state": "warning" if line.has_warnings else "valid",
                    "validation_messages": validation_messages,
                }
            )
        if values:
            self.env["sire.sales.accounting.line"].create(values)

    def _create_purchase_lines(self, batch, parsed_file):
        values = []
        for line in parsed_file.valid_lines:
            validation_messages = "\n".join(issue.message for issue in line.issues)
            normalized = line.normalized
            values.append(
                {
                    "period_id": self.period_id.id,
                    "batch_id": batch.id,
                    "source_line_number": line.line_number,
                    "source_raw_text": line.raw_text,
                    "source_hash": normalized.get("source_hash"),
                    "cuo": normalized.get("cuo"),
                    "entry_sequence": normalized.get("entry_sequence"),
                    "issue_date": normalized.get("issue_date") or False,
                    "due_date": normalized.get("due_date") or False,
                    "document_type": normalized.get("document_type"),
                    "series": normalized.get("series"),
                    "purchase_year": normalized.get("purchase_year"),
                    "number": normalized.get("number"),
                    "final_number": normalized.get("final_number"),
                    "supplier_document_type": normalized.get("supplier_document_type"),
                    "supplier_document_number": normalized.get("supplier_document_number"),
                    "supplier_name": normalized.get("supplier_name"),
                    "currency_code": normalized.get("currency_code"),
                    "exchange_rate": normalized.get("exchange_rate"),
                    "taxable_base": normalized.get("taxable_base"),
                    "igv_amount": normalized.get("igv_amount"),
                    "non_taxable_amount": normalized.get("non_taxable_amount"),
                    "taxable_base_dg": normalized.get("taxable_base_dg"),
                    "igv_dg": normalized.get("igv_dg"),
                    "taxable_base_dgng": normalized.get("taxable_base_dgng"),
                    "igv_dgng": normalized.get("igv_dgng"),
                    "taxable_base_dng": normalized.get("taxable_base_dng"),
                    "igv_dng": normalized.get("igv_dng"),
                    "non_taxed_amount": normalized.get("non_taxed_amount"),
                    "isc_amount": normalized.get("isc_amount"),
                    "icbper_amount": normalized.get("icbper_amount"),
                    "other_tax_amount": normalized.get("other_tax_amount"),
                    "total_amount": normalized.get("total_amount"),
                    "original_document_date": normalized.get("original_document_date") or False,
                    "original_document_type": normalized.get("original_document_type"),
                    "original_document_series": normalized.get("original_document_series"),
                    "original_document_number": normalized.get("original_document_number"),
                    "normalized_key": normalized.get("normalized_key"),
                    "record_state": normalized.get("record_state"),
                    "validation_state": "warning" if line.has_warnings else "valid",
                    "validation_messages": validation_messages,
                }
            )
        if values:
            self.env["sire.purchase.accounting.line"].create(values)

    def _finalize_period(self, batch, parsed_file):
        self.period_id.write(
            {
                "accounting_batch_id": batch.id,
                "total_accounting_records": len(parsed_file.valid_lines),
                "state": "file_imported",
            }
        )
        self.period_id.message_post(
            body=_("Archivo PLE importado: %s (%s filas validas).")
            % (self.filename, len(parsed_file.valid_lines))
        )

    def _build_error_summary(self, issues):
        if not issues:
            return False
        return "\n".join(
            "Linea %s [%s] %s: %s"
            % (issue.line_number, issue.level, issue.code, issue.message)
            for issue in issues[:50]
        )
