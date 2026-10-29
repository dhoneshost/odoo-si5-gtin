# SI5 Global GTIN lookup for Odoo 18

Odoo Community 18.0 addons that look up a product by its barcode (GTIN/EAN)
on [SI5 Global](https://global.si5.com.br) — a Brazilian product catalogue with
millions of GTINs — and let the user **review** the suggested data before
anything is written.

| Addon | What it does |
|---|---|
| [`product_si5_gtin`](product_si5_gtin) — *Product GTIN Lookup* | Button **Look up GTIN with SI5** on the product form. Asks for explicit consent, then opens a review with the suggested name, internal note (brand, category), gross weight and image. Nothing is selected by default; each field is applied only when ticked. |
| [`product_si5_gtin_l10n_br_fiscal`](product_si5_gtin_l10n_br_fiscal) — *GTIN Brazilian Fiscal* | Bridge with the OCA Brazilian fiscal engine ([`l10n_br_fiscal`](https://github.com/OCA/l10n-brazil/tree/18.0/l10n_br_fiscal)). Also offers the NCM and CEST records found in the fiscal tables, applied to the product template only after review. Installed automatically when both addons are present. |

## Design

Inspired by the review-then-confirm workflow of OCA
[`l10n_br_cnpj_search`](https://github.com/OCA/l10n-brazil/tree/16.0/l10n_br_cnpj_search):

- **Explicit consent** — the button opens a dialog that lists what will be sent
  (barcode, company API token, module User-Agent) with an unticked consent box;
  the API is called only after the user ticks it and clicks *Look up*. Cancel,
  close or Esc send nothing. Never on onchange, import, cron or bulk.
- **Review first** — current and suggested values side by side; every replacement
  checkbox starts unchecked. Fields shared by variants/companies (name,
  description, NCM, CEST) need an extra confirmation. Weight and image are written
  on the variant.
- **Image safety** — only HTTPS pictures from the SI5 hosts, size/MIME/dimension
  checks, user-confirmed download, and the reviewed bytes are the ones applied
  (no second download).
- **Fiscal data is a suggestion** — NCM/CEST are only offered when the exact code
  exists in the `l10n_br_fiscal` tables; a CEST linked to another NCM is not
  offered, and one the tables cannot check (no NCM link, or no product NCM) is
  marked as not verified. Only `ncm_id`/`cest_id` are written. Fiscal
  classification remains the responsibility of the company and its accountant.
- **Credentials** — one token per company. Set it in *Settings › General
  Settings › SI5 Global* (administrators only; masked in the settings form).
  Administrators can read the stored value: masking is not encryption and does
  not prevent authorized reads or exports. Alternatively, use the server
  environment variable
  `SI5_TOKEN_COMPANY_<company id>`, which takes precedence. No fallback between
  companies.
- **Network hardening** — fixed hosts, public IPs only, TLS verified, 8 s socket
  timeout, response size limits, sanitized error messages (no token, URL or body
  in errors or logs).

## Getting a token

Create a free account at <https://global.si5.com.br>, then create a token in *Minha conta*
(<https://global.si5.com.br/conta>). The free plan has a daily quota; paid plans
(<https://global.si5.com.br/precos/api>) add a higher quota and the full fiscal
sheet (IBPT, IPI, PIS/COFINS, ST and IBS/CBS by state).

## Installation

Add this repository to the addons path of an Odoo Community 18.0 server and
install `product_si5_gtin` (and `l10n_br_fiscal` if you use the Brazilian
localization). Python dependency: Pillow, already required by Odoo.

## Tests

```bash
# pure client (no Odoo needed)
python -m unittest discover -s tests -v

# Odoo, on a disposable database
odoo -d test_si5 -i product_si5_gtin,product_si5_gtin_l10n_br_fiscal \
  --test-enable --test-tags=/product_si5_gtin,/product_si5_gtin_l10n_br_fiscal \
  --stop-after-init --without-demo=all
```

All tests mock the network; a guard fails the test if real transport is attempted.

```bash
# concurrency of the lookup consent (two real transactions, disposable database)
odoo shell -d test_si5 < tests/odoo_concurrency_consent.py
```

A consent allows one lookup: two simultaneous clicks produce a single API request.

## Release scope and versioning

| Addon | Version | Maturity (`development_status`) |
|---|---|---|
| `product_si5_gtin` (Product GTIN Lookup) | 18.0.2.3.0 | Stable |
| `product_si5_gtin_l10n_br_fiscal` (GTIN Brazilian Fiscal) | 18.0.1.3.0 | Stable |

Stable describes the tested **assisted review-and-apply software workflow**, not
certification of catalogue data, fiscal classification, every Odoo deployment,
or a claim of 30 days in production. No field is selected automatically.

The release criteria are executable client/ORM tests, consent and permission
checks, duplicate-request prevention, safe image handling, upgrade preservation,
and fail-closed fiscal review contracts. See [release validation](docs/release-18.0.md)
for results, supported scope and explicit limits.

The previous README's 30-day prerequisite has been consciously replaced by
these scope-specific acceptance criteria. Production observation is follow-up,
not evidence already obtained. Accountant review remains essential for each
business's fiscal classifications; this software does not certify them.
Versions remain monotonic: no downgrade was used to change maturity.

## Status and OCA

Discussed with the Brazilian localization maintainers in
[OCA/l10n-brazil#5358](https://github.com/OCA/l10n-brazil/discussions/5358):
the plan is to mature it here first and propose it to the OCA once validated by
users. Issues and pull requests are welcome.

## License

[AGPL-3.0-or-later](LICENSE). Copyright 2026 SI5.
