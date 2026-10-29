# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Product GTIN Lookup",
    "version": "18.0.2.3.0",
    "summary": "Look up a product barcode on SI5 Global and apply reviewed data. "
    "External service: after explicit consent on each lookup, only the barcode, "
    "the company API token and a module User-Agent are sent to global.si5.com.br",
    "author": "SI5",
    "license": "AGPL-3",
    "development_status": "Stable",
    "category": "Sales/Sales",
    "website": "https://github.com/dhoneshost/odoo-si5-gtin",
    "maintainers": ["dhoneshost"],
    "support": "dev@si5.com.br",
    "images": ["static/description/banner_en.png"],
    "depends": ["product"],
    "external_dependencies": {"python": ["Pillow"]},
    "data": ["security/ir.model.access.csv", "security/rules.xml", "views/lookup.xml"],
    "installable": True,
    "application": False,
}
