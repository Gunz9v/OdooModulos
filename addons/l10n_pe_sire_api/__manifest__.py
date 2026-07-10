{
    "name": "Peru SIRE API",
    "summary": "Conexion API SUNAT para procesos SIRE.",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Gustavo",
    "license": "LGPL-3",
    "depends": [
        "l10n_pe_sire_core",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/sire_api_ticket_views.xml",
        "views/sire_period_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
}
