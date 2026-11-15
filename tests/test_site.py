"""The page in a real browser (headless Chromium driven by rustwright).

The catalogue here is synthetic: sixty printers generated below, so that
each filter, the pages, the comparison and the detail view have something
to act on. It goes through the real ``printers build`` and is served over
HTTP, as GitHub Pages serves it. Screenshots land in ``_site-shots/``.
"""

import functools
import http.server
import os
import re
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest

from printers import cli
from printers.catalog import save

rustwright = pytest.importorskip("rustwright.sync_api")

SHOTS = Path(__file__).resolve().parent.parent / "_site-shots"
DAY = "2026-11-16"


def printer(i):
    """A varied printer: every third laser, every second two-sided..."""
    laser = i % 3 == 0
    return {
        "schema": 2,
        "icecat_id": 1000 + i,
        "brand": ["HP", "Brother", "Epson", "Canon"][i % 4],
        "name": f"Model {i:02d}",
        "title": f"Model {i:02d}",
        "category": "Multifunction Printers",
        "code": f"M{i:02d}",
        "technology": "laser" if laser else "inkjet",
        "color": i % 5 != 0,
        "duplex_print": i % 2 == 0,
        "duplex_scan": i % 4 == 0,
        "scan": True,
        "fax": i % 6 == 0,
        "adf": i % 4 == 0,
        "wifi": True,
        "ethernet": laser,
        "ppm_black": 10 + i,
        "weight_kg": 5 + i / 2,
        "max_paper": "A3" if i == 7 else "A4",
        "release_date": f"{2018 + i % 8}-01-01",
        "consumables": [
            {"code": f"T{i}BK", "name": f"Black ink {i}", "kind": "ink", "own": True},
            {"code": f"D{i}", "name": f"Drum {i}", "kind": "drum", "own": True},
            {
                "code": f"X{i}",
                "name": f"Compatible ink {i}",
                "kind": "ink",
                "brand": "Xerox",
                "own": False,
            },
        ],
        "first_seen": DAY,
        "sightings": {
            "icecat:ALL": {
                "date": DAY,
                "markets": ["BE", "FR"] if i % 2 else ["DE", "NL", "CH"],
                "url": f"https://example.com/{i}",
            }
        },
        # Model 03 is confirmed by Epson's site; Model 06 is not
        "checks": {"epson": {"date": DAY, "differ": {}}}
        if i == 3
        else {"epson": {"date": DAY, "differ": {"fax": [True, False]}}}
        if i == 6
        else {},
    }


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - the stdlib's name
        pass


def old_printer(i, release):
    """A plain inkjet sold in the US only, released ``release`` (or undated)."""
    record = {
        "schema": 3,
        "icecat_id": 2000 + i,
        "brand": "Ricoh",
        "name": f"Old printer {i}",
        "title": f"Old printer {i}",
        "category": "Inkjet Printers",
        "technology": "inkjet",
        "color": True,
        "first_seen": DAY,
        "sightings": {"icecat:ALL": {"date": DAY, "markets": ["US"], "url": ""}},
    }
    if release:
        record["added"] = release
    return record


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    data = root / "data"
    if os.environ.get("SITE_DATA"):
        # `SITE_DATA=data uv run pytest tests/test_site.py -k every`: the
        # control checks on the real catalogue
        data = Path(os.environ["SITE_DATA"]).resolve()
        yield from serve(data, root / "out")
        return
    products = {str(1000 + i): printer(i) for i in range(60)}
    # two models from 2010 and 2012, hidden by default, and one with no date
    products |= {
        "2000": old_printer(0, "2010-05-01"),
        "2001": old_printer(1, "2012-01-01"),
        "2002": old_printer(2, ""),
    }
    save(data / "products.json", products)
    save(
        data / "state.json",
        {
            "lookups": {},
            "caches": {},
            "runs": {"icecat:ALL": DAY},
            "started": "2026-10-01",
            "report": {
                "date": DAY,
                "sources": {
                    "icecat:ALL": {"status": "ok", "found": 63},
                    "epson:GB": {"status": "ok", "found": 5},
                    "epson:BE": {"status": "error", "detail": "down"},
                    "hp.com:GB": {"status": "error", "detail": "timeout"},
                },
            },
        },
    )
    yield from serve(data, root / "out")


