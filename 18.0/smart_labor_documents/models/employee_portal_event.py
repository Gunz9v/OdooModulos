from odoo import fields, models


class EmployeePortalEvent(models.Model):
    _name = "employee.portal.event"
    _description = "Fecha especial del portal"
    _order = "event_date asc, id asc"

    name = fields.Char(string="Titulo", required=True)
    event_date = fields.Date(string="Fecha", required=True)
    description = fields.Text(string="Descripcion")
    event_type = fields.Selection(
        selection=[
            ("company", "Empresa"),
            ("holiday", "Feriado"),
            ("training", "Capacitacion"),
            ("deadline", "Cierre"),
            ("other", "Otro"),
        ],
        string="Tipo",
        default="company",
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("published", "Publicado"),
            ("archived", "Archivado"),
        ],
        string="Estado",
        default="draft",
        required=True,
    )

    def action_publish(self):
        self.write({"state": "published"})

    def action_archive(self):
        self.write({"state": "archived"})

    def action_set_draft(self):
        self.write({"state": "draft"})
