{
    "name": "Salesperson Route Tracking",
    "summary": "Captura GPS en primer plano y recorrido historico de vendedores.",
    "version": "18.0.1.1.0",
    "category": "Sales/Sales",
    "author": "Gustavo",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "web",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/route_tracking_views.xml",
        "views/route_tracking_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "salesperson_route_tracking/static/src/**/*.js",
            "salesperson_route_tracking/static/src/**/*.xml",
            "salesperson_route_tracking/static/src/**/*.scss",
        ],
    },
    "application": True,
    "installable": True,
}
