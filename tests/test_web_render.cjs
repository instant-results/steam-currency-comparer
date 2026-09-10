const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {test} = require("node:test");

// Minimal DOM contract for rendering tests; no browser or network required.
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.value = ""; this.checked = false; this.parent = null; this.classList = {toggle() {}}; }
  append(...children) { for (const child of children) this.insertBefore(child, null); }
  insertBefore(child, target) { child.remove(); const index = target ? this.children.indexOf(target) : this.children.length; this.children.splice(index, 0, child); child.parent = this; this.insertions = (this.insertions || 0) + 1; }
  remove() { if(this.parent) { const list = this.parent.children; list.splice(list.indexOf(this), 1); this.parent = null; } }
  replaceChildren(...children) { for (const child of [...this.children]) child.remove(); this.append(...children); }
  addEventListener(name, handler) { (this.listeners ||= {})[name] = handler; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  querySelector() { return new Element("p"); }
}
function setup(selectors = {}) {
  const elements = new Map();
  const get = id => { if(!elements.has(id)) elements.set(id, new Element("div")); return elements.get(id); };
  const context = vm.createContext({Intl, console, document: {getElementById: get, createElement: tag => new Element(tag), querySelectorAll: query => selectors[query] || []}, sessionStorage: {getItem: () => null}, window: {}});
  vm.runInContext(fs.readFileSync("web/app.js", "utf8"), context);
  return {get, run: source => vm.runInContext(source, context)};
}
const game = (id, name) => ({app_id:id, name, comparison:{home_price:{amount:10}, alternatives:[{region:"us", original_amount:5, currency:"USD", rate_to_home:4, amount_in_home:20}], is_fair:true}});
const skipped = (id, category) => ({app_id:id, name:id, skipped:{category, reason:category}});

test("default hides unavailable products while retaining technical failures", () => {
  const {get,run} = setup();
  run(`items = ${JSON.stringify([game("1","Zebra"), skipped("2","no_regional_price"), skipped("3","app_unavailable"), skipped("4","temporary_failure")])}; render();`);
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["1","4"]);
  assert.match(get("row-count").textContent, /2 unavailable hidden/);
  get("show-unavailable").checked = true; run("render()");
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["1","2","3","4"]);
});

test("new alphabetically earlier games append without replacing existing rows", () => {
  const {get,run} = setup(); const first = game("1","Zebra");
  run(`items = ${JSON.stringify([first])}; render();`);
  const row = get("rows").children[0], insertions = get("rows").insertions;
  run(`items = ${JSON.stringify([first])}; render();`);
  assert.equal(get("rows").children[0], row);
  assert.equal(get("rows").insertions, insertions);
  run(`items = ${JSON.stringify([first,game("2","Alpha")])}; render();`);
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["1","2"]);
  assert.equal(get("rows").children[0], row);
});

test("explicit sorting and discovery-order restore reuse rows", () => {
  const {get,run} = setup();
  run(`items = ${JSON.stringify([game("1","Zebra"),game("2","Alpha")])}; render();`);
  const row = get("rows").children[0];
  run('sort = "name"; render();');
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["2","1"]);
  assert.equal(get("rows").children[1], row);
  run('sort = "arrival"; render();');
  assert.equal(get("rows").children[0], row);
});

test("search and unavailable-only filters work together", () => {
  const {get,run} = setup();
  run(`items = ${JSON.stringify([game("1","Zebra"),skipped("missing","app_unavailable"),skipped("error","invalid_response")])}; filter = "skipped"; render();`);
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["error"]);
  get("show-unavailable").checked = true; get("search").value = "missing"; run("render();");
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["missing"]);
});

test("saved request restores profile attribution and retry context", () => {
  const {get,run} = setup();
  assert.equal(run('restoreRequest({request:{identifier:"https://steamcommunity.com/profiles/76561198000000000/",regions:["de"]}})'), true);
  assert.match(get("identifier").value, /76561198000000000/);
  assert.match(get("profile-attribution").textContent, /76561198000000000/);
  assert.equal(run('lastRequest.regions[0]'), "de");
  assert.equal(run('restoreRequest({request:{identifier:"bad",regions:["invalid"]}})'), false);
});

