import base64
import hashlib
import io
import json
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7
from PyPDF2 import PdfFileReader, PdfFileWriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EmployeeDocumentType(models.Model):
    _name = "employee.document.type"
    _description = "Tipo de Documento de Empleado"
    _order = "sequence, name"

    name = fields.Char(string="Nombre", required=True, translate=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    category = fields.Selection(
        selection=[
            ("basic", "Datos Basicos / Reclutamiento"),
            ("declaration", "Actas y Declaraciones"),
            ("sunat", "SUNAT / PLAME Obligatorio"),
            ("agreement", "Acuerdos"),
            ("sanction", "Sanciones"),
            ("termination", "Cese"),
            ("audit", "Auditoria"),
            ("other", "Otros"),
        ],
        default="other",
        required=True,
        string="Categoria",
    )
    required = fields.Boolean(string="Obligatorio", default=False)
    signature_required = fields.Boolean(string="Requiere firma por defecto")
    allow_history = fields.Boolean(
        string="Permite historico",
        default=True,
        help="Permite conservar cada archivo cargado como una entrada historica.",
    )
    legajo_document_count = fields.Integer(string="Legajos", compute="_compute_legajo_document_count")
    active = fields.Boolean(string="Activo", default=True)

    @api.model_create_multi
    def create(self, vals_list):
        document_types = super().create(vals_list)
        employees = self.env["hr.employee"].sudo().search([("active", "=", True)])
        employees._prepare_legajo_documents_for_types(document_types)
        return document_types

    def _compute_legajo_document_count(self):
        groups = self.env["employee.document.file"].read_group(
            [("document_type_id", "in", self.ids)],
            ["document_type_id"],
            ["document_type_id"],
        )
        counts = {group["document_type_id"][0]: group["document_type_id_count"] for group in groups}
        for document_type in self:
            document_type.legajo_document_count = counts.get(document_type.id, 0)

    def action_prepare_active_employee_legajos(self):
        employees = self.env["hr.employee"].sudo().search([("active", "=", True)])
        employees._prepare_legajo_documents_for_types(self)
        return self.action_view_legajo_documents()

    def action_view_legajo_documents(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Legajos",
            "res_model": "employee.document.file",
            "view_mode": "list,form",
            "domain": [("document_type_id", "in", self.ids)],
            "context": {
                "default_document_type_id": self[:1].id if len(self) == 1 else False,
                "search_default_group_employee": 1,
            },
        }


class EmployeeDocumentFile(models.Model):
    _name = "employee.document.file"
    _description = "Legajo de Empleado"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "employee_id, document_type_id, document_date desc, id desc"

    name = fields.Char(string="Nombre", required=True, tracking=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, ondelete="cascade", index=True)
    employee_user_id = fields.Many2one(string="Usuario del empleado", related="employee_id.user_id", store=True, index=True)
    employee_partner_id = fields.Many2one(string="Contacto del empleado", related="employee_id.user_id.partner_id", store=True, index=True)
    department_id = fields.Many2one(string="Departamento", related="employee_id.department_id", store=True, readonly=True)
    document_type_id = fields.Many2one("employee.document.type", string="Tipo de documento", required=True, ondelete="restrict")
    category = fields.Selection(string="Categoria", related="document_type_id.category", store=True, readonly=True)
    source_model = fields.Char(string="Modelo origen", readonly=True)
    source_res_id = fields.Integer(string="ID origen", readonly=True, index=True)
    document_date = fields.Date(string="Fecha documento")
    expiration_date = fields.Date(string="Fecha vencimiento")
    upload_date = fields.Datetime(string="Fecha carga", default=fields.Datetime.now, readonly=True)
    uploaded_by_id = fields.Many2one("res.users", string="Subido por", default=lambda self: self.env.user, readonly=True)
    file_data = fields.Binary(string="Archivo", attachment=True)
    file_name = fields.Char(string="Nombre de archivo")
    worker_signature_required = fields.Boolean(string="Requiere firma del trabajador", tracking=True)
    worker_signature_state = fields.Selection(
        selection=[
            ("not_required", "No requerida"),
            ("unsigned", "Pendiente"),
            ("signed", "Firmado"),
        ],
        default="not_required",
        required=True,
        tracking=True,
        string="Estado firma trabajador",
    )
    worker_signed_date = fields.Datetime(string="Fecha firma trabajador", readonly=True, tracking=True)
    worker_signed_by_id = fields.Many2one("res.users", string="Trabajador firmante", readonly=True)
    worker_signed_partner_id = fields.Many2one("res.partner", string="Contacto trabajador firmante", readonly=True)
    worker_signature_name = fields.Char(string="Nombre firma trabajador", readonly=True)
    worker_signature_hash = fields.Char(string="Hash firma trabajador", readonly=True, copy=False)
    signature_required = fields.Boolean(string="Requiere firma del encargado", tracking=True)
    signature_state = fields.Selection(
        selection=[
            ("not_required", "No requerida"),
            ("unsigned", "Pendiente"),
            ("signed", "Firmado"),
        ],
        default="not_required",
        required=True,
        tracking=True,
        string="Estado firma encargado",
    )
    signed_date = fields.Datetime(string="Fecha firma encargado", readonly=True, tracking=True)
    signed_by_id = fields.Many2one("res.users", string="Encargado firmante", readonly=True)
    signed_partner_id = fields.Many2one("res.partner", string="Contacto encargado firmante", readonly=True)
    signature_name = fields.Char(string="Nombre firma encargado", readonly=True)
    signature_hash = fields.Char(string="Hash firma encargado", readonly=True, copy=False)
    signature_certificate_subject = fields.Char(string="Sujeto del certificado", readonly=True)
    signature_certificate_issuer = fields.Char(string="Emisor del certificado", readonly=True)
    signature_attachment_name = fields.Char(string="Metodo / archivo de firma", readonly=True)
    history_ids = fields.One2many("employee.document.history", "legajo_id", string="Historico")
    history_count = fields.Integer(string="Historicos", compute="_compute_history_count")
    latest_history_id = fields.Many2one("employee.document.history", string="Ultimo historico", compute="_compute_latest_history", store=True)
    latest_upload_date = fields.Datetime(string="Ultima fecha de carga", related="latest_history_id.upload_date", store=True, readonly=True)
    notes = fields.Text(string="Notas")
    state = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("uploaded", "Cargado"),
            ("validated", "Validado"),
            ("rejected", "Rechazado"),
            ("expired", "Vencido"),
        ],
        default="pending",
        required=True,
        tracking=True,
        string="Estado",
    )

    @api.onchange("document_type_id", "employee_id")
    def _onchange_document_name(self):
        for document in self:
            if document.document_type_id and document.employee_id and not document.name:
                document.name = "%s - %s" % (document.document_type_id.name, document.employee_id.name)
            if document.document_type_id and not document.signature_required:
                document.signature_required = document.document_type_id.signature_required
                document.signature_state = "unsigned" if document.signature_required else "not_required"

    @api.onchange("signature_required")
    def _onchange_signature_required(self):
        for document in self:
            if document.signature_required and document.signature_state == "not_required":
                document.signature_state = "unsigned"
            if not document.signature_required and document.signature_state != "signed":
                document.signature_state = "not_required"

    @api.depends("history_ids")
    def _compute_history_count(self):
        for document in self:
            document.history_count = len(document.history_ids)

    @api.depends("history_ids.upload_date")
    def _compute_latest_history(self):
        for document in self:
            document.latest_history_id = document.history_ids[:1]

    @api.model_create_multi
    def create(self, vals_list):
        history_payloads = []
        for vals in vals_list:
            if not vals.get("name"):
                vals["name"] = self._get_default_document_name(vals)
            if vals.get("file_data") and not vals.get("state"):
                vals["state"] = "uploaded"
            if "signature_required" not in vals and vals.get("document_type_id"):
                document_type = self.env["employee.document.type"].browse(vals["document_type_id"])
                vals["signature_required"] = document_type.signature_required
            if vals.get("signature_required") and not vals.get("signature_state"):
                vals["signature_state"] = "unsigned"
            if vals.get("worker_signature_required") and not vals.get("worker_signature_state"):
                vals["worker_signature_state"] = "unsigned"
            history_payloads.append(self._extract_history_payload(vals))
        records = super().create(vals_list)
        for record, payload in zip(records, history_payloads):
            if payload:
                record._create_history_from_payload(payload)
        return records

    def write(self, vals):
        if "signature_required" in vals and "signature_state" not in vals:
            vals = dict(vals)
            if vals["signature_required"]:
                vals["signature_state"] = "unsigned"
            else:
                vals["signature_state"] = "not_required"
        if "worker_signature_required" in vals and "worker_signature_state" not in vals:
            vals = dict(vals)
            if vals["worker_signature_required"]:
                vals["worker_signature_state"] = "unsigned"
            else:
                vals["worker_signature_state"] = "not_required"
        history_payload = self._extract_history_payload(vals)
        if vals.get("file_data") and not vals.get("state"):
            vals = dict(vals)
            vals["state"] = "uploaded"
        result = super().write(vals)
        for document in self.filtered(lambda item: not item.name):
            document.name = document._get_default_document_name({})
        if history_payload:
            for document in self:
                document._create_history_from_payload(history_payload)
        return result

    def _get_default_document_name(self, vals):
        employee = self.env["hr.employee"].browse(vals.get("employee_id")) if vals.get("employee_id") else self.employee_id
        document_type = (
            self.env["employee.document.type"].browse(vals.get("document_type_id"))
            if vals.get("document_type_id")
            else self.document_type_id
        )
        if document_type and employee:
            return "%s - %s" % (document_type.name, employee.name)
        if document_type:
            return document_type.name
        if vals.get("file_name"):
            return vals["file_name"]
        return "Documento"

    def action_validate(self):
        self.write({"state": "validated"})

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_set_pending(self):
        self.write({"state": "pending"})

    def action_open_digital_signature_wizard(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Debe adjuntar un PDF antes de firmar digitalmente."))
        if self.signature_state == "signed":
            raise UserError(_("Este documento ya fue firmado."))
        user = self.env.user
        return {
            "type": "ir.actions.act_window",
            "name": _("Firmar PDF con certificado"),
            "res_model": "employee.document.digital.signature.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_document_id": self.id,
                "default_signer_name": user.digital_signature_name or user.name,
                "default_use_user_certificate": bool(user.digital_signature_certificate),
            },
        }

    def action_reset_signature(self):
        self.write(
            {
                "signature_state": "unsigned" if self.signature_required else "not_required",
                "signed_date": False,
                "signed_by_id": False,
                "signed_partner_id": False,
                "signature_name": False,
                "signature_hash": False,
                "signature_certificate_subject": False,
                "signature_certificate_issuer": False,
                "signature_attachment_name": False,
            }
        )

    def action_sign_pdf_with_user_certificate(self, signer_name=None, user=None):
        user = user or self.env.user
        certificate_file, certificate_password, default_name = user.sudo()._get_digital_signature_credentials()
        return self.action_sign_pdf_with_certificate(
            signer_name or default_name or user.name,
            certificate_file,
            certificate_password,
            user=user,
        )

    def action_sign_pdf_with_certificate(self, signer_name, certificate_file, certificate_password=None, user=None):
        user = user or self.env.user
        signer_name = (signer_name or "").strip()
        if not signer_name:
            raise UserError(_("Debe ingresar el nombre del firmante."))
        if not certificate_file:
            raise UserError(_("Debe configurar un certificado digital en su usuario o adjuntar uno para esta firma."))

        for document in self:
            document._check_can_digitally_sign(user)
            pdf_content = document._get_pdf_content_for_signature()
            signed_date = self.env.context.get("forced_digital_signed_date") or fields.Datetime.now()
            signed_pdf, signature_name, certificate_info = document._build_signed_pdf_with_certificate(
                pdf_content,
                certificate_file,
                certificate_password,
                signer_name,
                signed_date,
            )
            signed_file_name = document._get_signed_pdf_filename()
            signed_pdf_b64 = base64.b64encode(signed_pdf)
            signature_hash = document._build_digital_signature_hash(
                signer_name,
                user,
                signed_date,
                pdf_content,
                signed_pdf,
                signature_name,
                certificate_info,
            )
            signature_values = {
                "file_data": signed_pdf_b64,
                "file_name": signed_file_name,
                "state": "validated",
                "signature_required": True,
                "signature_state": "signed",
                "signed_date": signed_date,
                "signed_by_id": user.id,
                "signed_partner_id": user.partner_id.id,
                "signature_name": signer_name,
                "signature_hash": signature_hash,
                "signature_certificate_subject": certificate_info.get("subject"),
                "signature_certificate_issuer": certificate_info.get("issuer"),
                "signature_attachment_name": signature_name,
            }
            document.with_context(skip_document_history=True).sudo().write(signature_values)
            document.sudo()._create_history_from_payload(
                dict(
                    signature_values,
                    name=document.name,
                    document_date=document.document_date or fields.Date.context_today(document),
                    notes=_("PDF firmado digitalmente con certificado."),
                )
            )
            document.sudo().message_post(body=_("Documento firmado digitalmente por %s.") % signer_name)
        return True

    def _check_can_digitally_sign(self, user):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Debe adjuntar un PDF antes de firmar digitalmente."))
        if self.signature_state == "signed":
            raise UserError(_("Este documento ya fue firmado."))
        if user.has_group("hr.group_hr_user"):
            return True
        if self.env.context.get("allow_designated_digital_signer"):
            return True
        if self.employee_user_id == user or self.employee_partner_id == user.partner_id:
            return True
        raise UserError(_("No tiene permisos para firmar este documento."))

    def _get_pdf_content_for_signature(self):
        self.ensure_one()
        try:
            pdf_content = base64.b64decode(self.file_data or b"")
        except Exception as error:
            raise UserError(_("No se pudo leer el archivo PDF adjunto.")) from error
        if not pdf_content.startswith(b"%PDF"):
            raise UserError(_("El archivo adjunto debe ser un PDF para firmarlo digitalmente."))
        return pdf_content

    def _build_signed_pdf_with_certificate(
        self,
        pdf_content,
        certificate_file,
        certificate_password=None,
        signer_name=None,
        signed_date=None,
    ):
        try:
            return self._build_pdf_with_pades_signature(
                pdf_content,
                certificate_file,
                certificate_password,
                signer_name,
                signed_date,
            )
        except ImportError:
            return self._build_pdf_with_pkcs7_attachment(
                pdf_content,
                certificate_file,
                certificate_password,
                signer_name,
                signed_date,
            )

    def _build_pdf_with_pades_signature(
        self,
        pdf_content,
        certificate_file,
        certificate_password=None,
        signer_name=None,
        signed_date=None,
    ):
        self.ensure_one()
        try:
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.sign import fields as sign_fields
            from pyhanko.sign import signers
        except ImportError as error:
            raise error

        certificate_bytes = base64.b64decode(certificate_file or b"")
        password = certificate_password.encode("utf-8") if certificate_password else None
        certificate_info = self._get_certificate_info(certificate_bytes, password)
        field_name = "FirmaDigital%s" % self.id
        output = io.BytesIO()
        with tempfile.NamedTemporaryFile(suffix=".p12") as certificate_temp:
            certificate_temp.write(certificate_bytes)
            certificate_temp.flush()
            try:
                signer = signers.SimpleSigner.load_pkcs12(
                    certificate_temp.name,
                    passphrase=password,
                )
                metadata = signers.PdfSignatureMetadata(
                    field_name=field_name,
                    reason=self.env.context.get("digital_signature_reason") or "Firma digital de documento laboral",
                    location="Odoo",
                    name=signer_name or "",
                )
                writer = IncrementalPdfFileWriter(io.BytesIO(pdf_content))
                signers.sign_pdf(
                    writer,
                    signature_meta=metadata,
                    signer=signer,
                    existing_fields_only=False,
                    output=output,
                    new_field_spec=sign_fields.SigFieldSpec(sig_field_name=field_name),
                )
            except Exception as error:
                raise UserError(_("No se pudo firmar el PDF con pyHanko. Verifique que el PDF y el certificado sean validos.")) from error
        return output.getvalue(), "PAdES", certificate_info

    def _build_pdf_with_pkcs7_attachment(
        self,
        pdf_content,
        certificate_file,
        certificate_password=None,
        signer_name=None,
        signed_date=None,
    ):
        self.ensure_one()
        certificate_bytes = base64.b64decode(certificate_file or b"")
        password = certificate_password.encode("utf-8") if certificate_password else None
        try:
            private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                certificate_bytes,
                password,
            )
        except Exception as error:
            raise UserError(_("No se pudo abrir el certificado. Verifique el archivo .p12/.pfx y la contrasena.")) from error
        if not private_key or not certificate:
            raise UserError(_("El certificado no contiene llave privada utilizable para firmar."))

        signature = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(pdf_content)
            .add_signer(certificate, private_key, hashes.SHA256())
            .sign(
                serialization.Encoding.DER,
                [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
            )
        )
        certificate_info = self._get_certificate_info(certificate_bytes, password)
        if additional_certificates:
            for extra_certificate in additional_certificates:
                if isinstance(extra_certificate, x509.Certificate):
                    certificate_info.setdefault("chain", []).append(extra_certificate.subject.rfc4514_string())

        reader = PdfFileReader(io.BytesIO(pdf_content))
        writer = PdfFileWriter()
        for page_number in range(reader.getNumPages()):
            writer.addPage(reader.getPage(page_number))
        signature_filename = "%s.p7s" % self._get_signature_attachment_basename()
        metadata = {
            "/SignedBy": signer_name or "",
            "/SignedDate": str(signed_date or ""),
            "/SignatureAttachment": signature_filename,
            "/SignatureReason": self.env.context.get("digital_signature_reason") or "Firma digital de documento laboral",
            "/CertificateSubject": certificate_info["subject"],
        }
        try:
            existing_metadata = reader.getDocumentInfo() or {}
            metadata.update({key: str(value) for key, value in existing_metadata.items() if key and value})
        except Exception:
            pass
        writer.addMetadata(metadata)
        writer.addAttachment(signature_filename, signature)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue(), signature_filename, certificate_info

    def _get_certificate_info(self, certificate_bytes, password=None):
        try:
            private_key, certificate, _additional_certificates = pkcs12.load_key_and_certificates(
                certificate_bytes,
                password,
            )
        except Exception as error:
            raise UserError(_("No se pudo abrir el certificado. Verifique el archivo .p12/.pfx y la contrasena.")) from error
        if not private_key or not certificate:
            raise UserError(_("El certificado no contiene llave privada utilizable para firmar."))
        return {
            "subject": certificate.subject.rfc4514_string(),
            "issuer": certificate.issuer.rfc4514_string(),
            "serial_number": str(certificate.serial_number),
        }

    def _get_signature_attachment_basename(self):
        self.ensure_one()
        base_name = (self.file_name or self.name or "documento").rsplit(".", 1)[0]
        return "%s_firma_digital" % base_name

    def _get_signed_pdf_filename(self):
        self.ensure_one()
        base_name = (self.file_name or self.name or "documento").rsplit(".", 1)[0]
        return "%s_firmado.pdf" % base_name

    def _build_digital_signature_hash(
        self,
        signer_name,
        user,
        signed_date,
        original_pdf,
        signed_pdf,
        signature_attachment_name,
        certificate_info,
    ):
        self.ensure_one()
        payload = {
            "document_id": self.id,
            "document_name": self.name,
            "employee_id": self.employee_id.id,
            "signer_name": signer_name,
            "signed_date": signed_date,
            "user_id": user.id,
            "partner_id": user.partner_id.id,
            "original_pdf_sha256": hashlib.sha256(original_pdf).hexdigest(),
            "signed_pdf_sha256": hashlib.sha256(signed_pdf).hexdigest(),
            "signature_attachment_name": signature_attachment_name,
            "certificate": certificate_info,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _extract_history_payload(self, vals):
        if self.env.context.get("skip_document_history") or not vals.get("file_data"):
            return False
        return {
            "file_data": vals.get("file_data"),
            "file_name": vals.get("file_name"),
            "document_date": vals.get("document_date"),
            "expiration_date": vals.get("expiration_date"),
            "notes": vals.get("notes"),
            "state": vals.get("state") or "uploaded",
        }

    def _create_history_from_payload(self, payload):
        self.ensure_one()
        if not self.document_type_id.allow_history:
            return False
        history_values = {
            "legajo_id": self.id,
            "name": payload.get("name") or payload.get("file_name") or self.name,
            "period": payload.get("period") or False,
            "document_date": payload.get("document_date") or self.document_date,
            "expiration_date": payload.get("expiration_date") or self.expiration_date,
            "file_data": payload["file_data"],
            "file_name": payload.get("file_name") or self.file_name,
            "state": payload.get("state") or "uploaded",
            "notes": payload.get("notes") or self.notes,
            "source_model": payload.get("source_model") or self.source_model,
            "source_res_id": payload.get("source_res_id") or self.source_res_id,
            "worker_signature_required": payload.get("worker_signature_required", self.worker_signature_required),
            "worker_signature_state": payload.get("worker_signature_state") or self.worker_signature_state,
            "worker_signed_date": payload.get("worker_signed_date") or self.worker_signed_date,
            "worker_signed_by_id": payload.get("worker_signed_by_id") or self.worker_signed_by_id.id,
            "worker_signed_partner_id": payload.get("worker_signed_partner_id") or self.worker_signed_partner_id.id,
            "worker_signature_name": payload.get("worker_signature_name") or self.worker_signature_name,
            "worker_signature_hash": payload.get("worker_signature_hash") or self.worker_signature_hash,
            "signature_required": payload.get("signature_required", self.signature_required),
            "signature_state": payload.get("signature_state") or self.signature_state,
            "signed_date": payload.get("signed_date") or self.signed_date,
            "signed_by_id": payload.get("signed_by_id") or self.signed_by_id.id,
            "signed_partner_id": payload.get("signed_partner_id") or self.signed_partner_id.id,
            "signature_name": payload.get("signature_name") or self.signature_name,
            "signature_hash": payload.get("signature_hash") or self.signature_hash,
            "signature_certificate_subject": payload.get("signature_certificate_subject") or self.signature_certificate_subject,
            "signature_certificate_issuer": payload.get("signature_certificate_issuer") or self.signature_certificate_issuer,
            "signature_attachment_name": payload.get("signature_attachment_name") or self.signature_attachment_name,
        }
        existing = False
        if history_values["source_model"] and history_values["source_res_id"]:
            existing = self.env["employee.document.history"].sudo().search(
                [
                    ("source_model", "=", history_values["source_model"]),
                    ("source_res_id", "=", history_values["source_res_id"]),
                ],
                limit=1,
            )
        if existing:
            existing.write(history_values)
            history = existing
        else:
            history = self.env["employee.document.history"].sudo().create(history_values)
        self.with_context(skip_document_history=True).sudo().write(
            {
                "file_data": payload["file_data"],
                "file_name": payload.get("file_name") or self.file_name,
                "document_date": payload.get("document_date") or self.document_date,
                "expiration_date": payload.get("expiration_date") or self.expiration_date,
                "state": "validated" if history.state == "validated" else "uploaded",
                "source_model": payload.get("source_model") or self.source_model,
                "source_res_id": payload.get("source_res_id") or self.source_res_id,
                "worker_signature_required": payload.get("worker_signature_required", self.worker_signature_required),
                "worker_signature_state": payload.get("worker_signature_state") or self.worker_signature_state,
                "worker_signed_date": payload.get("worker_signed_date") or self.worker_signed_date,
                "worker_signed_by_id": payload.get("worker_signed_by_id") or self.worker_signed_by_id.id,
                "worker_signed_partner_id": payload.get("worker_signed_partner_id") or self.worker_signed_partner_id.id,
                "worker_signature_name": payload.get("worker_signature_name") or self.worker_signature_name,
                "worker_signature_hash": payload.get("worker_signature_hash") or self.worker_signature_hash,
                "signature_required": payload.get("signature_required", self.signature_required),
                "signature_state": payload.get("signature_state") or self.signature_state,
                "signed_date": payload.get("signed_date") or self.signed_date,
                "signed_by_id": payload.get("signed_by_id") or self.signed_by_id.id,
                "signed_partner_id": payload.get("signed_partner_id") or self.signed_partner_id.id,
                "signature_name": payload.get("signature_name") or self.signature_name,
                "signature_hash": payload.get("signature_hash") or self.signature_hash,
                "signature_certificate_subject": payload.get("signature_certificate_subject") or self.signature_certificate_subject,
                "signature_certificate_issuer": payload.get("signature_certificate_issuer") or self.signature_certificate_issuer,
                "signature_attachment_name": payload.get("signature_attachment_name") or self.signature_attachment_name,
            }
        )
        return history


class EmployeeDocumentHistory(models.Model):
    _name = "employee.document.history"
    _description = "Historico de Documento de Empleado"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "upload_date desc, id desc"

    name = fields.Char(string="Nombre", required=True)
    legajo_id = fields.Many2one("employee.document.file", string="Legajo", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one(string="Empleado", related="legajo_id.employee_id", store=True, readonly=True, index=True)
    employee_user_id = fields.Many2one(related="legajo_id.employee_user_id", store=True, readonly=True, index=True)
    employee_partner_id = fields.Many2one(related="legajo_id.employee_partner_id", store=True, readonly=True, index=True)
    document_type_id = fields.Many2one(string="Tipo de documento", related="legajo_id.document_type_id", store=True, readonly=True, index=True)
    category = fields.Selection(string="Categoria", related="legajo_id.category", store=True, readonly=True)
    period = fields.Char(string="Periodo")
    document_date = fields.Date(string="Fecha documento")
    expiration_date = fields.Date(string="Fecha vencimiento")
    upload_date = fields.Datetime(string="Fecha carga", default=fields.Datetime.now, readonly=True)
    uploaded_by_id = fields.Many2one("res.users", string="Subido por", default=lambda self: self.env.user, readonly=True)
    file_data = fields.Binary(string="Archivo", attachment=True, required=True)
    file_name = fields.Char(string="Nombre de archivo")
    worker_signature_required = fields.Boolean(string="Requiere firma del trabajador", readonly=True)
    worker_signature_state = fields.Selection(
        selection=[
            ("not_required", "No requerida"),
            ("unsigned", "Pendiente"),
            ("signed", "Firmado"),
        ],
        default="not_required",
        readonly=True,
        string="Estado firma trabajador",
    )
    worker_signed_date = fields.Datetime(string="Fecha firma trabajador", readonly=True)
    worker_signed_by_id = fields.Many2one("res.users", string="Trabajador firmante", readonly=True)
    worker_signed_partner_id = fields.Many2one("res.partner", string="Contacto trabajador firmante", readonly=True)
    worker_signature_name = fields.Char(string="Nombre firma trabajador", readonly=True)
    worker_signature_hash = fields.Char(string="Hash firma trabajador", readonly=True, copy=False)
    signature_required = fields.Boolean(string="Requiere firma del encargado", readonly=True)
    signature_state = fields.Selection(
        selection=[
            ("not_required", "No requerida"),
            ("unsigned", "Pendiente"),
            ("signed", "Firmado"),
        ],
        default="not_required",
        readonly=True,
        string="Estado firma encargado",
    )
    signed_date = fields.Datetime(string="Fecha firma encargado", readonly=True)
    signed_by_id = fields.Many2one("res.users", string="Encargado firmante", readonly=True)
    signed_partner_id = fields.Many2one("res.partner", string="Contacto encargado firmante", readonly=True)
    signature_name = fields.Char(string="Nombre firma encargado", readonly=True)
    signature_hash = fields.Char(string="Hash firma encargado", readonly=True, copy=False)
    signature_certificate_subject = fields.Char(string="Sujeto del certificado", readonly=True)
    signature_certificate_issuer = fields.Char(string="Emisor del certificado", readonly=True)
    signature_attachment_name = fields.Char(string="Metodo / archivo de firma", readonly=True)
    source_model = fields.Char(string="Modelo origen", readonly=True)
    source_res_id = fields.Integer(string="ID origen", readonly=True, index=True)
    notes = fields.Text(string="Notas")
    state = fields.Selection(
        selection=[
            ("uploaded", "Cargado"),
            ("validated", "Validado"),
            ("rejected", "Rechazado"),
        ],
        default="uploaded",
        required=True,
        tracking=True,
        string="Estado",
    )

    def action_validate(self):
        self.write({"state": "validated"})
        self.mapped("legajo_id").write({"state": "validated"})

    def action_reject(self):
        self.write({"state": "rejected"})


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    legajo_document_ids = fields.One2many("employee.document.file", "employee_id", string="Legajos")
    legajo_document_count = fields.Integer(compute="_compute_legajo_document_count")

    def _compute_legajo_document_count(self):
        for employee in self:
            employee.legajo_document_count = len(employee.legajo_document_ids)

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.action_prepare_legajo_documents()
        return employees

    def action_view_legajo_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Legajos",
            "res_model": "employee.document.file",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.id)],
            "context": {
                "default_employee_id": self.id,
                "search_default_employee_id": self.id,
            },
        }

    def action_prepare_legajo_documents(self):
        document_types = self.env["employee.document.type"].sudo().search([("active", "=", True)])
        self._prepare_legajo_documents_for_types(document_types)
        if len(self) == 1:
            return self.action_view_legajo_documents()
        return True

    def _prepare_legajo_documents_for_types(self, document_types):
        DocumentType = self.env["employee.document.type"].sudo()
        DocumentFile = self.env["employee.document.file"].sudo()
        document_types = document_types or DocumentType.search([("active", "=", True)])
        for employee in self:
            for document_type in document_types:
                existing = DocumentFile.search(
                    [
                        ("employee_id", "=", employee.id),
                        ("document_type_id", "=", document_type.id),
                    ],
                    limit=1,
                )
                if existing:
                    continue
                DocumentFile.create(
                    {
                        "employee_id": employee.id,
                        "document_type_id": document_type.id,
                        "state": "pending",
                        "signature_required": document_type.signature_required,
                        "signature_state": "unsigned" if document_type.signature_required else "not_required",
                    }
                )
        return True


