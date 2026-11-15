// The page's logic, free of the DOM so the tests can drive it directly:
// which filters exist, which printers match, the order, the URL state, pages.

export const PAGE_SIZE = 48;
export const COMPARE_MAX = 4;
// cards in a grid, or one row each: a small photo, the details beside it
export const VIEWS = ["grid", "list"];
// By default the list starts this many years back: Icecat still counts some
// long-gone models as on the market somewhere.
export const DEFAULT_YEARS = 10;

export function defaultYear(data) {
  const year = data && data.updated ? Number(data.updated.slice(0, 4)) : new Date().getFullYear();
  return String(year - DEFAULT_YEARS);
}

// Every filter of the side panel, by group. A flag keeps printers that have
// the feature; a choice keeps one value; a range keeps printers between a
// lowest and a highest value, either side optional (a printer whose sheet
// does not state the value is left out once a bound is set).
export const GROUPS = [
  { id: "class", open: true, filters: [
    { key: "class", type: "choice", values: ["home", "office"], labels: ["class_home", "class_office"], default: "home" },
  ] },
  { id: "availability", open: true, filters: [
    { key: "available", type: "flag", default: true },
    { key: "new", label: "new_week", type: "flag" },
    // its maker's own site still lists it: not a long-gone model Icecat
    // keeps "on the market"
    { key: "maker_listed", label: "listed_by_maker", type: "flag" },
  ] },
  { id: "two_sided", open: true, filters: [
    { key: "duplex_print", type: "flag" },
    { key: "duplex_scan", type: "flag" },
  ] },
  { id: "technology", open: true, filters: [
    { key: "technology", type: "choice", values: ["laser", "inkjet"] },
    { key: "ink_tank", type: "flag" },
  ] },
  { id: "colour", open: true, filters: [
    { key: "color", type: "choice", values: ["1", "0"], labels: ["colour_yes", "colour_no"] },
  ] },
  { id: "functions", open: true, filters: [
    { key: "scan", type: "flag" },
    { key: "copy", type: "flag" },
    { key: "fax", type: "flag" },
    { key: "adf", type: "flag" },
    { key: "borderless", type: "flag" },
  ] },
  { id: "connectivity", open: true, filters: [
    { key: "wifi", type: "flag" },
    { key: "wifi_direct", type: "flag" },
    { key: "ethernet", type: "flag" },
    { key: "usb", type: "flag" },
    { key: "airprint", type: "flag" },
    { key: "mopria", type: "flag" },
    { key: "nfc", type: "flag" },
    { key: "bluetooth", type: "flag" },
  ] },
  { id: "paper", filters: [
    { key: "a3", type: "flag" },
    { key: "paper_input", type: "range", step: 50 },
    { key: "paper_output", type: "range", step: 25 },
    { key: "adf_capacity", type: "range", step: 10 },
    { key: "trays", type: "range", step: 1 },
  ] },
  { id: "controls", filters: [
    { key: "display", type: "flag" },
    { key: "touchscreen", type: "flag" },
  ] },
  { id: "speed", filters: [
    { key: "ppm_black", type: "range", step: 5 },
    { key: "ppm_color", type: "range", step: 5 },
    { key: "first_page_s", type: "range", step: 1 },
  ] },
  { id: "workload", filters: [
    { key: "duty_cycle", type: "range", step: 5000 },
    { key: "monthly_volume", type: "range", step: 500 },
  ] },
  { id: "quality", filters: [
    { key: "print_dpi", type: "range", step: 600 },
    { key: "scan_dpi", type: "range", step: 600 },
  ] },
  { id: "size", filters: [
    { key: "width_mm", type: "range", step: 10 },
    { key: "depth_mm", type: "range", step: 10 },
    { key: "height_mm", type: "range", step: 10 },
    { key: "weight_kg", type: "range", step: 1 },
  ] },
  { id: "energy", filters: [
    { key: "noise_db", type: "range", step: 1 },
    { key: "power_w", type: "range", step: 10 },
    { key: "tec_kwh", type: "range", step: 0.1 },
  ] },
];

export const FILTERS = GROUPS.flatMap((g) => g.filters);
const BY_KEY = Object.fromEntries(FILTERS.map((f) => [f.key, f]));

// The rows of the detail view and the comparison, in reading order.
export const SPEC_ROWS = [
  "brand", "code", "technology", "color", "ink_tank", "duplex_print", "duplex_scan",
  "scan", "copy", "fax", "adf", "adf_capacity", "borderless", "max_paper",
  "paper_input", "paper_output", "trays", "ppm_black", "ppm_color", "ppm_iso",
  "first_page_s", "print_dpi", "scan_dpi", "duty_cycle", "monthly_volume", "wifi",
  "wifi_direct", "ethernet", "usb", "airprint", "mopria", "nfc", "bluetooth",
  "display", "touchscreen", "cartridges", "starter_yield", "width_mm", "depth_mm",
  "height_mm", "weight_kg", "noise_db", "power_w", "tec_kwh", "release_date",
  "added", "end_of_life",
];