test("sale labels distinguish discounted, regular, and unknown prices", () => {
  const {run} = setup();
  assert.equal(run('saleNote({base_amount:10,discount_percent:50}, "USD").children[0].textContent'), "−50%");
  assert.equal(run('saleNote({base_amount:10,discount_percent:0}, "USD").children[0].textContent'), "Base price · no sale");
  assert.equal(run('saleNote({}, "USD").children[0].textContent'), "Sale details unavailable");
});


test("discount distinctions use known values and include sale versus no sale", () => {
  const {run} = setup();
  const check = values => run(`hasDifferentDiscounts({home_price:{discount_percent:${values[0]}},alternatives:[${values.slice(1).map(v => `{discount_percent:${v}}`).join(",")}]})`);
  assert.equal(check([0,50]), true);
  assert.equal(check([50,50]), false);
  assert.equal(check([null,0]), false);
  assert.equal(check([null,25,50]), true);
  assert.equal(run("hasDifferentDiscounts(null)"), false);
});

test("discount filter and badge distinguish mismatches and preserve search", () => {
  const {get,run} = setup();
  const mismatch = game("1", "Alpha");
  mismatch.comparison.home_price.discount_percent = 0;
  mismatch.comparison.alternatives[0].discount_percent = 50;
  run(`items = ${JSON.stringify([mismatch,game("2","Beta"),skipped("3","temporary_failure")])}; filter = "discounts"; render();`);
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["1"]);
  const badge = get("rows").children[0].children[0].children.at(-1);
  assert.equal(badge.textContent, "Different regional discounts");
  assert.match(badge.title, /PL: 0% off.*US: 50% off/);
  get("search").value = "Beta"; run("render()");
  assert.equal(get("rows").children.length, 0);
});

test("percentage uses cheapest converted final price and handles a zero reference", () => {
  const {get,run} = setup();
  const label = (home, prices) => run(`percentageLabel(percentageDifference({home_price:{amount:${home}},alternatives:${JSON.stringify(prices.map(amount_in_home => ({amount_in_home})))}}))`);
  assert.equal(label(125,[150,100]), "+25.0%");
  assert.equal(label(80,[100,150]), "−20.0%");
  assert.equal(label(100,[100]), "0.0%");
  assert.equal(label(0,[100]), "−100.0%");
  assert.equal(label(10,[0]), "Percentage unavailable");
  assert.equal(label(0,[0]), "Percentage unavailable");
  assert.equal(label(99.999,[100]), "0.0%");
  run(`items = ${JSON.stringify([game("1","Alpha")])}; render();`);
  const difference = get("rows").children[0].children[3];
  assert.equal(difference.textContent, "−10.00 zł");
  assert.equal(difference.children[0].textContent, "−50.0%");
});


test("CSV includes hidden results and rate provenance, with owner opt-in", () => {
  const {run} = setup();
  run(`items = ${JSON.stringify([game("1",'Quoted "game", name'),skipped("2","app_unavailable")])}; currentProfile = "private-profile"; currentRates = [{currency:"USD",rate_to_pln:4,effective_date:"2026-09-09",retrieved_at_utc:"2026-09-10T09:00:00Z",checked_at_utc:"2026-09-10T10:00:00Z",source:"NBP",cache_status:"cache"}];`);
  const csv = run('buildCsv(false, "2026-09-10T11:00:00Z")');
  assert.ok(csv.startsWith("\uFEFF"));
  assert.match(csv, /Quoted ""game"", name/);
  assert.match(csv, /app_unavailable/);
  assert.match(csv, /2026-09-10T09:00:00Z/);
  assert.match(csv, /2026-09-10T10:00:00Z/);
  assert.ok(!csv.includes("wishlist_profile"));
  assert.ok(!csv.includes("private-profile"));
  assert.match(run('buildCsv(true)'), /private-profile/);
  assert.equal(csv.split("\r\n").length, 5);
});

test("CSV protects spreadsheet formulas without converting numeric differences to text", () => {
  const {run} = setup();
  assert.equal(run('csvCell("=HYPERLINK(1)")'), '\"\'=HYPERLINK(1)\"');
  assert.equal(run('csvCell(-20)'), '\"-20\"');
  assert.equal(run('csvCell(null)'), '\"\"');
});


