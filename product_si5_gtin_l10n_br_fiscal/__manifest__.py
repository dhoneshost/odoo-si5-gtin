# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Product SI5 GTIN lookup - Brazilian fiscal data",
    "version": "18.0.1.1.0",
    "summary": "Apply reviewed NCM and CEST from SI5 Global to l10n_br_fiscal products",
    "author": "SI5",
    "license": "AGPL-3",
    "development_status": "Alpha",
    "category": "Localization/Brazil",
    "website": "https://github.com/dhoneshost/odoo-si5-gtin",
    "maintainers": ["dhoneshost"],
    "support": "dev@si5.com.br",
    "images": ["static/description/banner.png"],
    "depends": ["product_si5_gtin", "l10n_br_fiscal"],
    "data": ["views/lookup.xml"],
    "installable": True,
    "auto_install": True,
    "application": False,
}
