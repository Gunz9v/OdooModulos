from odoo import api, fields, models


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
    allow_history = fields.Boolean(
        string="Permite historico",
        default=True,
        help="Permite conservar cada archivo cargado como una entrada historica.",
    )
    active = fields.Boolean(string="Activo", default=True)

    @api.model_create_multi
    def create(self, vals_list):
        document_types = super().create(vals_list)
        employees = self.env["hr.employee"].sudo().search([("active", "=", True)])
        employees._prepare_legajo_documents_for_types(document_types)
        return document_types


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
            history_payloads.append(self._extract_history_payload(vals))
        records = super().create(vals_list)
        for record, payload in zip(records, history_payloads):
            if payload:
                record._create_history_from_payload(payload)
        return records

    def write(self, vals):
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
                    }
                )
        return True
