{
    "name": "Peru SIRE Core",
    "summary": "Base comun para procesos SIRE de SUNAT.",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Gustavo",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/menu_views.xml",
        "views/sire_period_views.xml",
        "views/sire_import_batch_views.xml",
    ],
    "application": True,
    "installable": True,
}
