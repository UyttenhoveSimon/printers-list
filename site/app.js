// The page itself: builds the panel from logic.GROUPS, renders a page of
// results, the comparison and the detail view. All decisions live in logic.js.

import * as L from "./logic.js";
import { LANGUAGES, countryName, formatNumber, language, pickLanguage, setLanguage, t } from "./i18n.js";

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

let all = [];
let byId = new Map();
let bounds = {};
let data = {};
let state = L.emptyState();
let details = null; // details.json, fetched the first time a detail is opened
let onlyDifferences = false;

const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
};

// --- formatting ---------------------------------------------------------------

function value(key, v) {
  if (v === undefined || v === null || v === "") return t("unknown");
  if (typeof v === "boolean") return v ? t("yes") : t("no");
  if (key === "technology") return t(v);
  if (key === "color") return v ? t("colour_yes") : t("colour_no");
  if (typeof v === "number") return formatNumber(v);
  return String(v);
}

function tags(p) {
  const out = [];
  if (p.office) out.push([t("class_office"), "office"]);
  if (p.new) out.push([t("new"), "new"]);
  if (!p.available) out.push([t("not_on_sale"), "off"]);
  if (p.technology) out.push([p.technology === "laser" && p.led ? "LED" : t(p.technology), ""]);
  if (p.ink_tank) out.push([t("ink_tank"), ""]);
  out.push([p.color ? t("colour_yes") : t("colour_no"), ""]);
  if (p.duplex_print) out.push([t("duplex_print"), "good"]);
  if (p.duplex_scan) out.push([t("duplex_scan"), "good"]);
  for (const k of ["scan", "fax", "adf", "wifi", "ethernet", "airprint", "a3"]) if (p[k]) out.push([t(k), ""]);
  return out.map(([label, cls]) => `<span class="tag ${cls}">${esc(label)}</span>`).join("");
}

// --- the side panel -------------------------------------------------------------

function filterControl(f) {
  const label = t(f.label || f.key);
  if (f.type === "flag") {
    return `<label class="check"><input type="checkbox" data-key="${f.key}"> ${esc(label)}</label>`;
  }
  if (f.type === "choice") {
    const names = f.labels || f.values;
    const buttons = [`<button type="button" data-value="">${esc(t("any"))}</button>`]
      .concat(f.values.map((v, i) => `<button type="button" data-value="${v}">${esc(t(names[i]))}</button>`));
    return `<div class="seg" data-key="${f.key}" role="group" aria-label="${esc(label)}">${buttons.join("")}</div>`;
  }
  const r = bounds[f.key];
  if (!r || r.min === r.max) return "";
  // from and to: either may stay empty; the hints show what the data holds
  const box = (side, hint) => `<input type="number" inputmode="decimal" data-range="${f.key}" data-side="${side}"
      min="${r.min}" max="${r.max}" step="any" placeholder="${formatNumber(hint)}" aria-label="${esc(label)}: ${esc(t(side ? "to" : "from"))}">`;
  return `<div class="range" role="group" aria-label="${esc(label)}">
    <span class="range-head">${esc(label)}</span>
    <span class="range-boxes">${box(0, r.min)}<span aria-hidden="true">–</span>${box(1, r.max)}</span>
  </div>`;
}

