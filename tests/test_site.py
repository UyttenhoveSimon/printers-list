"""The page in a real browser (headless Chromium driven by rustwright).

The catalogue here is synthetic: sixty printers generated below, so that
each filter, the pages, the comparison and the detail view have something
to act on. It goes through the real ``printers build`` and is served over
HTTP, as GitHub Pages serves it. Screenshots land in ``_site-shots/``.
"""

import functools
import http.server
import threading
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
    out = root / "out"
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
