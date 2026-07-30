import math
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


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


class SalespersonRouteSession(models.Model):
    _name = "salesperson.route.session"
    _description = "Sesion de recorrido de vendedor"
    _inherit = ["mail.thread"]
    _order = "started_at desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("Nuevo recorrido"))
    user_id = fields.Many2one(
        "res.users",
        string="Vendedor",
        required=True,
        index=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        [("running", "En curso"), ("paused", "Pausado"), ("done", "Finalizado")],
        required=True,
        default="running",
        index=True,
        tracking=True,
    )
    started_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True, tracking=True)
    ended_at = fields.Datetime(readonly=True, tracking=True)
    point_ids = fields.One2many("salesperson.route.point", "session_id", string="Puntos GPS", readonly=True)
    point_count = fields.Integer(compute="_compute_point_count", string="Puntos")
    distance_m = fields.Float(string="Distancia (m)", readonly=True, digits=(16, 2))
    distance_km = fields.Float(compute="_compute_distance_km", string="Distancia (km)", digits=(16, 2))
    last_latitude = fields.Float(readonly=True, digits=(10, 7))
    last_longitude = fields.Float(readonly=True, digits=(10, 7))
    last_position_at = fields.Datetime(readonly=True)

    @api.depends("point_ids")
    def _compute_point_count(self):
        grouped = self.env["salesperson.route.point"]._read_group(
            [("session_id", "in", self.ids)], ["session_id"], ["__count"]
        )
        counts = {session.id: count for session, count in grouped}
        for session in self:
            session.point_count = counts.get(session.id, 0)

    @api.depends("distance_m")
    def _compute_distance_km(self):
        for session in self:
            session.distance_km = session.distance_m / 1000.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            user = self.env["res.users"].browse(vals.get("user_id")) if vals.get("user_id") else self.env.user
            if user != self.env.user and not self.env.user.has_group(
                "salesperson_route_tracking.group_route_tracking_manager"
            ):
                raise AccessError(_("Solo un supervisor puede iniciar recorridos para otro vendedor."))
            if not vals.get("name") or vals.get("name") == _("Nuevo recorrido"):
                started = fields.Datetime.to_datetime(vals.get("started_at")) or fields.Datetime.now()
                vals["name"] = _("Ruta %(user)s - %(date)s", user=user.name, date=started.date())
        return super().create(vals_list)

    def unlink(self):
        if not self.env.user.has_group("salesperson_route_tracking.group_route_tracking_manager"):
            raise AccessError(_("Solo un supervisor puede eliminar recorridos."))
        return super().unlink()

    def action_pause(self):
        self._check_owner_or_manager()
        self.filtered(lambda session: session.state == "running").write({"state": "paused"})

    def action_resume(self):
        self._check_owner_or_manager()
        self.filtered(lambda session: session.state == "paused").write({"state": "running"})

    def action_finish(self):
        self._check_owner_or_manager()
        self.filtered(lambda session: session.state != "done").write(
            {"state": "done", "ended_at": fields.Datetime.now()}
        )

    def action_open_map(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "salesperson_route_history",
            "name": _("Recorrido: %s", self.display_name),
            "params": {"session_id": self.id},
        }

    def _check_owner_or_manager(self):
        if self.filtered(lambda session: session.user_id != self.env.user) and not self.env.user.has_group(
            "salesperson_route_tracking.group_route_tracking_manager"
        ):
            raise AccessError(_("No puede modificar el recorrido de otro vendedor."))

    @api.model
    def tracking_state(self):
        session = self.search(
            [("user_id", "=", self.env.user.id), ("state", "in", ["running", "paused"])],
            order="started_at desc",
            limit=1,
        )
        return session._tracking_payload() if session else {"active": False}

    @api.model
    def start_tracking(self):
        session = self.search(
            [("user_id", "=", self.env.user.id), ("state", "in", ["running", "paused"])],
            order="started_at desc",
            limit=1,
        )
        if session:
            if session.state == "paused":
                session.action_resume()
            return session._tracking_payload()
        session = self.create({})
        return session._tracking_payload()

    @api.model
    def pause_tracking(self, session_id):
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La sesión de recorrido ya no existe."))
        session.action_pause()
        return session._tracking_payload()

    @api.model
    def finish_tracking(self, session_id):
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La sesión de recorrido ya no existe."))
        session.action_finish()
        return session._tracking_payload()

    @api.model
    def ingest_points(self, session_id, points):
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("La sesión de recorrido ya no existe."))
        session._check_owner_or_manager()
        if session.state == "done":
            raise UserError(_("No se pueden agregar coordenadas a una sesión finalizada."))
        if not isinstance(points, list) or len(points) > 500:
            raise ValidationError(_("El lote GPS debe contener como máximo 500 puntos."))

        Point = self.env["salesperson.route.point"]
        existing_ids = set(
            Point.search([("client_uuid", "in", [point.get("uuid") for point in points if point.get("uuid")])]).mapped(
                "client_uuid"
            )
        )
        values = []
        for point in points:
            client_uuid = point.get("uuid") or str(uuid.uuid4())
            if client_uuid in existing_ids:
                continue
            latitude = float(point.get("latitude"))
            longitude = float(point.get("longitude"))
            if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
                raise ValidationError(_("Se recibió una coordenada GPS fuera de rango."))
            recorded_at = point.get("recorded_at") or fields.Datetime.now()
            if isinstance(recorded_at, str):
                recorded_at = recorded_at.replace("T", " ").replace("Z", "")[:19]
            values.append(
                {
                    "session_id": session.id,
                    "client_uuid": client_uuid,
                    "recorded_at": recorded_at,
                    "latitude": latitude,
                    "longitude": longitude,
                    "accuracy": max(float(point.get("accuracy") or 0.0), 0.0),
                    "altitude": point.get("altitude"),
                    "speed": point.get("speed"),
                    "heading": point.get("heading"),
                    "source": point.get("source") or "browser",
                }
            )

        created = Point.create(values) if values else Point
        if created:
            session._refresh_route_totals()
        return {"accepted": len(created), "queued": len(points) - len(created), **session._tracking_payload()}

    def _refresh_route_totals(self):
        for session in self:
            points = session.point_ids.sorted(lambda point: (point.recorded_at, point.id))
            distance = 0.0
            previous = None
            for point in points:
                if previous:
                    distance += _haversine_meters(
                        previous.latitude,
                        previous.longitude,
                        point.latitude,
                        point.longitude,
                    )
                previous = point
            values = {"distance_m": distance}
            if previous:
                values.update(
                    {
                        "last_latitude": previous.latitude,
                        "last_longitude": previous.longitude,
                        "last_position_at": previous.recorded_at,
                    }
                )
            session.write(values)

    def _tracking_payload(self):
        self.ensure_one()
        return {
            "active": self.state != "done",
            "session_id": self.id,
            "name": self.display_name,
            "state": self.state,
            "started_at": fields.Datetime.to_string(self.started_at),
            "point_count": self.point_count,
            "distance_km": round(self.distance_km, 2),
            "last_position_at": fields.Datetime.to_string(self.last_position_at) if self.last_position_at else False,
        }

    @api.model
    def route_data(self, session_id):
        session = self.browse(session_id).exists()
        if not session:
            raise UserError(_("El recorrido solicitado no existe."))
        session.check_access("read")
        points = [
            {
                "latitude": point.latitude,
                "longitude": point.longitude,
                "recorded_at": fields.Datetime.to_string(point.recorded_at),
                "accuracy": point.accuracy,
                "speed": point.speed,
            }
            for point in session.point_ids.sorted(lambda point: (point.recorded_at, point.id))
        ]
        return {
            "session": {
                "id": session.id,
                "name": session.display_name,
                "seller": session.user_id.name,
                "state": session.state,
                "started_at": fields.Datetime.to_string(session.started_at),
                "ended_at": fields.Datetime.to_string(session.ended_at) if session.ended_at else False,
                "distance_km": round(session.distance_km, 2),
            },
            "points": points,
        }