def serve(data, out):
    cli.main(["--data", str(data), "build", "--out", str(out)])
    handler = functools.partial(Quiet, directory=str(out))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with rustwright.sync_playwright() as engine:
        try:
            chromium = engine.chromium.launch(headless=True)
        except Exception as error:  # noqa: BLE001 - no browser installed here
            pytest.skip(f"no Chromium: {error}")
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser, site):
    context = browser.new_context(
        locale="en-GB", viewport={"width": 1280, "height": 900}
    )
    tab = context.new_page()
    errors = []
    tab.on("pageerror", errors.append)
    tab.goto(site)
    tab.wait_for_selector(".card")
    yield tab
    assert errors == []
    context.close()


def hash_of(page):
    return page.evaluate("location.hash")


def count(page):
    return page.text_content("#count")


def shot(page, name, *, full_page=True):
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=full_page)


# --- the page logic, run in the browser that will run it ----------------------


def logic(page, script):
    return page.evaluate(
        f"async () => {{ const L = await import('./logic.js'); {script} }}"
    )


def test_url_state_round_trips(page):
    assert logic(
        page,
        """
        const s = L.emptyState();
        s.duplex_scan = true; s.technology = 'laser'; s.ppm_black = 20;
        s.markets.add('BE'); s.brands.add('HP'); s.sort = 'fastest'; s.page = 3;
        s.compare = ['1', '2']; s.available = false;
        const back = L.decode('#' + L.encode(s));
        return back.duplex_scan && back.technology === 'laser' && back.ppm_black === 20
          && back.markets.has('BE') && back.brands.has('HP') && back.sort === 'fastest'
          && back.page === 3 && back.compare.join() === '1,2' && back.available === false;
        """,
    )


def test_bad_url_values_fall_back_to_defaults(page):
    assert logic(
        page,
        """
        const s = L.decode('#technology=plasma&sort=random&page=-4&ppm_black=abc');
        return s.technology === '' && s.sort === 'newest' && s.page === 1
          && s.ppm_black === 0 && s.available === true;
        """,
    )


def test_matching_rules(page):
    result = logic(
        page,
        """
        const s = L.emptyState();
        const p = {brand: 'HP', name: 'X', available: true, color: false,
                   technology: 'inkjet', ppm_black: 20, weight_kg: 8, markets: ['BE'],
                   _text: 'hp x', _year: 2022};
        const out = {};
        out.plain = L.matches(p, s);
        s.color = '0'; out.mono = L.matches(p, s);
        s.color = '1'; out.colour = L.matches(p, s); s.color = '';
        s.ppm_black = 25; out.tooSlow = L.matches(p, s); s.ppm_black = 0;
        s.weight_kg = 10; out.lightEnough = L.matches(p, s); s.weight_kg = 0;
        s.ppm_color = 5; out.unknownSpeed = L.matches(p, s); s.ppm_color = 0;
        s.markets.add('FR'); out.otherCountry = L.matches(p, s); s.markets.clear();
        s.year = '2023'; out.older = L.matches(p, s); s.year = '';
        s.q = 'hp  x'; out.search = L.matches(p, s);
        return out;
        """,
    )
    assert result == {
        "plain": True,
        "mono": True,
        "colour": False,
        "tooSlow": False,
        "lightEnough": True,
        "unknownSpeed": False,
        "otherCountry": False,
        "older": False,
        "search": True,
    }


def test_pagination_and_page_numbers(page):
    assert logic(
        page,
        """
        const items = Array.from({length: 100}, (_, i) => i);
        const p = L.paginate(items, 9, 48);
        const nums = L.pageNumbers(5, 10);
        return p.page === 3 && p.pages === 3 && p.items.length === 4
          && JSON.stringify(nums) === JSON.stringify([1, null, 4, 5, 6, null, 10])
          && L.paginate([], 1).pages === 1;
        """,
    )


def test_compare_holds_four_at_most(page):
    assert logic(
        page,
        """
        let r = {list: []};
        for (const id of ['a', 'b', 'c', 'd']) r = L.toggleCompare(r.list, id);
        const full = L.toggleCompare(r.list, 'e');
        const removed = L.toggleCompare(r.list, 'b');
        return full.full && full.list.length === 4 && removed.list.join() === 'a,c,d';
        """,
    )


def test_differing_rows(page):
    assert logic(
        page,
        """
        const rows = L.differingRows([{fax: true, wifi: true}, {fax: false, wifi: true}], ['fax', 'wifi']);
        return rows.join() === 'fax';
        """,
    )


def test_every_language_is_complete(page):
    missing = page.evaluate("async () => (await import('./i18n.js')).missingKeys()")
    assert missing == {"fr": [], "nl": [], "de": []}


