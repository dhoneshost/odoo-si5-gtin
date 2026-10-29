# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "GTIN Brazilian Fiscal",
    "version": "18.0.1.3.0",
    "summary": "Review NCM and CEST suggestions from SI5 Global on l10n_br_fiscal products. "
    "Uses the lookup of Product GTIN Lookup (consent first, only the barcode and "
    "the company API token are sent); sends no other data",
    "author": "SI5",
    "license": "AGPL-3",
    "development_status": "Stable",
    "category": "Localization/Brazil",
    "website": "https://github.com/dhoneshost/odoo-si5-gtin",
    "maintainers": ["dhoneshost"],
    "support": "dev@si5.com.br",
    "images": ["static/description/banner_en.png"],
    "depends": ["product_si5_gtin", "l10n_br_fiscal"],
    "data": ["views/lookup.xml"],
    "installable": True,
    "auto_install": True,
    "application": False,
}
