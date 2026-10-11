import base64

import odoo
from odoo import SUPERUSER_ID, api
from odoo.tools import config


config.parse_config(["-c", "/etc/odoo/odoo.conf", "-d", "odoo18"])
registry = odoo.registry("odoo18")

with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    legajo = env["employee.document.file"].search([], limit=1)
    if not legajo:
        print("no_legajo")
    else:
        before = len(legajo.history_ids)
        legajo.write(
            {
                "file_data": base64.b64encode(b"historial test"),
                "file_name": "historial-test.txt",
            }
        )
        after = len(legajo.history_ids)
        print("legajo=%s state=%s before=%s after=%s" % (legajo.id, legajo.state, before, after))
        cr.rollback()