def test_language_is_picked_from_the_browser(page):
    assert (
        page.evaluate(
            """async () => { const i = await import('./i18n.js');
        return [i.pickLanguage(null, ['nl-BE', 'en']), i.pickLanguage('de', ['fr']),
                i.pickLanguage(null, ['ja']), i.pickLanguage('xx', [])].join(); }"""
        )
        == "nl,de,en,en"
    )


# --- the page ------------------------------------------------------------------


def test_first_page_shows_48_of_60(page):
    assert count(page) == "61 of 63 printers"
    assert len(page.query_selector_all(".card")) == 48
    assert "Page 1 of 2" in page.text_content("#pager")
    shot(page, "desktop")


def test_next_page(page):
    page.click('#pager button[data-page="2"]')
    assert len(page.query_selector_all(".card")) == 13
    assert "page=2" in hash_of(page)


def test_two_sided_scanning_filter(page):
    page.check('input[data-key="duplex_scan"]')
    assert count(page) == "15 of 63 printers"
    chips = page.text_content("#active")
    assert "Two-sided scanning" in chips
    page.click('#active button[data-clear="duplex_scan"]')
    assert count(page) == "61 of 63 printers"


def test_technology_and_colour_choices(page):
    page.click('.seg[data-key="technology"] button[data-value="laser"]')
    assert count(page) == "20 of 63 printers"
    page.click('.seg[data-key="color"] button[data-value="0"]')
    # lasers (every 3rd) that are mono (every 5th): 0, 15, 30, 45
    assert count(page) == "4 of 63 printers"
    page.click('#active button[data-clear="all"]')
    assert count(page) == "61 of 63 printers"


def test_speed_slider(page):
    page.eval_on_selector(
        'input[data-key="ppm_black"]',
        "el => { el.value = 60; el.dispatchEvent(new Event('input', {bubbles: true})); }",
    )
    assert count(page) == "10 of 63 printers"
    assert "≥ 60" in page.text_content('output[data-out="ppm_black"]')


def test_country_and_brand(page):
    page.check('input[data-market="BE"]')
    assert count(page) == "30 of 63 printers"
    page.check('input[data-brand="HP"]')
    assert count(page) == "0 of 63 printers"  # HP is every 4th: even, so never BE
    assert "No printer matches" in page.text_content("#results")


def test_search(page):
    # every word must match: "4" is in Model 04, 14, 24, 34, 40 to 49 and 54
    page.fill("#q", "model 4")
    page.wait_for_function(
        "() => document.querySelector('#count').textContent.startsWith('15 ')"
    )
    page.fill("#q", "canon model 4")
    page.wait_for_function(
        "() => document.querySelector('#count').textContent.startsWith('2 ')"
    )  # Canon: Model 43, 47


def test_detail_shows_supplies_and_countries(page):
    page.click('.card[data-id="1006"] [data-open]')
    page.wait_for_selector("#detail[open]")
    body = page.text_content("#detail-body")
    assert "T6BK" in body and "Drum" in body
    assert "Germany" in body and "Switzerland" in body
    assert "epson states otherwise" in body
    shot(page, "detail")
    page.click("#detail [data-close]")
    assert not page.is_visible("#detail")


def test_compare_two_printers(page, site):
    page.goto(site + "#sort=name")
    page.reload()
    page.wait_for_selector(".card")
    page.check('input[data-compare="1000"]')
    assert page.is_visible("#tray")
    assert page.is_disabled("#open-compare")
    page.check('input[data-compare="1001"]')
    page.click("#open-compare")
    page.wait_for_selector("#compare[open]")
    table = page.text_content("#compare-body")
    assert "Model 00" in table and "Model 01" in table
    assert page.query_selector_all("#compare tr.diff")
    page.check("#only-diff")
    rows = page.query_selector_all("#compare tbody tr")
    assert all(
        "diff" in (r.get_attribute("class") or "") for r in rows[:-2]
    )  # the last two rows are supplies and countries
    shot(page, "compare")
    assert "cmp=1000%2C1001" in hash_of(page)
    page.click('#compare button[data-uncompare="1001"]')
    assert not page.is_visible("#compare")  # one printer left: nothing to compare
    assert "Model 00" in page.text_content("#tray")


def test_url_restores_the_view(page, site):
    page.goto(site + "#duplex_print=1&technology=inkjet&sort=fastest")
    page.reload()
    page.wait_for_selector(".card")
    assert count(page) == "20 of 63 printers"
    assert page.is_checked('input[data-key="duplex_print"]')
    first = page.text_content(".card h3")
    assert first == "Model 58"


