import base64
import hashlib
import io
import zipfile

from odoo import fields, models, _
from odoo.exceptions import UserError

from .proposal_parser import ProposalParserError, PurchaseProposalParser


class SunatPurchaseProposalImportWizard(models.TransientModel):
    _name = "sunat.purchase.proposal.import.wizard"
    _description = "Importar propuesta de compras SUNAT"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    file = fields.Binary(string="Archivo ZIP o TXT", required=True)
    filename = fields.Char(required=True)
    compare_after_import = fields.Boolean(string="Comparar despues de importar", default=True)

    def action_import(self):
        self.ensure_one()
        raw_file = base64.b64decode(self.file)
        txt_name, txt_content = self._extract_txt(raw_file)
        file_hash = hashlib.sha256(txt_content).hexdigest()
        existing = self.env["sunat.purchase.proposal"].search(
            [("company_id", "=", self.company_id.id), ("source_hash", "=", file_hash)],
            limit=1,
        )
        if existing:
            raise UserError(_("El archivo ya fue importado en %s.") % existing.display_name)
        try:
            rows, issues = PurchaseProposalParser().parse(txt_content)
        except ProposalParserError as error:
            raise UserError(str(error)) from error
        periods = {row.pop("period") for row in rows}
        if len(periods) != 1:
            raise UserError(_("El archivo contiene mas de un periodo: %s") % ", ".join(sorted(periods)))
        period = periods.pop()
        proposal = self.env["sunat.purchase.proposal"].create(
            {
                "name": _("Propuesta RCE %s - %s") % (period, self.company_id.name),
                "company_id": self.company_id.id,
                "period": period,
                "source_filename": txt_name,
                "source_file": base64.b64encode(txt_content),
                "source_hash": file_hash,
                "state": "error" if issues else "imported",
            }
        )
        for row in rows:
            row["proposal_id"] = proposal.id
        self.env["sunat.purchase.proposal.line"].create(rows)
        if self.compare_after_import:
            return proposal.action_compare()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sunat.purchase.proposal",
            "res_id": proposal.id,
            "view_mode": "form",
        }

    def _extract_txt(self, raw_file):
        if not (self.filename or "").lower().endswith(".zip"):
            return self.filename, raw_file
        try:
            with zipfile.ZipFile(io.BytesIO(raw_file)) as archive:
                txt_names = [name for name in archive.namelist() if name.lower().endswith(".txt") and not name.endswith("/")]
                if len(txt_names) != 1:
                    raise UserError(_("El ZIP debe contener exactamente un archivo TXT."))
                return txt_names[0].rsplit("/", 1)[-1], archive.read(txt_names[0])
        except zipfile.BadZipFile as error:
            raise UserError(_("El archivo ZIP no es valido.")) from error

