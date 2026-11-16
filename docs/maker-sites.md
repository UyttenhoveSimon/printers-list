# Makers' sites outside Europe

Open Icecat leaves many fields empty. The makers' European sites fill part of
them (see the README's source table). Their sites for Asia, Oceania and the
Americas were also tried, in November 2026, through headless Chromium as well
as plain HTTP, to find out what else they could fill. This page lists what each
one answered. Read it before writing a new reader.

"Read" means a reader in `printers/sources/` uses it. "Not read" gives the
reason.

## HP

| Site | Answers | What it states | Read? |
| --- | --- | --- | --- |
| Shops of GB, CA, IN, DE, CH, FR, ES (`products_url_*.txt`) | Chromium only | full spec sheet, as JSON in the page | ✅ `hp_shop` |
| Global product sitemap (`sitemap-index-store-global-hreflang-pdp.xml`, 29 countries) | Chromium only | every SKU's page in every country | ✅ `hp_shop.store_pages` |
| Shops of AR, CL, CO, PE, MX, BR, SG, MY, TH, ID, HK, KR, AU, NZ (Magento) | Chromium only | spec sheet as `<dd data-th>` pairs, in English, Spanish or Portuguese | ✅ through the global sitemap |
| `products_url_*.txt` of those shops | 404 | | they have no such list |
| Shops of JP, TW, VN, PH, AE, ZA | 403, even to Chromium | | ⛔ |
| Shop of CN | 503 | | ⛔ |
| US shop | empty list | | ⛔ |

Many links in the global sitemap are stale. The legacy `product.aspx?id=` links
of the European shops lead to the home page. Some Asian links lead to a
category page. Out of 114 SKUs with gaps tried, 23 had a live sheet, mostly in
Argentina, Chile and Colombia. That is why `hp_shop` tries a few links per SKU
and never treats a sitemap entry as a sign that HP still sells the printer
(`hp_shop.listed`).

The Latin American sheets write thousands both ways: "25.000 páginas" and
"20,000 páginas", "1,200 dpi". A comma before three digits is taken as a
thousands separator, except in a weight or an energy figure ("1,144 kWh" is a
decimal). See `hp_shop.english_figures`.

## Canon

| Site | Answers | What it states | Read? |
| --- | --- | --- | --- |
| canon.co.uk | Chromium only | spec pages per model or series | ✅ `canon_uk` |
| sg.canon, in.canon | Chromium only | product sitemaps; each page carries the spec table | ✅ `canon_asia` |
| canon.com.au | Cloudflare challenge, even to Chromium | | ⛔ |
| usa.canon.com | 403, even to Chromium | | ⛔ |
| canon.com.mx | no sitemap (404) | | ⛔ |
| canon.com.br | sitemap links to pages that are gone (404) | | ⛔ |
| canon.jp | sitemaps answer | Japanese-market models only | not read |

Canon Asia only lists current models, about 120 printers. It sells some under
the European code (LBP246dw II, MF275dw) and others under its own (PIXMA
G3010, MAXIFY GX7170), which Icecat also carries. Model codes keep their
generation ("MF275dw II" is not the MF275dw).

## Epson

| Site | Answers | What it states | Read? |
| --- | --- | --- | --- |
| Epson's European sites | plain HTTP | catalogue and spec sheets | ✅ `epson` |
| epson.com.au | plain HTTP | older site, one `_Specs.asp` page per model, models Europe dropped included | ✅ `epson_au` |
| epson.com (US), epson.ca | sitemaps answer | specs loaded from a third party (1WorldSync), not in the page | ⛔ |
| epson.co.in, epson.com.br, epson.com.mx | sitemaps answer, pages answer | copy, scan and ADF specs only: no weight, size, power or speed | not read |
| epson.com.sg, epson.co.th | empty sitemap | | ⛔ |

The Americas' and India's sitemaps keep discontinued models, and nothing on a
page marks one as discontinued. So they cannot tell whether a printer is still
sold either.

Epson Australia's tables changed layout over the years: a label may be
"INPUT PAPER CAPACITY", "PAPER TRAY CAPACITY" or "PAPER HOLD CAPACITY", and
noise may be given as sound power (B) next to sound pressure (dB). The reader
matches labels loosely and keeps the figure in the range of a sound pressure.
Its site keeps models long gone, so it never marks a printer as listed.

## Brother, Kyocera

| Site | Answers | What it states | Read? |
| --- | --- | --- | --- |
| support.brother.com | plain HTTP | spec pages per model family | ✅ `brother_support` |
| brother-usa.com | sitemaps answer; product pages behind a Cloudflare challenge | | ⛔ |
| brother.com.au, .com.sg, .com.br, .co.jp | robots.txt only, no sitemap | | ⛔ |
| kyoceradocumentsolutions.eu | plain HTTP | product pages | ✅ `kyocera` |
| kyoceradocumentsolutions.com.au | Chromium | 86 model pages with specs | not read: only 8 printers with gaps that Europe lacks |
| kyoceradocumentsolutions.com/asia, /in, /sg... | sitemaps list a home page only | | ⛔ |

## What is left

Most remaining gaps are printers from 2016 to 2019 that makers have dropped
everywhere, regional SKUs whose sites refuse even a browser (HP Japan, Canon US
and Australia), bare Icecat sheets named by their code alone, and fields
makers do not publish at all. Xerox and Ricoh have no reader yet.