def test_french(page):
    page.select_option("#lang", "fr")
    assert page.text_content("#count") == "61 imprimantes sur 63"
    assert "Recto verso" in page.text_content("#filters")
    assert "Belgique" in page.text_content("#filters")
    assert page.evaluate("document.documentElement.lang") == "fr"
    assert page.text_content("#count") == "61 imprimantes sur 63"
    page.select_option("#lang", "en")


def test_every_filter_section_is_reachable(page):
    """No section of the panel is cut off or scrolls out of sight on its own."""
    clipped = page.evaluate(
        """() => [...document.querySelectorAll('#filters .group')].filter((g) => {
          const r = g.getBoundingClientRect();
          return r.width === 0 || g.scrollWidth > g.clientWidth + 1;
        }).map((g) => g.querySelector('summary').textContent)"""
    )
    assert clipped == []
    for summary in page.query_selector_all("#filters details:not([open]) summary"):
        summary.click()
    assert page.evaluate(
        "[...document.querySelectorAll('#filters details')].every((d) => d.open)"
    )


def test_phone_width_has_no_sideways_scroll(browser, site):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    tab = context.new_page()
    tab.goto(site)
    tab.wait_for_selector(".card")
    shot(tab, "phone-list", full_page=False)
    assert tab.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not tab.is_visible("#filters")
    tab.click("#toggle-filters")
    assert tab.is_visible("#filters")
    shot(tab, "phone-filters", full_page=False)
    context.close()


def test_data_files_are_versioned_and_split(site, page):
    html = page.content()
    assert "app.js?v=" in html and "style.css?v=" in html
    rows = page.evaluate(
        "async () => (await (await fetch('printers.json')).json()).printers"
    )
    assert "consumables" not in rows[0]
    assert all("color" in row for row in rows)
    extra = page.evaluate(
        "async () => (await (await fetch('details.json')).json())['1003']"
    )
    assert extra["confirmed"] == ["epson"]
    assert extra["consumables"][0] == {
        "code": "T3BK",
        "name": "Black ink 3",
        "kind": "ink",
        "own": True,
    }


def test_the_last_ten_years_by_default(page):
    """2010 and 2012 models are hidden; an undated one is not, it may be recent."""
    assert page.input_value('select[data-key="year"]') == "2016"
    assert (
        "Old printer 2" in page.text_content("#results")
        or count(page) == "61 of 63 printers"
    )
    page.select_option('select[data-key="year"]', "")
    assert count(page) == "63 of 63 printers"
    assert "Any year" in page.text_content("#active")
    assert "year=all" in hash_of(page)
    page.click('#active button[data-clear="year"]')
    assert count(page) == "61 of 63 printers"


def test_older_years_from_the_url(page, site):
    page.goto(site + "#year=2011")
    page.reload()
    page.wait_for_selector(".card")
    assert count(page) == "62 of 63 printers"


def test_other_brands_supplies_are_set_apart(page):
    page.click('.card[data-id="1004"] [data-open]')
    page.wait_for_selector("#detail[open]")
    own = page.text_content("#detail-body ul.supplies")
    assert "T4BK" in own
    assert "X4" not in own
    other = page.text_content("#detail-body .supplies-other")
    assert "Compatible, other brands (1)" in other
    assert "Xerox" in other


# --- every control, against an independent count ---------------------------
#
# The expected numbers are computed here in Python from the very file the page
# loads, with the page's documented rules, then each control is operated and
# the page's count compared. A control that does nothing, or the wrong thing,
# shows up as a mismatch.

DEFAULT_YEAR = 2016  # ten years before the catalogue's date


def rows(page):
    return page.evaluate(
        "async () => (await (await fetch('printers.json')).json()).printers"
    )


def year(p):
    date = p.get("release_date") or p.get("added") or ""
    return int(date[:4]) if date else None


def shown(p):
    """The default view: on sale, and from the last ten years or undated."""
    y = year(p)
    return p.get("available") and (y is None or y >= DEFAULT_YEAR)


def expected(data, keep):
    """The count line as the page writes it in English: "1,880 of 7,440 printers"."""
    return f"{sum(1 for p in data if shown(p) and keep(p)):,} of {len(data):,} printers"


def is_new(page):
    """The page's rule: first seen in the latest week, never on the first fill."""
    meta = page.evaluate(
        "async () => { const d = await (await fetch('printers.json')).json(); return [d.updated, d.started]; }"
    )
    updated, started = (date.fromisoformat(d) for d in meta)
    since = max(started, updated - timedelta(days=7)).isoformat()
    return lambda p: p.get("first_seen", "") > since


