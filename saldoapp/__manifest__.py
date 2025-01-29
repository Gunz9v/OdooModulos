# -*- coding: utf-8 -*-
{
    'name': "saldoapp",

    'summary': "Controla tus egresos e ingresos con SaldoApp",

    'description': """
Long description of module's purpose
    """,

    'author': "Gustavo G.",
    'website': "https://www.goansystem.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'productivity',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'views/data.xml',
    ],
    'assets': {
    'web.assets_backend': [
        'saldoapp/static/src/scss/style.scss',
    ],
    },

    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}

