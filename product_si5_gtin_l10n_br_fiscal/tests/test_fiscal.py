# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFiscalBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ncm = cls.env["l10n_br_fiscal.ncm"].create(
            {"code": "9999.99.01", "name": "SI5 fixture NCM"}
        )
        cls.other_ncm = cls.env["l10n_br_fiscal.ncm"].create(
            {"code": "9999.99.02", "name": "SI5 fixture other NCM"}
        )
        segment = cls.env["l10n_br_fiscal.cest"]._fields["segment"].selection[0][0]
        cls.cest = cls.env["l10n_br_fiscal.cest"].create(
            {
                "segment": segment,
                "code": "99.999.01",
                "item": "999",
                "name": "SI5 fixture CEST",
                "ncms": "99999901",
            }
        )
        cls.cest.ncm_ids = cls.ncm
        cls.product = cls.env["product.product"].create(
            {"name": "Existing", "barcode": "7891000325858"}
        )

    def setUp(self):
        super().setUp()
        guard = patch(
            "odoo.addons.product_si5_gtin.service.PinnedHTTPS",
            side_effect=AssertionError("Offline test attempted real transport"),
        )
        guard.start()
        self.addCleanup(guard.stop)

    def preview(self, ncm="99999901", cest="9999901"):
        data = {
            "produto": "Proposed",
            "marca": "",
            "imagem_url": "",
            "ncm": ncm,
            "cest_codigo": cest,
            "ncm_descricao": "",
            "categoria": "",
            "peso": None,
        }
        with patch("odoo.addons.product_si5_gtin.models.lookup", return_value=data):
            consent = self.env["si5.lookup.consent"].browse(
                self.product.action_si5_lookup()["res_id"]
            )
            consent.consent = True
            action = consent.action_lookup()
        return self.env["si5.lookup"].browse(action["res_id"])

    def test_nothing_applied_by_default(self):
        before = self.product.ncm_id
        wizard = self.preview()
        self.assertEqual(wizard.proposed_ncm_id, self.ncm)
        wizard.action_apply()
        self.assertEqual(self.product.ncm_id, before)

    def test_apply_ncm_and_cest_requires_confirmation(self):
        wizard = self.preview()
        wizard.write({"apply_ncm": True, "apply_cest": True})
        self.assertEqual(wizard.proposed_cest_id, self.cest)
        self.assertEqual(wizard.cest_ncm_link, "verified")
        with self.assertRaises(UserError):
            wizard.action_apply()
        wizard.confirm_shared = True
        wizard.action_apply()
        self.assertEqual(self.product.ncm_id, self.ncm)
        self.assertEqual(self.product.cest_id, self.cest)

    def test_unknown_ncm_is_not_guessed(self):
        wizard = self.preview(ncm="99999999", cest="")
        self.assertFalse(wizard.proposed_ncm_id)
        wizard.write({"apply_ncm": True, "confirm_shared": True})
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_cest_must_match_target_ncm(self):
        self.product.product_tmpl_id.ncm_id = self.other_ncm
        wizard = self.preview()
        # Keeping the current (other) NCM: the CEST does not belong to it.
        self.assertFalse(wizard.proposed_cest_id)
        wizard.apply_ncm = True
        self.assertEqual(wizard.proposed_cest_id, self.cest)

    def test_cest_without_ncm_link_is_offered(self):
        unlinked = self.cest.copy({"code": "99.999.02", "ncms": False})
        unlinked.ncm_ids = False
        wizard = self.preview(cest="9999902")
        wizard.apply_ncm = True
        self.assertEqual(wizard.proposed_cest_id, unlinked)
        # Offered for review, but never presented as compatible with the NCM.
        self.assertEqual(wizard.cest_ncm_link, "not_linked")

    def test_cest_unverified_without_product_ncm(self):
        self.product.product_tmpl_id.ncm_id = False
        wizard = self.preview()
        # Not applying the NCM and the product has none: nothing to check against.
        self.assertEqual(wizard.proposed_cest_id, self.cest)
        self.assertEqual(wizard.cest_ncm_link, "no_ncm")
        wizard.apply_ncm = True
        self.assertEqual(wizard.cest_ncm_link, "verified")

    def test_other_fiscal_settings_untouched(self):
        template = self.product.product_tmpl_id
        fields_kept = [
            "fiscal_type",
            "icms_origin",
            "tax_icms_or_issqn",
            "ipi_guideline_class_id",
            "service_type_id",
        ]
        before = {name: template[name] for name in fields_kept}
        wizard = self.preview()
        wizard.write({"apply_ncm": True, "apply_cest": True, "confirm_shared": True})
        wizard.action_apply()
        self.assertEqual(template.ncm_id, self.ncm)
        for name in fields_kept:
            self.assertEqual(template[name], before[name], name)

    def test_plain_ncm_preferred_over_ex_variant(self):
        self.env["l10n_br_fiscal.ncm"].create(
            {"code": "9999.99.01", "exception": "01", "name": "SI5 fixture Ex"}
        )
        wizard = self.preview()
        self.assertEqual(wizard.proposed_ncm_id, self.ncm)

    def test_ex_only_ncm_is_not_guessed(self):
        for exception in ("01", "02"):
            self.env["l10n_br_fiscal.ncm"].create(
                {
                    "code": "9999.99.03",
                    "exception": exception,
                    "name": "SI5 ambiguous Ex fixture",
                }
            )
        wizard = self.preview(ncm="99999903", cest="")
        self.assertFalse(wizard.proposed_ncm_id)
        before = self.product.ncm_id
        wizard.write({"apply_ncm": True, "confirm_shared": True})
        with self.assertRaises(UserError):
            wizard.action_apply()
        self.assertEqual(self.product.ncm_id, before)

    def test_changed_ncm_requires_new_review(self):
        wizard = self.preview()
        wizard.write({"apply_ncm": True, "confirm_shared": True})
        self.product.product_tmpl_id.ncm_id = self.other_ncm
        with self.assertRaisesRegex(UserError, "product changed"):
            wizard.action_apply()
        self.assertEqual(self.product.ncm_id, self.other_ncm)
        self.assertEqual(wizard.state, "draft")

    def test_changed_cest_requires_new_review(self):
        wizard = self.preview()
        wizard.write({"apply_ncm": True, "apply_cest": True, "confirm_shared": True})
        self.product.product_tmpl_id.cest_id = self.cest
        with self.assertRaisesRegex(UserError, "product changed"):
            wizard.action_apply()
        self.assertEqual(self.product.cest_id, self.cest)
        self.assertEqual(wizard.state, "draft")

    def test_ncm_only_rejects_incompatible_retained_cest(self):
        self.product.product_tmpl_id.write(
            {"ncm_id": self.ncm.id, "cest_id": self.cest.id}
        )
        wizard = self.preview(ncm="99999902", cest="")
        wizard.write({"apply_ncm": True, "confirm_shared": True})
        with self.assertRaisesRegex(UserError, "existing CEST"):
            wizard.action_apply()
        self.assertEqual(self.product.ncm_id, self.ncm)
        self.assertEqual(self.product.cest_id, self.cest)
        self.assertEqual(wizard.state, "draft")

    def test_ncm_only_preserves_compatible_retained_cest(self):
        self.product.product_tmpl_id.write(
            {"ncm_id": self.ncm.id, "cest_id": self.cest.id}
        )
        wizard = self.preview(cest="")
        wizard.write({"apply_ncm": True, "confirm_shared": True})
        wizard.action_apply()
        self.assertEqual(self.product.ncm_id, self.ncm)
        self.assertEqual(self.product.cest_id, self.cest)

    def test_ncm_only_without_retained_cest(self):
        self.product.product_tmpl_id.cest_id = False
        wizard = self.preview(cest="")
        wizard.write({"apply_ncm": True, "confirm_shared": True})
        wizard.action_apply()
        self.assertEqual(self.product.ncm_id, self.ncm)
        self.assertFalse(self.product.cest_id)

    def test_ncm_only_does_not_clear_unlinked_retained_cest(self):
        self.cest.ncm_ids = False
        self.product.product_tmpl_id.cest_id = self.cest
        wizard = self.preview(cest="")
        wizard.write({"apply_ncm": True, "confirm_shared": True})
        wizard.action_apply()
        self.assertEqual(self.product.ncm_id, self.ncm)
        self.assertEqual(self.product.cest_id, self.cest)

    def test_legacy_review_without_fiscal_snapshot_is_rejected(self):
        wizard = self.preview()
        # Simulate a pre-upgrade review: it contains only the base hash.
        wizard.sudo().write(
            {"source_fingerprint": wizard.source_fingerprint.split(":", 1)[0]}
        )
        before = (self.product.ncm_id, self.product.cest_id)
        wizard.write({"apply_ncm": True, "apply_cest": True, "confirm_shared": True})
        with self.assertRaisesRegex(UserError, "product changed"):
            wizard.action_apply()
        self.assertEqual((self.product.ncm_id, self.product.cest_id), before)