def open_all(page):
    """Open every section of the panel, as someone looking for a filter would."""
    for summary in page.query_selector_all("#filters details:not([open]) summary"):
        summary.click()


def takes_a3(p):
    """A3, A3+ and SRA3 all take an A3 sheet, as the page reads them."""
    digits = re.sub(r"\D", "", p.get("max_paper") or "")
    return bool(digits) and int(digits) <= 3


def check_each(page, cases):
    """Run (name, act, undo, expected) cases; return the mismatches."""
    open_all(page)
    wrong = []
    for name, act, undo, want in cases:
        act()
        got = count(page)
        if got != want:
            wrong.append((name, got, want))
        undo()
    return wrong


def test_every_flag(page):
    data = rows(page)
    flags = page.evaluate(
        "async () => (await import('./logic.js')).FILTERS.filter((f) => f.type === 'flag' && !f.default).map((f) => f.key)"
    )
    assert len(flags) >= 20
    new = is_new(page)

    def case(key):
        selector = f'input[data-key="{key}"]'
        keep = new if key == "new" else (lambda p: bool(p.get(key)))
        if key == "a3":
            keep = takes_a3
        return (
            key,
            lambda: page.check(selector),
            lambda: page.uncheck(selector),
            expected(data, keep),
        )

    assert check_each(page, [case(key) for key in flags]) == []


def test_on_sale_only_can_be_unticked(page):
    page.uncheck('input[data-key="available"]')
    assert (
        count(page) == "61 of 63 printers"
    )  # all on sale here; the year still applies
    assert "Not on sale" in page.text_content("#active")


def test_every_choice(page):
    data = rows(page)
    cases = []
    for key, value, keep in [
        ("technology", "laser", lambda p: p.get("technology") == "laser"),
        ("technology", "inkjet", lambda p: p.get("technology") == "inkjet"),
        ("color", "1", lambda p: bool(p.get("color"))),
        ("color", "0", lambda p: not p.get("color")),
    ]:
        button = f'.seg[data-key="{key}"] button[data-value="{value}"]'
        anyone = f'.seg[data-key="{key}"] button[data-value=""]'
        cases.append(
            (
                f"{key}={value}",
                lambda b=button: page.click(b),
                lambda a=anyone: page.click(a),
                expected(data, keep),
            )
        )
    assert check_each(page, cases) == []


def test_every_slider(page):
    data = rows(page)
    sliders = page.eval_on_selector_all(
        "#filters input[type=range]",
        "els => els.map((e) => ({key: e.dataset.key, min: +e.min, max: +e.max, step: +e.step}))",
    )
    kinds = page.evaluate(
        "async () => Object.fromEntries((await import('./logic.js')).FILTERS.map((f) => [f.key, f.type]))"
    )
    assert {s["key"] for s in sliders} >= {"ppm_black", "weight_kg"}
    cases = []
    for s in sliders:
        key, kind = s["key"], kinds[s["key"]]
        middle = s["min"] + round((s["max"] - s["min"]) / 2 / s["step"]) * s["step"]
        selector = f'input[data-key="{key}"]'
        off = s["min"] if kind == "min" else s["max"]

        def move(sel=selector, value=middle):
            page.eval_on_selector(
                sel,
                f"el => {{ el.value = {value}; el.dispatchEvent(new Event('input', {{bubbles: true}})); }}",
            )

        def keep(p, key=key, kind=kind, value=middle):
            v = p.get(key)
            if not isinstance(v, (int, float)):
                return False
            return v >= value if kind == "min" else v <= value

        cases.append(
            (
                key,
                move,
                lambda sel=selector, value=off: move(sel, value),
                expected(data, keep),
            )
        )
    assert check_each(page, cases) == []


def test_every_country_and_brand(page):
    data = rows(page)
    cases = []
    for box in page.query_selector_all("#filters input[data-market]"):
        market = box.get_attribute("data-market")
        selector = f'input[data-market="{market}"]'
        keep = lambda p, m=market: m in p.get("markets", [])  # noqa: E731
        cases.append(
            (
                market,
                lambda s=selector: page.check(s),
                lambda s=selector: page.uncheck(s),
                expected(data, keep),
            )
        )
    for box in page.query_selector_all("#filters input[data-brand]"):
        brand = box.get_attribute("data-brand")
        selector = f'input[data-brand="{brand}"]'
        keep = lambda p, b=brand: p["brand"] == b  # noqa: E731
        cases.append(
            (
                brand,
                lambda s=selector: page.check(s),
                lambda s=selector: page.uncheck(s),
                expected(data, keep),
            )
        )
    assert len(cases) >= 9
    assert check_each(page, cases) == []


