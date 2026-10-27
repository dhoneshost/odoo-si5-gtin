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
    apply_ncm = fields.Boolean(string="Replace NCM", default=False)
    apply_cest = fields.Boolean(string="Replace CEST", default=False)

    @api.depends("ncm_code", "cest_code", "apply_ncm", "current_ncm_id")
    def _compute_proposed_fiscal(self):
        Ncm = self.env["l10n_br_fiscal.ncm"]
        Cest = self.env["l10n_br_fiscal.cest"]
        for review in self:
            code = (review.ncm_code or "").strip()
            # Exact 8-digit match only; never guess a "closest" classification.
            ncm = Ncm
            if len(code) == 8 and code.isdigit():
                # The table also holds "Ex" variants of a code; prefer the plain one.
                candidates = Ncm.search([("code_unmasked", "=", code)])
                ncm = candidates.filtered(lambda n: not n.exception)[:1] or candidates[:1]
            review.proposed_ncm_id = ncm
            cest_code = (review.cest_code or "").strip()
            cest = (
                Cest.search([("code_unmasked", "=", cest_code)], limit=1)
                if len(cest_code) == 7 and cest_code.isdigit()
                else Cest
            )
            # The fiscal engine restricts CEST to the product NCM; keep that rule.
            # A few CEST rows have no NCM link in the tables (codes like "4029"
            # that lost the leading zero): nothing to check against, keep the
            # suggestion for the user to review.
            target_ncm = ncm if review.apply_ncm else review.current_ncm_id
            if cest and target_ncm and cest.ncm_ids and target_ncm not in cest.ncm_ids:
                cest = Cest
            review.proposed_cest_id = cest

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
