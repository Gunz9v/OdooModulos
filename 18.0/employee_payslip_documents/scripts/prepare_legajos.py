import odoo
from odoo import SUPERUSER_ID, api
from odoo.tools import config


config.parse_config(["-c", "/etc/odoo/odoo.conf", "-d", "odoo18"])
registry = odoo.registry("odoo18")

with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env["hr.employee"].search([("active", "=", True)])
    employees.action_prepare_legajo_documents()
    cr.commit()
    print("prepared_employees=%s" % len(employees))
