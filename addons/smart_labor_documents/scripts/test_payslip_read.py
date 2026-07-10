import odoo
from odoo import SUPERUSER_ID, api
from odoo.tools import config


config.parse_config(["-c", "/etc/odoo/odoo.conf", "-d", "odoo18"])
registry = odoo.registry("odoo18")

with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    document = env["employee.payslip.document"].search([], limit=1)
    if not document:
        print("no_document")
    else:
        before = document.is_read
        document.action_mark_read()
        print("document=%s before=%s after=%s read_date=%s" % (document.id, before, document.is_read, bool(document.read_date)))
        cr.rollback()
