# Attendance Location Tracking

**Odoo:** 18.0 · **Version:** 18.0.2.1.0 · **Licencia:** LGPL-3

## Descripcion

Modulo para dispositivos corporativos y seguimiento GPS de jornadas laborales, separado de `salesperson_route_tracking`.

## Funcionalidades

- Vinculacion de dispositivos mediante codigo temporal y tokens revocables.
- Registro de asistencia movil y sesiones GPS laborales.
- Mapa historico por jornada y mapa del equipo activo, con actualizacion prevista cada 30 segundos.
- Cierre de sesion GPS al finalizar la asistencia; la aplicacion consulta periodicamente el estado del servidor.

## API movil

- `POST /mobile_tracking/v1/enroll`
- `GET /mobile_tracking/v1/status`
- `POST /mobile_tracking/v1/attendance/check-in`
- `POST /mobile_tracking/v1/locations/batch`
- `POST /mobile_tracking/v1/attendance/check-out`

Las rutas autenticadas requieren `Authorization: Bearer ...` y `X-Installation-UUID`.

## Dependencias

- `hr_attendance`
- `mail`
- `web`

## Instalacion

Coloca el modulo en el directorio de addons de Odoo 18, actualiza la lista de aplicaciones e instala las dependencias. Configura HTTPS y permisos de acceso antes de conectar dispositivos reales.

## Evidencias

Capturas de pantalla y pruebas de instalacion pendientes de incorporar. Consulta [el manifest](./__manifest__.py) para detalles tecnicos.