class SalespersonRoutePoint(models.Model):
    _name = "salesperson.route.point"
    _description = "Punto GPS de recorrido"
    _order = "recorded_at, id"

    session_id = fields.Many2one(
        "salesperson.route.session", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="session_id.company_id", store=True, index=True)
    user_id = fields.Many2one(related="session_id.user_id", store=True, index=True)
    client_uuid = fields.Char(required=True, index=True, copy=False)
    recorded_at = fields.Datetime(required=True, index=True)
    latitude = fields.Float(required=True, digits=(10, 7))
    longitude = fields.Float(required=True, digits=(10, 7))
    accuracy = fields.Float(string="Precisión (m)", digits=(16, 2))
    altitude = fields.Float(string="Altitud (m)", digits=(16, 2))
    speed = fields.Float(string="Velocidad (m/s)", digits=(16, 2))
    heading = fields.Float(string="Rumbo", digits=(16, 2))
    source = fields.Selection(
        [("browser", "Navegador/PWA"), ("mobile", "Aplicación móvil"), ("manual", "Manual")],
        required=True,
        default="browser",
    )

    _sql_constraints = [
        ("client_uuid_unique", "unique(client_uuid)", "El punto GPS ya fue registrado."),
    ]

    @api.constrains("latitude", "longitude")
    def _check_coordinates(self):
        for point in self:
            if not -90.0 <= point.latitude <= 90.0 or not -180.0 <= point.longitude <= 180.0:
                raise ValidationError(_("Las coordenadas GPS están fuera de rango."))

