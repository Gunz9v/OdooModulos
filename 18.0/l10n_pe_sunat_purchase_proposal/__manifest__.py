{
    "name": "Peru SUNAT Purchase Proposal",
    "summary": "Importa propuestas RCE, compara compras y genera facturas faltantes.",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Gustavo",
    "license": "LGPL-3",
    "depends": [
        "account",
        "l10n_pe",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/purchase_proposal_views.xml",
        "views/purchase_proposal_line_views.xml",
        "views/account_move_views.xml",
        "wizards/purchase_proposal_import_wizard_views.xml",
        "wizards/purchase_proposal_invoice_wizard_views.xml",
        "views/menu_views.xml",
    ],
    "application": True,
    "installable": True,
}

