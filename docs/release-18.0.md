# Odoo 18 assisted lookup release

## Decision and bounded scope

Product GTIN Lookup **18.0.2.3.0** and GTIN Brazilian Fiscal **18.0.1.3.0**
are released as Stable for their assisted review-and-apply workflow. This is a
software acceptance decision, not a certification of catalogue information,
tax classifications, all Odoo customizations, or production uptime.

Acceptance uses reproducible client, Odoo ORM, permissions, transaction and
upgrade checks. The previous 30-day production prerequisite was a project
policy, not an Odoo requirement; it is replaced by these scope-specific gates.
Production observation and user feedback remain post-release follow-up. No
30-day observation or independent accountant sign-off is claimed.

## Contracts

- Opening or discarding consent sends no lookup; consent always starts unchecked.
- One accepted consent permits one successful lookup, including concurrent calls.
- Service errors are sanitized; failed transactions can be retried explicitly.
- Suggestions do not write products until the user selects fields and applies.
- Company, creator and write permissions are checked; tokens are company-specific
  and accessible only to administrators. Settings mask them, not encrypt them.
- Images require a separate download/validation and only selected reviewed bytes
  are applied. Transport host, size, format and dimension checks remain in place.
- The fiscal bridge proposes exact non-Ex NCM codes, never chooses an Ex exception
  without an identifier, and rejects changed NCM/CEST targets after a review.
- NCM-only application cannot retain a CEST explicitly linked to another NCM.
  Unknown mappings remain visibly unverified; they are not certified compatible.
- The bridge directly writes only selected NCM/CEST fields. OCA may derive fiscal
  genre and export unit from NCM; these effects are disclosed in the review.

## Upgrade behavior

Versions increase monotonically; module technical names are unchanged.
Existing product values, images, configuration and fiscal codes are preserved.
With the bridge installed, reviews created before this release cannot be applied; start a new lookup and
review because the old snapshot lacks the new fiscal-target binding.
Old reviews are not silently trusted, migrated to current values, or deleted.
No product data is cleared to resolve a fiscal incompatibility.

## Evidence and limitations

The fiscal contract patch passed 25 client tests, 41 base ORM tests and 57 tests
with the bridge (16 bridge tests); test counts overlap and must not be added.
A two-transaction test produced one mocked API call and one review, refusing the
second caller after serialization retry. Eight bridge regressions cover Ex-only
ambiguity, changed fiscal targets, retained CEST combinations and old snapshots.

Final release tree validated on 2026-10-29 at 20:29 UTC: 25 client tests,
41 base tests, 57 base-plus-bridge tests and Ruff passed. The two-transaction
concurrency check again produced one API mock call and one review; the second
caller was refused. On the unpatched baseline, the five negative fiscal
regressions failed as expected; with the correction, all passed.

An actual upgrade from commit `591ef384577afd59eccdbeff3b217a2df136c67f`
(base 18.0.2.2.1, bridge 18.0.1.2.0) to these release versions passed. Product
values, image bytes, the fake token and fiscal codes were preserved. The old
review still existed but application was rejected; a new consent/lookup/review
successfully applied selected fields in a rolled-back test transaction.
Earlier upgrade paths from `4fa4a31` and `bd5b3aa` to the preceding release are
recorded in the historical QA document; they were not rerun directly to this
release and are not represented as direct final-version tests.

The runtime is isolated Odoo 18 with PostgreSQL 17.11, Python 3.12 and OCA fiscal
18.0.10.6.0. Network calls use mocks and an outbound guard; no live SI5 token or
production database was used. Prior English screenshots were visually reviewed.
The release changes no form layout; it adds guarded server-side behavior and
translated error text. A new browser end-to-end run was not possible because
the browser cannot reach the isolated runtime's loopback network. Automated
business-flow checks are not claimed as browser Cancel/Esc/Back tests.

Live SI5 behavior, third-party customizations, all deployment combinations and
production observation were not tested. Validate in a backed-up staging copy
before deployment. Fiscal classifications remain the responsibility of each
business and its accountant; this module assists review and does not determine
legal tax treatment.
