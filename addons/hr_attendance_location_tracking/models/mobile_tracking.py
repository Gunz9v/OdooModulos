import hashlib
import math
import secrets
import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


def _token_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _haversine_meters(lat1, lon1, lat2, lon2):
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return radius * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


class HrAttendanceTrackingDevice(models.Model):
    _name = "hr.attendance.tracking.device"
    _description = "Dispositivo movil de asistencia"
    _inherit = ["mail.thread"]
    _order = "employee_id, name"

    name = fields.Char(required=True, tracking=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True, ondelete="cascade")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    asset_code = fields.Char(string="Codigo patrimonial", index=True)
    state = fields.Selection(
        [("pending", "Pendiente"), ("active", "Activo"), ("revoked", "Revocado")],
        default="pending",
        required=True,
        index=True,
        tracking=True,
    )
    installation_uuid = fields.Char(readonly=True, copy=False, index=True)
    token_hash = fields.Char(readonly=True, copy=False, groups="base.group_system")
    enrollment_code = fields.Char(string="Codigo de vinculacion", readonly=True, copy=False, groups="hr_attendance.group_hr_attendance_manager")
    enrollment_expires_at = fields.Datetime(readonly=True, copy=False)
    enrolled_at = fields.Datetime(readonly=True, copy=False)
    manufacturer = fields.Char(readonly=True)
    device_model = fields.Char(string="Modelo", readonly=True)
    android_version = fields.Char(readonly=True)
    app_version = fields.Char(readonly=True)
    last_seen_at = fields.Datetime(readonly=True)
    last_latitude = fields.Float(readonly=True, digits=(10, 7))
    last_longitude = fields.Float(readonly=True, digits=(10, 7))
    last_accuracy = fields.Float(readonly=True, digits=(16, 2))

    _sql_constraints = [
        ("installation_uuid_unique", "unique(installation_uuid)", "Esta instalacion ya esta vinculada."),
    ]

    def action_generate_enrollment_code(self):
        self.ensure_one()
        code = "-".join((secrets.token_hex(2).upper(), secrets.token_hex(2).upper()))
        self.write({
            "enrollment_code": code,
            "enrollment_expires_at": fields.Datetime.now() + timedelta(minutes=10),
            "state": "pending",
            "token_hash": False,
            "installation_uuid": False,
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Codigo de vinculacion"),
                "message": _("Use %(code)s en la aplicacion. Vence en 10 minutos.", code=code),
                "type": "success",
                "sticky": True,
            },
        }

    def action_revoke(self):
        self.write({
            "state": "revoked",
            "token_hash": False,
            "enrollment_code": False,
            "enrollment_expires_at": False,
        })
        self.mapped("session_ids").filtered(lambda session: session.state == "running").action_finish()

    session_ids = fields.One2many("hr.attendance.location.session", "device_id", readonly=True)

    @api.model
    def enroll(self, code, installation_uuid, device_info=None):
        code = (code or "").strip().upper()
        installation_uuid = (installation_uuid or "").strip()
        if not code or not installation_uuid:
            raise ValidationError(_("El codigo y el identificador de instalacion son obligatorios."))
        device = self.search([("enrollment_code", "=ilike", code), ("state", "=", "pending")], limit=1)
        if not device or not device.enrollment_expires_at or device.enrollment_expires_at < fields.Datetime.now():
            raise ValidationError(_("El codigo de vinculacion es invalido o ha vencido."))
        existing = self.search([("installation_uuid", "=", installation_uuid), ("id", "!=", device.id)], limit=1)
        if existing:
            raise ValidationError(_("Esta instalacion ya esta vinculada con otro dispositivo."))
        token = secrets.token_urlsafe(32)
        info = device_info if isinstance(device_info, dict) else {}
        device.write({
            "state": "active",
            "installation_uuid": installation_uuid,
            "token_hash": _token_hash(token),
            "enrollment_code": False,
            "enrollment_expires_at": False,
            "enrolled_at": fields.Datetime.now(),
            "last_seen_at": fields.Datetime.now(),
            "manufacturer": str(info.get("manufacturer") or "")[:128],
            "device_model": str(info.get("model") or "")[:128],
            "android_version": str(info.get("android_version") or "")[:64],
            "app_version": str(info.get("app_version") or "")[:64],
        })
        return device, token

    @api.model
    def authenticate(self, token, installation_uuid):
        if not token or not installation_uuid:
            return self.browse()
        device = self.search([
            ("installation_uuid", "=", installation_uuid),
            ("token_hash", "=", _token_hash(token)),
            ("state", "=", "active"),
        ], limit=1)
        if device:
            device.last_seen_at = fields.Datetime.now()
        return device