// The value of a filter that filters nothing.
export function offValue(f) {
  if (f.type === "flag") return Boolean(f.default);
  if (f.type === "choice") return f.default ?? "";
  return [null, null];
}

export function isOff(f, v) {
  if (f.type === "range") return v[0] === null && v[1] === null;
  return v === offValue(f);
}

export function emptyState(defaultYear = "") {
  const state = { q: "", year: defaultYear, defaultYear, markets: new Set(), brands: new Set(), sort: DEFAULT_SORT, page: 1, compare: [], view: "grid" };
  for (const f of FILTERS) state[f.key] = offValue(f);
  return state;
}

// "new" means first seen in the latest week, but not on the very first fill,
// when every printer was first seen at once.
export function prepare(data) {
  const updated = data.updated ? new Date(data.updated) : new Date();
  const week = new Date(updated - 7 * 864e5).toISOString().slice(0, 10);
  const since = data.started && data.started > week ? data.started : week;
  for (const p of data.printers) {
    p.new = Boolean(p.first_seen && p.first_seen > since);
    p.a3 = Boolean(p.max_paper && Number(p.max_paper.replace(/\D/g, "")) <= 3);
    p._text = `${p.brand} ${p.name} ${p.code || ""}`.toLowerCase();
    // the release date when Icecat has one, else the day it added the model
    p._date = p.release_date || p.added || "";
    p._year = p._date ? Number(p._date.slice(0, 4)) : null;
    p._footprint = p.width_mm && p.depth_mm ? p.width_mm * p.depth_mm : null;
    p.class = p.office ? "office" : "home";
  }
  return data.printers;
}

// The bounds of the range filters, from the values the data holds.
export function ranges(printers) {
  const out = {};
  for (const f of FILTERS) {
    if (f.type !== "range") continue;
    let lo = Infinity, hi = -Infinity;
    for (const p of printers) {
      const v = p[f.key];
      if (typeof v === "number") { if (v < lo) lo = v; if (v > hi) hi = v; }
    }
    if (hi === -Infinity) continue;
    const step = f.step;
    out[f.key] = { min: Math.floor(lo / step) * step, max: Math.ceil(hi / step) * step, step };
  }
  return out;
}

export function matches(p, state) {
  for (const f of FILTERS) {
    const want = state[f.key];
    if (f.type === "flag") {
      if (want && !p[f.key]) return false;
    } else if (f.type === "choice") {
      if (want === "") continue;
      if (f.key === "color") { if (Boolean(p.color) !== (want === "1")) return false; }
      else if (p[f.key] !== want) return false;
    } else {
      const [lo, hi] = want;
      if (lo === null && hi === null) continue;
      const v = p[f.key];
      if (typeof v !== "number") return false;
      if (lo !== null && v < lo) return false;
      if (hi !== null && v > hi) return false;
    }
  }
  // a printer whose sheet gives no date at all is kept: it may well be recent
  if (state.year && p._year !== null && p._year < Number(state.year)) return false;
  if (state.brands.size && !state.brands.has(p.brand)) return false;
  if (state.markets.size && !(p.markets || []).some((m) => state.markets.has(m))) return false;
  if (state.q) {
    for (const word of state.q.toLowerCase().split(/\s+/)) {
      if (word && !p._text.includes(word)) return false;
    }
  }
  return true;
}

const byName = (a, b) => a.brand.localeCompare(b.brand) || a.name.localeCompare(b.name);

// Values sort with the unknowns last whichever the direction, so "fastest"
// does not open on printers whose speed nobody published.
const by = (key, dir) => (a, b) => {
  const x = a[key], y = b[key];
  const xNone = x === null || x === undefined || x === "";
  const yNone = y === null || y === undefined || y === "";
  if (xNone || yNone) return xNone === yNone ? byName(a, b) : xNone ? 1 : -1;
  const order = typeof x === "string" ? x.localeCompare(y) : x - y;
  return dir * order || byName(a, b);
};

export const DEFAULT_SORT = "newest";
export const SORTS = {
  newest: by("_date", -1),
  oldest: by("_date", 1),
  name: byName,
  fastest: by("ppm_black", -1),
  fastest_colour: by("ppm_color", -1),
  most_paper: by("paper_input", -1),
  lightest: by("weight_kg", 1),
  smallest: by("_footprint", 1),
  quietest: by("noise_db", 1),
  greenest: by("tec_kwh", 1),
};

export function search(printers, state) {
  return printers.filter((p) => matches(p, state)).sort(SORTS[state.sort] || SORTS[DEFAULT_SORT]);
}

