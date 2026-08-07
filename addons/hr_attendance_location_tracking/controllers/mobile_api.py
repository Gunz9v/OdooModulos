import json

from odoo import SUPERUSER_ID, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request


class AttendanceMobileApi(http.Controller):
    def _model(self, model_name):
        return request.env[model_name].with_user(SUPERUSER_ID).sudo()

    def _payload(self):
        return request.httprequest.get_json(silent=True) or {}

    def _response(self, data, status=200):
        return request.make_response(
            json.dumps(data, ensure_ascii=False, default=str),
            headers=[("Content-Type", "application/json")],
            status=status,
        )

    def _error(self, message, status=400, code="invalid_request"):
        return self._response({"ok": False, "error": code, "message": str(message)}, status=status)

    def _device(self, payload):
        authorization = request.httprequest.headers.get("Authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        installation_uuid = request.httprequest.headers.get("X-Installation-UUID") or payload.get("installation_uuid")
        return self._model("hr.attendance.tracking.device").authenticate(token, installation_uuid)

    def _geo(self, payload):
        point = payload.get("location") or {}
        return {
            "latitude": float(point.get("latitude") or 0.0),
            "longitude": float(point.get("longitude") or 0.0),
            "country_name": "",
            "city": "",
            "ip_address": request.httprequest.remote_addr or "",
            "browser": "Yohersa Android",
            "mode": "mobile",
        }

    @http.route("/mobile_tracking/v1/enroll", type="http", auth="none", methods=["POST"], csrf=False)
    def enroll(self):
        payload = self._payload()
        try:
            device, token = self._model("hr.attendance.tracking.device").enroll(
                payload.get("code"), payload.get("installation_uuid"), payload.get("device_info")
            )
            return self._response({
                "ok": True,
                "token": token,
                "device": {"id": device.id, "name": device.name},
                "employee": {"id": device.employee_id.id, "name": device.employee_id.name},
            })
        except (UserError, ValidationError, ValueError) as error:
            return self._error(error)

    @http.route("/mobile_tracking/v1/status", type="http", auth="none", methods=["GET", "POST"], csrf=False)
    def status(self):
        payload = self._payload()
        device = self._device(payload)
        if not device:
            return self._error("Dispositivo no autorizado.", 401, "unauthorized")
        attendance = self._model("hr.attendance").search([
            ("employee_id", "=", device.employee_id.id), ("check_out", "=", False)
        ], order="check_in desc", limit=1)
        session = self._model("hr.attendance.location.session").search([
            ("device_id", "=", device.id), ("state", "=", "running")
        ], order="started_at desc", limit=1)
        last_attendance = attendance or self._model("hr.attendance").search([
            ("employee_id", "=", device.employee_id.id)
        ], order="check_in desc", limit=1)
        return self._response({
            "ok": True,
            "employee": {"id": device.employee_id.id, "name": device.employee_id.name},
            "checked_in": bool(attendance),
            "attendance_id": attendance.id or False,
            "session_id": session.id or False,
            "check_in": fields.Datetime.to_string(attendance.check_in) if attendance else False,
            "last_check_in": fields.Datetime.to_string(last_attendance.check_in) if last_attendance else False,
            "last_check_out": fields.Datetime.to_string(last_attendance.check_out) if last_attendance and last_attendance.check_out else False,
            "can_check_in": not bool(attendance),
            "can_check_out": bool(attendance),
        })

    @http.route("/mobile_tracking/v1/attendance/check-in", type="http", auth="none", methods=["POST"], csrf=False)
    def check_in(self):
        payload = self._payload()
        device = self._device(payload)
        if not device:
            return self._error("Dispositivo no autorizado.", 401, "unauthorized")
        try:
            Attendance = self._model("hr.attendance")
            attendance = Attendance.search([
                ("employee_id", "=", device.employee_id.id), ("check_out", "=", False)
            ], order="check_in desc", limit=1)
            already_checked_in = bool(attendance)
            if not attendance:
                attendance = device.employee_id.sudo()._attendance_action_change(self._geo(payload))
            Session = self._model("hr.attendance.location.session")
            session = Session.search([
                ("attendance_id", "=", attendance.id), ("device_id", "=", device.id), ("state", "=", "running")
            ], limit=1)
            if not session:
                session = Session.create({
                    "name": "Jornada %s - %s" % (device.employee_id.name, fields.Date.context_today(device)),
                    "employee_id": device.employee_id.id,
                    "attendance_id": attendance.id,
                    "device_id": device.id,
                })
            location = payload.get("location")
            if location:
                point = dict(location, uuid=location.get("uuid") or payload.get("request_uuid"))
                session.ingest_points([point])
            return self._response({
                "ok": True, "attendance_id": attendance.id, "session_id": session.id,
                "check_in": fields.Datetime.to_string(attendance.check_in),
                "already_checked_in": already_checked_in,
            })
        except (UserError, ValidationError, ValueError, TypeError) as error:
            return self._error(error)

    @http.route("/mobile_tracking/v1/locations/batch", type="http", auth="none", methods=["POST"], csrf=False)
    def locations_batch(self):
        payload = self._payload()
        device = self._device(payload)
        if not device:
            return self._error("Dispositivo no autorizado.", 401, "unauthorized")
        session = self._model("hr.attendance.location.session").search([
            ("device_id", "=", device.id), ("state", "=", "running")
        ], order="started_at desc", limit=1)
        if not session:
            return self._error("No existe una jornada activa.", 409, "no_active_attendance")
        try:
            accepted = session.ingest_points(payload.get("points"))
            return self._response({"ok": True, "accepted": accepted, "session_id": session.id})
        except (UserError, ValidationError, ValueError, TypeError) as error:
            return self._error(error)

    @http.route("/mobile_tracking/v1/attendance/check-out", type="http", auth="none", methods=["POST"], csrf=False)
    def check_out(self):
        payload = self._payload()
        device = self._device(payload)
        if not device:
            return self._error("Dispositivo no autorizado.", 401, "unauthorized")
        attendance = self._model("hr.attendance").search([
            ("employee_id", "=", device.employee_id.id), ("check_out", "=", False)
        ], order="check_in desc", limit=1)
        if not attendance:
            return self._error("El empleado no tiene una asistencia abierta.", 409, "not_checked_in")
        sessions = self._model("hr.attendance.location.session").search([
            ("attendance_id", "=", attendance.id), ("state", "=", "running")
        ])
        try:
            location = payload.get("location")
            own_session = sessions.filtered(lambda item: item.device_id == device)[:1]
            if location and own_session:
                point = dict(location, uuid=location.get("uuid") or payload.get("request_uuid"))
                own_session.ingest_points([point])
            attendance = device.employee_id.sudo()._attendance_action_change(self._geo(payload))
            sessions.action_finish()
            return self._response({
                "ok": True, "attendance_id": attendance.id,
                "check_in": fields.Datetime.to_string(attendance.check_in),
                "check_out": fields.Datetime.to_string(attendance.check_out),
            })
        except (UserError, ValidationError, ValueError, TypeError) as error:
            return self._error(error)