class EmployeeDocumentDigitalSignatureWizard(models.TransientModel):
    _name = "employee.document.digital.signature.wizard"
    _description = "Asistente de Firma Digital de Legajo"

    document_id = fields.Many2one("employee.document.file", string="Documento", required=True, readonly=True)
    signer_name = fields.Char(string="Nombre del firmante", required=True)
    use_user_certificate = fields.Boolean(string="Usar certificado de mi usuario", default=True)
    certificate_file = fields.Binary(string="Certificado .p12/.pfx")
    certificate_filename = fields.Char(string="Nombre del certificado")
    certificate_password = fields.Char(string="Contrasena del certificado", password=True)

    def action_sign_document(self):
        self.ensure_one()
        if self.use_user_certificate:
            self.document_id.action_sign_pdf_with_user_certificate(self.signer_name, user=self.env.user)
        else:
            self.document_id.action_sign_pdf_with_certificate(
                self.signer_name,
                self.certificate_file,
                self.certificate_password,
                user=self.env.user,
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Firma digital"),
                "message": _("El PDF fue firmado digitalmente con el certificado."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class ResUsers(models.Model):
    _inherit = "res.users"

    digital_signature_certificate = fields.Binary(
        string="Certificado digital .p12/.pfx",
        attachment=True,
        groups="base.group_system",
    )
    digital_signature_certificate_filename = fields.Char(
        string="Nombre del certificado",
        groups="base.group_system",
    )
    digital_signature_password = fields.Char(
        string="Contrasena del certificado",
        password=True,
        groups="base.group_system",
    )
    digital_signature_name = fields.Char(
        string="Nombre para firma digital",
        groups="base.group_system",
    )
    digital_signature_job_id = fields.Many2one(
        "hr.job",
        string="Cargo relacionado",
        groups="base.group_system",
    )
    digital_signature_position = fields.Char(
        string="Cargo para firma digital",
        groups="base.group_system",
    )
    digital_signature_reason = fields.Char(
        string="Motivo por defecto",
        default="BOLETA DE PAGO",
        groups="base.group_system",
    )
    digital_signature_image = fields.Binary(
        string="Imagen de firma visual",
        attachment=True,
        groups="base.group_system",
    )
    digital_signature_certificate_subject = fields.Char(
        string="Sujeto del certificado",
        readonly=True,
        groups="base.group_system",
    )
    digital_signature_certificate_issuer = fields.Char(
        string="Emisor del certificado",
        readonly=True,
        groups="base.group_system",
    )

    @api.onchange("digital_signature_job_id")
    def _onchange_digital_signature_job_id(self):
        for user in self:
            if user.digital_signature_job_id and not user.digital_signature_position:
                user.digital_signature_position = user.digital_signature_job_id.name

    def action_use_employee_job_for_digital_signature(self):
        for user in self:
            employee = self.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
            if not employee or not employee.job_id:
                continue
            user.sudo().write(
                {
                    "digital_signature_job_id": employee.job_id.id,
                    "digital_signature_position": user.digital_signature_position or employee.job_id.name,
                }
            )
        return True

    def action_validate_digital_signature_certificate(self):
        for user in self:
            user._validate_digital_signature_certificate()
        return True

    def _validate_digital_signature_certificate(self):
        self.ensure_one()
        certificate_file, certificate_password, _signer_name = self._get_digital_signature_credentials()
        certificate_bytes = base64.b64decode(certificate_file or b"")
        password = certificate_password.encode("utf-8") if certificate_password else None
        try:
            private_key, certificate, _additional_certificates = pkcs12.load_key_and_certificates(
                certificate_bytes,
                password,
            )
        except Exception as error:
            raise UserError(_("No se pudo abrir el certificado del usuario. Verifique el archivo .p12/.pfx y la contrasena.")) from error
        if not private_key or not certificate:
            raise UserError(_("El certificado del usuario no contiene llave privada utilizable para firmar."))
        self.sudo().write(
            {
                "digital_signature_certificate_subject": certificate.subject.rfc4514_string(),
                "digital_signature_certificate_issuer": certificate.issuer.rfc4514_string(),
            }
        )
        return True

    def _get_digital_signature_credentials(self):
        self.ensure_one()
        if not self.digital_signature_certificate:
            raise UserError(_("Su usuario no tiene un certificado digital configurado."))
        return (
            self.digital_signature_certificate,
            self.digital_signature_password,
            self.digital_signature_name or self.name,
        )