function renderPanel() {
  const groups = L.GROUPS.map((g) => {
    const body = g.filters.map(filterControl).join("");
    if (!body.trim()) return "";
    return `<details class="group" ${g.open ? "open" : ""}><summary>${esc(t("g_" + g.id))}</summary>${body}</details>`;
  });
  const years = [...new Set(all.map((p) => p._year).filter(Boolean).concat(state.defaultYear ? [Number(state.defaultYear)] : []))].sort((a, b) => b - a);
  if (years.length) {
    // high up: the default "ten years back" hides half the catalogue
    groups.splice(2, 0, `<details class="group" open><summary>${esc(t("g_year"))}</summary>
      <select data-key="year" aria-label="${esc(t("g_year"))}"><option value="">${esc(t("any_year"))}</option>
      ${years.map((y) => `<option value="${y}">${esc(t("or_later", { year: y }))}</option>`).join("")}</select></details>`);
  }
  const markets = L.markets(all);
  if (markets.length) {
    const named = markets.map(([m, n]) => [m, countryName(m), n]).sort((a, b) => a[1].localeCompare(b[1], language()));
    groups.push(`<details class="group" open><summary>${esc(t("g_markets"))}</summary><div class="scroll-list">
      ${named.map(([m, name, n]) => `<label class="check"><input type="checkbox" data-market="${m}"> ${esc(name)} <span class="n">${formatNumber(n)}</span></label>`).join("")}
      </div></details>`);
  }
  const brands = L.brands(all);
  if (brands.length) {
    groups.push(`<details class="group" open><summary>${esc(t("g_brands"))}</summary><div class="scroll-list">
      ${brands.map(([b, n]) => `<label class="check"><input type="checkbox" data-brand="${esc(b)}"> ${esc(b)} <span class="n">${formatNumber(n)}</span></label>`).join("")}
      </div></details>`);
  }
  // first, and sticky: the panel runs long once the country and brand lists open
  groups.unshift(`<button type="button" id="reset" class="ghost wide reset">${esc(t("reset"))}</button>`);
  $("#filters").innerHTML = groups.join("");
}

function syncPanel() {
  const panel = $("#filters");
  for (const f of L.FILTERS) {
    if (f.type === "flag") {
      const el = panel.querySelector(`input[data-key="${f.key}"]`);
      if (el) el.checked = state[f.key];
    } else if (f.type === "choice") {
      panel.querySelectorAll(`.seg[data-key="${f.key}"] button`).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === state[f.key])));
    } else {
      panel.querySelectorAll(`input[data-range="${f.key}"]`).forEach((el) => {
        const v = state[f.key][Number(el.dataset.side)];
        // leave a box alone while it is being typed in
        if (document.activeElement !== el) el.value = v === null ? "" : String(v);
      });
    }
  }
  const year = panel.querySelector('select[data-key="year"]');
  if (year) year.value = state.year;
  panel.querySelectorAll("input[data-market]").forEach((i) => (i.checked = state.markets.has(i.dataset.market)));
  panel.querySelectorAll("input[data-brand]").forEach((i) => (i.checked = state.brands.has(i.dataset.brand)));
  $("#q").value = state.q;
  $("#sort").value = state.sort;
}

// --- results --------------------------------------------------------------------

function card(p) {
  const meta = [];
  if (p.ppm_black) meta.push(`${p.ppm_black} ppm`);
  if (p._year) meta.push(String(p._year));
  if (p.markets?.length) meta.push(p.markets.length > 4 ? t("countries", { n: p.markets.length }) : p.markets.map(countryName).join(", "));
  const img = p.image ? `<img src="${esc(p.image)}" alt="" loading="lazy" decoding="async" width="200" height="150">` : "";
  const picked = state.compare.includes(p.id);
  return `<li class="card" data-id="${esc(p.id)}">
    <button type="button" class="img" data-open="${esc(p.id)}" aria-label="${esc(t("details"))}: ${esc(p.name)}">${img}</button>
    <h3><button type="button" class="linkish" data-open="${esc(p.id)}">${esc(p.name)}</button></h3>
    <div class="meta">${meta.map(esc).join(" · ")}</div>
    <div class="tags">${tags(p)}</div>
    <label class="check compare-check"><input type="checkbox" data-compare="${esc(p.id)}" ${picked ? "checked" : ""}> ${esc(t("compare"))}</label>
  </li>`;
}

