import odoo
from odoo import SUPERUSER_ID, api
from odoo.tools import config


config.parse_config(["-c", "/etc/odoo/odoo.conf", "-d", "odoo18"])
registry = odoo.registry("odoo18")

with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    batch = env["employee.payslip.document.batch"].new({})
    values = batch._build_classified_values(
        ["", "", "I", "I", "D", "D", "AE"],
        ["employee_identification", "employee_name", "SUELDO BASICO", "BONO", "AFP", "EPS", "ESSALUD"],
        ["74402884", "Miguel Angel", 1500, None, 180, "0.00", 135],
    )
    print("income=%s discount=%s employer=%s amount=%s" % (
        len(values["income_lines"]),
        len(values["discount_lines"]),
        len(values["employer_contribution_lines"]),
        values["income_lines"][0]["amount"],
    ))
    aliases = batch._apply_header_aliases(
        {
            "apellidosynombres": "Miguel Angel",
            "total_a_pagar": "1234.50",
            "fecha_ingreso": "2026-01-01",
        }
    )
    print("employee_name=%s net_amount=%s hire_date=%s" % (
        aliases["employee_name"],
        aliases["net_amount"],
        aliases["hire_date"],
    ))
