import base64
import hashlib
import io
import zipfile

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.l10n_pe_sire_ple_import.models.ple_parser import (
    PleFileParser,
    PleParserError,
)


class SireSunatProposalImportWizard(models.TransientModel):
    _name = "sire.sunat.proposal.import.wizard"
    _description = "Importar propuesta SUNAT SIRE"

    period_id = fields.Many2one("sire.period", string="Periodo", required=True)
    file_data = fields.Binary(string="Archivo SUNAT ZIP/TXT", required=True)
    filename = fields.Char(string="Nombre de archivo", required=True)

    def action_import_file(self):
        self.ensure_one()
        proposal = self._import_file()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sire.sunat.proposal",
            "view_mode": "form",
            "res_id": proposal.id,
        }

    def action_import_downloaded_proposal(self, proposal):
        self.ensure_one()
        return self._import_file(existing_proposal=proposal)

    def _import_file(self, existing_proposal=False):
        raw_content = base64.b64decode(self.file_data or b"")
        txt_filename, txt_content = self._extract_txt_content(raw_content)
        try:
            parsed_file = PleFileParser().parse(txt_filename, txt_content)
        except PleParserError as error:
            if "nombre del archivo PLE" not in str(error):
                raise UserError(str(error)) from error
            fallback_filename = self._build_fallback_filename(txt_filename)
            try:
                parsed_file = PleFileParser().parse(fallback_filename, txt_content)
            except PleParserError as retry_error:
                raise UserError(str(retry_error)) from retry_error

        self._validate_file_context(parsed_file)
        self._validate_no_active_sunat_import(existing_proposal)
        zip_hash = hashlib.sha256(raw_content).hexdigest()
        existing = self.env["sire.sunat.proposal"].search(
            [
                ("period_id", "=", self.period_id.id),
                ("file_hash", "=", zip_hash),
                ("id", "!=", existing_proposal.id if existing_proposal else 0),
            ],
            limit=1,
        )
        if existing:
            raise UserError(_("Esta propuesta SUNAT ya fue importada en la version %s.") % existing.proposal_version)

        with self.env.cr.savepoint():
            proposal = self._create_proposal(parsed_file, raw_content, txt_content, txt_filename, zip_hash, existing_proposal)
            batch = self._create_batch(parsed_file)
            self._create_errors(batch, parsed_file.issues)
            if parsed_file.filename_info.registry_kind == "purchase":
                self._create_purchase_sunat_lines(batch, proposal, parsed_file)
            else:
                self._create_sales_sunat_lines(batch, proposal, parsed_file)
            self._finalize_period(proposal, parsed_file)
        return proposal

    def _extract_txt_content(self, raw_content):
        if zipfile.is_zipfile(io.BytesIO(raw_content)):
            with zipfile.ZipFile(io.BytesIO(raw_content)) as archive:
                txt_names = [
                    name
                    for name in archive.namelist()
                    if not name.endswith("/") and name.lower().endswith(".txt")
                ]
                if not txt_names:
                    raise UserError(_("El ZIP SUNAT no contiene un archivo TXT."))
                txt_name = txt_names[0]
                return txt_name.split("/")[-1], archive.read(txt_name)
        return self.filename, raw_content

    def _build_fallback_filename(self, txt_filename):
        company_ruc = (self.period_id.company_id.vat or "00000000000").strip()[:11].zfill(11)
        book_code = "080400" if self.period_id.registry_type == "rce" else "140400"
        extension = ".txt" if (txt_filename or "").lower().endswith(".txt") else ".txt"
        return "LE%s%s%s00%s0001EXP2%s" % (
            company_ruc,
            self.period_id.year,
            self.period_id.month,
            book_code,
            extension,
        )

    def _validate_file_context(self, parsed_file):
        if parsed_file.filename_info.registry_kind == "sales" and self.period_id.registry_type != "rvie":
            raise ValidationError(_("La propuesta importada debe corresponder a RVIE."))
        if parsed_file.filename_info.registry_kind == "purchase" and self.period_id.registry_type != "rce":
            raise ValidationError(_("La propuesta importada debe corresponder a RCE."))
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
                    "La propuesta SUNAT corresponde al periodo %(file_period)s, pero el periodo seleccionado es %(period)s. "
                    "Adjunta o sincroniza la propuesta del mismo anio y mes."
                )
                % {
                    "file_period": ", ".join(sorted(found_periods)),
                    "period": expected_period,
                }
            )

    def _validate_no_active_sunat_import(self, existing_proposal=False):
        existing_batch = self.env["sire.import.batch"].search(
            [
                ("period_id", "=", self.period_id.id),
                ("line_model", "in", ("sire.sales.sunat.line", "sire.purchase.sunat.line")),
            ],
            limit=1,
        )
        if existing_batch:
            raise UserError(
                _(
                    "Ya existe una propuesta SUNAT importada para este periodo: %s. "
                    "Eliminala desde la pestana Importaciones antes de adjuntar una nueva."
                )
                % existing_batch.filename
            )
        active_proposal = self.period_id.sunat_proposal_id
        if active_proposal and active_proposal != existing_proposal and active_proposal.state in ("downloaded", "parsed", "empty"):
            raise UserError(
                _(
                    "Ya existe una propuesta SUNAT activa para este periodo. "
                    "Eliminala desde la pestana Importaciones antes de adjuntar una nueva."
                )
            )

    def _create_proposal(self, parsed_file, raw_content, txt_content, txt_filename, zip_hash, existing_proposal=False):
        values = {
            "downloaded_at": fields.Datetime.now(),
            "source_filename": self.filename,
            "zip_file": base64.b64encode(raw_content),
            "txt_file": base64.b64encode(txt_content),
            "file_hash": zip_hash,
            "record_count": len(parsed_file.valid_lines),
            "state": "parsed",
        }
        if existing_proposal:
            existing_proposal.write(values)
            return existing_proposal
        last = self.env["sire.sunat.proposal"].search(
            [("period_id", "=", self.period_id.id)],
            order="proposal_version desc",
            limit=1,
        )
        return self.env["sire.sunat.proposal"].create(
            {
                "period_id": self.period_id.id,
                "proposal_version": (last.proposal_version or 0) + 1,
                **values,
            }
        )

    def _create_batch(self, parsed_file):
        invalid_rows = len([line for line in parsed_file.lines if line.has_errors])
        warning_rows = len([line for line in parsed_file.lines if line.has_warnings and not line.has_errors])
        return self.env["sire.import.batch"].create(
            {
                "company_id": self.period_id.company_id.id,
                "period_id": self.period_id.id,
                "filename": self.filename,
                "file_data": self.file_data,
                "file_hash": parsed_file.file_hash,
                "file_encoding": parsed_file.encoding,
                "book_code": parsed_file.filename_info.book_code,
                "format_version": "14.4" if parsed_file.filename_info.book_code == "140400" else "8.4",
                "total_rows": len(parsed_file.lines),
                "valid_rows": len(parsed_file.valid_lines),
                "warning_rows": warning_rows,
                "invalid_rows": invalid_rows,
                "state": "imported_with_warnings" if invalid_rows or warning_rows else "imported",
                "line_model": (
                    "sire.purchase.sunat.line"
                    if parsed_file.filename_info.registry_kind == "purchase"
                    else "sire.sales.sunat.line"
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

    def _create_sales_sunat_lines(self, batch, proposal, parsed_file):
        values = []
        for line in parsed_file.valid_lines:
            validation_messages = "\n".join(issue.message for issue in line.issues)
            normalized = line.normalized
            values.append(
                {
                    "period_id": self.period_id.id,
                    "batch_id": batch.id,
                    "proposal_id": proposal.id,
                    "source_line_number": line.line_number,
                    "source_raw_text": line.raw_text,
                    "source_hash": normalized.get("source_hash"),
                    "cuo": normalized.get("cuo"),
                    "entry_sequence": normalized.get("entry_sequence"),
                    "car_sunat": normalized.get("car_sunat"),
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
            self.env["sire.sales.sunat.line"].create(values)

    def _create_purchase_sunat_lines(self, batch, proposal, parsed_file):
        values = []
        for line in parsed_file.valid_lines:
            validation_messages = "\n".join(issue.message for issue in line.issues)
            normalized = line.normalized
            values.append(
                {
                    "period_id": self.period_id.id,
                    "batch_id": batch.id,
                    "proposal_id": proposal.id,
                    "source_line_number": line.line_number,
                    "source_raw_text": line.raw_text,
                    "source_hash": normalized.get("source_hash"),
                    "cuo": normalized.get("cuo"),
                    "entry_sequence": normalized.get("entry_sequence"),
                    "car_sunat": normalized.get("car_sunat"),
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
                    "classification": normalized.get("classification"),
                    "car_original_indicator": normalized.get("car_original_indicator"),
                    "deduction_indicator": normalized.get("deduction_indicator"),
                    "deduction_amount": normalized.get("deduction_amount"),
                    "note_type": normalized.get("note_type"),
                    "inconsistency": normalized.get("inconsistency"),
                    "normalized_key": normalized.get("normalized_key"),
                    "record_state": normalized.get("record_state"),
                    "validation_state": "warning" if line.has_warnings else "valid",
                    "validation_messages": validation_messages,
                }
            )
        if values:
            self.env["sire.purchase.sunat.line"].create(values)

    def _finalize_period(self, proposal, parsed_file):
        self.period_id.write(
            {
                "sunat_proposal_id": proposal.id,
                "total_sunat_records": len(parsed_file.valid_lines),
                "state": "proposal_downloaded",
            }
        )
        self.period_id.message_post(
            body=_("Propuesta SUNAT importada manualmente: %s (%s filas validas).")
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
