# Copyright 2026 SI5
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import UserError


class Si5Lookup(models.TransientModel):
    _inherit = "si5.lookup"

    current_ncm_id = fields.Many2one(
        related="product_id.product_tmpl_id.ncm_id", string="Current NCM"
    )
    current_cest_id = fields.Many2one(
        related="product_id.product_tmpl_id.cest_id", string="Current CEST"
    )
    proposed_ncm_id = fields.Many2one(
        "l10n_br_fiscal.ncm",
        string="Suggested NCM",
        compute="_compute_proposed_fiscal",
    )
    proposed_cest_id = fields.Many2one(
        "l10n_br_fiscal.cest",
        string="Suggested CEST",
        compute="_compute_proposed_fiscal",
    )
    cest_ncm_link = fields.Selection(
        [
            ("verified", "Linked to the NCM in the fiscal tables"),
            ("not_linked", "The fiscal tables do not link this CEST to any NCM"),
            ("no_ncm", "No NCM to check this CEST against"),
        ],
        string="CEST × NCM check",
        compute="_compute_proposed_fiscal",
    )
    apply_ncm = fields.Boolean(string="Replace NCM", default=False)
    apply_cest = fields.Boolean(string="Replace CEST", default=False)

    @api.model
    def _source_fingerprint(self, product):
        template = product.product_tmpl_id
        # Re-read the fiscal targets on the final pre-write check as well.
        template.invalidate_recordset(["ncm_id", "cest_id"])
        base = super()._source_fingerprint(product)
        return f"{base}:{template.ncm_id.id or 0}:{template.cest_id.id or 0}"

    @api.depends("ncm_code", "cest_code", "apply_ncm", "current_ncm_id")
    def _compute_proposed_fiscal(self):
        Ncm = self.env["l10n_br_fiscal.ncm"]
        Cest = self.env["l10n_br_fiscal.cest"]
        for review in self:
            code = (review.ncm_code or "").strip()
            # Exact 8-digit match only; never guess a "closest" classification.
            ncm = Ncm
            if len(code) == 8 and code.isdigit():
                # The API supplies no Ex identifier: never guess an exception.
                candidates = Ncm.search([("code_unmasked", "=", code)])
                ncm = candidates.filtered(lambda n: not n.exception)[:1]
            review.proposed_ncm_id = ncm
            cest_code = (review.cest_code or "").strip()
            cest = (
                Cest.search([("code_unmasked", "=", cest_code)], limit=1)
                if len(cest_code) == 7 and cest_code.isdigit()
                else Cest
            )
            # The fiscal engine restricts CEST to the product NCM; keep that rule.
            # Some CEST rows have no NCM link in the tables (codes like "4029" that
            # lost the leading zero), and a product may have no NCM yet: then the
            # pair cannot be checked, so the suggestion stays but is flagged as
            # unverified instead of being presented as compatible.
            target_ncm = ncm if review.apply_ncm else review.current_ncm_id
            link = False
            if cest:
                if not cest.ncm_ids:
                    link = "not_linked"
                elif not target_ncm:
                    link = "no_ncm"
                elif target_ncm in cest.ncm_ids:
                    link = "verified"
                else:
                    cest = Cest
            review.proposed_cest_id = cest
            review.cest_ncm_link = link

    def _si5_selected(self):
        return super()._si5_selected() or self.apply_ncm or self.apply_cest

    def _si5_needs_shared_confirmation(self, product):
        # NCM/CEST live on product.template: every variant is affected.
        return (
            super()._si5_needs_shared_confirmation(product)
            or self.apply_ncm
            or self.apply_cest
        )

    def _si5_template_values(self, product):
        values = super()._si5_template_values(product)
        if self.apply_ncm:
            if not self.proposed_ncm_id:
                raise UserError(
                    self.env._("This NCM was not found in the fiscal tables.")
                )
            retained_cest = product.product_tmpl_id.cest_id
            if (
                not self.apply_cest
                and retained_cest.ncm_ids
                and self.proposed_ncm_id not in retained_cest.ncm_ids
            ):
                raise UserError(
                    self.env._(
                        "The existing CEST does not match the selected NCM. "
                        "Review both fiscal codes before applying; no data was changed."
                    )
                )
            values["ncm_id"] = self.proposed_ncm_id.id
        if self.apply_cest:
            if not self.proposed_cest_id:
                raise UserError(
                    self.env._(
                        "This CEST was not found or does not match the product NCM."
                    )
                )
            values["cest_id"] = self.proposed_cest_id.id
        return values
