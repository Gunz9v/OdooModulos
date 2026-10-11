# OdooModulos · Portafolio de desarrollo Odoo

Repositorio centralizado de desarrollos personalizados para Odoo, organizado por version y area funcional.

## Versiones

- [Odoo 18](./18.0/) — 9 modulos personalizados y 5 addons MuK de terceros.
- [Odoo 17](./17.0/) — espacio preparado para futuros desarrollos.
- [Documentacion](./docs/) — plantilla y guias de documentacion.

## Modulos personalizados · Odoo 18

| Modulo | Area | Proposito |
| --- | --- | --- |
| [Legajos de Empleados](./18.0/employee_legajo_documents/) | Recursos Humanos | Gestion de legajos, tipos documentales e historial de documentos de empleados. |
| [Documentos y Boletas de Empleados (compatibilidad)](./18.0/employee_payslip_documents/) | Recursos Humanos | Modulo puente de compatibilidad entre Legajos de Empleados y SmartDoc Laboral; no constituye una aplicacion independiente. |
| [Attendance Location Tracking](./18.0/hr_attendance_location_tracking/) | Asistencia y geolocalizacion | Gestion de dispositivos corporativos y seguimiento GPS durante jornadas laborales; incluye integracion con aplicacion movil y mapas. |
| [Peru SIRE API](./18.0/l10n_pe_sire_api/) | Localizacion peruana / SUNAT | Conexion con servicios API de SUNAT para procesos SIRE, gestion de tickets y generacion de registros. |
| [Peru SIRE Core](./18.0/l10n_pe_sire_core/) | Localizacion peruana / SUNAT | Base comun para periodos, lotes de importacion y flujos de gestion SIRE. |
| [Peru SIRE PLE Import](./18.0/l10n_pe_sire_ple_import/) | Localizacion peruana / SUNAT | Importacion y normalizacion de archivos PLE, propuestas SUNAT y conciliacion de registros. |
| [Peru SUNAT Purchase Proposal](./18.0/l10n_pe_sunat_purchase_proposal/) | Contabilidad / SUNAT | Importacion de propuestas RCE, comparacion con compras registradas y asistencia para generar facturas faltantes. |
| [Salesperson Route Tracking](./18.0/salesperson_route_tracking/) | Ventas y geolocalizacion | Captura GPS en primer plano y consulta del recorrido historico de vendedores. |
| [SmartDoc Laboral](./18.0/smart_labor_documents/) | Recursos Humanos | Portal documental para boletas, contratos firmables y comunicados a trabajadores. |

## Addons de terceros

El directorio `18.0/` tambien contiene `muk_web_appsbar`, `muk_web_chatter`, `muk_web_colors`, `muk_web_dialog` y `muk_web_theme`. **No son desarrollos propios**: conserva sus atribuciones y condiciones de licencia.

## Instalacion local

1. Copia `.env.example` a `.env` y `config/odoo.conf.example` a `config/odoo.conf`.
2. Sustituye los valores de ejemplo por credenciales locales seguras y coherentes entre Docker, PostgreSQL y Odoo.
3. Revisa las rutas y dependencias; `docker-compose.yml` monta `./18.0` en `/mnt/extra-addons`.
4. Inicia los servicios con `docker compose up -d --build` y actualiza la lista de aplicaciones de Odoo.

**Nota:** la documentacion describe el codigo del repositorio; no certifica pruebas de despliegue ni compatibilidad en produccion.

## Buenas practicas

- No publiques archivos `.env`, `config/odoo.conf`, logs, tokens ni datos de clientes.
- Documenta cambios funcionales y agrega pruebas antes de desplegar.
- Usa [la plantilla de README](./docs/MODULE_README_TEMPLATE.md) para nuevos addons.
