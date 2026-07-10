from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EmployeeAnnouncement(models.Model):
    _name = "employee.announcement"
    _description = "Comunicado Interno"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "publish_date desc, id desc"

    name = fields.Char(string="Titulo", required=True, tracking=True)
    description = fields.Text(string="Descripcion")
    file_data = fields.Binary(string="Archivo PDF", attachment=True, required=True)
    file_name = fields.Char(string="Nombre de archivo")
    publish_date = fields.Datetime(string="Fecha publicacion", readonly=True)
    published_by_id = fields.Many2one("res.users", string="Publicado por", readonly=True)
    target_type = fields.Selection(
        selection=[
            ("all", "Todos los empleados"),
            ("department", "Por departamento"),
            ("employee", "Empleados especificos"),
        ],
        default="all",
        required=True,
        tracking=True,
        string="Destinatarios",
    )
    department_ids = fields.Many2many("hr.department", string="Departamentos")
    employee_ids = fields.Many2many("hr.employee", string="Empleados")
    recipient_ids = fields.One2many("employee.announcement.recipient", "announcement_id", string="Destinatarios")
    recipient_count = fields.Integer(string="Destinatarios", compute="_compute_recipient_stats")
    read_count = fields.Integer(string="Leidos", compute="_compute_recipient_stats")
    unread_count = fields.Integer(string="No leidos", compute="_compute_recipient_stats")
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("published", "Publicado"),
            ("archived", "Archivado"),
        ],
        default="draft",
        required=True,
        tracking=True,
        string="Estado",
    )

    def _compute_recipient_stats(self):
        for announcement in self:
            recipients = announcement.recipient_ids
            announcement.recipient_count = len(recipients)
            announcement.read_count = len(recipients.filtered("is_read"))
            announcement.unread_count = announcement.recipient_count - announcement.read_count

    def action_publish(self):
        for announcement in self:
            if not announcement.file_data:
                raise UserError(_("Debe adjuntar un PDF antes de publicar."))
            employees = announcement._get_target_employees()
            if not employees:
                raise UserError(_("No se encontraron empleados destinatarios."))
            announcement._prepare_recipients(employees)
            announcement.write(
                {
                    "state": "published",
                    "publish_date": fields.Datetime.now(),
                    "published_by_id": self.env.user.id,
                }
            )
            announcement._send_recipient_emails()

    def action_archive(self):
        self.write({"state": "archived"})

    def action_set_draft(self):
        self.write({"state": "draft"})

    def action_view_recipients(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Destinatarios"),
            "res_model": "employee.announcement.recipient",
            "view_mode": "list,form",
            "domain": [("announcement_id", "=", self.id)],
            "context": {"default_announcement_id": self.id},
        }

    def _get_target_employees(self):
        self.ensure_one()
        Employee = self.env["hr.employee"].sudo()
        if self.target_type == "all":
            return Employee.search([("active", "=", True)])
        if self.target_type == "department":
            return Employee.search([("active", "=", True), ("department_id", "in", self.department_ids.ids)])
        return self.employee_ids.filtered("active")

    def _prepare_recipients(self, employees):
        Recipient = self.env["employee.announcement.recipient"].sudo()
        for employee in employees:
            existing = Recipient.search(
                [
                    ("announcement_id", "=", self.id),
                    ("employee_id", "=", employee.id),
                ],
                limit=1,
            )
            if existing:
                continue
            Recipient.create(
                {
                    "announcement_id": self.id,
                    "employee_id": employee.id,
                }
            )

    def _send_recipient_emails(self):
        Mail = self.env["mail.mail"].sudo()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        for recipient in self.recipient_ids.filtered(lambda item: item.email and not item.sent_date):
            url = "%s/my/announcements/%s" % (base_url, recipient.announcement_id.id)
            body = """
                <p>Hola %s,</p>
                <p>Se ha publicado un nuevo comunicado: <strong>%s</strong>.</p>
                <p>%s</p>
                <p><a href="%s">Ver comunicado</a></p>
            """ % (
                recipient.employee_id.name,
                recipient.announcement_id.name,
                recipient.announcement_id.description or "",
                url,
            )
            Mail.create(
                {
                    "subject": "Nuevo comunicado: %s" % recipient.announcement_id.name,
                    "body_html": body,
                    "email_to": recipient.email,
                    "auto_delete": False,
                }
            )
            recipient.sent_date = fields.Datetime.now()


class EmployeeAnnouncementRecipient(models.Model):
    _name = "employee.announcement.recipient"
    _description = "Destinatario de Comunicado Interno"
    _order = "announcement_id desc, employee_id"

    announcement_id = fields.Many2one("employee.announcement", string="Comunicado", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, ondelete="cascade", index=True)
    employee_user_id = fields.Many2one(related="employee_id.user_id", store=True, index=True)
    employee_partner_id = fields.Many2one(related="employee_id.user_id.partner_id", store=True, index=True)
    email = fields.Char(string="Correo", compute="_compute_email", store=True)
    sent_date = fields.Datetime(string="Fecha envio", readonly=True)
    is_read = fields.Boolean(string="Leido", default=False)
    read_date = fields.Datetime(string="Fecha lectura", readonly=True)
    state = fields.Selection(string="Estado", related="announcement_id.state", store=True, readonly=True)

    _sql_constraints = [
        (
            "announcement_employee_unique",
            "unique(announcement_id, employee_id)",
            "El empleado ya esta como destinatario de este comunicado.",
        )
    ]

    @api.depends("employee_id.work_email", "employee_id.user_id.email")
    def _compute_email(self):
        for recipient in self:
            recipient.email = recipient.employee_id.work_email or recipient.employee_id.user_id.email

    def action_mark_read(self):
        self.filtered(lambda recipient: not recipient.is_read).sudo().write(
            {
                "is_read": True,
                "read_date": fields.Datetime.now(),
            }
        )
