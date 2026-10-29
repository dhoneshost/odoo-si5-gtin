# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Disposable DB upgrade fixture; run with an Odoo shell-provided ``env``.

Set SI5_QA_PHASE=before|after and SI5_QA_STATE to an external JSON file.
Run 'before' with the source revision, upgrade both addons, then run 'after'
with the destination revision. Never run on a production database. All lookups
are mocked and the real SI5 transport is guarded. This script commits fixtures.
"""
import base64
import hashlib
import io
import json
import os
from unittest.mock import patch

from PIL import Image

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import new_test_user

DATA = {
    "produto": "Offline upgrade suggestion", "marca": "QA fixture",
    "imagem_url": "", "ncm": "99999901", "cest_codigo": "9999901",
}
TOKEN = "OFFLINE-UPGRADE-FIXTURE-NOT-A-REAL-TOKEN"


def snapshot(product):
    return {
        "name": product.name, "barcode": product.barcode,
        "weight": product.weight, "description": product.description,
        "image_sha256": hashlib.sha256(product.image_1920 or b"").hexdigest(),
        "ncm_id": product.ncm_id.id, "cest_id": product.cest_id.id,
        "fiscal_type": product.fiscal_type, "icms_origin": product.icms_origin,
        "tax_icms_or_issqn": product.tax_icms_or_issqn,
    }


def denied(call):
    try:
        call()
    except (AccessError, UserError):
        return
    raise AssertionError("Expected access/validation rejection")


def execute(env):
    phase = os.environ["SI5_QA_PHASE"]
    state_path = os.environ["SI5_QA_STATE"]
    if phase == "before":
        env.company.si5_token = TOKEN
        ncm = env["l10n_br_fiscal.ncm"].create(
            {"code": "9999.99.01", "name": "Offline upgrade NCM"}
        )
        cest_model = env["l10n_br_fiscal.cest"]
        cest = cest_model.create({
            "segment": cest_model._fields["segment"].selection[0][0],
            "code": "99.999.01", "item": "999", "name": "Offline upgrade CEST",
            "ncms": "99999901",
        })
        cest.ncm_ids = ncm
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
        product = env["product.product"].create({
            "name": "Offline upgrade preserved product", "barcode": "036000291452",
            "weight": 0.45, "description": "Preserve this internal note",
            "image_1920": base64.b64encode(buffer.getvalue()),
            "ncm_id": ncm.id, "cest_id": cest.id,
        })
        action = product.action_si5_lookup()
        if action["res_model"] == "si5.lookup.consent":
            consent = env["si5.lookup.consent"].browse(action["res_id"])
            consent.consent = True
            action = consent.action_lookup()
        review = env["si5.lookup"].browse(action["res_id"])
        other = new_test_user(env, login="upgrade_other_manager",
                              groups="base.group_user,product.group_product_manager")
        company = env["res.company"].create({"name": "Offline upgrade other company"})
        other_product = env["product.product"].create({
            "name": "Other company fixture", "company_id": company.id,
            "barcode": "7891000325858",
        })
        state = {"product": product.id, "review": review.id,
                 "snapshot": snapshot(product), "company": env.company.id,
                 "other_user": other.id, "other_product": other_product.id,
                 "other_company": company.id}
        with open(state_path, "w", encoding="utf-8") as stream:
            json.dump(state, stream)
        env.cr.commit()
        print("BEFORE PASS: product, image, fiscal pair, fake token and review persisted")
    elif phase == "after":
        with open(state_path, encoding="utf-8") as stream:
            state = json.load(stream)
        product = env["product.product"].browse(state["product"])
        assert snapshot(product) == state["snapshot"], "Product/fiscal/image changed"
        assert env["res.company"].browse(state["company"]).si5_token == TOKEN
        review = env["si5.lookup"].browse(state["review"])
        assert review.exists() and review.state == "draft"
        assert review.product_id == product and review.proposed_name == DATA["produto"]
        denied(lambda: review.with_user(state["other_user"]).read(["proposed_name"]))
        other_product = env["product.product"].browse(state["other_product"])
        denied(lambda: other_product.with_context(
            allowed_company_ids=[state["company"], state["other_company"]]
        ).action_si5_lookup())
        with patch("odoo.addons.product_si5_gtin.models.lookup") as lookup:
            action = product.with_context(default_consent=True).action_si5_lookup()
            consent = env["si5.lookup.consent"].browse(action["res_id"])
            assert not consent.consent and consent.state == "pending"
            denied(consent.action_lookup)
            lookup.assert_not_called()
        consent.consent = True
        consent.action_lookup()
        denied(consent.action_lookup)
        denied(lambda: env["si5.lookup.consent"].with_user(state["other_user"]).create(
            {"product_id": product.id, "consent": True}
        ))
        assert snapshot(product) == state["snapshot"]
        env.cr.rollback()
        print("AFTER PASS: product/image/token/NCM/CEST/other fiscal fields/review preserved")
        print("AFTER PASS: consent unchecked, replay denied, owner/company/create ACL enforced")
    else:
        raise ValueError("SI5_QA_PHASE must be before or after")


if "env" in globals():
    with patch("odoo.addons.product_si5_gtin.service.PinnedHTTPS",
               side_effect=AssertionError("Offline upgrade attempted real transport")):
        with patch("odoo.addons.product_si5_gtin.models.lookup", return_value=DATA):
            execute(env)  # noqa: F821
