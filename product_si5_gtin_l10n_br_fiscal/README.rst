================================================
Product SI5 GTIN lookup - Brazilian fiscal data
================================================

Bridge between ``product_si5_gtin`` and the OCA Brazilian fiscal engine
(``l10n_br_fiscal``). The SI5 review also shows the NCM and CEST records found in
the fiscal tables and lets the user apply them to the product template, one
checkbox each, never by default.

A code is only suggested when the exact record exists in ``l10n_br_fiscal.ncm`` /
``l10n_br_fiscal.cest``, and the CEST only when it is linked to the NCM the
product will have. Fiscal classification remains the responsibility of the
company and its accountant.

Installed automatically when ``product_si5_gtin`` and ``l10n_br_fiscal`` are both
installed.

Credits
=======

* SI5 - Dhones Meneses