function renderPager(page, pages) {
  if (pages <= 1) return "";
  const nums = L.pageNumbers(page, pages).map((n) => n === null
    ? '<span class="gap">…</span>'
    : `<button type="button" data-page="${n}" ${n === page ? 'aria-current="page"' : ""}>${n}</button>`);
  return `<button type="button" data-page="${page - 1}" ${page === 1 ? "disabled" : ""}>${esc(t("previous"))}</button>
    ${nums.join("")}
    <button type="button" data-page="${page + 1}" ${page === pages ? "disabled" : ""}>${esc(t("next"))}</button>
    <span class="page-of">${esc(t("page", { n: page, pages }))}</span>`;
}

function rangeText([lo, hi]) {
  if (lo !== null && hi !== null) return `${formatNumber(lo)}–${formatNumber(hi)}`;
  return lo !== null ? t("at_least", { value: formatNumber(lo) }) : t("at_most", { value: formatNumber(hi) });
}

function renderActive() {
  const chips = L.activeFilters(state).map(([key, v]) => {
    let label;
    if (key === "q") label = `“${v}”`;
    else if (key === "market") label = countryName(v);
    else if (key === "brand") label = v;
    else if (key === "year") label = v ? t("or_later", { year: v }) : t("any_year");
    else if (key === "available" && !v) label = t("not_on_sale");
    else {
      const f = L.FILTERS.find((x) => x.key === key);
      if (f.type === "choice") label = key === "color" ? t(v === "1" ? "colour_yes" : "colour_no") : t(v);
      else if (f.type === "flag") label = t(f.label || key);
      else label = `${t(key)} ${rangeText(v)}`;
    }
    return `<button type="button" data-clear="${esc(key)}" data-value="${esc(v)}" title="${esc(t("remove_filter"))}">${esc(label)}</button>`;
  });
  if (chips.length > 1) chips.push(`<button type="button" class="clear" data-clear="all">${esc(t("clear_all"))}</button>`);
  $("#active").innerHTML = chips.join("");
}

function renderTray() {
  const tray = $("#tray");
  const picked = state.compare.map((id) => byId.get(id)).filter(Boolean);
  tray.hidden = picked.length === 0;
  $("#tray-items").innerHTML = picked.map((p) => `<li>${esc(p.name)} <button type="button" data-uncompare="${esc(p.id)}" aria-label="${esc(t("remove"))}">✕</button></li>`).join("");
  $("#open-compare").textContent = t("compare_n", { n: picked.length });
  $("#open-compare").disabled = picked.length < 2;
}

function render({ scroll = false } = {}) {
  const found = L.search(all, state);
  const { page, pages, items } = L.paginate(found, state.page);
  state.page = page;
  $("#results").innerHTML = items.length ? items.map(card).join("") : `<li class="empty">${esc(t("none"))}</li>`;
  $("#pager").innerHTML = renderPager(page, pages);
  $("#count").textContent = t("count", { n: formatNumber(found.length), total: formatNumber(all.length) });
  const since = $("#since");
  since.hidden = !state.year;
  if (state.year) since.textContent = t("since_year", { year: state.year });
  renderActive();
  renderTray();
  syncPanel();
  const hash = L.encode(state);
  history.replaceState(null, "", hash ? `#${hash}` : location.pathname + location.search);
  if (scroll) $("#results").scrollIntoView({ block: "start", behavior: "smooth" });
}

// --- the detail view and the comparison ----------------------------------------------

async function loadDetails() {
  if (details) return details;
  try {
    const response = await fetch("details.json");
    details = await response.json();
  } catch {
    details = {};
  }
  return details;
}

function supplyLine(c) {
  const brand = c.own || !c.brand ? "" : `<span class="supply-brand">${esc(c.brand)}</span> `;
  const name = c.name !== c.code ? esc(c.name) : "";
  return `<li class="${c.own ? "own" : "other"}"><span class="tag">${esc(t("kind_" + c.kind))}</span> ${brand}<code>${esc(c.code)}</code> ${name}</li>`;
}

