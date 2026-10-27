# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Product SI5 GTIN lookup",
    "version": "18.0.2.0.0",
    "summary": "Look up a product by GTIN on SI5 Global and apply reviewed data",
    "author": "SI5",
    "license": "AGPL-3",
    "development_status": "Beta",
    "category": "Sales/Sales",
    "website": "https://github.com/dhoneshost/odoo-si5-gtin",
    "maintainers": ["dhoneshost"],
    "depends": ["product"],
    "external_dependencies": {"python": ["Pillow"]},
    "data": ["security/ir.model.access.csv", "security/rules.xml", "views/lookup.xml"],
    "installable": True,
    "application": False,
}