test("artwork loads lazily in a fixed slot and falls back without replacing the row", () => {
  const {get,run} = setup();
  run(`items = ${JSON.stringify([game("413150","Stardew Valley")])}; render();`);
  const row = get("rows").children[0];
  const frame = row.children[0].children[0].children[0];
  const img = frame.children[1];
  assert.equal(img.src, "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/413150/header.jpg");
  assert.equal(img.loading, "lazy");
  assert.equal(img.referrerPolicy, "no-referrer");
  assert.equal(img.width, 120); assert.equal(img.height, 56);
  img.listeners.error();
  assert.equal(img.hidden, true);
  assert.equal(frame.children[0].textContent, "No artwork");
  run("render()");
  assert.equal(get("rows").children[0], row);
  assert.equal(run('gameArtwork("../bad").children.length'), 1);
});


test("percentage sorting differs from absolute sorting and keeps undefined percentages last", () => {
  const {get,run} = setup();
  const a = game("1","Large absolute"); a.comparison.home_price.amount = 120; a.comparison.alternatives[0].amount_in_home = 100;
  const b = game("2","Large percent"); b.comparison.home_price.amount = 15; b.comparison.alternatives[0].amount_in_home = 10;
  const zero = game("3","Zero reference"); zero.comparison.alternatives[0].amount_in_home = 0;
  run(`items = ${JSON.stringify([a,b,zero,skipped("4","temporary_failure")])}; sort = "percentage"; render();`);
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["1","2","3","4"]);
  run('direction = -1; render();');
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["2","1","3","4"]);
  run('sort = "difference"; render();');
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["1","3","2","4"]);
  run('filter = "skipped"; render();');
  assert.equal(get("filter-help").hidden, false);
  run('filter = "all"; render();');
  assert.equal(get("filter-help").hidden, true);
});


test("baseline selection excludes itself and caps alternatives at two", () => {
  const inputs = ["pl","us","de","no","gb"].map(value => { const el = new Element("input"); el.value = value; const label = new Element("label"); el.closest = () => label; return el; });
  const homes = ["pl","us","de","no","gb"].map(value => { const el = new Element("input"); el.value = value; el.checked = value === "pl"; return el; });
  inputs[1].checked = inputs[2].checked = true;
  const {get,run} = setup({'[name="region"]':inputs,'[name="home"]':homes});
  assert.equal(inputs[0].closest().hidden, true);
  assert.equal(inputs[3].disabled, true);
  inputs[2].checked = false; run('updateSelections({target:{name:"region"}})');
  assert.equal(inputs[3].disabled, false);
  homes[0].checked = false; homes[1].checked = true; run("updateSelections()");
  assert.equal(inputs[1].checked, false);
  assert.equal(inputs[1].closest().hidden, true);
  assert.equal(get("compare-legend").textContent, "Compare USD with");
});

test("GBP results and CSV keep their baseline while form selection changes", () => {
  const {get,run} = setup();
  assert.equal(run('restoreRequest({request:{identifier:"profile",home:"gb",regions:["no","pl"]}})'), true);
  const item = game("1","Game"); item.comparison.home_price = {region:"gb",currency:"GBP",amount:10}; item.comparison.alternatives[0].amount_in_home = 8;
  run(`items = ${JSON.stringify([item])}; render();`);
  assert.equal(get("rows").children[0].children[1].textContent, "10.00 GBP");
  assert.match(run('buildCsv(false)'), /baseline_currency/);
  assert.match(run('buildCsv(false)'), /"gb","GBP"/);
  run("updateSelections(); render()");
  assert.equal(get("difference-currency").textContent, "GBP");
  assert.equal(run('restoreRequest({request:{identifier:"profile",home:"gb",regions:["gb"]}})'), false);
  assert.equal(run('restoreRequest({request:{identifier:"profile",home:"gb",regions:["no","pl","us"]}})'), false);
});


