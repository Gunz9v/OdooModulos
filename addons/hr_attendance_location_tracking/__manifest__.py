{
    "name": "Attendance Location Tracking",
    "summary": "Dispositivos corporativos y ubicacion GPS durante la jornada laboral.",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Attendances",
    "author": "Gustavo",
    "license": "LGPL-3",
    "depends": ["hr_attendance", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/mobile_tracking_views.xml",
        "views/mobile_tracking_menus.xml",
    ],
    "application": False,
    "installable": True,
}
