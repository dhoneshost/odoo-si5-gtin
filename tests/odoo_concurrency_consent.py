# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Concurrency check for the lookup consent (real PostgreSQL transactions).

Not part of the automatic suites: TransactionCase runs on a single cursor and
cannot reproduce two requests at once. Run it on a disposable database where
product_si5_gtin is installed:

    odoo-bin shell -d <db> < tests/odoo_concurrency_consent.py

Two threads, each with its own cursor, call action_lookup on the same consent at
the same time; the API is mocked and slow. A serialization failure is retried
like Odoo's HTTP layer does. Expected: exactly one API request, one review, and
the other call refused because the consent was already used.
"""
import threading
import time
from unittest.mock import patch

from psycopg2.errors import SerializationFailure

import odoo
from odoo.addons.product_si5_gtin import models as si5_models
from odoo.exceptions import UserError

registry = env.registry  # noqa: F821  (provided by odoo-bin shell)
uid = env.uid  # noqa: F821
Product = env["product.product"]  # noqa: F821
product = Product.create({"name": "SI5 concurrency fixture", "barcode": "7891000325858"})
cid = product.action_si5_lookup()["res_id"]
env["si5.lookup.consent"].browse(cid).consent = True  # noqa: F821
env.cr.commit()  # noqa: F821

calls = []
results = {}
barrier = threading.Barrier(2)
DATA = {"produto": "Proposed", "marca": "", "imagem_url": "", "ncm": "", "cest_codigo": ""}


def slow_lookup(code, token):
    calls.append(code)
    time.sleep(2)  # keeps the first transaction open while the second one arrives
    return DATA


def worker(name):
    first = True
    for attempt in range(1, 6):
        with registry.cursor() as cr:
            wenv = odoo.api.Environment(cr, uid, {})
            try:
                if first:
                    barrier.wait()
                    first = False
                action = wenv["si5.lookup.consent"].browse(cid).action_lookup()
                cr.commit()
                results[name] = f"review {action['res_model']} (attempt {attempt})"
                return
            except SerializationFailure:
                cr.rollback()
                results[name] = f"serialization failure, retrying (attempt {attempt})"
            except UserError as error:
                cr.rollback()
                results[name] = f"refused: {error.args[0]} (attempt {attempt})"
                return


with patch.object(si5_models, "lookup", slow_lookup):
    threads = [threading.Thread(target=worker, args=(n,)) for n in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

env.invalidate_all()  # noqa: F821
consent = env["si5.lookup.consent"].browse(cid)  # noqa: F821
reviews = env["si5.lookup"].search_count([("product_id", "=", product.id)])  # noqa: F821
print("API requests:", len(calls))
print("results:", results)
print("consent state:", consent.state, "| reviews created:", reviews)
ok = len(calls) == 1 and reviews == 1 and consent.state == "used"
ok = ok and sorted(r.split(":")[0].split(" ")[0] for r in results.values()) == ["refused", "review"]
print("CONCURRENCY OK" if ok else "CONCURRENCY FAILED")
# clean up the fixture
env["si5.lookup"].search([("product_id", "=", product.id)]).unlink()  # noqa: F821
consent.unlink()
product.unlink()
env.cr.commit()  # noqa: F821