function selectionSetup() {
  const codes = ["pl","us","de","no","gb"];
  const inputs = codes.map(value => { const el = new Element("input"); el.value = value; el.name = "region"; el.checked = ["us","de"].includes(value); const label = new Element("label"); el.closest = () => label; return el; });
  const homes = codes.map(value => { const el = new Element("input"); el.value = value; el.name = "home"; el.checked = value === "pl"; return el; });
  const ui = setup({'[name="region"]':inputs,'[name="home"]':homes,'[name="home"], [name="region"]':[...homes,...inputs]});
  return {...ui, inputs, homes,
    chooseHome(value) { const input = homes.find(el => el.value === value); homes.forEach(el => el.checked = el === input); input.listeners.change({target:input}); },
    chooseRegion(value, checked) { const input = inputs.find(el => el.value === value); assert.equal(input.disabled, false); input.checked = checked; input.listeners.change({target:input}); },
    selected() { return inputs.filter(el => el.checked).map(el => el.value); },
    caption() { return ui.get("welcome-currencies").children.map(el => el.textContent).join(" "); }
  };
}

test("baseline conflicts restore original choices across repeated switches", () => {
  const ui = selectionSetup();
  assert.equal(ui.caption(), "PLN ↔ USD ↔ EUR");
  ui.chooseHome("us"); assert.deepEqual(ui.selected(), ["de"]);
  assert.equal(ui.caption(), "USD ↔ EUR");
  ui.chooseHome("de"); assert.deepEqual(ui.selected(), ["us"]);
  ui.chooseHome("no"); assert.deepEqual(ui.selected(), ["us","de"]);
  ui.chooseHome("pl"); assert.deepEqual(ui.selected(), ["us","de"]);
  assert.equal(ui.caption(), "PLN ↔ USD ↔ EUR");
});

test("explicit replacement takes precedence over hidden preferences and retains the limit", () => {
  const ui = selectionSetup();
  ui.chooseHome("us"); ui.chooseRegion("gb", true);
  assert.deepEqual(ui.selected(), ["de","gb"]);
  ui.chooseHome("pl"); assert.deepEqual(ui.selected(), ["de","gb"]);
  assert.equal(ui.inputs.find(el => el.value === "us").disabled, true);
  ui.chooseRegion("de", false); ui.chooseHome("no");
  assert.deepEqual(ui.selected(), ["gb"]);
  ui.chooseRegion("gb", false); ui.chooseHome("pl");
  assert.deepEqual(ui.selected(), []);
  assert.equal(ui.caption(), "PLN");
});

test("busy state preserves hidden preferences and restoration replaces old preferences", () => {
  const ui = selectionSetup(); ui.chooseHome("us");
  ui.run("setBusy(true)");
  assert.ok([...ui.inputs,...ui.homes].every(el => el.disabled));
  ui.run("setBusy(false)"); ui.chooseHome("pl");
  assert.deepEqual(ui.selected(), ["us","de"]);
  assert.equal(ui.run('restoreRequest({request:{identifier:"profile",home:"gb",regions:["no","pl"]}})'), true);
  assert.equal(ui.caption(), "GBP ↔ PLN ↔ NOK");
  ui.chooseHome("no"); assert.deepEqual(ui.selected(), ["pl"]);
  ui.chooseHome("de"); assert.deepEqual(ui.selected(), ["pl","no"]);
});

test("showRates displays publication date with retrieval hour and cache status", () => {
  const {get, run} = setup();
  run('showRates([{currency:"USD",rate_to_pln:4.1,effective_date:"2026-09-09",retrieved_at_utc:"2026-09-10T09:15:00Z",cache_status:"cache"}])');
  const lines = get("rates").children;
  assert.equal(lines.length, 1);
  assert.match(lines[0].children[0].children[0].textContent, /2026-09-09 \d{2}:\d{2} · cache/);
  assert.equal(lines[0].children[1].textContent, "4.10 PLN");
});

test("price tooltips show standalone provenance for baseline and combined calculation for alternatives", () => {
  const {get, run} = setup();
  const item = {
    app_id: "1",
    name: "Test Game",
    source_summary: "cache 1, live 1",
    comparison: {
      home_price: { amount: 10, source: "cache" },
      alternatives: [{ region: "us", original_amount: 5, currency: "USD", rate_to_home: 4, amount_in_home: 20, source: "live" }],
      is_fair: true,
    }
  };
  run(`items = ${JSON.stringify([item])}; render();`);
  const row = get("rows").children[0];
  const titleCell = row.children[0];
  assert.equal(titleCell.children.find(c => c.className === "game-meta"), undefined);
  const homeCell = row.children[1];
  assert.equal(homeCell.title, "cached");
  const altSpan = row.children[2].children[0].children[0];
  assert.equal(altSpan.title, "5.00 USD × 4 · live");
});
