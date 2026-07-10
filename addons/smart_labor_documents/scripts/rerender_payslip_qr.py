import odoo
from odoo import SUPERUSER_ID, api
from odoo.tools import config


config.parse_config(["-c", "/etc/odoo/odoo.conf", "-d", "odoo18"])
registry = odoo.registry("odoo18")

with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env["employee.payslip.document"].search([])
    for document in documents:
        document.action_render_template()
        document.action_sync_legajo_document()
    cr.commit()
    print("rerendered_payslip_documents=%s" % len(documents))
