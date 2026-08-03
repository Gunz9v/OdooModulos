from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAttendanceMobileTracking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Empleado movil"})
        cls.device = cls.env["hr.attendance.tracking.device"].create({
            "name": "Telefono de prueba", "employee_id": cls.employee.id,
        })

    def test_enrollment_attendance_and_points(self):
        self.device.action_generate_enrollment_code()
        code = self.device.enrollment_code
        device, token = self.env["hr.attendance.tracking.device"].enroll(
            code, "test-installation-uuid", {"model": "Test Phone", "app_version": "1.0.0"}
        )
        self.assertEqual(device.state, "active")
        self.assertTrue(token)
        self.assertEqual(
            self.env["hr.attendance.tracking.device"].authenticate(token, "test-installation-uuid"), device
        )
        attendance = self.env["hr.attendance"].create({
            "employee_id": self.employee.id,
            "check_in": fields.Datetime.now(),
            "in_mode": "mobile",
        })
        session = self.env["hr.attendance.location.session"].create({
            "name": "Jornada de prueba",
            "employee_id": self.employee.id,
            "attendance_id": attendance.id,
            "device_id": device.id,
        })
        accepted = session.ingest_points([
            {"uuid": "point-1", "latitude": -12.05, "longitude": -77.04, "accuracy": 8},
            {"uuid": "point-2", "latitude": -12.0505, "longitude": -77.0405, "accuracy": 10},
        ])
        self.assertEqual(accepted, 2)
        self.assertEqual(session.point_count, 2)
        self.assertGreater(session.distance_m, 0)
        self.assertEqual(session.ingest_points([
            {"uuid": "point-1", "latitude": -12.05, "longitude": -77.04, "accuracy": 8},
        ]), 0)
        attendance.check_out = fields.Datetime.now()
        with self.assertRaises(ValidationError):
            session.ingest_points([
                {"uuid": "point-3", "latitude": -12.06, "longitude": -77.05, "accuracy": 8},
            ])
