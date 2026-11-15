"use strict";

// The catalogue omits false and empty fields to stay small: a missing flag is "no".
const FLAGS = [
  "available", "new", "duplex_print", "duplex_scan", "ink_tank", "scan", "copy",
  "fax", "adf", "a3", "wifi", "ethernet", "wifi_direct", "airprint", "nfc",
];
const PAGE = 48;
const MARKET_NAMES = {
  BE: "Belgium", NL: "Netherlands", LU: "Luxembourg", FR: "France", DE: "Germany",
  GB: "United Kingdom", CH: "Switzerland", AT: "Austria", IT: "Italy", ES: "Spain",
  US: "United States", PL: "Poland", SE: "Sweden", DK: "Denmark",
};
const SHOWN_MARKETS = ["BE", "NL", "LU", "FR", "DE", "GB", "CH", "AT", "IT", "ES", "US"];

const $ = (sel) => document.querySelector(sel);
const filtersEl = $("#filters");
const state = { q: "", technology: "", color: "", ppm: 0, year: "", markets: new Set(), brands: new Set(), sort: "name" };
FLAGS.forEach((f) => (state[f] = f === "available"));

let all = [];
let matches = [];
let shown = 0;
let newSince = "";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function year(p) {
  return p.release_date ? Number(p.release_date.slice(0, 4)) : null;
}

function prepare(data) {
  // "new" means first seen in the latest week, but not on the very first fill
  const updated = data.updated ? new Date(data.updated) : new Date();
  const week = new Date(updated - 7 * 864e5).toISOString().slice(0, 10);
  newSince = data.started && data.started > week ? data.started : week;
  for (const p of data.printers) {
    p.new = p.first_seen > newSince;
    p.a3 = p.max_paper ? p.max_paper.replace("A", "") <= 3 : false;
    p._text = `${p.brand} ${p.name} ${p.code || ""}`.toLowerCase();
    p._year = year(p);
  }
  return data.printers;
}

function test(p) {
  for (const f of FLAGS) if (state[f] && !p[f]) return false;
  if (state.technology && p.technology !== state.technology) return false;
  if (state.color === "1" && !p.color) return false;
  if (state.color === "0" && p.color) return false;
  if (state.ppm && !((p.ppm_black || 0) >= state.ppm)) return false;
  if (state.year && !(p._year >= Number(state.year))) return false;
  if (state.brands.size && !state.brands.has(p.brand)) return false;
  if (state.markets.size && !(p.markets || []).some((m) => state.markets.has(m))) return false;
  if (state.q) {
    for (const word of state.q.toLowerCase().split(/\s+/)) if (word && !p._text.includes(word)) return false;
  }
  return true;
}

const SORTS = {
  name: (a, b) => a.brand.localeCompare(b.brand) || a.name.localeCompare(b.name),
  newest: (a, b) => (b.release_date || b.first_seen).localeCompare(a.release_date || a.first_seen),
  fastest: (a, b) => (b.ppm_black || 0) - (a.ppm_black || 0),
};

function tags(p) {
  const t = [];
  if (p.new) t.push(["New", "new"]);
  if (!p.available) t.push(["Not on sale", "off"]);
  t.push([p.technology === "laser" ? (p.led ? "LED" : "Laser") : p.technology === "inkjet" ? "Inkjet" : p.technology, ""]);
  if (p.ink_tank) t.push(["Ink tank", ""]);
  t.push([p.color ? "Colour" : "Mono", ""]);
  if (p.duplex_print) t.push(["2-sided print", "good"]);
  if (p.duplex_scan) t.push(["2-sided scan", "good"]);
  if (p.scan) t.push(["Scan", ""]);
  if (p.fax) t.push(["Fax", ""]);
  if (p.adf) t.push(["ADF", ""]);
  if (p.wifi) t.push(["Wi-Fi", ""]);
  if (p.ethernet) t.push(["Ethernet", ""]);
  if (p.airprint) t.push(["AirPrint", ""]);
  if (p.a3) t.push(["A3", ""]);
  return t.map(([label, cls]) => `<span class="tag ${cls}">${esc(label)}</span>`).join("");
}

function card(p) {
  const meta = [];
  if (p.ppm_black) meta.push(`${p.ppm_black} ppm`);
  if (p._year) meta.push(`${p._year}`);
  if (p.markets?.length) meta.push(p.markets.length > 6 ? `${p.markets.length} countries` : p.markets.join(" · "));
  const img = p.image ? `<img src="${esc(p.image)}" alt="" loading="lazy" decoding="async" width="200" height="150">` : "";
  return `<li class="card">
    <div class="img">${img}</div>
    <h3><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)}</a></h3>
    <div class="meta">${meta.map(esc).join("<span aria-hidden>·</span>")}</div>
    <div class="tags">${tags(p)}</div>
  </li>`;
}

function renderMore() {
  const next = matches.slice(shown, shown + PAGE);
  $("#results").insertAdjacentHTML("beforeend", next.map(card).join(""));
  shown += next.length;
}

