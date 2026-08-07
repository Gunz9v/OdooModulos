# Attendance Location Tracking

Addon Odoo 18 separado de `salesperson_route_tracking`.

Proporciona dispositivos vinculados por codigo temporal, tokens revocables, asistencia movil, sesiones GPS laborales y API HTTPS para la aplicacion Android.

Incluye un mapa historico por jornada y un mapa del equipo activo que actualiza posiciones cada 30 segundos.

## API

- `POST /mobile_tracking/v1/enroll`
- `GET /mobile_tracking/v1/status`
- `POST /mobile_tracking/v1/attendance/check-in`
- `POST /mobile_tracking/v1/locations/batch`
- `POST /mobile_tracking/v1/attendance/check-out`

Las rutas autenticadas requieren `Authorization: Bearer ...` y `X-Installation-UUID`.
