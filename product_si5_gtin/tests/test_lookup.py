# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import float_round

from ..service import LookupError


def lookup_action(record):
    """Button → consent dialog → tick the box → lookup (the only path to the API)."""
    consent = record.env["si5.lookup.consent"].browse(
        record.action_si5_lookup()["res_id"]
    )
    consent.consent = True
    return consent.action_lookup()


@tagged("post_install", "-at_install")
class TestLookup(TransactionCase):
    def setUp(self):
        super().setUp()
        guard = patch(
            "odoo.addons.product_si5_gtin.service.PinnedHTTPS",
            side_effect=AssertionError("Offline test attempted real transport"),
        )
        guard.start()
        self.addCleanup(guard.stop)
        self.product = self.env["product.product"].create(
            {"name": "Existing", "barcode": "7891000325858"}
        )

    def preview(self, product=None):
        product = product if product is not None else self.product
        data = {
            "produto": "Proposed",
            "marca": "Fixture",
            "imagem_url": "",
            "ncm": "",
            "cest_codigo": "",
        }
        with patch("odoo.addons.product_si5_gtin.models.lookup", return_value=data):
            consent = product.env["si5.lookup.consent"].browse(
                product.action_si5_lookup()["res_id"]
            )
            consent.consent = True
            action = consent.action_lookup()
        return product.env["si5.lookup"].browse(action["res_id"])

    def test_consent_before_any_request(self):
        data = {"produto": "Proposed", "marca": "", "imagem_url": "", "ncm": "", "cest_codigo": ""}
        with patch(
            "odoo.addons.product_si5_gtin.models.lookup", return_value=data
        ) as api:
            action = self.product.action_si5_lookup()
            # The button only opens the consent dialog: nothing is sent.
            self.assertEqual(action["res_model"], "si5.lookup.consent")
            api.assert_not_called()
            consent = self.env["si5.lookup.consent"].browse(action["res_id"])
            self.assertFalse(consent.consent, "Consent must start unticked")
            self.assertEqual(consent.code, self.product.barcode)
            # Without the box ticked the lookup is refused and nothing is sent.
            with self.assertRaises(UserError):
                consent.action_lookup()
            api.assert_not_called()
            consent.consent = True
            review = consent.action_lookup()
            api.assert_called_once()
            self.assertEqual(api.call_args.args[0], self.product.barcode)
            self.assertEqual(review["res_model"], "si5.lookup")

    def test_consent_target_is_server_owned(self):
        other = self.env["product.product"].create(
            {"name": "Other", "barcode": "036000291452"}
        )
        consent = self.env["si5.lookup.consent"].browse(
            self.product.action_si5_lookup()["res_id"]
        )
        with self.assertRaises(AccessError):
            consent.write({"product_id": other.id})
        with self.assertRaises(AccessError):
            consent.write({"code": other.barcode})

    def test_consent_barcode_changed(self):
        consent = self.env["si5.lookup.consent"].browse(
            self.product.action_si5_lookup()["res_id"]
        )
        consent.consent = True
        self.product.barcode = "036000291452"
        with patch("odoo.addons.product_si5_gtin.models.lookup") as api:
            with self.assertRaises(UserError):
                consent.action_lookup()
            api.assert_not_called()

    def test_preserve_and_select(self):
        wizard = self.preview()
        wizard.action_apply()
        self.assertEqual(self.product.name, "Existing")
        wizard.apply_name = True
        with self.assertRaises(UserError):
            wizard.action_apply()
        wizard.confirm_shared = True
        wizard.action_apply()
        self.assertEqual(self.product.name, "Proposed")
        wizard = self.preview()
        wizard.write(
            {
                "apply_description": True,
                "confirm_shared": True,
                "proposed_description": "Review <script>alert(1)</script> & brand",
            }
        )
        wizard.action_apply()
        self.assertNotIn("<script>", self.product.description)
        self.assertIn("&lt;script&gt;", self.product.description)

    def test_company_switch(self):
        wizard = self.preview()
        company = self.env["res.company"].create({"name": "Other fixture"})
        with self.assertRaises(AccessError):
            wizard.with_company(company).action_apply()

    def test_changed_gtin(self):
        wizard = self.preview()
        self.product.barcode = "036000291452"
        with self.assertRaises(UserError):
            wizard.action_preview_image()
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_no_image_without_selection(self):
        wizard = self.preview()
        with patch(
            "odoo.addons.product_si5_gtin.models.image",
            side_effect=AssertionError("Unexpected image request"),
        ):
            wizard.action_apply()

    def test_public_user_cannot_consult(self):
        with patch(
            "odoo.addons.product_si5_gtin.models.lookup",
            side_effect=AssertionError("Unauthorized API access"),
        ):
            with self.assertRaises(AccessError):
                self.product.with_user(
                    self.env.ref("base.public_user")
                ).action_si5_lookup()

    def test_company_token_selection(self):
        company = self.env["res.company"].create({"name": "Token fixture company"})
        product = self.product.with_company(company)
        data = {
            "produto": "Fixture",
            "marca": "",
            "imagem_url": "",
            "ncm": "",
            "cest_codigo": "",
        }
        key = f"SI5_TOKEN_COMPANY_{company.id}"
        with patch.dict("os.environ", {key: "FAKE_COMPANY_TOKEN"}, clear=True):
            with patch(
                "odoo.addons.product_si5_gtin.models.lookup", return_value=data
            ) as fake:
                lookup_action(product)
                fake.assert_called_once_with("7891000325858", "FAKE_COMPANY_TOKEN")

    def test_invalid_image_preview(self):
        wizard = self.preview()
        with patch(
            "odoo.addons.product_si5_gtin.models.image", return_value=b"invalid image"
        ):
            with self.assertRaises(UserError):
                wizard.action_preview_image()

    def make_variants(self):
        attribute = self.env["product.attribute"].create({"name": "Fixture option"})
        values = self.env["product.attribute.value"].create(
            [
                {"name": "A", "attribute_id": attribute.id},
                {"name": "B", "attribute_id": attribute.id},
            ]
        )
        template = self.env["product.template"].create(
            {
                "name": "Shared fixture",
                "attribute_line_ids": [
                    (
                        0,
                        0,
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [(6, 0, values.ids)],
                        },
                    )
                ],
            }
        )
        self.assertEqual(len(template.product_variant_ids), 2)
        self.product = template.product_variant_ids[0]
        self.product.barcode = "036000291452"
        return template, template.product_variant_ids[1]

    def test_variant_template_name_impact(self):
        template, sibling = self.make_variants()
        wizard = self.preview()
        wizard.apply_name = True
        with self.assertRaises(UserError):
            wizard.action_apply()
        self.assertEqual(template.name, "Shared fixture")
        wizard.confirm_shared = True
        wizard.action_apply()
        self.assertEqual(template.name, "Proposed")
        self.assertEqual(sibling.name, "Proposed")
        self.assertEqual(self.product.barcode, "036000291452")
        self.assertFalse(sibling.barcode)

    def test_variant_image_does_not_replace_sibling_or_template(self):
        import io

        from PIL import Image

        template, sibling = self.make_variants()
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
        wizard = self.preview()
        wizard.write({"apply_image": True, "confirm_shared": True})
        with patch(
            "odoo.addons.product_si5_gtin.models.image", return_value=buffer.getvalue()
        ):
            wizard.action_preview_image()
            wizard.action_apply()
        self.assertTrue(self.product.image_variant_1920)
        self.assertFalse(sibling.image_variant_1920)
        self.assertFalse(template.image_1920)

    def test_packaging_preserved(self):
        package = self.env["product.packaging"].create(
            {
                "name": "Case fixture",
                "product_id": self.product.id,
                "qty": 6,
                "barcode": "96385074",
            }
        )
        wizard = self.preview()
        wizard.write({"apply_name": True, "confirm_shared": True})
        wizard.action_apply()
        self.assertEqual(package.barcode, "96385074")
        self.assertEqual(package.qty, 6)
        self.assertEqual(self.product.barcode, "7891000325858")

    def test_optional_oca_fiscal_fields_unchanged(self):
        names = [
            name
            for name in ("ncm_id", "cest_id", "fiscal_type", "icms_origin")
            if name in self.product.product_tmpl_id._fields
        ]
        if not names:
            self.skipTest("Optional l10n_br_fiscal not installed")
        before = self.product.product_tmpl_id.read(names)[0]
        wizard = self.preview()
        wizard.write({"apply_name": True, "confirm_shared": True})
        wizard.action_apply()
        self.assertEqual(self.product.product_tmpl_id.read(names)[0], before)

    def manager(self, login="si5_review_manager"):
        return new_test_user(
            self.env["res.users"].with_context(no_reset_password=True).env,
            login=login,
            groups="base.group_user,product.group_product_manager",
            company_id=self.env.company.id,
            company_ids=[Command.set(self.env.company.ids)],
        )

    def test_product_change_requires_new_review(self):
        wizard = self.preview()
        wizard.write({"apply_name": True, "confirm_shared": True})
        self.product.name = "Concurrent edit"
        with self.assertRaises(UserError):
            wizard.action_apply()
        self.assertEqual(self.product.name, "Concurrent edit")

    def test_review_cannot_be_applied_twice(self):
        wizard = self.preview()
        wizard.write({"apply_name": True, "confirm_shared": True})
        wizard.action_apply()
        self.assertEqual(wizard.state, "applied")
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_normal_user_cannot_alter_lookup_source(self):
        wizard = self.preview(self.product.with_user(self.manager()))
        self.assertFalse(wizard.env.su)
        for vals in (
            {"product_id": self.product.id},
            {"company_id": self.env.company.id},
            {"code": "036000291452"},
            {"source_fingerprint": "forged"},
            {"image_url": "https://localhost/"},
            {"state": "draft"},
            {"preview_image": b"forged"},
        ):
            with self.subTest(vals=tuple(vals)), self.assertRaises(AccessError):
                wizard.write(vals)

    def test_normal_user_cannot_forge_review_creation(self):
        model = self.env["si5.lookup"].with_user(self.manager())
        with self.assertRaises(AccessError):
            model.create(
                {
                    "product_id": self.product.id,
                    "company_id": self.env.company.id,
                    "source_fingerprint": "forged",
                }
            )

    def test_read_only_user_denied_before_lookup(self):
        user = new_test_user(
            self.env["res.users"].with_context(no_reset_password=True).env,
            login="si5_read_only",
            groups="base.group_user",
        )
        self.assertFalse(user.has_group("product.group_product_manager"))
        with patch(
            "odoo.addons.product_si5_gtin.models.lookup",
            side_effect=AssertionError("Unauthorized quota use"),
        ):
            with self.assertRaises(AccessError):
                self.product.with_user(user).action_si5_lookup()

    def test_other_creator_cannot_read_review(self):
        owner = self.manager("si5_owner")
        other = self.manager("si5_other")
        wizard = self.preview(self.product.with_user(owner))
        self.assertEqual(wizard.create_uid, owner)
        with self.assertRaises(AccessError):
            wizard.with_user(other).read(["code"])

    def test_other_company_denied_before_lookup(self):
        manager = self.manager()
        company = self.env["res.company"].create({"name": "Outside allowed companies"})
        product = self.env["product.product"].create(
            {
                "name": "Other company fixture",
                "company_id": company.id,
                "barcode": "036000291452",
            }
        )
        with patch(
            "odoo.addons.product_si5_gtin.models.lookup",
            side_effect=AssertionError("Cross-company quota use"),
        ):
            with self.assertRaises(AccessError):
                product.with_user(manager).action_si5_lookup()

    def test_token_never_reaches_review_or_export(self):
        import json

        manager = self.manager()
        manager.write(
            {"groups_id": [Command.link(self.env.ref("base.group_allow_export").id)]}
        )
        marker = "FAKE_SERVER_ONLY_SECRET"
        key = f"SI5_TOKEN_COMPANY_{self.env.company.id}"
        with patch.dict("os.environ", {key: marker}, clear=True):
            wizard = self.preview(self.product.with_user(manager))
        values = wizard.read()
        exported = wizard.export_data(["code", "proposed_name", "fiscal_reference"])
        self.assertNotIn(
            marker, json.dumps([values, exported, wizard._window_action()], default=str)
        )
        self.assertFalse(any("token" in name for name in wizard.fields_get()))

    def test_template_single_variant_entry(self):
        data = {
            "produto": "Fixture",
            "marca": "",
            "imagem_url": "",
            "ncm": "",
            "cest_codigo": "",
        }
        with patch("odoo.addons.product_si5_gtin.models.lookup", return_value=data):
            action = lookup_action(self.product.product_tmpl_id)
        self.assertEqual(
            self.env["si5.lookup"].browse(action["res_id"]).product_id, self.product
        )

    def test_template_multiple_variants_requires_selection(self):
        template, sibling = self.make_variants()
        with patch(
            "odoo.addons.product_si5_gtin.models.lookup",
            side_effect=AssertionError("Ambiguous variant lookup"),
        ):
            with self.assertRaises(UserError):
                template.action_si5_lookup()

    def test_empty_name_cannot_be_applied(self):
        wizard = self.preview()
        wizard.write(
            {"apply_name": True, "confirm_shared": True, "proposed_name": "   "}
        )
        with self.assertRaises(UserError):
            wizard.action_apply()
        self.assertEqual(self.product.name, "Existing")

    def test_validated_preview_does_not_modify_product(self):
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
        wizard = self.preview(self.product.with_user(self.manager()))
        with patch(
            "odoo.addons.product_si5_gtin.models.image", return_value=buffer.getvalue()
        ):
            wizard.action_preview_image()
        self.assertTrue(wizard.preview_image)
        self.assertFalse(self.product.image_1920)
        self.assertEqual(self.product.name, "Existing")

    def test_no_cross_company_token_fallback(self):
        company = self.env["res.company"].create({"name": "Company without token"})
        key = f"SI5_TOKEN_COMPANY_{self.env.company.id}"

        def reject_missing(code, token):
            self.assertIsNone(token)
            raise LookupError("configuration")

        with patch.dict("os.environ", {key: "FAKE_OTHER_COMPANY_TOKEN"}, clear=True):
            with patch(
                "odoo.addons.product_si5_gtin.models.lookup", side_effect=reject_missing
            ):
                with self.assertRaises(UserError):
                    lookup_action(self.product.with_company(company))

    def test_portuguese_error_translation(self):
        self.env["res.lang"]._activate_lang("pt_BR")
        self.env["ir.module.module"]._load_module_terms(
            ["product_si5_gtin"], ["pt_BR"], overwrite=True
        )
        wizard = self.preview(self.product.with_context(lang="pt_BR"))
        wizard.write(
            {"apply_name": True, "confirm_shared": True, "proposed_name": False}
        )
        with self.assertRaises(UserError) as error:
            wizard.action_apply()
        self.assertIn("O nome", str(error.exception))
        self.assertNotIn("The name", str(error.exception))

    def test_image_requires_validated_preview_before_apply(self):
        wizard = self.preview(self.product.with_user(self.manager()))
        wizard.write({"apply_image": True, "confirm_shared": True})
        with patch(
            "odoo.addons.product_si5_gtin.models.image",
            side_effect=AssertionError("Applying must not download an image"),
        ):
            with self.assertRaisesRegex(UserError, "review the image"):
                wizard.action_apply()
        self.assertFalse(self.product.image_1920)
        self.assertFalse(wizard.preview_image)
        self.assertEqual(wizard.state, "draft")

    def test_applied_image_matches_review_without_refetch(self):
        import base64
        import io

        from PIL import Image

        images = []
        for color in ("red", "blue"):
            buffer = io.BytesIO()
            Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
            images.append(buffer.getvalue())
        wizard = self.preview(self.product.with_user(self.manager()))
        wizard.write({"apply_image": True, "confirm_shared": True})
        with patch(
            "odoo.addons.product_si5_gtin.models.image", side_effect=images
        ) as download:
            wizard.action_preview_image()
            reviewed = wizard.with_context(bin_size=False).preview_image
            self.assertEqual(base64.b64decode(reviewed), images[0])
            self.assertFalse(self.product.image_1920)
            wizard.with_context(bin_size=True).action_apply()
        download.assert_called_once()
        self.assertEqual(self.product.image_1920, reviewed)
        self.assertEqual(self.product.product_tmpl_id.image_1920, reviewed)
        self.assertNotEqual(
            base64.b64decode(self.product.image_1920), images[1]
        )
        self.assertEqual(wizard.state, "applied")

    def test_deep_json_returns_friendly_contract_error(self):
        from .. import service

        body = (
            b'{"codbar":"7891000325858","produto":"Fixture","extra":'
            + b"[" * 10000
            + b"0"
            + b"]" * 10000
            + b"}"
        )

        def fake_lookup(code, token):
            return service.lookup(
                code,
                "FAKE",
                lambda *a, **kw: (200, {"content-type": "application/json"}, body),
            )

        with patch(
            "odoo.addons.product_si5_gtin.models.lookup", side_effect=fake_lookup
        ):
            with self.assertRaisesRegex(UserError, "response contract") as error:
                lookup_action(self.product)
        self.assertNotIn("RecursionError", str(error.exception))
        self.assertNotIn("extra", str(error.exception))

    def test_weight_is_suggested_in_grams_and_applied_only_when_selected(self):
        data = {
            "produto": "Proposed",
            "marca": "",
            "imagem_url": "",
            "ncm": "",
            "cest_codigo": "",
            "peso": 415.0,
        }
        with patch("odoo.addons.product_si5_gtin.models.lookup", return_value=data):
            action = lookup_action(self.product)
        wizard = self.env["si5.lookup"].browse(action["res_id"])
        # Stored with the database "Stock Weight" precision (2 decimals by default).
        digits = self.env["decimal.precision"].precision_get("Stock Weight")
        expected = float_round(0.415, precision_digits=digits)
        self.assertAlmostEqual(wizard.proposed_weight, expected, places=digits)
        wizard.action_apply()
        self.assertFalse(self.product.weight)
        # Weight belongs to the variant: no shared-template confirmation required.
        wizard.apply_weight = True
        wizard.action_apply()
        self.assertAlmostEqual(self.product.weight, expected, places=digits)

    def test_company_setting_token_and_environment_precedence(self):
        company = self.env.company
        company.sudo().si5_token = "FAKE_SETTINGS_TOKEN"
        data = {
            "produto": "Fixture",
            "marca": "",
            "imagem_url": "",
            "ncm": "",
            "cest_codigo": "",
        }
        key = f"SI5_TOKEN_COMPANY_{company.id}"
        with patch.dict("os.environ", {}, clear=True):
            with patch(
                "odoo.addons.product_si5_gtin.models.lookup", return_value=data
            ) as fake:
                lookup_action(self.product)
                fake.assert_called_once_with("7891000325858", "FAKE_SETTINGS_TOKEN")
        with patch.dict("os.environ", {key: "FAKE_ENV_TOKEN"}, clear=True):
            with patch(
                "odoo.addons.product_si5_gtin.models.lookup", return_value=data
            ) as fake:
                lookup_action(self.product)
                fake.assert_called_once_with("7891000325858", "FAKE_ENV_TOKEN")

    def test_token_setting_hidden_from_non_admin(self):
        manager = self.manager()
        fields_info = self.env["res.company"].with_user(manager).fields_get()
        self.assertNotIn("si5_token", fields_info)

    def _webp(self, frames=1, mode="RGB"):
        import io

        from PIL import Image, WebPImagePlugin  # noqa: F401

        buffer = io.BytesIO()
        colors = [(255, 0, 0, 128), (0, 0, 255, 128)] if mode == "RGBA" else ["red", "blue"]
        pictures = [Image.new(mode, (8, 8), c) for c in colors[:frames]]
        if frames > 1:
            pictures[0].save(
                buffer,
                format="WEBP",
                save_all=True,
                append_images=pictures[1:],
                duration=100,
            )
        else:
            pictures[0].save(buffer, format="WEBP")
        return buffer.getvalue()

    def test_webp_is_converted_for_odoo(self):
        import base64

        wizard = self.preview()
        wizard.sudo().image_url = "https://cdn3.si5.com.br/img/78/91/7891000325858.webp"
        with patch(
            "odoo.addons.product_si5_gtin.models.image", return_value=self._webp()
        ):
            wizard.action_preview_image()
        raw = base64.b64decode(wizard.with_context(bin_size=False).preview_image)
        self.assertTrue(raw.startswith(b"\xff\xd8\xff"), "static WebP becomes JPEG")
        with patch(
            "odoo.addons.product_si5_gtin.models.image",
            return_value=self._webp(mode="RGBA"),
        ):
            wizard.action_preview_image()
        raw = base64.b64decode(wizard.with_context(bin_size=False).preview_image)
        self.assertTrue(raw.startswith(b"\x89PNG"), "transparent WebP becomes PNG")

    def test_animated_webp_rejected(self):
        wizard = self.preview()
        with patch(
            "odoo.addons.product_si5_gtin.models.image", return_value=self._webp(2)
        ):
            with self.assertRaises(UserError):
                wizard.action_preview_image()
        self.assertFalse(wizard.preview_image)