function apply() {
  matches = all.filter(test).sort(SORTS[state.sort]);
  shown = 0;
  $("#results").innerHTML = matches.length ? "" : '<li class="empty">No printer matches these filters.</li>';
  renderMore();
  $("#count").textContent = `${matches.length.toLocaleString()} of ${all.length.toLocaleString()} printers`;
  $("#ppm-out").textContent = state.ppm ? `≥ ${state.ppm} ppm` : "any";
  writeHash();
}

// --- URL state, so a filtered list can be shared -----------------------------

function writeHash() {
  const h = new URLSearchParams();
  if (state.q) h.set("q", state.q);
  for (const f of FLAGS) if (state[f] !== (f === "available")) h.set(f, state[f] ? "1" : "0");
  for (const k of ["technology", "color", "year"]) if (state[k]) h.set(k, state[k]);
  if (state.ppm) h.set("ppm", state.ppm);
  if (state.sort !== "name") h.set("sort", state.sort);
  if (state.markets.size) h.set("in", [...state.markets].join(","));
  if (state.brands.size) h.set("brand", [...state.brands].join(","));
  const s = h.toString();
  history.replaceState(null, "", s ? `#${s}` : location.pathname);
}

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  state.q = h.get("q") || "";
  for (const f of FLAGS) if (h.has(f)) state[f] = h.get(f) === "1";
  for (const k of ["technology", "color", "year"]) state[k] = h.get(k) || "";
  state.ppm = Number(h.get("ppm")) || 0;
  state.sort = h.get("sort") || "name";
  state.markets = new Set((h.get("in") || "").split(",").filter(Boolean));
  state.brands = new Set((h.get("brand") || "").split(",").filter(Boolean));
}

function syncControls() {
  $("#q").value = state.q;
  for (const f of FLAGS) {
    const el = filtersEl.querySelector(`input[name="${f}"]`);
    if (el) el.checked = state[f];
  }
  filtersEl.querySelectorAll(".seg").forEach((seg) => {
    seg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.value === state[seg.dataset.name]));
  });
  filtersEl.querySelector('[name="ppm"]').value = state.ppm;
  filtersEl.querySelector('[name="year"]').value = state.year;
  document.querySelector('[name="sort"]').value = state.sort;
  document.querySelectorAll("#markets button").forEach((b) => b.classList.toggle("on", state.markets.has(b.dataset.value)));
  document.querySelectorAll("#brands input").forEach((i) => (i.checked = state.brands.has(i.value)));
}

// --- controls built from the data ---------------------------------------------

function buildChoices() {
  const brands = new Map();
  const years = new Set();
  for (const p of all) {
    brands.set(p.brand, (brands.get(p.brand) || 0) + 1);
    if (p._year) years.add(p._year);
  }
  $("#brands").innerHTML = [...brands.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([b, n]) => `<label class="check"><input type="checkbox" value="${esc(b)}"> ${esc(b)} <span class="n">${n}</span></label>`)
    .join("");
  $("#markets").innerHTML = SHOWN_MARKETS.map((m) => `<button data-value="${m}" title="${MARKET_NAMES[m]}">${m}</button>`).join("");
  const yearSelect = filtersEl.querySelector('[name="year"]');
  [...years].sort((a, b) => b - a).forEach((y) => yearSelect.insertAdjacentHTML("beforeend", `<option value="${y}">${y} or later</option>`));
  // a filter with nothing to choose from is noise: hide it until the data has some
  $("#brands").closest("section").hidden = brands.size === 0;
  yearSelect.closest("section").hidden = years.size === 0;
}

function bind() {
  let typing;
  $("#q").addEventListener("input", (e) => {
    clearTimeout(typing);
    typing = setTimeout(() => ((state.q = e.target.value.trim()), apply()), 120);
  });
  filtersEl.addEventListener("change", (e) => {
    const el = e.target;
    if (FLAGS.includes(el.name)) state[el.name] = el.checked;
    else if (el.name === "year") state.year = el.value;
    else if (el.closest("#brands")) el.checked ? state.brands.add(el.value) : state.brands.delete(el.value);
    else return;
    apply();
  });
  filtersEl.querySelector('[name="ppm"]').addEventListener("input", (e) => ((state.ppm = Number(e.target.value)), apply()));
  filtersEl.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const seg = b.closest(".seg");
    if (seg) state[seg.dataset.name] = b.dataset.value;
    else if (b.closest("#markets")) state.markets.has(b.dataset.value) ? state.markets.delete(b.dataset.value) : state.markets.add(b.dataset.value);
    else if (b.id === "reset") { location.hash = ""; readHash(); }
    else return;
    syncControls();
    apply();
  });
  document.querySelector('[name="sort"]').addEventListener("change", (e) => ((state.sort = e.target.value), apply()));
  $("#toggle-filters").addEventListener("click", (e) => {
    const open = filtersEl.classList.toggle("open");
    e.currentTarget.setAttribute("aria-expanded", open);
  });
  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && shown < matches.length) renderMore();
  }, { rootMargin: "800px" }).observe($("#sentinel"));
}

fetch("printers.json")
  .then((r) => r.json())
  .then((data) => {
    all = prepare(data);
    if (data.updated) $("#updated").textContent = `Updated ${data.updated}. New models are checked every week.`;
    buildChoices();
    readHash();
    syncControls();
    bind();
    apply();
  })
  .catch(() => ($("#count").textContent = "The printer list could not be loaded."));