export function paginate(items, page, size = PAGE_SIZE) {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(1, page), pages);
  return { page: current, pages, items: items.slice((current - 1) * size, current * size) };
}

// Page numbers to show: the ends, the neighbours of the current one, gaps as null.
export function pageNumbers(page, pages) {
  const keep = new Set([1, pages, page - 1, page, page + 1]);
  const out = [];
  for (let n = 1; n <= pages; n++) {
    if (keep.has(n)) out.push(n);
    else if (out[out.length - 1] !== null) out.push(null);
  }
  return out;
}

export function toggleCompare(list, id, max = COMPARE_MAX) {
  if (list.includes(id)) return { list: list.filter((x) => x !== id), full: false };
  if (list.length >= max) return { list, full: true };
  return { list: [...list, id], full: false };
}

// The filters that differ from the defaults, as [key, value] for the chips.
export function activeFilters(state) {
  const out = [];
  if (state.q) out.push(["q", state.q]);
  for (const f of FILTERS) {
    const v = state[f.key];
    if (!isOff(f, v)) out.push([f.key, v]);
  }
  if (state.year !== state.defaultYear) out.push(["year", state.year]);
  for (const m of state.markets) out.push(["market", m]);
  for (const b of state.brands) out.push(["brand", b]);
  return out;
}

export function clearFilter(state, key, value) {
  if (key === "q") state.q = "";
  else if (key === "year") state.year = state.defaultYear;
  else if (key === "market") state.markets.delete(value);
  else if (key === "brand") state.brands.delete(value);
  else if (BY_KEY[key]) state[key] = offValue(BY_KEY[key]);
  state.page = 1;
  return state;
}

// --- the URL: filters, sort, page and comparison, so a view can be shared ---

export function encode(state) {
  const h = new URLSearchParams();
  if (state.q) h.set("q", state.q);
  for (const f of FILTERS) {
    const v = state[f.key];
    if (isOff(f, v)) continue;
    if (f.type === "flag") h.set(f.key, v ? "1" : "0");
    else if (f.type === "choice") h.set(f.key, v || "all");
    else h.set(f.key, `${v[0] ?? ""}~${v[1] ?? ""}`);
  }
  if (state.year !== state.defaultYear) h.set("year", state.year || "all");
  if (state.markets.size) h.set("in", [...state.markets].join(","));
  if (state.brands.size) h.set("brand", [...state.brands].join(","));
  if (state.sort !== DEFAULT_SORT) h.set("sort", state.sort);
  if (state.page > 1) h.set("page", String(state.page));
  if (state.compare.length) h.set("cmp", state.compare.join(","));
  if (state.view !== "grid") h.set("view", state.view);
  return h.toString();
}

export function decode(hash, defaultYear = "") {
  const h = new URLSearchParams(hash.replace(/^#/, ""));
  const state = emptyState(defaultYear);
  state.q = h.get("q") || "";
  for (const f of FILTERS) {
    if (!h.has(f.key)) continue;
    const raw = h.get(f.key);
    if (f.type === "flag") state[f.key] = raw === "1";
    else if (f.type === "choice") state[f.key] = raw === "all" ? "" : f.values.includes(raw) ? raw : offValue(f);
    else state[f.key] = parseRange(raw);
  }
  if (h.has("year")) state.year = h.get("year") === "all" ? "" : h.get("year");
  state.markets = new Set((h.get("in") || "").split(",").filter(Boolean));
  state.brands = new Set((h.get("brand") || "").split(",").filter(Boolean));
  state.sort = SORTS[h.get("sort")] ? h.get("sort") : DEFAULT_SORT;
  state.page = Math.max(1, Number(h.get("page")) || 1);
  state.compare = (h.get("cmp") || "").split(",").filter(Boolean).slice(0, COMPARE_MAX);
  state.view = VIEWS.includes(h.get("view")) ? h.get("view") : "grid";
  return state;
}

// "100~250", "~250" or "100~": either bound may be left out.
export function parseRange(raw) {
  const [lo, hi] = String(raw).split("~");
  const read = (s) => (s === undefined || s.trim() === "" || Number.isNaN(Number(s)) ? null : Number(s));
  return [read(lo), read(hi)];
}

// Rows where the compared printers do not all agree.
export function differingRows(printers, rows = SPEC_ROWS) {
  return rows.filter((key) => new Set(printers.map((p) => JSON.stringify(p[key] ?? null))).size > 1);
}

export function markets(printers) {
  const counts = new Map();
  for (const p of printers) for (const m of p.markets || []) counts.set(m, (counts.get(m) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function brands(printers) {
  const counts = new Map();
  for (const p of printers) counts.set(p.brand, (counts.get(p.brand) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