// The brand's own supplies first; compatibles from other brands set apart.
function suppliesList(id) {
  const extra = (details && details[id]) || {};
  const items = extra.consumables || [];
  const own = items.filter((c) => c.own !== false);
  const other = items.filter((c) => c.own === false);
  let html = "";
  if (own.length) html += `<ul class="supplies">${own.map(supplyLine).join("")}</ul>`;
  if (extra.supplies) html += `<p class="supplies-text">${esc(extra.supplies)}</p>`;
  if (other.length) {
    html += `<details class="supplies-other"><summary>${esc(t("supplies_other", { n: other.length }))}</summary>
      <p class="muted">${esc(t("supplies_other_note"))}</p>
      <ul class="supplies">${other.map(supplyLine).join("")}</ul></details>`;
  }
  return html || `<p class="muted">${esc(t("supplies_none"))}</p>`;
}

function checksNote(p) {
  const extra = (details && details[p.id]) || {};
  const notes = [];
  for (const [source, differ] of Object.entries(extra.differs || {})) {
    const fields = Object.entries(differ).map(([k, [ours, theirs]]) => `${t(k)}: ${value(k, ours)} → ${value(k, theirs)}`).join("; ");
    notes.push(`<p class="warn">⚠ ${esc(t("differs", { source, fields }))}</p>`);
  }
  return notes.join("");
}

async function openDetail(id) {
  const p = byId.get(id);
  if (!p) return;
  await loadDetails();
  const filled = ((details && details[p.id]) || {}).filled || {};
  const rows = L.SPEC_ROWS.filter((k) => p[k] !== undefined && p[k] !== null)
    .map((k) => {
      // a value Icecat lacked, read from the maker's own page, says so
      const from = filled[k] ? ` <span class="from">${esc(t("from_source", { source: SOURCE_LABELS[filled[k]] || filled[k] }))}</span>` : "";
      return `<tr><th scope="row">${esc(t(k))}</th><td>${esc(value(k, p[k]))}${from}</td></tr>`;
    }).join("");
  const countries = (p.markets || []).map(countryName).sort((a, b) => a.localeCompare(b, language()));
  const links = [`<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(t("maker_page"))}</a>`];
  if (p.icecat_id) links.push(`<a href="https://icecat.biz/p/vendorName/mpn/desc-${p.icecat_id}.html" target="_blank" rel="noopener">${esc(t("icecat_page"))}</a>`);
  $("#detail-body").innerHTML = `
    <div class="detail-head">
      ${p.image ? `<img src="${esc(p.image)}" alt="" width="240" height="180">` : ""}
      <div><h2 id="detail-title">${esc(p.name)}</h2><div class="tags">${tags(p)}</div>${checksNote(p)}<p class="links">${links.join(" · ")}</p></div>
    </div>
    <h3>${esc(t("supplies"))}</h3>${suppliesList(p.id)}
    <h3>${esc(t("sold_in"))}</h3><p>${countries.length ? countries.map(esc).join(", ") : esc(t("unknown"))}</p>
    <h3>${esc(t("details"))}</h3><table class="specs">${rows}</table>`;
  $("#detail").showModal();
}

async function openCompare() {
  const picked = state.compare.map((id) => byId.get(id)).filter(Boolean);
  if (picked.length < 2) return;
  await loadDetails();
  const rows = onlyDifferences ? L.differingRows(picked) : L.SPEC_ROWS;
  const head = picked.map((p) => `<th scope="col">${p.image ? `<img src="${esc(p.image)}" alt="" width="120" height="90">` : ""}<span>${esc(p.name)}</span>
    <button type="button" class="ghost small" data-uncompare="${esc(p.id)}">${esc(t("remove"))}</button></th>`).join("");
  const differing = new Set(L.differingRows(picked));
  const body = rows.map((k) => `<tr class="${differing.has(k) ? "diff" : ""}"><th scope="row">${esc(t(k))}</th>${picked.map((p) => `<td>${esc(value(k, p[k]))}</td>`).join("")}</tr>`).join("");
  const sold = `<tr><th scope="row">${esc(t("sold_in"))}</th>${picked.map((p) => `<td>${esc((p.markets || []).map(countryName).join(", ") || t("unknown"))}</td>`).join("")}</tr>`;
  const supplies = `<tr><th scope="row">${esc(t("supplies"))}</th>${picked.map((p) => `<td>${suppliesList(p.id)}</td>`).join("")}</tr>`;
  $("#compare-body").innerHTML = `<div class="table-scroll"><table class="compare"><thead><tr><th></th>${head}</tr></thead><tbody>${body}${supplies}${sold}</tbody></table></div>`;
  $("#only-diff").checked = onlyDifferences;
  if (!$("#compare").open) $("#compare").showModal();
}

