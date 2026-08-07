{
    "name": "Attendance Location Tracking",
    "summary": "Dispositivos corporativos y ubicacion GPS durante la jornada laboral.",
    "version": "18.0.2.0.0",
    "category": "Human Resources/Attendances",
    "author": "Gustavo",
    "license": "LGPL-3",
    "depends": ["hr_attendance", "mail", "web"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/mobile_tracking_views.xml",
        "views/mobile_tracking_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_attendance_location_tracking/static/src/**/*.js",
            "hr_attendance_location_tracking/static/src/**/*.xml",
            "hr_attendance_location_tracking/static/src/**/*.scss",
        ],
    },
    "application": False,
    "installable": True,
}