def test_every_year(page):
    data = rows(page)
    sel = 'select[data-key="year"]'
    years = [
        v
        for v in page.eval_on_selector_all(
            sel + " option", "os => os.map((o) => o.value)"
        )
        if v
    ]
    cases = []
    for value in years:

        def keep(p, y=int(value)):
            known = year(p)
            return p.get("available") and (known is None or known >= y)

        want = f"{sum(1 for p in data if keep(p)):,} of {len(data):,} printers"
        cases.append(
            (value, lambda v=value: page.select_option(sel, v), lambda: None, want)
        )
    # picking one year after another must keep refreshing the list
    assert check_each(page, cases + list(reversed(cases))) == []


def test_every_sort(page):
    data = [p for p in rows(page) if shown(p)]
    for p in data:
        if p.get("width_mm") and p.get("depth_mm"):
            p["_footprint"] = p["width_mm"] * p["depth_mm"]
    by_name = lambda p: (p["brand"], p["name"])  # noqa: E731
    sorts = page.eval_on_selector_all("#sort option", "os => os.map((o) => o.value)")
    assert len(sorts) >= 8
    fields = {
        "newest": ("_date", -1),
        "oldest": ("_date", 1),
        "fastest": ("ppm_black", -1),
        "fastest_colour": ("ppm_color", -1),
        "most_paper": ("paper_input", -1),
        "lightest": ("weight_kg", 1),
        "quietest": ("noise_db", 1),
        "greenest": ("tec_kwh", 1),
        "smallest": ("_footprint", 1),
    }
    wrong = []
    for name in sorts:
        page.select_option("#sort", name)
        first = page.eval_on_selector_all(
            ".card h3", "hs => hs.slice(0, 5).map((h) => h.textContent)"
        )
        if name == "name":
            want = sorted(data, key=by_name)
        else:
            key, direction = fields[name]
            known = [
                p
                for p in data
                if (
                    p.get(key)
                    if key != "_date"
                    else (p.get("release_date") or p.get("added"))
                )
                is not None
            ]
            unknown = sorted((p for p in data if p not in known), key=by_name)
            if key == "_date":
                known.sort(key=by_name)
                known.sort(
                    key=lambda p: p.get("release_date") or p.get("added"),
                    reverse=direction < 0,
                )
            else:
                known.sort(key=by_name)
                known.sort(key=lambda p: p[key], reverse=direction < 0)
            want = known + unknown
        if first != [p["name"] for p in want[:5]]:
            wrong.append((name, first, [p["name"] for p in want[:5]]))
    assert wrong == []


def test_reset_and_clear_all_undo_everything(page):
    page.check('input[data-key="duplex_print"]')
    page.click('.seg[data-key="technology"] button[data-value="inkjet"]')
    page.check('input[data-market="BE"]')
    page.select_option('select[data-key="year"]', "")
    page.click("#reset")
    assert count(page) == "61 of 63 printers"
    assert page.text_content("#active") == ""
    page.check('input[data-key="fax"]')
    page.check('input[data-brand="HP"]')
    page.click('#active button[data-clear="all"]')
    assert count(page) == "61 of 63 printers"
    assert not page.is_checked('input[data-key="fax"]')
    assert not page.is_checked('input[data-brand="HP"]')


def test_every_language(page):
    for lang, word in [
        ("fr", "Filtres"),
        ("nl", "Filters"),
        ("de", "Filter"),
        ("en", "Filters"),
    ]:
        page.select_option("#lang", lang)
        assert page.evaluate("document.documentElement.lang") == lang
        assert page.text_content("#toggle-filters") == word
        assert page.query_selector_all(".card")


@pytest.mark.skipif(bool(os.environ.get("SITE_DATA")), reason="synthetic report only")
def test_every_source_is_listed_with_its_status(page):
    table = page.text_content("#sources-table")
    for name in ["Open Icecat", "Epson", "Lexmark", "HP", "Brother"]:
        assert name in table
    assert "OK, 63 printers" in table
    assert "1 of 2 countries answered" in table
    assert "Refuses automated readers" in table
    assert (
        page.get_attribute('#sources-table a[href="https://icecat.biz"]', "target")
        == "_blank"
    )