// --- where the data comes from ---------------------------------------------------

// Every source the catalogue reads, with what it gives; the run report says
// how each one answered last time.
const SOURCES = [
  { name: "icecat", url: "https://icecat.biz", label: "Open Icecat", gives: "source_icecat" },
  { name: "epson", url: "https://www.epson.eu", label: "Epson", gives: "source_epson" },
  { name: "lexmark", url: "https://www.lexmark.com", label: "Lexmark", gives: "source_lexmark" },
  { name: "hp.com", url: "https://www.hp.com", label: "HP", gives: "source_hp" },
  { name: "brother", url: "https://www.brother.eu", label: "Brother", gives: "source_brother" },
  { name: "brother-support", url: "https://support.brother.com", label: "Brother support", gives: "source_brother_support" },
  { name: "hp-shop", url: "https://www.hp.com/gb-en/shop", label: "HP shop", gives: "source_hp_shop" },
  { name: "canon-uk", url: "https://www.canon.co.uk", label: "Canon UK", gives: "source_canon_uk" },
  { name: "kyocera", url: "https://www.kyoceradocumentsolutions.eu", label: "Kyocera", gives: "source_kyocera" },
];

const SOURCE_LABELS = { epson: "Epson", lexmark: "Lexmark", "brother-support": "Brother support", "hp-shop": "HP shop", "canon-uk": "Canon UK", kyocera: "Kyocera" };

function renderSources() {
  const report = (data.report && data.report.sources) || {};
  const head = `<tr><th scope="col">${esc(t("source"))}</th><th scope="col">${esc(t("source_gives"))}</th><th scope="col">${esc(t("source_countries"))}</th><th scope="col">${esc(t("source_status"))}</th></tr>`;
  const body = SOURCES.map((s) => {
    const runs = Object.entries(report).filter(([where]) => where.split(":")[0] === s.name);
    const ok = runs.filter(([, r]) => r.status === "ok");
    const found = Math.max(0, ...ok.map(([, r]) => r.found || 0));
    const countries = runs.map(([where]) => where.split(":")[1]).filter((m) => m !== "ALL").map(countryName);
    const status = !runs.length ? t("unknown")
      : ok.length === runs.length ? t("source_ok", { n: formatNumber(found) })
      : ok.length ? t("source_partial", { ok: ok.length, all: runs.length })
      : t("source_refused");
    return `<tr><td><a href="${s.url}" target="_blank" rel="noopener">${esc(s.label)}</a></td><td>${esc(t(s.gives))}</td><td>${esc(countries.join(", ") || t("source_worldwide"))}</td><td>${esc(status)}</td></tr>`;
  });
  $("#sources-table").innerHTML = `<thead>${head}</thead><tbody>${body.join("")}</tbody>`;
}

// --- strings and events -----------------------------------------------------------

function applyStrings() {
  document.documentElement.lang = language();
  document.title = t("title");
  document.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => (el.placeholder = t(el.dataset.i18nPlaceholder)));
  document.querySelectorAll("[data-i18n-label]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nLabel)));
  $("#sort").innerHTML = Object.keys(L.SORTS).map((k) => `<option value="${k}">${esc(t("sort_" + k))}</option>`).join("");
  if (data.report) renderSources();
  if (data.updated) $("#updated").textContent = t("updated", { date: new Intl.DateTimeFormat(language(), { dateStyle: "long" }).format(new Date(data.updated)) });
}

