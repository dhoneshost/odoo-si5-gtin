# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64
import hashlib
import io
import json
import os
import warnings

from PIL import Image

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import clean_context, plaintext2html
from odoo.tools.image import get_webp_size

from .service import LookupError, image, lookup


def _fingerprint(product):
    product = product.with_context(bin_size=False)
    # image_1920 is the variant picture or, when it has none, the template one.
    picture = product.image_1920 or b""
    if isinstance(picture, bytes):
        picture = picture.decode("ascii")
    values = [
        product.name or "",
        product.description or "",
        picture,
        product.company_id.id,
        product.weight or 0.0,
    ]
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class ResCompany(models.Model):
    _inherit = "res.company"

    # Only administrators can read or write it; settings mask the displayed value.
    si5_token = fields.Char(
        string="SI5 Global API token",
        groups="base.group_system",
        copy=False,
        prefetch=False,
    )

    def _si5_token(self):
        """Server environment wins (SI5_TOKEN_COMPANY_<id>); then the company setting.

        No fallback between companies.
        """
        self.ensure_one()
        token = os.environ.get(f"SI5_TOKEN_COMPANY_{self.id}")
        if token:
            return token
        return self.sudo().si5_token or None


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    si5_token = fields.Char(
        related="company_id.si5_token",
        readonly=False,
        groups="base.group_system",
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_si5_lookup(self):
        self.ensure_one()
        self.check_access("write")
        if len(self.product_variant_ids) != 1:
            raise UserError(
                self.env._("Open the specific variant to look up its GTIN.")
            )
        return self.product_variant_ids.action_si5_lookup()


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _si5_check_lookup_access(self):
        self.ensure_one()
        self.check_access("write")
        self.env["si5.lookup"].check_access("create")
        if self.company_id and self.company_id != self.env.company:
            raise AccessError(self.env._("Select the product company first."))

    def action_si5_lookup(self):
        """Open the consent dialog. Nothing is sent to SI5 Global here."""
        self._si5_check_lookup_access()
        # Server-side factory: explicit values only, no default_* from the caller's
        # context (default_consent=True must not open the box already ticked).
        consent = (
            self.env["si5.lookup.consent"]
            .sudo()
            .with_context(clean_context(self.env.context))
            .create(
                {
                    "product_id": self.id,
                    "company_id": self.env.company.id,
                    "code": self.barcode,
                    "consent": False,
                }
            )
        )
        return consent.with_env(self.env)._window_action()

    def _si5_lookup_preview(self):
        """Query SI5 Global and open the review. Only called after explicit consent."""
        self._si5_check_lookup_access()
        try:
            data = lookup(self.barcode, self.env.company._si5_token())
        except LookupError as error:
            raise UserError(
                self.env["si5.lookup"]._service_message(error.code)
            ) from None
        # Only the private factory can populate server-owned target/source fields.
        wizard = self.env["si5.lookup"]._create_preview(self, data)
        return wizard._window_action()


class Si5LookupConsent(models.TransientModel):
    _name = "si5.lookup.consent"
    _description = "SI5 lookup consent"
    _check_company_auto = True

    product_id = fields.Many2one(
        "product.product",
        required=True,
        readonly=True,
        check_company=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(string="Barcode to send", readonly=True)
    consent = fields.Boolean(
        string="I agree to send this barcode to SI5 Global",
        default=False,
    )
    # One consent, one request: "used" is claimed atomically before the request.
    state = fields.Selection(
        [("pending", "Pending"), ("used", "Used")],
        default="pending",
        required=True,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(
                self.env._("Use the product lookup button to start a lookup.")
            )
        # Always born unticked and unused, whatever the caller passes.
        for vals in vals_list:
            vals.update(consent=False, state="pending")
        return super().create(vals_list)

    def write(self, vals):
        # Only the consent box is the user's to change.
        if set(vals) - {"consent"}:
            raise AccessError(self.env._("The product and barcode cannot be changed."))
        return super().write(vals)

    def _claim(self):
        """Mark this consent as used, once.

        The conditional UPDATE locks the row: a concurrent call waits for this
        transaction and then gets a serialization failure (Odoo retries the
        request, which then finds the consent used). If the lookup raises, the
        transaction is rolled back and the consent is pending again, so the user
        can click Look up again in the same dialog.
        """
        self.env.cr.execute(
            "UPDATE si5_lookup_consent SET state = 'used', write_date = now() at time zone 'UTC'"
            " WHERE id = %s AND state = 'pending' RETURNING id",
            (self.id,),
        )
        claimed = bool(self.env.cr.fetchone())
        self.invalidate_recordset(["state"])
        return claimed

    def _window_action(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Look up GTIN with SI5 Global"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_lookup(self):
        self.ensure_one()
        if self.create_uid != self.env.user or self.company_id != self.env.company:
            raise AccessError(
                self.env._("This request belongs to another user or company.")
            )
        if not self.consent:
            raise UserError(
                self.env._(
                    "Tick the consent box to send the barcode to SI5 Global, "
                    "or cancel to send nothing."
                )
            )
        if self.product_id.barcode != self.code:
            raise UserError(self.env._("The barcode changed. Start the lookup again."))
        if not self._claim():
            raise UserError(
                self.env._(
                    "This consent was already used for a lookup. "
                    "Click Look up GTIN with SI5 again to start a new one."
                )
            )
        return self.product_id._si5_lookup_preview()


class Si5Lookup(models.TransientModel):
    _name = "si5.lookup"
    _description = "SI5 product review"
    _check_company_auto = True

    # Server-owned fields: only the lookup factory (sudo) may set them.
    _si5_protected_fields = {
        "product_id",
        "company_id",
        "code",
        "source_fingerprint",
        "state",
        "image_url",
        "fiscal_reference",
        "preview_image",
        "ncm_code",
        "cest_code",
        "create_uid",
    }

    product_id = fields.Many2one(
        "product.product",
        required=True,
        readonly=True,
        check_company=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(string="GTIN", readonly=True)
    source_fingerprint = fields.Char(required=True, readonly=True)
    state = fields.Selection(
        [("draft", "To review"), ("applied", "Applied")],
        default="draft",
        readonly=True,
        required=True,
    )
    current_name = fields.Char(
        related="product_id.name", readonly=True, string="Current name"
    )
    current_description = fields.Html(
        related="product_id.description", readonly=True, string="Current description"
    )
    current_weight = fields.Float(
        related="product_id.weight", readonly=True, string="Current weight"
    )
    weight_uom_name = fields.Char(related="product_id.weight_uom_name")
    current_image = fields.Binary(
        related="product_id.image_128", readonly=True, string="Current picture"
    )
    proposed_name = fields.Char(string="Suggested name")
    proposed_description = fields.Text(string="Suggested description")
    proposed_weight = fields.Float(
        string="Suggested weight", digits="Stock Weight", readonly=True
    )
    image_url = fields.Char(string="Image source", readonly=True)
    ncm_code = fields.Char(string="NCM", readonly=True)
    cest_code = fields.Char(string="CEST", readonly=True)
    fiscal_reference = fields.Char(string="Fiscal reference", readonly=True)
    apply_name = fields.Boolean(string="Replace name", default=False)
    apply_description = fields.Boolean(string="Replace description", default=False)
    apply_weight = fields.Boolean(string="Replace weight", default=False)
    apply_image = fields.Boolean(string="Replace image", default=False)
    preview_image = fields.Binary(
        string="Validated image preview", readonly=True, attachment=False
    )
    confirm_shared = fields.Boolean(
        string="Confirm impact on the shared template and companies"
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(
                self.env._("Use the product lookup button to create a review.")
            )
        return super().create(vals_list)

    def write(self, vals):
        if self._si5_protected_fields.intersection(vals) and not self.env.su:
            raise AccessError(
                self.env._("The lookup target and source cannot be changed.")
            )
        return super().write(vals)

    @api.model
    def _weight_from_grams(self, grams):
        """Convert the API gross weight (grams) to the database weight unit."""
        if not grams:
            return 0.0
        target = self.env["product.template"]._get_weight_uom_id_from_ir_config_parameter()
        kilogram = self.env.ref("uom.product_uom_kgm")
        return kilogram._compute_quantity(grams / 1000.0, target, round=False)

    @api.model
    def _source_fingerprint(self, product):
        """Snapshot reviewed fields; bridges extend with their own targets."""
        return _fingerprint(product)

    @api.model
    def _preview_values(self, product, data):
        """Values for a new review; extend to stage more suggestions."""
        reference = self.env._(
            "NCM: %(ncm)s | CEST: %(cest)s. Reference only; ask your accountant.",
            ncm=" - ".join(filter(None, (data["ncm"], data.get("ncm_descricao"))))
            or "-",
            cest=data["cest_codigo"] or "-",
        )
        return {
            "product_id": product.id,
            "company_id": self.env.company.id,
            "code": product.barcode,
            "source_fingerprint": self._source_fingerprint(product),
            "proposed_name": data["produto"],
            # Odoo 18 shows "description" as internal notes: keep useful facts,
            # not a copy of the name.
            "proposed_description": "\n".join(
                filter(
                    None,
                    (
                        data["marca"]
                        and self.env._("Brand: %(brand)s", brand=data["marca"]),
                        data.get("categoria")
                        and self.env._(
                            "Category: %(category)s", category=data["categoria"]
                        ),
                        self.env._(
                            "Source: SI5 Global, GTIN %(code)s", code=product.barcode
                        ),
                    ),
                )
            ),
            "proposed_weight": self._weight_from_grams(data.get("peso")),
            "image_url": data["imagem_url"],
            "ncm_code": data["ncm"],
            "cest_code": data["cest_codigo"],
            "fiscal_reference": reference,
        }

    @api.model
    def _create_preview(self, product, data):
        # Minimal elevation: transient creation only; product permissions and active
        # company were checked before lookup. sudo preserves the requesting uid.
        record = self.sudo().create(self._preview_values(product, data))
        return record.with_env(self.env)

    def _window_action(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Review SI5 suggestions"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _check_target(self):
        self.ensure_one()
        self.check_access("write")
        if self.create_uid != self.env.user or self.company_id != self.env.company:
            raise AccessError(
                self.env._("This review belongs to another user or company.")
            )
        if self.state != "draft":
            raise UserError(self.env._("This review has already been applied."))
        product = self.product_id
        product.check_access("write")
        if product.company_id and product.company_id != self.env.company:
            raise AccessError(self.env._("Select the product company first."))
        if product.barcode != self.code:
            raise UserError(self.env._("The GTIN changed. Run the lookup again."))
        if self._source_fingerprint(product) != self.source_fingerprint:
            raise UserError(
                self.env._(
                    "The product changed after this lookup. Review it again before replacing data."
                )
            )
        return product

    @api.model
    def _si5_webp_to_raster(self, raw):
        """Return PNG/JPEG bytes for a static WebP, or raise ValueError.

        Odoo 18 only preloads the core Pillow plugins and stores WebP untouched,
        so thumbnails and PDF reports would get the full WebP. Check the size from
        the header first (like Odoo), then decode with the WebP plugin explicitly.
        """
        try:
            size = get_webp_size(raw)
        except UserError:
            raise ValueError() from None
        if not size or size[0] * size[1] > 16000000:
            raise ValueError()
        # VP8X extended header: bit 1 of the flags byte marks an animation.
        if raw[12:16] == b"VP8X" and len(raw) > 20 and raw[20] & 0x02:
            raise ValueError()
        from PIL import WebPImagePlugin  # noqa: F401  (registers the decoder)

        with Image.open(io.BytesIO(raw), formats=["WEBP"]) as picture:
            picture.load()
            output = io.BytesIO()
            if picture.mode in ("RGBA", "LA") or "transparency" in picture.info:
                picture.save(output, "PNG", optimize=True)
            else:
                picture.convert("RGB").save(output, "JPEG", quality=90)
        return output.getvalue()

    def _validated_image(self):
        try:
            raw = image(self.image_url)
            if raw[:4] == b"RIFF":
                raw = self._si5_webp_to_raster(raw)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as picture:
                    if (
                        picture.width * picture.height > 16000000
                        or getattr(picture, "n_frames", 1) != 1
                    ):
                        raise ValueError()
                    picture.verify()
            return base64.b64encode(raw)
        except LookupError as error:
            raise UserError(self._service_message(error.code)) from None
        except (
            ValueError,
            OSError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ):
            raise UserError(
                self.env._("The image content, dimensions or format is not allowed.")
            ) from None

    def action_preview_image(self):
        self._check_target()
        # Only validated bytes may enter this server-owned field.
        self.sudo().write({"preview_image": self._validated_image()})
        return self._window_action()

    def _si5_selected(self):
        """True when at least one replacement is selected; extend with new options."""
        return (
            self.apply_name
            or self.apply_description
            or self.apply_weight
            or self.apply_image
        )

    def _si5_needs_shared_confirmation(self, product):
        """Selections that change data shared by variants or companies."""
        return (
            self.apply_name
            or self.apply_description
            or (self.apply_image and not product.company_id)
        )

    def _si5_variant_values(self, product):
        values = {}
        if self.apply_weight:
            if self.proposed_weight <= 0:
                raise UserError(self.env._("No weight was suggested for this product."))
            values["weight"] = self.proposed_weight
        if self.apply_image:
            # Server-owned bytes validated and shown by action_preview_image.
            # Never download a potentially different image during application.
            reviewed_image = self.with_context(bin_size=False).preview_image
            if not reviewed_image:
                raise UserError(
                    self.env._("Download and review the image before applying it.")
                )
            # A single-variant product shows the template picture: image_1920 lets
            # Odoo store it there. With several variants keep it on this variant
            # so siblings and the template are untouched.
            single = len(product.product_tmpl_id.product_variant_ids) == 1
            values["image_1920" if single else "image_variant_1920"] = reviewed_image
        return values

    def _si5_template_values(self, product):
        values = {}
        if self.apply_name:
            if not (self.proposed_name or "").strip():
                raise UserError(self.env._("The name cannot be empty."))
            values["name"] = self.proposed_name
        if self.apply_description:
            values["description"] = plaintext2html(self.proposed_description or "")
        return values

    def action_apply(self):
        product = self._check_target()
        if not self._si5_selected():
            return {"type": "ir.actions.act_window_close"}
        if self._si5_needs_shared_confirmation(product) and not self.confirm_shared:
            raise UserError(
                self.env._(
                    "Confirm the impact on other variants and companies before applying."
                )
            )
        template_values = self._si5_template_values(product)
        variant_values = self._si5_variant_values(product)
        if template_values:
            product.product_tmpl_id.check_access("write")
        # Recheck the target before writing; ORM still enforces access checks.
        product.invalidate_recordset()
        self._check_target()
        if template_values:
            product.product_tmpl_id.write(template_values)
        if variant_values:
            product.write(variant_values)
        self.sudo().write({"state": "applied"})
        return {"type": "ir.actions.act_window_close"}

    @api.model
    def _service_message(self, code):
        messages = {
            "gtin_format": self.env._(
                "Enter 8, 12, 13 or 14 ASCII digits, preserving leading zeros."
            ),
            "restricted_code": self.env._(
                "This is a restricted circulation code, not a universal GTIN lookup."
            ),
            "gtin_checksum": self.env._("The GTIN check digit is invalid."),
            "destination": self.env._("The network destination is not allowed."),
            "response_size": self.env._("The response exceeds the allowed size."),
            "network": self.env._(
                "The network request failed or timed out. Try again later."
            ),
            "challenge": self.env._(
                "A web protection challenge blocked the request. This does not prove the token is invalid."
            ),
            "authentication": self.env._("The SI5 token is invalid or expired."),
            "forbidden": self.env._("The provider denied access."),
            "not_found": self.env._(
                "Product not found. Catalogue coverage is not guaranteed."
            ),
            "quota": self.env._(
                "The SI5 request limit was reached. Wait before trying again."
            ),
            "unavailable": self.env._(
                "The service is unavailable or returned an unexpected status. Try again later."
            ),
            "configuration": self.env._(
                "Ask an administrator to set the SI5 Global token for this company "
                "in Settings."
            ),
            "json_type": self.env._(
                "The response is not JSON; a web protection page may have been returned."
            ),
            "contract": self.env._(
                "The response contract or returned GTIN is invalid."
            ),
            "image_url": self.env._(
                "Only SI5 HTTPS images without redirects are allowed."
            ),
            "image_content": self.env._("The image format or size is not allowed."),
        }
        return messages.get(code, self.env._("The SI5 lookup could not be completed."))
