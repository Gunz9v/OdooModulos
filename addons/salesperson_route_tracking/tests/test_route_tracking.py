from odoo.tests.common import TransactionCase


class TestRouteTracking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # La base de integración puede contener columnas de módulos Enterprise
        # no cargados en el registro. Reutilizar el usuario de prueba evita que
        # la prueba del recorrido dependa de extensiones ajenas de res.partner.
        cls.user = cls.env.user
        cls.Session = cls.env["salesperson.route.session"]

    def test_start_ingest_and_finish_route(self):
        payload = self.Session.start_tracking()
        self.assertTrue(payload["active"])
        result = self.Session.ingest_points(
            payload["session_id"],
            [
                {
                    "uuid": "test-point-1",
                    "recorded_at": "2026-07-27 10:00:00",
                    "latitude": -12.0464,
                    "longitude": -77.0428,
                    "accuracy": 8,
                },
                {
                    "uuid": "test-point-2",
                    "recorded_at": "2026-07-27 10:01:00",
                    "latitude": -12.0454,
                    "longitude": -77.0428,
                    "accuracy": 8,
                },
            ],
        )
        self.assertEqual(result["accepted"], 2)
        session = self.Session.browse(payload["session_id"])
        self.assertEqual(session.point_count, 2)
        self.assertGreater(session.distance_m, 100)
        self.assertLess(session.distance_m, 120)
        finished = self.Session.finish_tracking(session.id)
        self.assertFalse(finished["active"])
        self.assertEqual(session.state, "done")

    def test_duplicate_point_is_idempotent(self):
        session = self.Session.create({})
        point = {
            "uuid": "duplicate-point",
            "recorded_at": "2026-07-27 10:00:00",
            "latitude": -12.0464,
            "longitude": -77.0428,
        }
        self.Session.ingest_points(session.id, [point])
        result = self.Session.ingest_points(session.id, [point])
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(session.point_count, 1)
