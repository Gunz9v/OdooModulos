# Odoo Modules | Development Portfolio

Custom Odoo addons organized by major version.

## Repository structure

- [`17.0/`](./17.0/) — Odoo 17 modules (future additions)
- [`18.0/`](./18.0/) — Odoo 18 modules
- [`docs/`](./docs/) — Functional and technical documentation

## Odoo 18 modules

- **Human resources:** `employee_legajo_documents`, `employee_payslip_documents`, `smart_labor_documents`, `hr_attendance_location_tracking`
- **Sales:** `salesperson_route_tracking`
- **Peruvian localization / SUNAT SIRE:** `l10n_pe_sire_core`, `l10n_pe_sire_api`, `l10n_pe_sire_ple_import`, `l10n_pe_sunat_purchase_proposal`
- **Third-party UI dependencies:** `muk_web_*` (retain original authorship and licenses)

## Local environment

The Docker Compose setup runs Odoo 18 with custom addons mounted from `./18.0`.

Review module dependencies and security before production use. Do not commit live credentials, private business data, or generated caches.