class HrAttendanceLocationSession(models.Model):
    _name = "hr.attendance.location.session"
    _description = "Seguimiento de ubicacion durante asistencia"
    _inherit = ["mail.thread"]
    _order = "started_at desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="cascade")
    attendance_id = fields.Many2one("hr.attendance", required=True, index=True, ondelete="cascade")
    device_id = fields.Many2one("hr.attendance.tracking.device", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    state = fields.Selection([("running", "En curso"), ("done", "Finalizado")], default="running", required=True, index=True)
    started_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    ended_at = fields.Datetime(readonly=True)
    finish_reason = fields.Selection(
        [("mobile", "Salida desde la aplicacion"), ("automatic", "Salida automatica"), ("other", "Otro cierre")],
        string="Motivo de cierre",
        readonly=True,
    )
    point_ids = fields.One2many("hr.attendance.location.point", "session_id", readonly=True)
    point_count = fields.Integer(compute="_compute_point_count")
    distance_m = fields.Float(readonly=True, digits=(16, 2))
    distance_km = fields.Float(compute="_compute_distance_km", digits=(16, 2))
    last_latitude = fields.Float(readonly=True, digits=(10, 7))
    last_longitude = fields.Float(readonly=True, digits=(10, 7))
    last_position_at = fields.Datetime(readonly=True)

    @api.depends("point_ids")
    def _compute_point_count(self):
        grouped = self.env["hr.attendance.location.point"]._read_group(
            [("session_id", "in", self.ids)], ["session_id"], ["__count"]
        )
        counts = {session.id: count for session, count in grouped}
        for session in self:
            session.point_count = counts.get(session.id, 0)

    @api.depends("distance_m")
    def _compute_distance_km(self):
        for session in self:
            session.distance_km = session.distance_m / 1000.0

    def action_finish(self, ended_at=None, reason="other"):
        self.filtered(lambda session: session.state == "running").write({
            "state": "done",
            "ended_at": ended_at or fields.Datetime.now(),
            "finish_reason": reason,
        })

    def action_open_map(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "attendance_location_journey_map",
            "name": _("Mapa: %s", self.display_name),
            "params": {"session_id": self.id},
        }

    @api.model
    def route_data(self, session_id):
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La jornada solicitada no existe."))
        session.check_access("read")
        return {
            "session": {
                "id": session.id,
                "name": session.display_name,
                "employee": session.employee_id.name,
                "state": session.state,
                "started_at": fields.Datetime.to_string(session.started_at),
                "ended_at": fields.Datetime.to_string(session.ended_at) if session.ended_at else False,
                "distance_km": round(session.distance_km, 2),
            },
            "points": [
                {
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                    "accuracy": point.accuracy,
                    "recorded_at": fields.Datetime.to_string(point.recorded_at),
                }
                for point in session.point_ids.sorted(lambda point: (point.recorded_at, point.id))
            ],
        }

    @api.model
    def team_map_data(self):
        sessions = self.search([("state", "=", "running"), ("last_position_at", "!=", False)])
        now = fields.Datetime.now()
        return [
            {
                "session_id": session.id,
                "employee": session.employee_id.name,
                "device": session.device_id.name,
                "latitude": session.last_latitude,
                "longitude": session.last_longitude,
                "accuracy": session.device_id.last_accuracy,
                "last_position_at": fields.Datetime.to_string(session.last_position_at),
                "age_seconds": max(int((now - session.last_position_at).total_seconds()), 0),
                "started_at": fields.Datetime.to_string(session.started_at),
            }
            for session in sessions
        ]

    def ingest_points(self, points):
        self.ensure_one()
        if self.state != "running" or self.attendance_id.check_out:
            raise ValidationError(_("La jornada ya esta cerrada."))
        if not isinstance(points, list) or not points or len(points) > 500:
            raise ValidationError(_("El lote debe contener entre 1 y 500 puntos."))
        Point = self.env["hr.attendance.location.point"]
        uuids = [point.get("uuid") for point in points if isinstance(point, dict) and point.get("uuid")]
        existing = set(Point.search([("client_uuid", "in", uuids)]).mapped("client_uuid"))
        values = []
        for payload in points:
            if not isinstance(payload, dict):
                raise ValidationError(_("Formato de punto GPS invalido."))
            point_uuid = str(payload.get("uuid") or uuid.uuid4())
            if point_uuid in existing:
                continue
            latitude = float(payload.get("latitude"))
            longitude = float(payload.get("longitude"))
            accuracy = max(float(payload.get("accuracy") or 0.0), 0.0)
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValidationError(_("Coordenada GPS fuera de rango."))
            recorded_at = payload.get("recorded_at") or fields.Datetime.now()
            if isinstance(recorded_at, str):
                recorded_at = recorded_at.replace("T", " ").replace("Z", "")[:19]
            values.append({
                "session_id": self.id,
                "client_uuid": point_uuid,
                "recorded_at": recorded_at,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
                "altitude": payload.get("altitude"),
                "speed": payload.get("speed"),
                "heading": payload.get("heading"),
            })
            existing.add(point_uuid)
        created = Point.create(values) if values else Point
        if created:
            self._refresh_totals()
        return len(created)

    def _refresh_totals(self):
        for session in self:
            points = session.point_ids.sorted(lambda point: (point.recorded_at, point.id))
            distance = 0.0
            previous = None
            for point in points:
                if previous:
                    distance += _haversine_meters(previous.latitude, previous.longitude, point.latitude, point.longitude)
                previous = point
            values = {"distance_m": distance}
            if previous:
                values.update({
                    "last_latitude": previous.latitude,
                    "last_longitude": previous.longitude,
                    "last_position_at": previous.recorded_at,
                })
                session.device_id.write({
                    "last_latitude": previous.latitude,
                    "last_longitude": previous.longitude,
                    "last_accuracy": previous.accuracy,
                    "last_seen_at": fields.Datetime.now(),
                })
            session.write(values)


class HrAttendanceLocationPoint(models.Model):
    _name = "hr.attendance.location.point"
    _description = "Punto GPS durante asistencia"
    _order = "recorded_at, id"

    session_id = fields.Many2one("hr.attendance.location.session", required=True, index=True, ondelete="cascade")
    employee_id = fields.Many2one(related="session_id.employee_id", store=True, index=True)
    company_id = fields.Many2one(related="session_id.company_id", store=True, index=True)
    client_uuid = fields.Char(required=True, index=True, copy=False)
    recorded_at = fields.Datetime(required=True, index=True)
    latitude = fields.Float(required=True, digits=(10, 7))
    longitude = fields.Float(required=True, digits=(10, 7))
    accuracy = fields.Float(digits=(16, 2))
    altitude = fields.Float(digits=(16, 2))
    speed = fields.Float(digits=(16, 2))
    heading = fields.Float(digits=(16, 2))

    _sql_constraints = [("client_uuid_unique", "unique(client_uuid)", "El punto GPS ya fue registrado.")]


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    in_mode = fields.Selection(selection_add=[("mobile", "Aplicacion movil")], ondelete={"mobile": "set default"})
    out_mode = fields.Selection(selection_add=[("mobile", "Aplicacion movil")], ondelete={"mobile": "set default"})
    location_session_ids = fields.One2many("hr.attendance.location.session", "attendance_id", readonly=True)

    def write(self, values):
        # Odoo's automatic check-out and every other attendance exit eventually
        # write check_out on hr.attendance. Hooking that transition keeps the GPS
        # lifecycle synchronized regardless of where the exit originated.
        open_attendances = self.filtered(lambda attendance: not attendance.check_out) if values.get("check_out") else self.browse()
        result = super().write(values)
        for attendance in open_attendances.filtered("check_out"):
            reason = "automatic" if attendance.out_mode == "auto_check_out" else (
                "mobile" if attendance.out_mode == "mobile" else "other"
            )
            attendance.location_session_ids.action_finish(attendance.check_out, reason)
        return result
