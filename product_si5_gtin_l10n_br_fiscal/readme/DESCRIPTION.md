Bridge between `product_si5_gtin` (Product GTIN Lookup) and the OCA Brazilian
fiscal engine (`l10n_br_fiscal`). The SI5 review also shows the NCM and CEST
records found in the fiscal tables and lets the user apply them to the product
template, one switch each, never by default.

A code is only suggested when the exact record exists in `l10n_br_fiscal.ncm` /
`l10n_br_fiscal.cest`. A CEST that the tables link to another NCM is not offered.
The review states whether the tables link the CEST to the target NCM; when the
CEST has no NCM link in the tables, or the product has no NCM, the suggestion is
marked as not verified.

Only `ncm_id` and `cest_id` are written. `l10n_br_fiscal` itself derives the
Fiscal Product Genre and the Export UoM from the NCM; fiscal type, ICMS origin,
taxes and operations are not changed. Fiscal classification remains the
responsibility of the company and its accountant.

No extra data is sent: NCM and CEST come in the same consented lookup of
`product_si5_gtin` (barcode, company API token and module User-Agent only).
