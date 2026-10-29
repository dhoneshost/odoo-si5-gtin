# Historical release QA and promotion gates

This records the pre-release assessment at `591ef38`. The current acceptance
decision and additional fiscal contract validation are in
[release-18.0.md](release-18.0.md). Previous unmet production-observation gates
are historical, not claims of subsequently completed production testing.

## Scope and maturity

The current release remains **Beta** (`product_si5_gtin`) / **Alpha**
(`product_si5_gtin_l10n_br_fiscal`). Passing automated checks is not a Stable
release, production validation, an Odoo Apps approval, or an accountant's review.
Versions have not been lowered or changed merely to alter the maturity label.

Evidence below was collected on **2026-10-29**, using the release working tree
based on `988dd6176d2fa6fb5ff71cbe428c985ac3cebfe7`. The release changes under test
were documentation, the token-storage comment, and the QA helper; fiscal and
lookup behavior were not changed by this release preparation.

## Upgrade evidence — both addons

Actual Odoo `-u product_si5_gtin,product_si5_gtin_l10n_br_fiscal` was executed,
not inferred from installation tests.

| Source revision | Source base / bridge versions | Destination versions | Result |
| --- | --- | --- | --- |
| `4fa4a31` | `18.0.2.1.0` / `18.0.1.1.0` | `18.0.2.2.1` / `18.0.1.2.0` | PASS |
| `bd5b3aa` | `18.0.2.2.0` / `18.0.1.2.0` | Same destination | PASS |
| `988dd61` | `18.0.2.2.1` / `18.0.1.2.0` | Same-version explicit update | PASS |

The first source was installed fresh from its archived revision. The other two
sources used disposable database copies of the previously tested installations;
fixtures were then created with each source revision's code before updating.

For **each** source, the before/after helper verified:

- Product name, barcode, weight, internal description and image-byte hash retained.
- The deliberately fake company token retained; no real SI5 token used.
- NCM, CEST, fiscal type, ICMS origin and ICMS/ISSQN tax setting retained.
- Existing draft review retained with its product and suggested name.
- Another user's access to the review rejected.
- Lookup of a product belonging to another active company rejected.
- Direct non-superuser consent creation rejected.
- New consent starts unchecked despite `default_consent=True`; unticked calls
  make no lookup; a successful consent cannot be reused.

These are fixture-based compatibility checks, not coverage of every possible
customer database or third-party customization.

## Automated checks

Final release-working-tree rerun:

| Check | Result |
| --- | --- |
| Pure client | 25 tests passed |
| Odoo base | 41 tests, zero failures/errors |
| Odoo base plus fiscal bridge | 49 tests, zero failures/errors |
| Ruff | All checks passed |

The base-only suite skips its optional fiscal check; the fiscal run exercises
it. Test counts from the two ORM runs overlap and must not be added as unique
coverage.

The separate real-transaction concurrency test on `988dd61` also passed:
**one mocked API call, one review, one caller refused after serialization retry**.
That is distinct from the single-cursor ORM tests. No lookup behavior changed
between that concurrency run and this release-working-tree validation.

An additional direct public-method check supplied
`default_apply_name`, `default_confirm_shared`, `default_apply_image` and
`default_preview_image` to `consent.action_lookup()`: all selection flags remained
false and the injected image was absent. This specific suspected issue was **not
reproduced**; it is not reported as a confirmed vulnerability.

## Reproduction and evidence location

`tests/release_upgrade.py` is an Odoo-shell helper, not an automatic unit test.
**Use only a disposable database.** It commits the before-upgrade fixtures.

```sh
# Use the source revision's addons path for this step.
SI5_QA_PHASE=before SI5_QA_STATE=/tmp/si5-upgrade-state.json \
  odoo-bin shell -d disposable_upgrade < tests/release_upgrade.py

# Switch to the destination revision's addons path and update both addons.
odoo-bin -d disposable_upgrade \
  -u product_si5_gtin,product_si5_gtin_l10n_br_fiscal --stop-after-init

SI5_QA_PHASE=after SI5_QA_STATE=/tmp/si5-upgrade-state.json \
  odoo-bin shell -d disposable_upgrade < tests/release_upgrade.py
```

In the isolated QA executor, logs and fixture snapshots are retained under
`/workspace/shared/si5-odoo-runtime/qa-release/`:

- `before-<revision>.log`, `upgrade-<revision>.log`, `after-<revision>.log`
- `state-<revision>.json` (IDs and non-secret preservation snapshots)
- `client-final.log`, `base-final.log`, `fiscal-final.log`, `lint-final.log`
- `defaults-check.log`

Earlier concurrency evidence is in `qa-988dd61/concurrency.log` under the same
runtime directory. These are executor-local evidence paths, not public links.
The runtime uses Odoo 18, PostgreSQL 17.11, Python 3.12 and OCA fiscal
`18.0.10.6.0`. API calls are mocked; a socket guard blocks non-loopback network
connections. The database and Odoo services are stopped after testing.

## Remaining release and Stable gates

Before treating a release as ready for user rollout:

- Review the exact final artifact and its distribution/publishing requirements.
- Complete current browser/UI acceptance: product entry, consent cancel/close,
  lookup review, selective application, company switching, settings/token
  handling, and English presentation. This QA run did not capture or validate
  new screenshots and did not retry the blocked browser runtime.
- Exercise a controlled real integration only with the owner's authorization,
  token and quota expectations; offline mocks do not verify live SI5 behavior.

Before promotion to Stable, retain the project's existing requirements from
its README at `988dd61`. The 30-day period is the author's project criterion,
**not an Odoo-mandated rule**:

- Validate installation/upgrade on real deployment databases with backups and a
  recovery plan, including the deployment's third-party modules.
- Observe at least **30 days with no blocking issue reported** in the intended
  production use; record the observation start and incidents rather than
  considering time elapsed during offline development sufficient.
- For the fiscal bridge, have NCM/CEST suggestions reviewed with an accountant on
  real products. This document adds no formal-signature requirement.

**Still pending:** production observation, deployment-specific acceptance, and
specialist fiscal review. Fiscal edge cases such as NCM Ex fallback, NCM-only
changes with an existing CEST, and a fiscal classification changing after a
review deserve that review. This release QA does not declare those policies
correct or silently change them. Existing automated tests and preserved fixture
values do not replace professional classification review.