function bind() {
  const panel = $("#filters");
  panel.addEventListener("change", (e) => {
    const el = e.target;
    if (el.dataset.market) el.checked ? state.markets.add(el.dataset.market) : state.markets.delete(el.dataset.market);
    else if (el.dataset.brand) el.checked ? state.brands.add(el.dataset.brand) : state.brands.delete(el.dataset.brand);
    else if (el.dataset.key === "year") state.year = el.value;
    else if (el.type === "checkbox" && el.dataset.key) state[el.dataset.key] = el.checked;
    else return;
    state.page = 1;
    render();
  });
  let ranging;
  panel.addEventListener("input", (e) => {
    const el = e.target;
    if (!el.dataset.range) return;
    clearTimeout(ranging);
    ranging = setTimeout(() => {
      const bounds = [...state[el.dataset.range]];
      bounds[Number(el.dataset.side)] = el.value.trim() === "" ? null : Number(el.value);
      state[el.dataset.range] = bounds;
      state.page = 1;
      render();
    }, 250);
  });
  panel.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const seg = b.closest(".seg");
    if (seg) state[seg.dataset.key] = b.dataset.value;
    else if (b.id === "reset") state = { ...L.emptyState(state.defaultYear), compare: state.compare };
    else return;
    state.page = 1;
    render();
  });
  let typing;
  $("#q").addEventListener("input", (e) => {
    clearTimeout(typing);
    typing = setTimeout(() => { state.q = e.target.value.trim(); state.page = 1; render(); }, 150);
  });
  $("#since").addEventListener("click", () => { state.year = ""; state.page = 1; render(); });
  $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; state.page = 1; render(); });
  $("#active").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.clear === "all") state = { ...L.emptyState(state.defaultYear), compare: state.compare };
    else L.clearFilter(state, b.dataset.clear, b.dataset.value);
    render();
  });
  $("#pager").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-page]");
    if (!b || b.disabled) return;
    state.page = Number(b.dataset.page);
    render({ scroll: true });
  });
  $("#results").addEventListener("click", (e) => {
    const open = e.target.closest("[data-open]");
    if (open) openDetail(open.dataset.open);
  });
  $("#results").addEventListener("change", (e) => {
    const id = e.target.dataset.compare;
    if (!id) return;
    const { list, full } = L.toggleCompare(state.compare, id);
    if (full) { e.target.checked = false; alert(t("compare_max", { n: L.COMPARE_MAX })); return; }
    state.compare = list;
    render();
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-uncompare]");
    if (!b) return;
    state.compare = state.compare.filter((x) => x !== b.dataset.uncompare);
    render();
    if ($("#compare").open) state.compare.length < 2 ? $("#compare").close() : openCompare();
  });
  $("#open-compare").addEventListener("click", openCompare);
  $("#only-diff").addEventListener("change", (e) => { onlyDifferences = e.target.checked; openCompare(); });
  document.querySelectorAll("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
  $("#toggle-filters").addEventListener("click", (e) => {
    const open = $("#filters").classList.toggle("open");
    e.currentTarget.setAttribute("aria-expanded", String(open));
  });
  $("#lang").addEventListener("change", (e) => {
    setLanguage(e.target.value);
    storage.set("lang", e.target.value);
    applyStrings();
    renderPanel();
    render();
  });
}

function start(payload) {
  data = payload;
  all = L.prepare(payload);
  byId = new Map(all.map((p) => [p.id, p]));
  bounds = L.ranges(all);
  state = L.decode(location.hash, L.defaultYear(payload));
  applyStrings();
  renderPanel();
  bind();
  render();
}

setLanguage(pickLanguage(storage.get("lang"), navigator.languages));
$("#lang").innerHTML = Object.entries(LANGUAGES).map(([k, name]) => `<option value="${k}" ${k === language() ? "selected" : ""}>${name}</option>`).join("");
applyStrings();
$("#count").textContent = t("loading");

fetch("printers.json")
  .then((r) => r.json())
  .then(start)
  .catch((error) => {
    console.error(error);
    $("#count").textContent = t("load_error");
  });
