===================
Product GTIN Lookup
===================

|badge1| |badge2|

.. |badge1| image:: https://img.shields.io/badge/maturity-Stable-green.png
    :target: https://odoo-community.org/page/development-status
    :alt: Stable
.. |badge2| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3

Look up a product by its barcode (GTIN/EAN) on SI5 Global
(https://global.si5.com.br) and review the suggested name, internal note (brand,
category), gross weight and image before applying any of them. NCM and CEST are
shown as a reference; install ``product_si5_gtin_l10n_br_fiscal`` to apply them
to ``l10n_br_fiscal`` products.

**Table of contents**

.. contents::
   :local:

Configuration
=============

#. Create an account at https://global.si5.com.br and an API token
   (*Minha conta*, https://global.si5.com.br/conta).
#. In Odoo, *Settings › General Settings › SI5 Global*, paste the token for the
   current company (administrators only). Repeat for each company.

Alternatively, set the server environment variable
``SI5_TOKEN_COMPANY_<company id>``; it takes precedence over the setting and
keeps the token out of the database. There is no fallback between companies.

Weights use the *Stock Weight* decimal precision (2 by default). Raise it to 3
in *Settings › Technical › Decimal Accuracy* for gram precision.

Usage
=====

#. Open a product (or the specific variant) with a barcode and click
   **Look up GTIN with SI5**.
#. A consent dialog lists what will be sent. Tick **I agree to send this
   barcode to SI5 Global** (it starts unticked) and click **Look up**.
   **Cancel**, the close button or Esc send nothing.
#. Each row shows current and suggested values. Turn on **Replace** only for
   the fields you want.
#. For the image, click **Download and preview**, check it, then
   turn on **Replace** in the picture row.
#. Name, internal note, NCM and CEST belong to the product template: turn on the
   confirmation about shared data, then **Apply selected fields**.

If the product changes after the lookup, run it again. A review can be applied
once. Restricted circulation codes (prefixes 2xx, 040-049) are rejected.

Data sent to SI5 Global
=======================

* Only after the consent above: one HTTPS request from the Odoo server to
  ``global.si5.com.br`` with the product barcode, the company API token and a
  User-Agent naming this module.
* The picture is downloaded from the SI5 picture server only when the user
  clicks **Download and preview**, without the token.
* No other Odoo data is sent (product name, prices, stock, customers, partners,
  invoices, users). Nothing runs in the background.
* SI5 Global receives the request itself (barcode, time, server IP address) to
  count the plan quota. Privacy policy: https://global.si5.com.br/privacidade

Known issues / Roadmap
======================

* "New product from GTIN" wizard. With ``l10n_br_fiscal``, NCM and fiscal type
  are required on the product form, so the lookup button (which saves first)
  only works on products that already have them.
* Fill the product brand when a brand addon is installed.

Credits
=======

Authors
-------

* SI5

Contributors
------------

* Dhones Meneses (SI5, https://si5.com.br)

Maintainers
-----------

This module is maintained by SI5: https://github.com/dhoneshost/odoo-si5-gtin
