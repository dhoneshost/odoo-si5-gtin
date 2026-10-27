1. Create an account at <https://global.si5.com.br> and an API token
   (*Minha conta*, https://global.si5.com.br/conta).
2. In Odoo, *Settings › General Settings › SI5 Global*, paste the token for the
   current company (administrators only). Repeat for each company.

Alternatively, set the server environment variable
`SI5_TOKEN_COMPANY_<company id>`; it takes precedence over the setting and keeps
the token out of the database. There is no fallback between companies.

Weights are stored with the *Stock Weight* decimal precision (2 by default, so
395 g becomes 0.40 kg). Raise it to 3 in *Settings › Technical › Decimal
Accuracy* for gram precision.
