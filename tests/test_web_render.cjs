const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {test} = require("node:test");

// Minimal DOM contract for rendering tests; no browser or network required.
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.scrollLeft = 0; this.value = ""; this.checked = false; this.parent = null; this.classList = {toggle() {}}; this.style = {values:{},setProperty(key,value) {this.values[key]=value;},getPropertyValue(key) {return this.values[key];}}; }
  get parentElement() { return this.parent; }
  get firstElementChild() { return this.children[0] || null; }
  append(...children) { for (const child of children) this.insertBefore(child, null); }
  insertBefore(child, target) { child.remove(); const index = target ? this.children.indexOf(target) : this.children.length; this.children.splice(index, 0, child); child.parent = this; this.insertions = (this.insertions || 0) + 1; }
  remove() { if(this.parent) { const list = this.parent.children; list.splice(list.indexOf(this), 1); this.parent = null; } }
  replaceChildren(...children) { for (const child of [...this.children]) child.remove(); this.append(...children); }
  addEventListener(name, handler) { const previous = this.listeners?.[name]; (this.listeners ||= {})[name] = previous ? (...args) => {previous(...args); return handler(...args);} : handler; }
  scrollBy({left}) { this.scrollLeft += left; this.listeners?.scroll?.(); }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  querySelector(selector) { return (this.queries ||= {})[selector] ||= new Element("p"); }
  focus() { this.focused = true; }
}
function setup(selectors = {}, extras = {}, ownedLibraryEnabled = false) {
  const elements = new Map(), documentEvents = new Map();
  const get = id => { if(!elements.has(id)) { const el = new Element("div"); el.id = id; elements.set(id, el); } return elements.get(id); };
  const context = vm.createContext({Intl, console, queueMicrotask, setTimeout, clearTimeout, document: {addEventListener:(name, callback) => documentEvents.set(name, callback),documentElement:{dataset:{ownedLibraryEnabled:String(ownedLibraryEnabled),storefronts:fs.readFileSync("steam_price_polisher/storefronts.json","utf8")}},getElementById: get, createElement: tag => new Element(tag), querySelectorAll: query => selectors[query] || []}, sessionStorage: {getItem: () => null}, window: {}, ...extras});
  vm.runInContext(fs.readFileSync("web/app.js", "utf8"), context);
  return {get, ready: () => { const callback = documentEvents.get("DOMContentLoaded"); documentEvents.delete("DOMContentLoaded"); callback?.(); }, run: source => vm.runInContext(source, context)};
}
const game = (id, name) => ({app_id:id, name, developers:["Test developer"], publishers:["Test publisher", "Co-publisher"], comparison:{home_price:{amount:10}, alternatives:[{region:"us", original_amount:5, currency:"USD", rate_to_home:4, amount_in_home:20}], is_fair:true}});
const skipped = (id, category) => ({app_id:id, name:id, skipped:{category, reason:category}});

// Parse quoted fields, including embedded commas, quotes, and line breaks.
function parseCsv(csv) {
  assert.ok(csv.startsWith("\uFEFF"));
  const text = csv.slice(1), rows = []; let row = [], offset = 0;
  for (const match of text.matchAll(/"((?:[^"]|"")*)"(,|\r\n)/g)) {
    assert.equal(match.index, offset);
    offset += match[0].length;
    row.push(match[1].replaceAll('""', '"'));
    if (match[2] === "\r\n") { rows.push(row); row = []; }
  }
  assert.equal(offset, text.length);
  const headers = rows.shift();
  assert.equal(new Set(headers).size, headers.length);
  for (const values of rows) assert.equal(values.length, headers.length);
  return {headers, rows: rows.map(values => Object.fromEntries(headers.map((name, i) => [name, values[i]])))};
}

const settle = async () => { for (let i = 0; i < 4; i++) await new Promise(setImmediate); };
const librarySnapshot = (items, state = "complete", extra = {}) => ({items, state, total:items.length, home:"pl", rates:[], warnings:[], message:"Checked owned games.", ...extra});
const savedLibrary = (items, extra = {}) => ({items, request:{identifier:"76561198000000000",home:"pl",regions:["us"],order:"name"},
  rates:[],home:"pl",state:"complete", ...extra});
function creatorSetup(savedValues = {}, kind = "developer", loadLibrary = false, initialSnapshots = [], ownedLibraryEnabled = loadLibrary, registryWait = null, allStorefronts = false) {
  const examples = [{app_id:"1",name:"First"},{app_id:"2",name:"Second"},{app_id:"3",name:"Third"}];
  const registry = [{id:"studio",name:"Studio",selector:{kind,name:"Studio"},role:kind,homepage:"https://store.steampowered.com/developer/studio/",icon:"https://avatars.fastly.steamstatic.com/icon.jpg",examples}];
  const storage = new Map(Object.entries(savedValues)), calls = [], snapshots = [...initialSnapshots], searches = [], submissions = [], timers = new Map();
  let timerId = 0;
  const radios = Object.keys(allStorefronts ? JSON.parse(fs.readFileSync("steam_price_polisher/storefronts.json","utf8")) : {pl:1,us:1,de:1,no:1,gb:1}).map(value => { const el = new Element("input"); el.value = value; el.name = "home"; el.checked = value === "pl"; return el; });
  const regions = radios.map(radio => { const el = new Element("input"); el.value = radio.value; el.name = "region"; el.checked = ["us","de"].includes(el.value); const label = new Element("label"); el.closest = () => label; return el; });
  const selectors = {'[name="home"]':radios,'[name="region"]':regions,'[name="region"]:checked':regions.filter(el => el.checked)};
  const libraryFilters = ["all","fair","expensive","discounts","skipped"].map(value => { const el = new Element("button"); el.dataset.filter = value; return el; });
  const librarySorts = ["name","home","difference","percentage"].map(value => { const el = new Element("button"); el.dataset.sort = value; const th = new Element("th"); el.closest = () => th; return el; });
  selectors[".library-filter"] = libraryFilters; selectors[".library-sort"] = librarySorts;
  const testContext = setup(selectors, {
    sessionStorage:{getItem:key => storage.get(key) || null,setItem:(key,value) => storage.set(key,value)},
    setTimeout:callback => { timers.set(++timerId, callback); return timerId; }, clearTimeout:id => timers.delete(id),
    fetch:async (path, options = {}) => {
      calls.push({path,body:options.body ? JSON.parse(options.body) : null, authorization:options.headers?.Authorization});
      let data;
      if (path === "/api/creators") {
        if (registryWait) await registryWait;
        data = {developers:registry.map(c => ({...c,selector:{kind:"developer",name:c.name}})),
          publishers:registry.map(c => ({...c,selector:{kind:"publisher",name:c.name}}))};
      }
      else if (path === "/api/creators/search") {
        data = searches.shift() || {creators: [], exact_matches: []};
        if (data.error) return {ok:false, json:async () => data};
      }
      else if (path === "/api/jobs" || path === "/api/creator-jobs" || path === "/api/library-jobs" || path.endsWith("/currencies")) data = submissions.shift() || {id:(path.endsWith("/currencies") ? "u" : "a").repeat(32),token:(path.endsWith("/currencies") ? "v" : "b").repeat(43)};
      else if (path.endsWith("/cancel")) data = {state:"cancelling"};
      else data = snapshots.shift() || {state:"complete",message:"Checked 3 games.",catalogs:{},items:examples.map(item => game(item.app_id,item.name)),rates:[],warnings:[]};
      return {ok:!data.httpStatus,status:data.httpStatus || 200,json:async () => data};
    }
  }, ownedLibraryEnabled);
  selectors['[data-storefront]'] = [...testContext.get("baseline-options").children,...testContext.get("comparison-options").children];
  if (loadLibrary) {
    testContext.get("library-wishlist-order").value = "name";
    testContext.run(fs.readFileSync("web/library.js", "utf8"));
  }
  testContext.run(fs.readFileSync("web/creators.js", "utf8"));
  const get = id => testContext.get(id.replace(/^creators-/, kind + "s-").replace(/^creator-/, kind + "-"));
  const group = () => get("creator-groups").children[0];
  const body = () => group().children[1].children[0].children[0].children[2];
  return {...testContext,get,calls,storage,snapshots,searches,submissions,radios,regions,timers,group,body,libraryFilters,librarySorts};
}

const wishlistSnapshot = (state = "complete", extra = {}) => ({...librarySnapshot([game("1", "Example game")], state), profile:"example", ...extra});
const savedWishlist = (identifier = "76561198000000000") => JSON.stringify({id:"w".repeat(32),token:"t".repeat(43),
  request:{identifier,home:"gb",regions:["us"],order:"date_added"}});

test("a fresh page automatically compares the example once using current selections", async () => {
  const ctx = creatorSetup();
  ctx.radios.forEach(el => el.checked = el.value === "gb");
  ctx.regions.forEach(el => el.checked = el.value === "no");
  ctx.get("wishlist-order").value = "name";
  ctx.snapshots.push(wishlistSnapshot());
  assert.equal(ctx.calls.length, 0);
  ctx.ready(); ctx.ready(); await settle();
  const starts = ctx.calls.filter(call => call.path === "/api/jobs");
  assert.equal(starts.length, 1);
  assert.deepEqual(starts[0].body, {identifier:"example",home:"gb",regions:["no"],order:"name"});
  assert.equal(ctx.get("identifier").value, "");
  assert.equal(ctx.get("results-title").textContent, "Example price comparison");
  assert.match(ctx.get("profile-attribution").textContent, /Curated example wishlist/);
  assert.equal(ctx.run("comparisonCoordinator.busy"), false);
  assert.doesNotMatch(fs.readFileSync("web/index.html", "utf8"), /id="demo"|Try an example comparison|or run an example/);
});

test("restored personal and example jobs take priority over automatic loading", async () => {
  for (const identifier of ["76561198000000000", "example"]) {
    const ctx = creatorSetup({"polisher-job":savedWishlist(identifier)}, "developer", false,
      [wishlistSnapshot("complete", {profile:identifier,home:"gb"})]);
    ctx.ready(); await settle();
    assert.equal(ctx.calls.filter(call => call.path.startsWith("/api/jobs/")).length, 1);
    assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 0);
    assert.equal(ctx.run("lastRequest.home"), "gb");
    assert.equal(ctx.run("items[0].name"), "Example game");
    assert.equal(ctx.get("identifier").value, identifier === "example" ? "" : identifier);
  }
});

test("an expired saved wishlist retains its retry context without starting an example", async () => {
  const ctx = creatorSetup({"polisher-job":savedWishlist()}, "developer", false,
    [{httpStatus:404,error:"Comparison expired"}]);
  ctx.ready(); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 0);
  assert.equal(ctx.get("status-badge").textContent, "COMPARISON EXPIRED");
  assert.equal(ctx.run("lastRequest.identifier"), "76561198000000000");
  assert.equal(ctx.run("comparisonCoordinator.busy"), false);
});

test("malformed saved wishlist state does not prevent the fresh example", async () => {
  for (const saved of ["{", JSON.stringify({id:"bad",token:"bad"})]) {
    const ctx = creatorSetup({"polisher-job":saved});
    ctx.snapshots.push(wishlistSnapshot()); ctx.ready(); await settle();
    assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 1);
  }
});

test("typing a profile dismisses a queued example even if the input is later cleared", async () => {
  const ctx = creatorSetup();
  ctx.run('comparisonCoordinator.setBusy("developer", true)');
  ctx.ready(); await settle();
  ctx.get("identifier").value = "76561198000000000";
  ctx.get("identifier").listeners.input(); ctx.get("identifier").value = "";
  ctx.run('comparisonCoordinator.setBusy("developer", false)'); await settle();
  assert.equal(ctx.calls.length, 0);
});

test("a user comparison submitted before startup finishes cannot be replaced by the example", async () => {
  const ctx = creatorSetup();
  ctx.snapshots.push(wishlistSnapshot("complete", {profile:"76561198000000000"}));
  ctx.get("identifier").value = "76561198000000000";
  ctx.get("wishlist-order").value = "priority";
  ctx.get("compare-form").listeners.submit({preventDefault(){}});
  ctx.ready(); await settle();
  assert.deepEqual(ctx.calls.filter(call => call.path === "/api/jobs").map(call => call.body.identifier), ["76561198000000000"]);
});

test("hidden saved catalog work reconnects before the example and releases it on completion", async () => {
  let release;
  const registryWait = new Promise(resolve => { release = resolve; });
  const saved = {home:"pl",regions:["us"],request:{mode:"products"},
    job:{id:"c".repeat(32),token:"d".repeat(43)},catalogs:[],results:[]};
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(saved)}, "developer", false, [], false, registryWait);
  ctx.ready(); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 0);
  assert.equal(ctx.get("analyze").disabled, true);
  ctx.snapshots.push({state:"running",message:"Checking catalog",items:[],rates:[],warnings:[]});
  release(); await settle();
  assert.equal(ctx.calls.filter(call => call.path.startsWith("/api/jobs/")).length, 1);
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 0);
  ctx.snapshots.push({state:"complete",message:"Done",items:[],rates:[],warnings:[]}, wishlistSnapshot());
  [...ctx.timers.values()][0](); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 1);
  assert.equal(ctx.run("comparisonCoordinator.busy"), false);
});

test("a restored active catalog keeps the example pending until the wishlist is opened", async () => {
  const ctx = creatorSetup({"polisher-active-tab":"publisher"});
  ctx.ready(); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/creator-jobs").length, 1);
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 0);
  ctx.snapshots.push(wishlistSnapshot());
  ctx.get("wishlist-tab").listeners.click(); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 1);
});

test("queued catalog auto-loading is cancelled when leaving the catalog tab", async () => {
  const ctx = creatorSetup();
  ctx.run("setBusy(true)");
  ctx.get("creators-tab").listeners.click(); await settle();
  ctx.get("wishlist-tab").listeners.click();
  ctx.run("setBusy(false)"); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/creator-jobs").length, 0);
});

test("failed example startup releases controls and requires an explicit retry", async () => {
  const ctx = creatorSetup();
  ctx.run('let exampleAttempts = 0; request = async () => { exampleAttempts++; throw new Error("Steam unavailable"); }');
  ctx.ready(); await settle();
  assert.equal(ctx.get("status-badge").textContent, "COULD NOT START");
  assert.equal(ctx.get("retry").hidden, false);
  assert.equal(ctx.get("analyze").disabled, false);
  ctx.run('comparisonCoordinator.wake()'); await settle();
  assert.equal(ctx.get("status-badge").textContent, "COULD NOT START");
  assert.equal(ctx.run("exampleAttempts"), 1);
  ctx.run('request = async path => path === "/api/jobs" ? {id:"a".repeat(32),token:"b".repeat(43)} : '+JSON.stringify(wishlistSnapshot()));
  ctx.get("retry").listeners.click(); await settle();
  assert.equal(ctx.get("status-badge").textContent, "COMPLETE");
});

test("duplicate starts cannot clear results or replace an active wishlist", async () => {
  const ctx = creatorSetup();
  ctx.snapshots.push(wishlistSnapshot("running")); ctx.ready(); await settle();
  await ctx.run('start({identifier:"76561198000000000",home:"pl",regions:["us"]})');
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 1);
  assert.equal(ctx.run("lastRequest.identifier"), "example");
  assert.equal(ctx.run("items[0].name"), "Example game");
});

test("cancelling an automatic example releases the worker without restarting it", async () => {
  const ctx = creatorSetup();
  ctx.snapshots.push(wishlistSnapshot("running")); ctx.ready(); await settle();
  await ctx.get("cancel").listeners.click();
  ctx.snapshots.push(wishlistSnapshot("cancelled", {items:[]}));
  [...ctx.timers.values()][0](); await settle();
  assert.equal(ctx.run("comparisonCoordinator.busy"), false);
  assert.equal(ctx.get("status-badge").textContent, "CANCELLED");
  assert.equal(ctx.get("retry").hidden, false);
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 1);
  assert.equal(ctx.calls.filter(call => call.path.endsWith("/cancel")).length, 1);
  ctx.snapshots.push(wishlistSnapshot("complete", {profile:"76561198000000000"}));
  await ctx.run('start({identifier:"76561198000000000",home:"pl",regions:["us"]})'); await settle();
  assert.equal(ctx.run("lastRequest.identifier"), "76561198000000000");
});

test("automatic examples wait for an enabled restored library but ignore disabled library state", async () => {
  const saved = savedLibrary([], {state:"running",job:{id:"a".repeat(32),token:"b".repeat(43)}});
  for (const enabled of [true, false]) {
    const ctx = creatorSetup({"polisher-library-job":JSON.stringify(saved)}, "developer", true,
      enabled ? [librarySnapshot([], "running")] : [wishlistSnapshot()], enabled);
    ctx.ready(); await settle();
    assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, enabled ? 0 : 1);
    if (enabled) {
      ctx.snapshots.push(librarySnapshot([]), wishlistSnapshot());
      [...ctx.timers.values()][0](); await settle();
      assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 1);
    } else assert.equal(ctx.storage.get("polisher-library-job"), JSON.stringify(saved));
  }
});

test("malformed hidden catalog storage does not block restoration of the active tab", async () => {
  const ctx = creatorSetup({"polisher-developer-job":"{", "polisher-active-tab":"publisher"});
  ctx.ready(); await settle();
  assert.equal(ctx.get("publishers-tab").attributes["aria-selected"], "true");
  assert.equal(ctx.calls.filter(call => call.path === "/api/creator-jobs").length, 1);
  assert.equal(ctx.calls.filter(call => call.path === "/api/jobs").length, 0);
});

test("unavailable session storage still permits automatic loading", async () => {
  const calls = [];
  const ctx = setup({}, {sessionStorage:{getItem(){throw new Error("Unavailable")},setItem(){throw new Error("Unavailable")},removeItem(){throw new Error("Unavailable")}},
    fetch:async path => { calls.push(path); return {ok:true,json:async () => path === "/api/jobs" ? {id:"a".repeat(32),token:"b".repeat(43)} : wishlistSnapshot()}; }});
  ctx.ready(); await settle();
  assert.equal(calls.filter(path => path === "/api/jobs").length, 1);
  assert.equal(ctx.get("status-badge").textContent, "COMPLETE");
});

test("developer search adds a dynamic catalog while retaining featured rows and restores its catalog", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  const retained = ctx.body().children[0];
  const creator = {id:"developer-"+"d".repeat(24),name:"ConcernedApe",selector:{kind:"developer",name:"ConcernedApe"}};
  ctx.searches.push({creators:[],exact_matches:[creator]});
  ctx.get("creator-query").value = "ConcernedApe";
  await ctx.get("creator-search-form").listeners.submit({preventDefault(){}});
  const button = ctx.get("creator-search-results").children[0].children[1].children[0];
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{[creator.id]:{
    products:[{app_id:"4",name:"Stardew Valley"}],next_start:12,has_more:true,total:15}},
    items:[game("4","Stardew Valley")],rates:[],warnings:[]});
  button.listeners.click(); await settle();
  assert.equal(ctx.get("creator-groups").children.length,2);
  assert.equal(ctx.body().children[0],retained);
  assert.equal(button.textContent,"Added");
  assert.equal(button.disabled,true);
  const submitted = ctx.calls.filter(c => c.path === "/api/creator-jobs").at(-1).body;
  assert.deepEqual(submitted.selector,creator.selector);
  assert.equal(submitted.creator_id,creator.id);
  const restored = creatorSetup({"polisher-developer-job":ctx.storage.get("polisher-developer-job")});
  restored.get("creators-tab").listeners.click(); await settle();
  assert.equal(restored.get("creator-groups").children.length,2);
  const dynamic = restored.get("creator-groups").children[1];
  assert.equal(dynamic.children[1].children[0].children[0].children[2].children.length,1);
  dynamic.children[1].children[1].children[1].listeners.click(); await settle();
  assert.equal(restored.calls.filter(c => c.path === "/api/creator-jobs").at(-1).body.start,12);
});

test("creator search distinguishes empty matches, failures, and exact-name roles", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  ctx.get("creator-query").value = "A & B";
  ctx.searches.push({creators:[],exact_matches:[{id:"developer-"+"a".repeat(24),name:"A & B",selector:{kind:"developer",name:"A & B"}}]});
  await ctx.get("creator-search-form").listeners.submit({preventDefault(){}});
  assert.match(ctx.get("creator-search-status").textContent,/Choose a developer/);
  assert.equal(ctx.get("creator-search-results").children[0].children[0].children[0].textContent,"A & B");
  ctx.run("setBusy(true); window.creatorPane.refreshControls();");
  assert.equal(ctx.get("creator-search-results").children[0].children[1].children[0].disabled,true);
  ctx.run("setBusy(false);");
  ctx.searches.push({error:"Steam is unavailable"});
  await ctx.get("creator-search-form").listeners.submit({preventDefault(){}});
  assert.equal(ctx.get("creator-search-status").textContent,"Steam is unavailable");
  assert.equal(ctx.get("creator-search-results").children.length,0);
  assert.equal(ctx.get("creator-search-submit").disabled,false);
  ctx.searches.push({creators:[],exact_matches:[]});
  await ctx.get("creator-search-form").listeners.submit({preventDefault(){}});
  assert.match(ctx.get("creator-search-status").textContent,/No matching developers/);
});

test("developer search ignores homepage and publisher options and deduplicates names", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  const developer = {id:"developer-"+"a".repeat(24),name:"Valve",selector:{kind:"developer",name:"Valve"}};
  const publisher = {id:"publisher-"+"b".repeat(24),name:"Valve",selector:{kind:"publisher",name:"Valve"}};
  ctx.searches.push({creators:[{id:"steam-123",name:"Valve",selector:{kind:"homepage",clan_id:"123"}}],exact_matches:[developer,developer,publisher]});
  ctx.get("creator-query").value = "Valve";
  await ctx.get("creator-search-form").listeners.submit({preventDefault(){}});
  const rows = ctx.get("creator-search-results").children;
  assert.equal(rows.length,1);
  assert.equal(rows[0].children[0].children[0].textContent,"Valve");
  const buttons = rows[0].children[1].children;
  assert.deepEqual(buttons.map(button => button.textContent),["Add & compare"]);
  buttons[0].listeners.click(); await settle();
  assert.deepEqual(ctx.calls.filter(call => call.path === "/api/creator-jobs").at(-1).body.selector,developer.selector);
  assert.equal(buttons[0].disabled,true);
});

test("saved dynamic creators cannot inject links and preserve exact-name selectors", async () => {
  const good = {id:"developer-"+"a".repeat(24),name:"A & B",homepage:"javascript:alert(1)",icon:"https://evil.test",selector:{kind:"developer",name:"A & B"}};
  const saved = {home:"pl",regions:["us"],request:{mode:"featured"},creators:[good,
    {id:"evil",name:"Bad",selector:{kind:"homepage",clan_id:"1/../secret"}}],catalogs:[],results:[]};
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.get("creator-groups").children.length,2);
  const identity = ctx.get("creator-groups").children[1].children[0].children[0];
  assert.equal(identity.children[0].src,"/steam-logo.svg");
  assert.equal(identity.children[1].children[0].href,"https://store.steampowered.com/search/?developer=A%20%26%20B");
});

test("an empty added catalog preserves the exchange rates for existing comparisons", async () => {
  const saved = {home:"pl",regions:["us"],request:{mode:"featured"},
    rates:[{currency:"USD",rate_to_pln:4,cache_status:"cache"}],catalogs:[],results:[]};
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  ctx.get("creators-tab").listeners.click(); await settle();
  ctx.snapshots.push({state:"complete",message:"No products",catalogs:{studio:{products:[],next_start:12,has_more:false,total:0}},items:[],rates:[],warnings:[]});
  ctx.group().children[1].children[1].children[1].listeners.click(); await settle();
  assert.equal(JSON.parse(ctx.storage.get("polisher-developer-job")).rates[0].rate_to_pln,4);
});

test("creator tab automatically compares examples and preserves wishlist results and baseline", async () => {
  const ctx = creatorSetup();
  ctx.run(`items = ${JSON.stringify([game("99","My wishlist")])}; resultHome = "gb";`);
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.get("wishlist-panel").hidden, true);
  assert.equal(ctx.get("compare-form").hidden, true);
  assert.equal(ctx.body().children.length, 3);
  assert.equal(ctx.body().children[0].children[1].textContent, "10.00 zł");
  assert.equal(ctx.calls.find(call => call.path === "/api/creator-jobs").body.mode, "products");
  assert.equal(ctx.run("items[0].app_id"), "99");
  assert.equal(ctx.run("resultHome"), "gb");
  ctx.get("wishlist-tab").listeners.click();
  assert.equal(ctx.get("compare-form").hidden, false);
  assert.equal(ctx.get("creators-panel").hidden, true);
  assert.ok(ctx.storage.has("polisher-developer-job"));
});

test("expanded catalogs retain soundtracks, avoid duplicate examples, and refresh displayed IDs", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  const count = () => ctx.group().children[1].children[1].children[0].textContent;
  assert.match(count(), /featured games/);
  const retainedRow = ctx.body().children[0];
  ctx.snapshots.push({state:"complete",message:"Checked catalog.",catalogs:{studio:{products:[{app_id:"1",name:"First"},{app_id:"4",name:"Original Soundtrack"}],next_start:12,has_more:true,total:30}},items:[game("4","Original Soundtrack")],rates:[],warnings:[]});
  ctx.group().children[1].children[1].children[1].listeners.click(); await settle();
  assert.deepEqual(ctx.body().children.map(row => row.dataset.appId), ["1","2","3","4"]);
  assert.equal(ctx.body().children[0], retainedRow);
  const expanded = ctx.calls.filter(call => call.path === "/api/creator-jobs").at(-1).body;
  assert.equal(expanded.mode, "catalog"); assert.equal(expanded.start, 0);
  assert.doesNotMatch(count(), /featured games/);
  ctx.radios.forEach(el => el.checked = el.value === "gb");
  ctx.get("creators-refresh").listeners.click(); await settle();
  const refreshed = ctx.calls.filter(call => call.path === "/api/creator-jobs").at(-1).body;
  assert.equal(refreshed.mode, "products"); assert.deepEqual(refreshed.app_ids, ["1","2","3","4"]);
  assert.equal(refreshed.home, "gb");
  assert.equal(JSON.parse(ctx.storage.get("polisher-developer-job")).catalogs[0].nextStart, 12);
  assert.equal(JSON.parse(ctx.storage.get("polisher-developer-job")).catalogs[0].discoveryHome, "pl");
  assert.equal(ctx.body().children.length, 4);
  assert.equal(count(), "4 products shown");
  const saved = JSON.parse(ctx.storage.get("polisher-developer-job"));
  delete saved.catalogs[0].expanded; // Older saved sessions have no explicit expansion flag.
  const restored = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  restored.get("creators-tab").listeners.click(); await settle();
  assert.equal(restored.group().children[1].children[1].children[0].textContent, "4 products shown");
});

test("creator catalogs hide free products but retain paid soundtracks and unavailable products", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  const zero = game("5", "Free game"); zero.comparison.home_price.amount = 0;
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{studio:{products:[
    {app_id:"4",name:"Demo"},{app_id:"5",name:"Free game"},{app_id:"6",name:"Paid soundtrack"},{app_id:"7",name:"Coming soon"}
  ],next_start:12,has_more:true,total:30}},items:[
    {...skipped("4","no_regional_price"),is_free:true},zero,game("6","Paid soundtrack"),skipped("7","no_regional_price")
  ],rates:[],warnings:[]});
  ctx.group().children[1].children[1].children[1].listeners.click(); await settle();
  assert.deepEqual(ctx.body().children.map(row => row.dataset.appId), ["1","2","3","6","7"]);
  ctx.get("creators-refresh").listeners.click(); await settle();
  assert.deepEqual(ctx.calls.filter(call => call.path === "/api/creator-jobs").at(-1).body.app_ids,["1","2","3","6","7"]);
  const restored = creatorSetup({"polisher-developer-job":ctx.storage.get("polisher-developer-job")});
  restored.get("creators-tab").listeners.click(); await settle();
  assert.deepEqual(restored.body().children.map(row => row.dataset.appId),["1","2","3","6","7"]);
});

test("free-only catalog pages still advance to later paid products", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{studio:{products:[{app_id:"4",name:"Demo"}],next_start:12,has_more:true,total:24}},items:[{...skipped("4","no_regional_price"),is_free:true}],rates:[],warnings:[]});
  const more = ctx.group().children[1].children[1].children[1];
  more.listeners.click(); await settle();
  assert.equal(ctx.body().children.length,3);
  assert.equal(more.hidden,false);
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{studio:{products:[{app_id:"5",name:"Paid game"}],next_start:24,has_more:false,total:24}},items:[game("5","Paid game")],rates:[],warnings:[]});
  more.listeners.click(); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/creator-jobs").at(-1).body.start,12);
  assert.equal(ctx.body().children.length,4);
  assert.equal(more.hidden,true);
});

test("creator icons fall back to Steam and terminal catalogs hide Load more", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  const img = ctx.group().children[0].children[0].children[0]; img.listeners.error();
  assert.equal(img.src, "/steam-logo.svg");
  assert.equal(img.referrerPolicy, "no-referrer");
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{studio:{products:[],next_start:12,has_more:false,total:3}},items:[],rates:[],warnings:[]});
  ctx.group().children[1].children[1].children[1].listeners.click(); await settle();
  assert.equal(ctx.group().children[1].children[1].children[1].hidden, true);
});

test("creator averages weight products equally and update after loading more", async () => {
  const comparison = (id, home, usd, eur, fair = false) => ({app_id:id,name:id,developers:[],publishers:[],comparison:{
    home_price:{amount:home},alternatives:[{region:"us",currency:"USD",original_amount:usd,rate_to_home:1,amount_in_home:usd},
      {region:"de",currency:"EUR",original_amount:eur,rate_to_home:1,amount_in_home:eur}],is_fair:fair}});
  const saved = {home:"pl",regions:["us","de"],request:{mode:"featured"},rates:[],
    catalogs:[{id:"studio",products:[{app_id:"1",name:"First"},{app_id:"2",name:"Second"},{app_id:"3",name:"Unavailable"}],nextStart:0,hasMore:true,total:null}],
    results:[comparison("1",120,100,150),comparison("2",20,10,0),skipped("3","no_regional_price")]};
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  ctx.get("creators-tab").listeners.click(); await settle();
  const statistics = () => ctx.group().children[0].children[1];
  assert.equal(statistics().children[0].children[0].textContent,"Average PLN vs USD");
  assert.equal(statistics().children[0].children[1].textContent,"+60.0%");
  assert.equal(statistics().children[0].children[3].children[1].textContent,"+60.0%");
  assert.equal(statistics().children[0].children[2].textContent,"2 products compared");
  assert.equal(statistics().children[1].children[1].textContent,"−20.0%");
  assert.equal(statistics().children[1].children[3].children[1].textContent,"−20.0%");
  assert.equal(statistics().children[1].children[2].textContent,"1 product compared");
  assert.match(statistics().children[2].textContent,/2 of 3 compared · 0 cheaper\/equal · 2 pricier · 1 uncompared/);
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{studio:{products:[{app_id:"1",name:"First"},{app_id:"4",name:"Soundtrack"},{app_id:"5",name:"Demo"}],next_start:12,has_more:false,total:5}},
    items:[comparison("4",30,60,40,true),{...skipped("5","no_regional_price"),is_free:true}],rates:[],warnings:[]});
  ctx.group().children[1].children[1].children[1].listeners.click(); await settle();
  assert.equal(statistics().children[0].children[1].textContent,"+23.3%");
  assert.equal(statistics().children[0].children[3].children[1].textContent,"+20.0%");
  assert.equal(statistics().children[1].children[1].textContent,"−22.5%");
  assert.equal(statistics().children[1].children[3].children[1].textContent,"−22.5%");
  assert.match(statistics().children[2].textContent,/3 of 4 compared · 1 cheaper\/equal · 2 pricier · 1 uncompared/);
  ctx.radios.forEach(el => el.checked = el.value === "gb");
  assert.equal(statistics().children[0].children[0].textContent,"Average PLN vs USD");
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{},items:[comparison("1",40,100,50,true)],rates:[],warnings:[]});
  ctx.get("creators-refresh").listeners.click(); await settle();
  assert.equal(statistics().children[0].children[0].textContent,"Average GBP vs USD");
  assert.equal(statistics().children[0].children[1].textContent,"−60.0%");
  assert.equal(statistics().children[0].children[3].children[1].textContent,"−60.0%");
  assert.match(statistics().children[2].textContent,/1 of 4 compared.*3 pending/);
});

test("creator statistics show no average while results are pending or reference prices are zero", async () => {
  const ctx = creatorSetup();
  ctx.snapshots.push({state:"running",message:"Checking",catalogs:{},items:[],rates:[],warnings:[]});
  ctx.get("creators-tab").listeners.click(); await settle();
  let stats = ctx.group().children[0].children[1];
  assert.equal(stats.children[0].children[1].textContent,"—");
  assert.equal(stats.children[0].children[3].children[1].textContent,"—");
  assert.match(stats.children[2].textContent,/0 of 3 compared.*3 pending/);
  const zero = game("1","First"); zero.comparison.alternatives[0].amount_in_home = 0;
  ctx.snapshots.push({state:"complete",message:"Done",catalogs:{},items:[zero,skipped("2","app_unavailable")],rates:[],warnings:[]});
  [...ctx.timers.values()][0](); await settle();
  stats = ctx.group().children[0].children[1];
  assert.equal(stats.children[0].children[1].textContent,"—");
  assert.equal(stats.children[0].children[2].textContent,"0 products compared");
  assert.equal(stats.children[0].children[3].children[1].textContent,"—");
  assert.match(stats.children[2].textContent,/1 of 3 compared.*1 uncompared · 1 pending/);
});

test("restored creator results keep expanded products and running jobs reconnect", async () => {
  const saved = {home:"gb",regions:["us"],request:{mode:"catalog"},job:{id:"a".repeat(32),token:"b".repeat(43)},
    catalogs:[{id:"studio",products:[{app_id:"4",name:"Soundtrack"}],nextStart:12,hasMore:true,total:30}],
    results:[game("4","Soundtrack")],rates:[]};
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.body().children.length, 1);
  assert.equal(ctx.body().children[0].children[1].textContent, "10.00 GBP");
  assert.ok(ctx.radios.find(el => el.value === "gb").checked);
  assert.ok(ctx.calls.some(call => call.path.startsWith("/api/jobs/")));
  assert.ok(!ctx.calls.some(call => call.path === "/api/creator-jobs"));
});

test("creator comparisons wait behind a wishlist and lock shared controls while running", async () => {
  const ctx = creatorSetup(); ctx.run("setBusy(true);");
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.ok(!ctx.calls.some(call => call.path === "/api/creator-jobs"));
  assert.match(ctx.get("creators-progress").textContent, /Waiting for the current comparison/);
  ctx.run("setBusy(false);");
  ctx.snapshots.push({state:"running",message:"Checking",catalogs:{},items:[],rates:[],warnings:[]});
  await settle();
  assert.equal(ctx.run("window.creatorPane.busy"), true);
  assert.ok(ctx.radios.every(el => el.disabled));
  assert.equal(ctx.get("analyze").disabled, true);
  assert.equal(ctx.get("retry").disabled, true);
  ctx.run('items = [{app_id:"existing-wishlist"}];');
  await ctx.run('start({identifier:"example",regions:["us"],home:"pl"})');
  assert.equal(ctx.run('items[0].app_id'), "existing-wishlist");
  ctx.get("creators-cancel").listeners.click(); await settle();
  assert.ok(ctx.calls.some(call => call.path.endsWith("/cancel")));
});

test("developer and publisher tabs retain independent searches, groups, prices, and saved cursors", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  const retained = ctx.body().children[0];
  const developer = {id:"developer-"+"d".repeat(24),name:"Valve",selector:{kind:"developer",name:"Valve"}};
  ctx.searches.push({creators:[],exact_matches:[developer]});
  ctx.get("creator-query").value = "Valve";
  await ctx.get("creator-search-form").listeners.submit({preventDefault(){}});
  assert.equal(ctx.calls.filter(call => call.path === "/api/creators/search").at(-1).body.role,"developer");
  ctx.get("creator-search-results").children[0].children[1].children[0].listeners.click(); await settle();
  const developerState = ctx.storage.get("polisher-developer-job");
  ctx.get("publishers-tab").listeners.click(); await settle();
  assert.equal(ctx.get("developers-panel").hidden,true);
  assert.equal(ctx.get("publishers-panel").hidden,false);
  assert.equal(ctx.get("publisher-groups").children.length,1);
  assert.equal(ctx.get("publisher-search-results").children.length,0);
  const publisher = {id:"publisher-"+"e".repeat(24),name:"Valve",selector:{kind:"publisher",name:"Valve"}};
  ctx.searches.push({creators:[],exact_matches:[publisher,developer]});
  ctx.get("publisher-query").value = "Valve";
  await ctx.get("publisher-search-form").listeners.submit({preventDefault(){}});
  assert.equal(ctx.calls.filter(call => call.path === "/api/creators/search").at(-1).body.role,"publisher");
  assert.equal(ctx.get("publisher-search-results").children.length,1);
  ctx.get("publisher-search-results").children[0].children[1].children[0].listeners.click(); await settle();
  assert.deepEqual(ctx.calls.filter(call => call.path === "/api/creator-jobs").at(-1).body.selector,publisher.selector);
  assert.equal(ctx.storage.get("polisher-developer-job"),developerState);
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.body().children[0],retained);
  assert.equal(ctx.get("creator-groups").children.length,2);
  assert.equal(ctx.get("creator-query").value,"Valve");
  assert.equal(ctx.get("creator-search-results").children[0].children[1].children[0].textContent,"Added");
  const restored = creatorSetup(Object.fromEntries(ctx.storage));
  restored.get("creators-tab").listeners.click(); await settle();
  restored.get("publishers-tab").listeners.click(); await settle();
  assert.equal(restored.get("creator-groups").children.length,2);
  assert.equal(restored.get("publisher-groups").children.length,2);
  assert.equal(restored.calls.filter(call => call.path === "/api/creator-jobs").length,0);
});

test("a running developer job blocks publisher additions and can be cancelled after switching back", async () => {
  const ctx = creatorSetup();
  ctx.snapshots.push({state:"running",message:"Checking",catalogs:{},items:[],rates:[],warnings:[]});
  ctx.get("creators-tab").listeners.click(); await settle();
  ctx.get("publishers-tab").listeners.click(); await settle();
  assert.equal(ctx.calls.filter(call => call.path === "/api/creator-jobs").length,1);
  assert.equal(ctx.get("publishers-refresh").disabled,true);
  assert.equal(ctx.get("analyze").disabled,true);
  assert.equal(ctx.run("window.creatorPane.busy"),true);
  ctx.get("creators-tab").listeners.click(); await settle();
  await ctx.get("creators-cancel").listeners.click();
  assert.ok(ctx.calls.some(call => call.path.endsWith("/cancel")));
});

test("legacy selections migrate by credit role and homepage catalogs are discarded", async () => {
  const developer = {id:"developer-"+"a".repeat(24),name:"Dev",selector:{kind:"developer",name:"Dev"}};
  const publisher = {id:"publisher-"+"b".repeat(24),name:"Pub",selector:{kind:"publisher",name:"Pub"}};
  const homepage = {id:"steam-123",name:"Home",selector:{kind:"homepage",clan_id:"123"}};
  const saved = {home:"pl",regions:["us"],request:{mode:"catalog"},creators:[developer,publisher,homepage],
    catalogs:[{id:developer.id,products:[{app_id:"4",name:"Dev game"}],nextStart:25,total:40,hasMore:true},
      {id:publisher.id,products:[{app_id:"5",name:"Pub game"}],nextStart:25,total:40,hasMore:true},
      {id:homepage.id,products:[{app_id:"6",name:"Homepage game"}],nextStart:12,total:20,hasMore:true}],results:[]};
  const ctx = creatorSetup({"polisher-creator-job":JSON.stringify(saved)});
  ctx.get("creators-tab").listeners.click(); await settle();
  ctx.get("publishers-tab").listeners.click(); await settle();
  const dev = JSON.parse(ctx.storage.get("polisher-developer-job"));
  const pub = JSON.parse(ctx.storage.get("polisher-publisher-job"));
  assert.equal(dev.creators.some(c => c.id === developer.id),true);
  assert.equal(pub.creators.some(c => c.id === publisher.id),true);
  assert.equal(dev.creators.some(c => c.selector.kind !== "developer"),false);
  assert.equal(pub.creators.some(c => c.selector.kind !== "publisher"),false);
  assert.equal(dev.catalogs.find(c => c.id === developer.id).nextStart,25);
  assert.equal(pub.catalogs.find(c => c.id === publisher.id).nextStart,25);
  assert.equal(dev.catalogs.some(c => c.id === homepage.id),false);
});

test("changed publisher defaults replace retired examples while preserving user catalogs", async () => {
  const retired = {id:"publisher-"+"a".repeat(24),name:"Self publisher",selector:{kind:"publisher",name:"Self publisher"},examples:[{app_id:"9",name:"Old game"}]};
  const selected = {id:"publisher-"+"b".repeat(24),name:"Selected publisher",selector:{kind:"publisher",name:"Selected publisher"},examples:[]};
  const saved = {home:"pl",regions:["us"],request:{mode:"products"},creators:[retired,selected],
    catalogs:[{id:selected.id,products:[{app_id:"4",name:"Selected game"}],nextStart:25,total:40,hasMore:true}],results:[]};
  const ctx = creatorSetup({"polisher-publisher-job":JSON.stringify(saved)},"publisher");
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.get("creator-groups").children.length,2);
  const updated = JSON.parse(ctx.storage.get("polisher-publisher-job"));
  assert.equal(updated.creators.some(c => c.id === retired.id),false);
  assert.equal(updated.creators.some(c => c.id === selected.id),true);
  assert.equal(updated.catalogs.find(c => c.id === selected.id).nextStart,25);
  assert.deepEqual(updated.featuredIds,["studio"]);
  assert.deepEqual(ctx.calls.filter(call => call.path === "/api/creator-jobs").at(-1).body.app_ids,["1","2","3","4"]);
  const restored = creatorSetup({"polisher-publisher-job":JSON.stringify(updated)},"publisher");
  restored.get("creators-tab").listeners.click(); await settle();
  assert.equal(restored.calls.filter(call => call.path === "/api/creator-jobs").length,0);
});

test("all twenty catalog selections survive restoration", async () => {
  const catalogs = Array.from({length:19}, (_,i) => ({id:"developer-"+(i+1).toString(16).padStart(24,"0"),
    name:"Developer "+i,selector:{kind:"developer",name:"Developer "+i}}));
  const saved = {home:"pl",regions:["us"],request:{mode:"products"},
    creators:[{id:"studio",name:"Studio",selector:{kind:"developer",name:"Studio"}},...catalogs],catalogs:[],results:[]};
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.get("creator-groups").children.length,20);
  assert.equal(JSON.parse(ctx.storage.get("polisher-developer-job")).creators.at(-1).id,catalogs.at(-1).id);
});

test("four-tab keyboard navigation places library after wishlist and wraps with Home and End", async () => {
  const ctx = creatorSetup({}, "developer", true);
  ctx.get("wishlist-tab").listeners.keydown({key:"ArrowLeft",preventDefault(){}}); await settle();
  assert.equal(ctx.get("publishers-tab").attributes["aria-selected"],"true");
  assert.equal(ctx.get("publishers-tab").focused,true);
  ctx.get("publishers-tab").listeners.keydown({key:"Home",preventDefault(){}});
  assert.equal(ctx.get("wishlist-tab").attributes["aria-selected"],"true");
  ctx.get("wishlist-tab").listeners.keydown({key:"ArrowRight",preventDefault(){}}); await settle();
  assert.equal(ctx.get("library-tab").attributes["aria-selected"],"true");
  assert.equal(ctx.get("library-tab").focused,true);
  assert.equal(ctx.get("library-panel").hidden,false);
  assert.equal(ctx.get("library-compare-form").hidden,false);
  assert.equal(ctx.get("compare-form").hidden,true);
  ctx.get("library-tab").listeners.keydown({key:"ArrowRight",preventDefault(){}}); await settle();
  assert.equal(ctx.get("creators-tab").attributes["aria-selected"],"true");
  ctx.get("creators-tab").listeners.keydown({key:"End",preventDefault(){}}); await settle();
  assert.equal(ctx.get("publishers-tab").attributes["aria-selected"],"true");
});

test("deferred library remains hidden and dormant even with a saved active library job", async () => {
  const saved = JSON.stringify(savedLibrary([game("1","Saved library")], {
    state:"running",job:{id:"a".repeat(32),token:"b".repeat(43)},
    request:{identifier:"76561198000000000",home:"gb",regions:["us"],order:"name"}}));
  const ctx = creatorSetup({"polisher-library-job":saved,"polisher-active-tab":"library"},"developer",true,[],false);
  await settle();
  assert.equal(ctx.get("library-tab").hidden,true);
  assert.equal(ctx.get("library-panel").hidden,true);
  assert.equal(ctx.get("library-compare-form").hidden,true);
  assert.equal(ctx.get("wishlist-panel").hidden,false);
  assert.equal(ctx.get("compare-form").hidden,false);
  assert.equal(ctx.get("wishlist-tab").attributes["aria-selected"],"true");
  assert.equal(ctx.run("window.libraryPane"),undefined);
  assert.equal(ctx.calls.length,0);
  assert.equal(ctx.timers.size,0);
  assert.equal(ctx.storage.get("polisher-library-job"),saved);
  assert.equal(ctx.radios.find(el => el.checked).value,"pl");
  assert.equal(ctx.get("analyze").disabled,false);
});

test("default keyboard navigation skips the hidden library and preserves three visible tabs", async () => {
  const ctx = creatorSetup();
  ctx.get("wishlist-tab").listeners.keydown({key:"ArrowRight",preventDefault(){}}); await settle();
  assert.equal(ctx.get("creators-tab").attributes["aria-selected"],"true");
  assert.equal(ctx.get("creators-tab").focused,true);
  assert.equal(ctx.get("library-tab").listeners,undefined);
  ctx.get("creators-tab").listeners.keydown({key:"End",preventDefault(){}}); await settle();
  assert.equal(ctx.get("publishers-tab").attributes["aria-selected"],"true");
  ctx.get("publishers-tab").listeners.keydown({key:"ArrowRight",preventDefault(){}});
  assert.equal(ctx.get("wishlist-tab").attributes["aria-selected"],"true");
  ctx.get("wishlist-tab").listeners.keydown({key:"ArrowLeft",preventDefault(){}});
  assert.equal(ctx.get("publishers-tab").attributes["aria-selected"],"true");
  ctx.get("publishers-tab").listeners.keydown({key:"Home",preventDefault(){}});
  assert.equal(ctx.get("wishlist-tab").attributes["aria-selected"],"true");
});

test("owned library submits independently and uses wishlist row credits and price columns", async () => {
  const ctx = creatorSetup({}, "developer", true);
  ctx.run(`items = ${JSON.stringify([game("99","Wishlist")])}; resultHome = "gb";`);
  ctx.get("library-tab").listeners.click();
  ctx.get("library-identifier").value = "76561198000000000";
  ctx.snapshots.push(librarySnapshot([game("1","Library")], "running"));
  ctx.get("library-compare-form").listeners.submit({preventDefault(){}}); await settle();
  assert.equal(ctx.calls.find(call => call.path === "/api/library-jobs").body.order,"name");
  assert.equal(ctx.get("library-rows").children[0].children.length,4);
  assert.equal(ctx.get("library-rows").children[0].children[0].children[1].children[1].textContent,"Test developer");
  assert.equal(ctx.run("items[0].app_id"),"99");
  assert.equal(ctx.run("resultHome"),"gb");
  assert.equal(ctx.run("window.libraryPane.busy"),true);
  assert.ok(ctx.radios.every(el => el.disabled));
  ctx.get("wishlist-tab").listeners.click();
  assert.equal(ctx.get("analyze").disabled,true);
  ctx.get("library-tab").listeners.click();
  await ctx.get("library-cancel").listeners.click();
  assert.ok(ctx.calls.some(call => call.path.endsWith("/cancel")));
  assert.equal(ctx.get("library-cancel").disabled,true);
});

test("library results restore with independent filters, sorting, rows, and opt-in attribution", async () => {
  const data = [game("1","Zebra"),game("2","Alpha"),skipped("3","app_unavailable"),skipped("4","request_failure")];
  const ctx = creatorSetup({"polisher-active-tab":"library", "polisher-library-job":JSON.stringify(savedLibrary(data))}, "developer", true);
  assert.equal(ctx.get("library-tab").attributes["aria-selected"],"true");
  assert.equal(ctx.get("library-identifier").value,"76561198000000000");
  assert.deepEqual(ctx.get("library-rows").children.map(row => row.dataset.appId),["1","2","4"]);
  const retained = ctx.get("library-rows").children[0];
  ctx.librarySorts[0].listeners.click();
  assert.deepEqual(ctx.get("library-rows").children.map(row => row.dataset.appId),["4","2","1"]);
  ctx.get("library-arrival-order").listeners.click();
  assert.equal(ctx.get("library-rows").children[0],retained);
  ctx.libraryFilters.at(-1).listeners.click();
  assert.deepEqual(ctx.get("library-rows").children.map(row => row.dataset.appId),["4"]);
  ctx.get("library-show-unavailable").checked = true; ctx.get("library-show-unavailable").listeners.change();
  assert.deepEqual(ctx.get("library-rows").children.map(row => row.dataset.appId),["3","4"]);
  ctx.get("library-search").value = "3"; ctx.get("library-search").listeners.input();
  assert.deepEqual(ctx.get("library-rows").children.map(row => row.dataset.appId),["3"]);
  assert.equal(ctx.calls.length,0);
  assert.equal(JSON.parse(ctx.storage.get("polisher-library-job")).filter,"skipped");
  assert.equal(ctx.get("library-export-owner").checked,false);
});

test("running library restoration reconnects once and locks catalog auto-start and wishlist", async () => {
  const saved = savedLibrary([], {state:"running",job:{id:"a".repeat(32),token:"b".repeat(43)}});
  const ctx = creatorSetup({"polisher-library-job":JSON.stringify(saved)}, "developer", true,
    [librarySnapshot([game("1","First")],"running")]);
  assert.equal(ctx.run("window.libraryPane.busy"),true);
  assert.equal(ctx.get("analyze").disabled,true);
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.run("window.libraryPane.busy"),true);
  assert.equal(ctx.calls.filter(call => /^\/api\/jobs\//.test(call.path)).length,1);
  assert.equal(ctx.calls.filter(call => call.path === "/api/library-jobs").length,0);
  assert.equal(ctx.calls.filter(call => call.path === "/api/creator-jobs").length,0);
});

test("library job prevents catalog starts until its completion and cancellation stays on owning tab", async () => {
  const ctx = creatorSetup({}, "developer", true);
  ctx.get("library-identifier").value = "76561198000000000";
  ctx.snapshots.push(librarySnapshot([],"running"));
  ctx.get("library-compare-form").listeners.submit({preventDefault(){}}); await settle();
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.calls.some(call => call.path === "/api/creator-jobs"),false);
  assert.equal(ctx.get("creators-refresh").disabled,true);
  assert.equal(ctx.get("creators-cancel").hidden,true);
  ctx.get("library-tab").listeners.click();
  assert.equal(ctx.get("library-cancel").hidden,false);
});

test("library handles empty and missing credentials and releases shared locks", async () => {
  for (const snapshot of [librarySnapshot([]),librarySnapshot([],"failed",{error:"Set STEAM_WEB_API_KEY."})]) {
    const ctx = creatorSetup({}, "developer", true);
    ctx.get("library-identifier").value = "76561198000000000";
    ctx.snapshots.push(snapshot);
    ctx.get("library-compare-form").listeners.submit({preventDefault(){}}); await settle();
    assert.equal(ctx.run("window.libraryPane.busy"),false);
    assert.equal(ctx.get("library-export-csv").disabled,true);
    assert.equal(ctx.get("library-retry").hidden,false);
    assert.equal(JSON.parse(ctx.storage.get("polisher-library-job")).job,null);
    assert.equal(ctx.get("library-notice").hidden,!snapshot.error);
  }
});

test("expired library reconnect retains checked results and clears only its access token", async () => {
  const saved = savedLibrary([game("1","Saved game")],{state:"running",job:{id:"a".repeat(32),token:"b".repeat(43)}});
  const ctx = creatorSetup({"polisher-library-job":JSON.stringify(saved)},"developer",true,[{httpStatus:404,error:"This comparison has expired."}]);
  ctx.run(`items = ${JSON.stringify([game("99","Wishlist")])}`);
  await settle();
  assert.equal(ctx.run("window.libraryPane.busy"),false);
  assert.equal(ctx.get("library-rows").children.length,1);
  assert.equal(ctx.get("library-status-badge").textContent,"COMPARISON EXPIRED");
  assert.equal(ctx.get("library-retry").hidden,false);
  assert.equal(JSON.parse(ctx.storage.get("polisher-library-job")).job,null);
  assert.equal(ctx.run("items[0].app_id"),"99");
});

test("active restored library restores its currencies and prevents wishlist rates overwriting it", async () => {
  const saved = savedLibrary([game("1","Saved game")],{request:{identifier:"76561198000000000",home:"gb",regions:["us"],order:"steam"},home:"gb",
    rates:[{currency:"GBP",rate_to_pln:5,cache_status:"cache"}]});
  const ctx = creatorSetup({"polisher-library-job":JSON.stringify(saved),"polisher-active-tab":"library"},"developer",true);
  assert.equal(ctx.radios.find(el => el.checked).value,"gb");
  assert.deepEqual(ctx.regions.filter(el => el.checked).map(el => el.value),["us"]);
  assert.equal(ctx.get("library-wishlist-order").value,"steam");
  assert.equal(ctx.get("library-home-heading").textContent,"PRICE IN UNITED KINGDOM");
  ctx.run("showRates([{currency:'USD',rate_to_pln:4,cache_status:'live'}])");
  assert.equal(ctx.get("rates").children[0].children[1].textContent,"5.00 PLN");
});

test("library CSV has identical shared headers, distinct source fields, and profile opt-in", () => {
  const ctx = setup();
  const item = game("1","Owned game");
  const rows = [];
  for (const includeOwner of [false,true]) {
    const data = parseCsv(ctx.run(`buildPriceCsv(${JSON.stringify([item])}, "pl", [], {sourceTab:"library",regions:["us"],order:"name",profile:"76561198000000000",includeOwner:${includeOwner}})`));
    const wishlist = parseCsv(ctx.run("buildPriceCsv([], 'pl', [])"));
    assert.deepEqual(data.headers,wishlist.headers);
    assert.equal(data.rows[0].source_tab,"library");
    assert.equal(data.rows[0].library_profile,includeOwner ? "76561198000000000" : "");
    assert.equal(data.rows[0].library_loading_order,"name");
    assert.equal(data.rows[0].wishlist_profile,"");
    assert.equal(data.rows[0].wishlist_loading_order,"");
    assert.equal(data.rows[0].catalog_role,"");
    assert.equal(data.rows[0].developers,"Test developer");
  }
});

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
  assert.equal(run('restoreRequest({request:{identifier:"https://steamcommunity.com/profiles/76561198000000000/",regions:["de"],order:"date_added"}})'), true);
  assert.match(get("identifier").value, /76561198000000000/);
  assert.match(get("profile-attribution").textContent, /76561198000000000/);
  assert.equal(run('lastRequest.regions[0]'), "de");
  assert.equal(run('lastRequest.order'), "date_added");
  assert.equal(get("wishlist-order").value, "date_added");
  assert.equal(run('restoreRequest({request:{identifier:"bad",regions:["invalid"]}})'), false);
  assert.equal(run('restoreRequest({request:{identifier:"profile",regions:["de"],order:"random"}})'), false);
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
  assert.ok(csv.includes("wishlist_profile"));
  assert.ok(parseCsv(csv).rows.every(row => row.wishlist_profile === ""));
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
  const gameTitle = row.children[0].children[0].children[1];
  const img = frame.children[1];
  assert.equal(frame.title, "Steam App ID: 413150");
  assert.equal(gameTitle.title, "Steam App ID: 413150");
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

test("wishlist rows show both compact credit lists beneath artwork without changing price columns", () => {
  const {get, run} = setup();
  const item = game("413150", "Stardew Valley");
  item.developers = ["First developer", "Second developer"];
  item.publishers = ['<script>unsafe text</script>', "Co-publisher"];
  run(`items = ${JSON.stringify([item])}; demoMode = true; render();`);
  const row = get("rows").children[0], title = row.children[0];
  assert.equal(row.children.length, 4);
  assert.equal(title.children[0].className, "game-name");
  const credits = title.children[1];
  assert.equal(credits.tagName, "small");
  assert.equal(credits.className, "catalog-credit wishlist-credits");
  assert.deepEqual(credits.children.map(child => [child.className, child.textContent]), [
    ["credit-label", "Developer: "], ["credit-names", "First developer, Second developer"],
    ["credit-label", "Publisher: "], ["credit-names", "<script>unsafe text</script>, Co-publisher"]
  ]);
  assert.equal(credits.children[3].children.length, 0); // Untrusted credits stay text.
  assert.match(row.children[1].className, /\bprice\b/);
  assert.match(row.children[3].className, /difference fair/);
  const csvBefore = run('buildCsv(false, "2026-10-13T11:00:00Z")');
  run('render(); sort = "name"; render(); sort = "arrival"; render();');
  assert.equal(get("rows").children[0], row);
  assert.equal(run('buildCsv(false, "2026-10-13T11:00:00Z")'), csvBefore);
  assert.equal(run(`comparisonRow(${JSON.stringify(item)}, "pl").children[0].children.length`), 1);
});

test("wishlist credits handle older, missing, skipped, and pending metadata and update when learned", () => {
  const {get, run} = setup();
  const old = game("1", "Old saved game"); delete old.developers; delete old.publishers;
  const missing = {...skipped("2", "temporary_failure"), developers:[], publishers:["Known publisher"]};
  const pending = {app_id:"3",name:"Pending game",pending:true};
  run(`items = ${JSON.stringify([old,missing,pending])}; render();`);
  const credits = row => { const spans = row.children[0].children[1].children; return [spans[0].textContent + spans[1].textContent, spans[2].textContent + spans[3].textContent]; };
  assert.deepEqual(get("rows").children.map(credits), [
    ["Developer: Unavailable", "Publisher: Unavailable"],
    ["Developer: Unavailable", "Publisher: Known publisher"],
    ["Developer: Loading…", "Publisher: Loading…"]
  ]);
  assert.equal(get("rows").children[1].children.length, 4);
  assert.match(get("rows").children[1].children[1].className, /pinned-home/);
  run('items[0].developers = ["Learned developer"]; items[0].publishers = ["Learned publisher"]; render();');
  assert.deepEqual(credits(get("rows").children[0]), ["Developer: Learned developer", "Publisher: Learned publisher"]);
  get("search").value = "old"; run("render();");
  assert.deepEqual(get("rows").children.map(row => row.dataset.appId), ["1"]);
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


test("baseline selection excludes itself without blocking additional alternatives", () => {
  const inputs = ["pl","us","de","no","gb"].map(value => { const el = new Element("input"); el.value = value; const label = new Element("label"); el.closest = () => label; return el; });
  const homes = ["pl","us","de","no","gb"].map(value => { const el = new Element("input"); el.value = value; el.checked = value === "pl"; return el; });
  inputs[1].checked = inputs[2].checked = true;
  const {get,run} = setup({'[name="region"]':inputs,'[name="home"]':homes});
  assert.equal(inputs[0].closest().hidden, true);
  assert.equal(inputs[3].disabled, false);
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
  assert.equal(run('restoreRequest({request:{identifier:"profile",home:"gb",regions:["no","pl","us"]}})'), true);
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

test("explicit replacement takes precedence over hidden preferences without a two-currency cap", () => {
  const ui = selectionSetup();
  ui.chooseHome("us"); ui.chooseRegion("gb", true);
  assert.deepEqual(ui.selected(), ["de","gb"]);
  ui.chooseHome("pl"); assert.deepEqual(ui.selected(), ["de","gb"]);
  assert.equal(ui.inputs.find(el => el.value === "us").disabled, false);
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
  assert.equal(ui.get("wishlist-order").disabled, true);
  ui.run("setBusy(false)"); ui.chooseHome("pl");
  assert.equal(ui.get("wishlist-order").disabled, false);
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

for (const kind of ["developer", "publisher"]) test(`${kind} credits switch between compact text and an aligned column without requests`, async () => {
  const ctx = creatorSetup(); ctx.get(kind + "s-tab").listeners.click(); await settle();
  const get = id => ctx.get(id.replace(/^creators-/, kind + "s-").replace(/^creator-/, kind + "-"));
  const group = () => get("creator-groups").children[0];
  const table = () => group().children[1].children[0].children[0];
  const row = () => table().children[2].children[0];
  const credit = kind === "developer" ? "Test publisher, Co-publisher" : "Test developer";
  const label = kind === "developer" ? "Publisher" : "Developer";
  assert.equal(row().children[0].children.at(-1).textContent, `${label}: ${credit}`);
  assert.equal(row().children.length,4);
  const calls = ctx.calls.length;
  get("creator-show-credits").checked = true; get("creator-show-credits").listeners.change();
  assert.equal(row().children.length,5); assert.equal(row().children[1].textContent,credit);
  assert.equal(row().children[0].children.length,1);
  assert.equal(table().children[0].children.length,5);
  assert.equal(table().children[1].children[0].children[1].children[0].children[0].textContent,label.toUpperCase());
  assert.equal(get("creator-columns-colgroup").children.length,5);
  assert.equal(get("creator-columns-head").children[0].children.length,5);
  assert.match(row().children[3].className,/catalog-foreign-price/);
  assert.equal(ctx.calls.length,calls);
  const restored = creatorSetup(Object.fromEntries(ctx.storage),kind);
  restored.get("creators-tab").listeners.click(); await settle();
  assert.equal(restored.get("creator-show-credits").checked,true);
  assert.equal(restored.body().children[0].children[1].textContent,credit);
  get("creator-show-credits").checked = false; get("creator-show-credits").listeners.change();
  assert.equal(row().children.length,4);
  assert.equal(row().children[0].children.at(-1).textContent,`${label}: ${credit}`);
  assert.equal(table().children[0].children.length,4);
  assert.equal(get("creator-columns-head").children[0].children.length,4);
});

test("credit columns retain separate pinned cells for pending and uncompared prices", async () => {
  const ctx = creatorSetup();
  ctx.snapshots.push({state:"running",message:"Checking…",catalogs:{},items:[skipped("1","app_unavailable")],rates:[],warnings:[]});
  ctx.get("creators-tab").listeners.click(); await settle();
  ctx.get("creator-show-credits").checked = true; ctx.get("creator-show-credits").listeners.change();
  const rows = ctx.body().children;
  assert.equal(rows[0].children[1].textContent,"Unavailable");
  assert.equal(rows[1].children[1].textContent,"Loading…");
  assert.equal(rows[0].children.length,5);
  assert.equal(rows[1].children.length,5);
  assert.match(rows[0].children[2].className,/pinned-home/);
  assert.match(rows[1].children[4].className,/pinned-difference/);
  assert.equal(ctx.get("creator-columns-head").children[0].children.length,5);
});

test("saved catalog prices without credits refresh once and retain loaded products", async () => {
  const old = {home:"pl",regions:["us","de"],request:{mode:"featured"},rates:[],
    catalogs:[{id:"studio",products:[{app_id:"1",name:"First"}],nextStart:25,hasMore:true,total:40}],
    results:[game("1","First")]};
  delete old.results[0].developers; delete old.results[0].publishers;
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(old)});
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.deepEqual(ctx.calls.find(c => c.path === "/api/creator-jobs").body.app_ids,["1"]);
  const saved = JSON.parse(ctx.storage.get("polisher-developer-job"));
  assert.equal(saved.catalogs[0].nextStart,25);
  const restored = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  restored.get("creators-tab").listeners.click(); await settle();
  assert.equal(restored.calls.filter(c => c.path === "/api/creator-jobs").length,0);
});

for (const kind of ["developer", "publisher"]) test(`${kind} CSV always includes both credits and only its own checked catalog data`, async () => {
  const ctx = creatorSetup({}, kind);
  assert.match(fs.readFileSync("web/index.html", "utf8"), new RegExp(`id="${kind}s-export"[^>]*disabled`));
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.get("creators-export").disabled, false);
  ctx.run('downloadCsv = (contents, filename) => {window.exportContents = contents; window.exportFilename = filename;}');
  ctx.get("creators-export").listeners.click();
  const csv = ctx.run('window.exportContents');
  assert.ok(csv.startsWith("\uFEFF"));
  assert.match(csv, /"catalog_role","catalog_name","developers","publishers"/);
  assert.match(csv, new RegExp(`"${kind}","Studio","Test developer","Test publisher; Co-publisher"`));
  assert.match(csv, /"PLN"/); assert.match(csv, /"USD"/);
  assert.equal(csv.trim().split("\r\n").length, 7); // Three games, two observed prices each.
  assert.equal(ctx.run('window.exportFilename'), `steam-${kind}s-comparison.csv`);
  assert.ok(parseCsv(csv).rows.every(row => row.wishlist_profile === ""));
  assert.doesNotMatch(csv, /token/);
  ctx.get("creator-show-credits").checked = true; ctx.get("creator-show-credits").listeners.change();
  ctx.get("creators-export").listeners.click();
  const withoutTime = text => text.replace(/\d{4}-\d{2}-\d{2}T[^"]+/g, "TIME");
  assert.equal(withoutTime(ctx.run('window.exportContents')), withoutTime(csv));
});

test("catalog CSV keeps saved baseline, escaped credits, and uncompared rows", async () => {
  const item = game("1", "A game"); item.publishers = ['=unsafe, "publisher"'];
  const saved = {home:"gb",regions:["us"],request:{mode:"products"},rates:[],
    catalogs:[{id:"studio",products:[{app_id:"1",name:"A game"},{app_id:"2",name:"Missing"}],nextStart:0,hasMore:true,total:null}],
    results:[item,skipped("2","no_regional_price")]};
  const ctx = creatorSetup({"polisher-developer-job":JSON.stringify(saved)});
  ctx.get("creators-tab").listeners.click(); await settle();
  ctx.radios.forEach(el => el.checked = el.value === "pl");
  ctx.run('downloadCsv = contents => {window.exportContents = contents;}');
  ctx.get("creators-export").listeners.click();
  const csv = ctx.run('window.exportContents');
  assert.match(csv, /"gb","GBP"/);
  assert.match(csv, /"'=unsafe, ""publisher"""/);
  assert.match(csv, /"no_regional_price"/);
  assert.equal(csv.trim().split("\r\n").length, 4);
});

test("all tabs and owner settings have identical CSV headers, including empty exports", async () => {
  const wishlist = setup();
  wishlist.run(`items = ${JSON.stringify([game("1", "Wishlist game")])}; currentProfile = "PRIVATE_PROFILE"; job = {token:"PRIVATE_TOKEN"};`);
  const plain = parseCsv(wishlist.run("buildCsv(false)"));
  const attributed = parseCsv(wishlist.run("buildCsv(true)"));
  assert.deepEqual(plain.headers, attributed.headers);
  assert.equal(plain.rows[0].wishlist_profile, "");
  assert.equal(attributed.rows[0].wishlist_profile, "PRIVATE_PROFILE");
  assert.equal(plain.rows[0].developers, "Test developer");
  assert.equal(plain.rows[0].publishers, "Test publisher; Co-publisher");
  assert.equal(plain.rows[0].catalog_name, "");
  assert.equal(plain.rows[0].catalog_role, "");
  assert.equal(plain.rows[0].source_tab, "wishlist");
  assert.equal(plain.rows[0].csv_schema_version, "1");
  assert.equal(plain.rows[0].steam_url, "https://store.steampowered.com/app/1/");
  for (const kind of ["developer", "publisher"]) {
    const ctx = creatorSetup({}, kind); ctx.get("creators-tab").listeners.click(); await settle();
    ctx.run('currentProfile = "PRIVATE_PROFILE"; downloadCsv = contents => {window.exportContents = contents;}');
    ctx.get("creators-export").listeners.click();
    const contents = ctx.run("window.exportContents"), catalog = parseCsv(contents);
    assert.deepEqual(catalog.headers, plain.headers);
    assert.ok(catalog.rows.every(row => row.source_tab === kind && row.catalog_role === kind && row.catalog_id === "studio"));
    assert.ok(catalog.rows.every(row => row.wishlist_profile === "" && row.wishlist_loading_order === ""));
    assert.doesNotMatch(contents, /PRIVATE_PROFILE|PRIVATE_TOKEN|bbbbbbbb/);
  }
  const empty = parseCsv(wishlist.run('items = []; buildCsv(false)'));
  assert.deepEqual(empty.headers, plain.headers);
  assert.equal(empty.rows.length, 0);
});

test("CSV retains both conversion legs, per-storefront differences, and mixed price sources", () => {
  const {run} = setup();
  const item = {app_id:"10",name:"Rich metadata",index:3,developers:["Dev A","Dev B"],publishers:[],
    cache_hits:1,stale_cache_hits:1,live_requests:1,source_summary:"cache 1, stale 1, live 1",
    comparison:{home_price:{amount:50,base_amount:100,discount_percent:50,source:"cache"},is_fair:false,
      alternatives:[{region:"no",currency:"NOK",original_amount:100,base_amount:100,discount_percent:0,rate_to_home:0.4,amount_in_home:40,source:"live"},
        {region:"pl",currency:"PLN",original_amount:150,base_amount:150,discount_percent:0,rate_to_home:0.2,amount_in_home:30,source:"stale cache"}]}};
  run(`items = ${JSON.stringify([item])}; resultHome = "gb"; lastRequest = {home:"pl",regions:["us"],order:"date_added"};
    currentRates = [{currency:"GBP",rate_to_pln:5,effective_date:"2026-10-09",retrieved_at_utc:"2026-10-10T10:00:00Z",checked_at_utc:"2026-10-13T10:00:00Z",source:"NBP table A (mid)",cache_status:"stale cache"},
      {currency:"NOK",rate_to_pln:2,effective_date:"2026-10-12",retrieved_at_utc:"2026-10-13T10:00:00Z",checked_at_utc:"2026-10-13T10:00:00Z",source:"NBP table A (mid)",cache_status:"live"}];`);
  const {rows} = parseCsv(run('buildCsv(false, "2026-10-13T11:00:00Z")'));
  const [home, nok, pln] = rows;
  assert.equal(home.final_price, "50"); assert.equal(home.base_price, "100");
  assert.equal(home.storefront_difference_baseline, ""); assert.equal(home.storefront_difference_percent, "");
  assert.equal(nok.rate_to_pln, "2"); assert.equal(nok.rate_to_baseline, "0.4");
  assert.equal(nok.base_price_baseline, "40"); assert.equal(nok.final_price_baseline, "40");
  assert.equal(nok.storefront_difference_baseline, "10"); assert.equal(nok.storefront_difference_percent, "25");
  assert.equal(nok.rate_publication_date, "2026-10-12"); assert.equal(nok.rate_cache_status, "live");
  assert.equal(pln.rate_to_pln, "1"); assert.equal(pln.rate_source, "Identity conversion");
  assert.equal(pln.rate_publication_date, ""); assert.equal(pln.rate_retrieved_at_utc, "");
  assert.equal(pln.storefront_difference_baseline, "20");
  assert.equal(Number(pln.storefront_difference_percent), 20 / 30 * 100);
  assert.deepEqual(rows.map(row => row.storefront_price_source), ["cache","live","stale cache"]);
  for (const row of rows) {
    assert.equal(row.baseline_storefront, "gb"); assert.equal(row.baseline_currency, "GBP");
    assert.equal(row.baseline_rate_to_pln, "5"); assert.equal(row.baseline_rate_publication_date, "2026-10-09");
    assert.equal(row.baseline_rate_cache_status, "stale cache"); assert.equal(row.baseline_rate_source, "NBP table A (mid)");
    assert.equal(row.comparison_storefronts, "no; pl"); assert.equal(row.comparison_currencies, "NOK; PLN");
    assert.equal(row.baseline_difference, "20"); assert.equal(Number(row.baseline_difference_percent), 20 / 30 * 100);
    assert.equal(row.cheapest_alternative_storefront, "pl"); assert.equal(row.cheapest_alternative_currency, "PLN");
    assert.equal(row.cheapest_alternative_final_price_baseline, "30"); assert.equal(row.baseline_is_cheaper_or_equal, "false");
    assert.equal(row.different_regional_discounts, "true"); assert.equal(row.developers, "Dev A; Dev B");
    assert.equal(row.publishers, ""); assert.equal(row.publishers_known, "true");
    assert.equal(row.cache_hits, "1"); assert.equal(row.stale_cache_hits, "1"); assert.equal(row.live_price_requests, "1");
    assert.equal(row.checked_index, "3"); assert.equal(row.wishlist_loading_order, "date_added");
  }
});

test("CSV round-trips unsafe text and exports failures and zero references without invented metadata", () => {
  const {run} = setup();
  const zero = game("1", 'Quoted "title", with\r\na new line');
  zero.developers = ["  =unsafe", "Other developer"]; zero.publishers = null;
  zero.comparison.alternatives[0].amount_in_home = 0;
  const failure = {...skipped("2", "temporary_failure"), skipped:{category:"temporary_failure",reason:"Temporary request failures",region:"no",retryable:true}};
  run(`items = ${JSON.stringify([zero,failure])}; demoMode = true; lastRequest = {regions:["no"],order:"priority"};`);
  const contents = run("buildCsv(false)"), {rows} = parseCsv(contents);
  assert.equal(rows.length, 3);
  assert.equal(rows[0].game, zero.name);
  assert.equal(rows[0].developers, "'  =unsafe; Other developer");
  assert.equal(rows[0].developers_known, "true"); assert.equal(rows[0].publishers_known, "false");
  assert.equal(rows[0].baseline_difference_percent, ""); assert.equal(rows[1].storefront_difference_percent, "");
  const missing = rows[2];
  assert.equal(missing.status, "temporary_failure"); assert.equal(missing.skipped_storefront, "no");
  assert.equal(missing.skipped_reason, "Temporary request failures"); assert.equal(missing.skipped_retryable, "true");
  assert.equal(missing.comparison_storefronts, "no"); assert.equal(missing.comparison_currencies, "NOK");
  for (const field of ["storefront","currency","final_price","base_price","discount_percent","rate_to_pln","baseline_difference","base_price_baseline","baseline_is_cheaper_or_equal","cache_hits"]) assert.equal(missing[field], "");
  assert.equal(missing.developers_known, "false"); assert.ok(rows.every(row => row.example_data === "true"));
  assert.doesNotMatch(contents, /NaN|Infinity|undefined/);
});

test("running catalog CSV preserves overlapping memberships and omits pending and free products", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  const creator = {id:"developer-"+"d".repeat(24),name:"Other Studio",selector:{kind:"developer",name:"Other Studio"}};
  ctx.searches.push({creators:[],exact_matches:[creator]}); ctx.get("creator-query").value = "Other Studio";
  await ctx.get("creator-search-form").listeners.submit({preventDefault(){}});
  ctx.snapshots.push({state:"running",message:"Checking",catalogs:{[creator.id]:{
    products:[{app_id:"1",name:"First"},{app_id:"4",name:"Pending"},{app_id:"5",name:"Free"},{app_id:"6",name:"Unavailable"}],next_start:25,has_more:true,total:30}},
    items:[{...game("5","Free"),is_free:true},skipped("6","no_regional_price")],rates:[],warnings:[]});
  ctx.get("creator-search-results").children[0].children[1].children[0].listeners.click(); await settle();
  ctx.run('downloadCsv = contents => {window.exportContents = contents;}'); ctx.get("creators-export").listeners.click();
  const {rows} = parseCsv(ctx.run("window.exportContents"));
  assert.equal(rows.length, 9); // Three featured products, one repeated product, one skipped product.
  assert.deepEqual(rows.filter(row => row.game_id === "1").map(row => row.catalog_name), ["Studio","Studio","Other Studio","Other Studio"]);
  assert.ok(!rows.some(row => ["4","5"].includes(row.game_id)));
  assert.equal(rows.find(row => row.game_id === "6").status, "no_regional_price");
});

const offerFixture = () => {
  const item = game("330020", "Children of Morta");
  item.best_offers = {
    pl:{status:"available",kind:"bundle",id:22978,name:"Complete Edition",source:"live",currency_basis:"requested storefront",price:{region:"pl",currency:"PLN",amount:19.99,base_amount:null,discount_percent:null}},
    us:{status:"available",kind:"package",id:123,name:"Base game",source:"cache",price:{region:"us",currency:"USD",amount:5,base_amount:10,discount_percent:50}}
  };
  item.best_offer_comparison = {home_price:item.best_offers.pl.price,alternatives:[{region:"us",currency:"USD",original_amount:5,rate_to_home:4,amount_in_home:20}],is_fair:true};
  return item;
};
const contentText = el => [el.textContent || "", ...el.children.map(contentText)].join(" ");

test("regional headings identify the country while rows retain converted and original prices separately", () => {
  const ctx = setup();
  const headings = ctx.run('regionalHeadings(["us", "de"])');
  assert.equal(headings[0].textContent, "USD");
  assert.equal(headings[0].children[0].textContent, "United States " + String.fromCharCode(183) + " US");
  const item = game("1", "Original prices");
  item.comparison.alternatives[0].original_amount = 12345.67;
  ctx.run(`items = ${JSON.stringify([item])}; render();`);
  const slot = ctx.get("rows").children[0].children[2].children[0].children[0];
  const line = slot.children[0];
  assert.equal(line.className, "regional-price-line");
  assert.equal(line.children[0].textContent, "20.00 zł");
  assert.equal(line.children[1].children[0].textContent, "12,345.67");
  assert.equal(line.children[1].children[1].textContent, "USD");
  assert.equal(line.children[1].children[1].className, "original-price-currency");
  item.comparison.alternatives[0].original_amount = 0;
  ctx.run(`items = ${JSON.stringify([item])}; render();`);
  assert.equal(ctx.get("rows").children[0].children[2].children[0].children[0].children[0].children[1].children[0].textContent, "0.00");
});

test("best offers show their own original price and omit country-code prefixes", () => {
  const ctx = setup(), item = offerFixture();
  ctx.run(`showBestOffers = true; items = ${JSON.stringify([item])}; render();`);
  const offer = ctx.get("rows").children[0].children[2].children[1].children[0];
  assert.equal(offer.children[0].textContent, "Steam best offer");
  assert.equal(offer.children[1].children[0].textContent, "20.00 zł");
  assert.equal(offer.children[1].children[1].children[0].textContent, "5.00");
  assert.equal(offer.children[1].children[1].children[1].textContent, "USD");
});

test("best-offer bands compensate for wrapped defaults and can shrink again after resizing", () => {
  const ctx = setup(), table = ctx.get("alignment-table"), row = new Element("tr");
  const heights = [{top:100,label:36,value:21,name:42}, {top:74,label:18,value:42,name:14}, {top:80,label:18,value:54,name:0}];
  const blocks = heights.map(metrics => {
    const block = new Element("div"), fields = {};
    for (const band of ["label", "value", "name"]) if (metrics[band]) {
      const field = new Element("span");
      field.getBoundingClientRect = () => ({top:metrics.top,height:metrics[band]});
      fields[`.offer-${band}`] = field;
    }
    block.querySelector = selector => fields[selector] || null;
    return block;
  });
  table.getBoundingClientRect = () => ({width:1000});
  table.querySelectorAll = () => [row]; row.querySelectorAll = () => blocks;
  ctx.run('showBestOffers = true; alignBestOffers(document.getElementById("alignment-table"));');
  assert.equal(row.style.getPropertyValue("--offer-label-height"), "36px");
  assert.equal(row.style.getPropertyValue("--offer-value-height"), "54px");
  assert.equal(row.style.getPropertyValue("--offer-name-height"), "42px");
  assert.deepEqual(blocks.map(block => block.style.getPropertyValue("--offer-align-offset")), ["0px", "26px", "20px"]);
  for (const metric of heights) Object.assign(metric, {top:90,label:18,value:21,name:14});
  ctx.run('alignBestOffers(document.getElementById("alignment-table"));');
  assert.equal(row.style.getPropertyValue("--offer-label-height"), "18px");
  assert.equal(row.style.getPropertyValue("--offer-value-height"), "21px");
  assert.equal(row.style.getPropertyValue("--offer-name-height"), "14px");
  assert.deepEqual(blocks.map(block => block.style.getPropertyValue("--offer-align-offset")), ["0px", "0px", "0px"]);
});

test("best-offer layout coalesces renders and responds only to width changes", () => {
  const frames = [], observers = [];
  const ctx = setup({}, {requestAnimationFrame:callback => { frames.push(callback); return frames.length; },
    ResizeObserver:class { constructor(callback) { this.callback = callback; observers.push(this); } observe(target) { this.target = target; } }});
  const table = ctx.get("alignment-table");
  ctx.run('alignBestOffers = table => {table.alignments = (table.alignments || 0) + 1;}; scheduleOfferAlignment(document.getElementById("alignment-table")); scheduleOfferAlignment(document.getElementById("alignment-table"));');
  assert.equal(frames.length, 1);
  frames.shift()(); assert.equal(table.alignments, 1);
  const observer = observers.find(value => value.target === table);
  observer.callback([{contentRect:{width:1000}}]);
  assert.equal(frames.length, 1); frames.shift()();
  observer.callback([{contentRect:{width:1000}}]);
  assert.equal(frames.length, 0);
  observer.callback([{contentRect:{width:800}}]);
  assert.equal(frames.length, 1); frames.shift()();
  assert.equal(table.alignments, 3);
});

test("best-offer display controls restore, synchronize and persist one shared setting", () => {
  const values = new Map([["polisher-best-offers", "true"]]);
  const storage = {getItem:key => values.get(key) || null, setItem:(key,value) => values.set(key,value)};
  const ctx = setup({}, {sessionStorage:storage});
  const ids = ["show-best-offers", "developers-show-best-offers", "publishers-show-best-offers", "library-show-best-offers"];
  for (const id of ids) assert.equal(ctx.get(id).checked, true);
  ctx.get("publishers-show-best-offers").checked = false;
  ctx.get("publishers-show-best-offers").listeners.change();
  for (const id of ids) assert.equal(ctx.get(id).checked, false);
  assert.equal(ctx.run("showBestOffers"), false);
  assert.equal(values.get("polisher-best-offers"), "false");
  const restored = setup({}, {sessionStorage:storage});
  for (const id of ids) assert.equal(restored.get(id).checked, false);
});

test("the catalog-local best-offer control rerenders loaded offers without new requests", async () => {
  const item = offerFixture();
  const ctx = creatorSetup({}, "developer", false, [{state:"complete",message:"Done",items:[item],rates:[],warnings:[],
    catalogs:{studio:{products:[{app_id:item.app_id,name:item.name}],next_start:1,has_more:false,total:1}}}]);
  ctx.get("creators-tab").listeners.click(); await settle();
  const before = ctx.calls.length;
  ctx.get("developers-show-best-offers").checked = true;
  ctx.get("developers-show-best-offers").listeners.change();
  assert.match(contentText(ctx.body()), /Complete Edition/);
  assert.equal(ctx.get("show-best-offers").checked, true);
  assert.equal(ctx.get("publishers-show-best-offers").checked, true);
  assert.equal(ctx.calls.length, before);
  ctx.get("developers-show-best-offers").checked = false;
  ctx.get("developers-show-best-offers").listeners.change();
  assert.doesNotMatch(contentText(ctx.body()), /Complete Edition/);
  assert.equal(ctx.calls.length, before);
});

test("best-offer checkbox reveals separate offers without replacing default prices or changing counts", () => {
  const ctx=setup();const item=offerFixture();
  ctx.run(`items=${JSON.stringify([item])}; render();`);
  assert.equal(ctx.get("rows").children[0].children.length,4);
  const before=ctx.get("rows").children[0];
  assert.doesNotMatch(contentText(before),/Complete Edition/);
  ctx.get("show-best-offers").checked=true;ctx.get("show-best-offers").listeners.change();
  const row=ctx.get("rows").children[0];
  assert.equal(row.children.length,4);
  assert.equal(row.children[1].textContent,"10.00 zł");
  assert.match(contentText(row.children[1]),/19.99 zł.*Complete Edition \(bundle\)/);
  assert.match(contentText(row.children[1]),/Regular-price discount unavailable/);
  assert.equal(ctx.get("count-total").textContent,1);
  ctx.get("show-best-offers").checked=false;ctx.get("show-best-offers").listeners.change();
  assert.doesNotMatch(contentText(ctx.get("rows").children[0]),/Complete Edition/);
});

test("best-offer rendering retains columns when default offers are missing", () => {
  const ctx=setup();const item=offerFixture();delete item.comparison;item.skipped={reason:"No regional price",category:"no_regional_price"};
  ctx.run(`showBestOffers=true; items=${JSON.stringify([item])}; $("show-unavailable").checked=true; render();`);
  const row=ctx.get("rows").children[0];
  assert.equal(row.children.length,4);
  assert.match(contentText(row.children[3]),/Steam best offers/);
});

test("CSV retains default and best-offer identity, amounts, and unknown discounts separately", () => {
  const ctx=setup();const item=offerFixture();
  const csv=parseCsv(ctx.run(`buildPriceCsv(${JSON.stringify([item])},"pl",[])`));
  assert.equal(csv.rows[0].final_price,"10");
  assert.equal(csv.rows[0].best_offer_final_price,"19.99");
  assert.equal(csv.rows[0].best_offer_kind,"bundle");
  assert.equal(csv.rows[0].best_offer_id,"22978");
  assert.equal(csv.rows[0].best_offer_regular_price,"");
  assert.equal(csv.rows[0].best_offer_discount_percent,"");
  assert.equal(csv.rows[1].best_offer_discount_percent,"50");
});

for (const kind of ["developer","publisher"]) test(`${kind} best-offer toggle rerenders without requests and preserves optional credit column`, async () => {
  const ctx=creatorSetup({},kind);ctx.snapshots.push({state:"complete",message:"Done",items:[offerFixture()],rates:[],warnings:[],catalogs:{studio:{products:[{app_id:"330020",name:"Children of Morta"}],next_start:1,has_more:false,total:1}}});
  ctx.get("creators-tab").listeners.click();await settle();
  const calls=ctx.calls.length;
  ctx.get("show-best-offers").checked=true;ctx.get("show-best-offers").listeners.change();
  ctx.get("creator-show-credits").checked=true;ctx.get("creator-show-credits").listeners.change();
  assert.equal(ctx.calls.length,calls);
  const row=ctx.body().children.find(row=>row.dataset.appId==="330020");
  assert.equal(row.children.length,5);
  assert.match(contentText(row.children[2]),/Complete Edition/);
});

test("calculated discounts display whole percentages and approximation without changing Steam badges", () => {
  const ctx=setup();
  assert.equal(ctx.run('saleNote({amount:66.66,base_amount:100,discount_percent:33,discount_calculated:true},"PLN").children[0].textContent'),"≈−33%");
  assert.equal(ctx.run('saleNote({amount:66.66,base_amount:100,discount_percent:33},"PLN").children[0].textContent'),"−33%");
  assert.equal(ctx.run('saleNote({amount:99.5,base_amount:100,discount_percent:0,discount_calculated:true},"PLN").children[0].textContent'),"≈0%");
  assert.equal(ctx.run('saleNote({amount:66.66,base_amount:100,discount_percent:33.34},"PLN").children[0].textContent'),"≈−33%");
  assert.match(ctx.run('saleNote({amount:66.66,base_amount:100,discount_percent:33,discount_calculated:true},"PLN").children[0].title'), /Calculated by this app.*rounded down/);
  assert.equal(ctx.run('saleNote({amount:66.66,base_amount:100,discount_percent:33,discount_calculated:false},"PLN").children[0].title'), "Discount percentage provided by Steam.");
  assert.match(ctx.run('saleNote({amount:99.5,base_amount:100,discount_percent:0,discount_calculated:true},"PLN").children[0].title'), /Calculated by this app/);
  assert.match(ctx.run('saleNote({amount:66.66,base_amount:100,discount_percent:33.34},"PLN").children[0].title'), /Calculated by this app/);
  const item=offerFixture(); item.comparison.home_price.discount_calculated=true;
  item.best_offers.pl.price.discount_calculated=true;
  const csv=parseCsv(ctx.run(`buildPriceCsv(${JSON.stringify([item])},"pl",[])`));
  assert.equal(csv.rows[0].discount_calculated,"true");
  assert.equal(csv.rows[0].best_offer_discount_calculated,"true");
});

function chooseCurrencies(ctx, home, regions) {
  ctx.radios.forEach(el => el.checked = el.value === home);
  ctx.regions.forEach(el => el.checked = regions.includes(el.value));
  ctx.run("preferredComparisons = null; updateSelections();");
}
async function loadedWishlist(snapshot = wishlistSnapshot()) {
  const ctx = creatorSetup(); ctx.get("wishlist-order").value = "priority";
  ctx.snapshots.push(snapshot); ctx.ready(); await settle(); return ctx;
}
const switchedWishlist = (state = "complete", extra = {}) => wishlistSnapshot(state, {
  home:"gb", regions:["us"], items:[game("1", "Updated game")], rates:[{currency:"GBP",rate_to_pln:5,cache_status:"cache"}], ...extra});

test("currency action is explicit, follows the active tab, and requires a valid changed selection", async () => {
  const ctx = await loadedWishlist();
  assert.equal(ctx.get("update-currencies").hidden, false);
  assert.equal(ctx.get("update-currencies").disabled, true);
  chooseCurrencies(ctx,"gb",["us"]);
  assert.equal(ctx.get("update-currencies").disabled, false);
  assert.equal(ctx.calls.filter(c => c.path.endsWith("/currencies")).length,0);
  assert.match(ctx.get("currency-update-help").textContent,/Displayed: PLN/);
  chooseCurrencies(ctx,"gb",[]);
  assert.equal(ctx.get("update-currencies").disabled,true);
  chooseCurrencies(ctx,"gb",["us"]);
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.match(ctx.get("currency-update-help").textContent,/Displayed: GBP/);
  ctx.get("wishlist-tab").listeners.click();
  assert.match(ctx.get("currency-update-help").textContent,/Displayed: PLN/);
});

test("wishlist switch preserves rows, rates, view and CSV while pending, then publishes one snapshot", async () => {
  const ctx = await loadedWishlist();
  ctx.get("search").value = "game"; ctx.get("show-unavailable").checked = true;
  ctx.run('sort = "name"; direction = -1; render();');
  const row = ctx.get("rows").children[0], csv = ctx.run('buildCsv(false,"fixed")');
  chooseCurrencies(ctx,"gb",["us"]);
  ctx.snapshots.push(switchedWishlist("running",{items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  assert.equal(ctx.get("rows").children[0],row);
  assert.equal(ctx.run('buildCsv(false,"fixed")'),csv);
  assert.equal(ctx.run("resultHome"),"pl");
  assert.equal(ctx.run("currentRates.length"),0);
  assert.equal(ctx.radios.every(el => el.disabled),true);
  const submission = ctx.calls.find(c => c.path.endsWith("/currencies"));
  assert.deepEqual(submission.body,{home:"gb",regions:["us"]});
  assert.equal(submission.authorization,"Bearer " + "b".repeat(43));
  assert.match(ctx.get("progress-label").textContent,/GBP against USD/);
  ctx.snapshots.push(switchedWishlist()); await ctx.run("pollWishlistCurrencies()");
  assert.equal(ctx.run("resultHome"),"gb");
  assert.equal(ctx.run("currentRates[0].currency"),"GBP");
  assert.equal(ctx.get("search").value,"game");
  assert.equal(ctx.get("show-unavailable").checked,true);
  assert.equal(ctx.run("sort + direction"),"name-1");
  assert.equal(ctx.run("job.id"),"u".repeat(32));
  assert.equal(parseCsv(ctx.run("buildCsv(false)")).rows[0].baseline_currency,"GBP");
  assert.equal(ctx.calls.filter(c => c.path === "/api/jobs").length,1);
});

for (const state of ["failed","cancelled"]) test(`wishlist ${state} update retains source credentials and retries the currency endpoint`, async () => {
  const ctx = await loadedWishlist(); chooseCurrencies(ctx,"gb",["us"]);
  ctx.snapshots.push(switchedWishlist(state));
  ctx.get("update-currencies").listeners.click(); await settle();
  assert.equal(ctx.run("resultHome"),"pl");
  assert.equal(ctx.run("job.id"),"a".repeat(32));
  assert.match(ctx.get("notice").textContent,/unchanged/);
  assert.equal(ctx.run("comparisonCoordinator.busy"),false);
  chooseCurrencies(ctx,"no",["de"]); // Retry uses the failed request, not later sidebar edits.
  ctx.snapshots.push(switchedWishlist());
  ctx.get("retry").listeners.click(); await settle();
  assert.deepEqual(ctx.calls.filter(c => c.path.endsWith("/currencies")).at(-1).body,{home:"gb",regions:["us"]});
  assert.equal(ctx.run("resultHome"),"gb");
});

for (const status of [429,403]) test(`wishlist submission ${status} preserves results and explains the next action`, async () => {
  const ctx = await loadedWishlist(); chooseCurrencies(ctx,"gb",["us"]);
  ctx.submissions.push({httpStatus:status,error:"Could not update"});
  ctx.get("update-currencies").listeners.click(); await settle();
  assert.equal(ctx.run("items[0].name"),"Example game");
  assert.equal(ctx.run("comparisonCoordinator.busy"),false);
  assert.match(ctx.get("notice").textContent,/unchanged.*Retry/);
  assert.equal(ctx.get("update-currencies").disabled,false);
  assert.equal(ctx.calls.filter(c => c.path === "/api/jobs").length,1);
});

function restoredWishlist(identifier = "example", expired = false, extra = {}) {
  const request = {identifier, home:"pl", regions:["us","de"], order:"name"};
  const displayed = {request, data:wishlistSnapshot("complete",{profile:identifier})};
  const saved = {id:"w".repeat(32),token:"t".repeat(43),request,displayed,expired,...extra};
  return creatorSetup({"polisher-job":JSON.stringify(saved)});
}

for (const identifier of ["example","76561198000000000"]) test(`expired restored ${identifier === "example" ? "example" : "wishlist"} recreates on currency update without discarding the snapshot`, async () => {
  const ctx = restoredWishlist(identifier); await settle();
  const row = ctx.get("rows").children[0], csv = ctx.run('buildCsv(false,"fixed")');
  chooseCurrencies(ctx,"pl",["gb"]);
  ctx.submissions.push({httpStatus:404,error:"Expired"});
  ctx.snapshots.push(wishlistSnapshot("running",{items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  const starts = ctx.calls.filter(c=>c.path==="/api/jobs");
  assert.equal(starts.length,1);
  assert.deepEqual(starts[0].body,{identifier,home:"pl",regions:["gb"],order:"name"});
  assert.equal(starts[0].authorization,undefined);
  assert.equal(ctx.calls.filter(c=>c.path.endsWith("/currencies")).length,1);
  assert.equal(ctx.get("rows").children[0],row);
  assert.equal(ctx.run('buildCsv(false,"fixed")'),csv);
  assert.equal(ctx.run("comparisonCoordinator.busy"),true);
  assert.match(ctx.get("currency-update-help").textContent,/reload this saved comparison/);
  ctx.snapshots.push(wishlistSnapshot("complete",{regions:["gb"]}));
  await ctx.run("pollWishlistCurrencies()");
  assert.equal(ctx.run("wishlistExpired"),false);
  assert.equal(ctx.run("job.id"),"a".repeat(32));
  assert.deepEqual(JSON.parse(ctx.storage.get("polisher-job")).request.regions,["gb"]);
});

test("known-expired snapshots still allow currency updates after refresh and recover retry selections", async () => {
  const ctx = restoredWishlist("example",true,{retryCurrency:{home:"pl",regions:["gb"]}}); await settle();
  chooseCurrencies(ctx,"pl",["gb"]);
  assert.equal(ctx.get("update-currencies").disabled,false);
  ctx.submissions.push({httpStatus:429,error:"Busy"});
  ctx.get("update-currencies").listeners.click(); await settle();
  assert.equal(ctx.calls.filter(c=>c.path.endsWith("/currencies")).length,0);
  assert.equal(ctx.run("items[0].name"),"Example game");
  assert.match(ctx.get("notice").textContent,/unchanged.*Retry/);
  const restored = creatorSetup(Object.fromEntries(ctx.storage)); await settle();
  chooseCurrencies(restored,"no",["de"]);
  restored.snapshots.push(wishlistSnapshot());
  restored.get("retry").listeners.click(); await settle();
  assert.deepEqual(restored.calls.find(c=>c.path==="/api/jobs").body,{identifier:"example",home:"pl",regions:["gb"],order:"name"});
  assert.equal(restored.run("wishlistExpired"),false);
});

test("recreated currency comparisons reconnect after refresh and cancel their own job", async () => {
  const ctx = restoredWishlist("example",true); await settle();
  chooseCurrencies(ctx,"pl",["gb"]);
  ctx.snapshots.push(wishlistSnapshot("running",{items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  const restored = creatorSetup(Object.fromEntries(ctx.storage),"developer",false,[wishlistSnapshot("running",{items:[]})]); await settle();
  assert.equal(restored.calls.some(c=>c.path==="/api/jobs"||c.path.endsWith("/currencies")),false);
  await restored.get("cancel").listeners.click();
  assert.equal(restored.calls.find(c=>c.path.endsWith("/cancel")).path,`/api/jobs/${"a".repeat(32)}/cancel`);
  restored.snapshots.push(wishlistSnapshot("cancelled")); await restored.run("pollWishlistCurrencies()");
  assert.equal(restored.run("items[0].name"),"Example game");
  assert.equal(restored.run("wishlistExpired"),true);
  assert.equal(restored.run("comparisonCoordinator.busy"),false);
});

test("wishlist cancellation targets the pending job and expired pending work can retry the source", async () => {
  const ctx = await loadedWishlist(); chooseCurrencies(ctx,"gb",["us"]);
  ctx.snapshots.push(switchedWishlist("running",{items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  await ctx.get("cancel").listeners.click();
  const cancel = ctx.calls.find(c => c.path.endsWith("/cancel"));
  assert.equal(cancel.path,`/api/jobs/${"u".repeat(32)}/cancel`);
  assert.equal(cancel.authorization,"Bearer " + "v".repeat(43));
  ctx.snapshots.push({httpStatus:404,error:"Expired"}); await ctx.run("pollWishlistCurrencies()");
  assert.equal(ctx.run("resultHome"),"pl");
  assert.match(ctx.get("notice").textContent,/update expired/);
  ctx.snapshots.push(switchedWishlist()); ctx.get("retry").listeners.click(); await settle();
  assert.equal(ctx.run("resultHome"),"gb");
});

test("wishlist reload restores displayed view and reconnects pending currencies independently", async () => {
  const ctx = await loadedWishlist();
  ctx.get("search").value = "game"; ctx.run('filter = "fair"; sort = "home"; direction = -1; render();');
  chooseCurrencies(ctx,"gb",["us"]); ctx.snapshots.push(switchedWishlist("running",{items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  const restored = creatorSetup(Object.fromEntries(ctx.storage),"developer",false,[switchedWishlist("running",{items:[]})]);
  await settle();
  assert.equal(restored.run("resultHome"),"pl");
  assert.equal(restored.get("search").value,"game");
  assert.equal(restored.run("filter + sort + direction"),"fairhome-1");
  assert.equal(restored.run("selectedHome()"),"gb");
  assert.equal(restored.run("comparisonCoordinator.busy"),true);
  assert.equal(restored.calls.some(c => c.path === "/api/jobs" || c.path.endsWith("/currencies")),false);
  restored.snapshots.push(switchedWishlist("partial",{items:[skipped("1","request_failed")]}));
  await restored.run("pollWishlistCurrencies()");
  assert.equal(restored.run("resultHome"),"gb");
  assert.equal(restored.run("items[0].skipped.category"),"request_failed");
  assert.match(restored.get("notice").textContent,/Some games/);
  const completed = creatorSetup(Object.fromEntries(restored.storage)); await settle();
  assert.equal(completed.run("resultHome"),"gb");
  assert.equal(completed.calls.length,0);
});

test("wishlist currency update locks other tabs and survives unavailable session storage", async () => {
  const ctx = await loadedWishlist();
  ctx.run('sessionStorage.setItem = () => {throw new Error("Full");}');
  chooseCurrencies(ctx,"gb",["us"]); ctx.snapshots.push(switchedWishlist("running",{items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.equal(ctx.get("creators-refresh").disabled,true);
  assert.equal(ctx.calls.filter(c => c.path === "/api/creator-jobs").length,0);
  ctx.snapshots.push(switchedWishlist()); await ctx.run("pollWishlistCurrencies()"); await settle();
  assert.equal(ctx.calls.filter(c => c.path === "/api/creator-jobs").length,1);
});

for (const kind of ["developer","publisher"]) test(`${kind} switch preserves groups, CSV, credit mode and cursor context`, async () => {
  const ctx = creatorSetup({},kind); ctx.get("creators-tab").listeners.click(); await settle();
  ctx.snapshots.push({state:"complete",message:"Expanded",items:[game("4","Soundtrack")],rates:[],warnings:[],catalogs:{studio:{products:[{app_id:"1",name:"First"},{app_id:"4",name:"Soundtrack"}],next_start:25,has_more:false,total:25}}});
  ctx.group().children[1].children[1].children[1].listeners.click(); await settle();
  ctx.get("creator-show-credits").checked = true; ctx.get("creator-show-credits").listeners.change();
  ctx.run('downloadCsv = value => {window.csv = value;}'); ctx.get("creators-export").listeners.click();
  const csv = ctx.run("window.csv"), row = ctx.body().children[0];
  chooseCurrencies(ctx,"gb",["us"]);
  ctx.snapshots.push({state:"running",message:"Checking",items:[],rates:[],warnings:[],catalogs:{}});
  ctx.get("update-currencies").listeners.click(); await settle();
  const submitted = ctx.calls.filter(c => c.path === "/api/creator-jobs").at(-1).body;
  assert.deepEqual(submitted,{home:"gb",regions:["us"],mode:"products",app_ids:["1","2","3","4"]});
  assert.equal(ctx.body().children[0],row);
  ctx.get("creators-export").listeners.click();
  const withoutTime = value => parseCsv(value).rows.map(({exported_at_utc, ...row}) => row);
  assert.deepEqual(withoutTime(ctx.run("window.csv")),withoutTime(csv));
  assert.equal(ctx.radios.every(el => el.disabled),true);
  const pending = JSON.parse(ctx.storage.get(`polisher-${kind}-job`));
  assert.equal(pending.home,"pl"); assert.equal(pending.currencyUpdating,true);
  ctx.snapshots.push({state:"complete",message:"Done",items:[1,2,3,4].map(id => game(String(id),"Updated")),rates:[],warnings:[],catalogs:{}});
  await [...ctx.timers.values()].at(-1)(); await settle();
  const saved = JSON.parse(ctx.storage.get(`polisher-${kind}-job`));
  assert.equal(saved.home,"gb"); assert.equal(saved.catalogs[0].nextStart,25);
  assert.equal(saved.catalogs[0].discoveryHome,"pl");
  assert.equal(ctx.get("creator-show-credits").checked,true);
  assert.equal(ctx.get("creator-columns-head").children[0].children.length,5);
  assert.equal(ctx.group().children[1].children[1].children[1].hidden,false);
  ctx.get("creators-export").listeners.click(); assert.equal(parseCsv(ctx.run("window.csv")).rows[0].baseline_currency,"GBP");
  ctx.group().children[1].children[1].children[1].listeners.click(); await settle();
  assert.equal(ctx.calls.filter(c => c.path === "/api/creator-jobs").at(-1).body.start,0);
  assert.equal(ctx.body().children.length,4);
});

for (const outcome of ["failed","cancelled",429,404,"partial"]) test(`catalog update outcome ${outcome} keeps snapshots and retry coherent`, async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  chooseCurrencies(ctx,"gb",["us"]);
  if (outcome === 429) ctx.submissions.push({httpStatus:429,error:"Slow down"});
  else ctx.snapshots.push(outcome === 404 ? {httpStatus:404,error:"Expired"} : {state:outcome,message:"Done",items:[skipped("1","request_failed")],rates:[],warnings:[],catalogs:{}});
  ctx.get("update-currencies").listeners.click(); await settle();
  const saved = JSON.parse(ctx.storage.get("polisher-developer-job"));
  assert.equal(saved.home,outcome === "partial" ? "gb" : "pl");
  assert.equal(ctx.run("comparisonCoordinator.busy"),false);
  if (outcome !== "partial") {
    assert.equal(saved.results.length,3);
    assert.match(ctx.get("creators-refresh").textContent,/Retry currency/);
    chooseCurrencies(ctx,"no",["de"]);
    ctx.get("creators-refresh").listeners.click(); await settle();
    assert.equal(ctx.calls.filter(c => c.path === "/api/creator-jobs").at(-1).body.home,"gb");
  } else assert.equal(saved.results[0].skipped.category,"request_failed");
});

test("a hidden catalog reconnects a pending currency update while preserving its display and locking the wishlist", async () => {
  const ctx = creatorSetup(); ctx.get("creators-tab").listeners.click(); await settle();
  chooseCurrencies(ctx,"gb",["us"]);
  ctx.snapshots.push({state:"running",message:"Checking",items:[],rates:[],warnings:[],catalogs:{}});
  ctx.get("update-currencies").listeners.click(); await settle();
  ctx.get("wishlist-tab").listeners.click();
  const restored = creatorSetup(Object.fromEntries(ctx.storage),"developer",false,[{state:"running",message:"Checking",items:[],rates:[],warnings:[],catalogs:{}}]);
  restored.ready(); await settle();
  assert.equal(JSON.parse(restored.storage.get("polisher-developer-job")).home,"pl");
  assert.equal(restored.run("comparisonCoordinator.busy"),true);
  assert.equal(restored.get("analyze").disabled,true);
  assert.equal(restored.calls.some(c => c.path === "/api/jobs" || c.path === "/api/creator-jobs"),false);
  restored.snapshots.push({state:"complete",message:"Done",items:[game("1","Switched")],rates:[],warnings:[],catalogs:{}});
  await [...restored.timers.values()].at(-1)(); await settle();
  assert.equal(JSON.parse(restored.storage.get("polisher-developer-job")).home,"gb");
});

test("currency update reconnects after a transport failure without unlocking or replacing displayed data", async () => {
  const ctx = await loadedWishlist(); chooseCurrencies(ctx,"gb",["us"]);
  ctx.run('const connectedRequest = request; let interruptPoll = true; request = async (path, options) => { if (path.endsWith("u".repeat(32)) && interruptPoll) {interruptPoll = false; throw new Error("Disconnected");} return connectedRequest(path, options); };');
  ctx.get("update-currencies").listeners.click(); await settle();
  assert.equal(ctx.run("resultHome"),"pl");
  assert.equal(ctx.run("comparisonCoordinator.busy"),true);
  assert.match(ctx.get("notice").textContent,/Reconnecting/);
  ctx.snapshots.push(switchedWishlist()); await ctx.run("pollWishlistCurrencies()");
  assert.equal(ctx.run("resultHome"),"gb");
  assert.equal(ctx.run("comparisonCoordinator.busy"),false);
});

test("currency switches retain both offer sets and reuse the newly completed source on the next switch", async () => {
  const original = offerFixture();
  const ctx = await loadedWishlist(wishlistSnapshot("complete",{items:[original]}));
  ctx.get("show-best-offers").checked = true; ctx.get("show-best-offers").listeners.change();
  const changed = offerFixture(); changed.best_offers.pl.name = "Updated edition";
  changed.best_offers.gb = {...changed.best_offers.us, price:{...changed.best_offers.us.price,region:"gb",currency:"GBP"}};
  delete changed.best_offers.us;
  for (const comparison of [changed.comparison,changed.best_offer_comparison]) {
    comparison.alternatives[0].region = "gb"; comparison.alternatives[0].currency = "GBP";
  }
  chooseCurrencies(ctx,"pl",["gb"]);
  ctx.snapshots.push(wishlistSnapshot("running",{items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  assert.match(contentText(ctx.get("rows").children[0]),/Complete Edition/);
  ctx.snapshots.push(wishlistSnapshot("complete",{items:[changed]})); await ctx.run("pollWishlistCurrencies()");
  assert.equal(ctx.get("show-best-offers").checked,true);
  assert.match(contentText(ctx.get("rows").children[0]),/Updated edition/);
  const csv = parseCsv(ctx.run("buildCsv(false)"));
  assert.equal(csv.rows[0].best_offer_name,"Updated edition");
  assert.equal(csv.rows[1].storefront,"gb");
  chooseCurrencies(ctx,"pl",["us"]); ctx.snapshots.push(wishlistSnapshot("complete",{items:[original]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  const submission = ctx.calls.filter(c => c.path.endsWith("/currencies")).at(-1);
  assert.equal(submission.path,`/api/jobs/${"u".repeat(32)}/currencies`);
  assert.equal(submission.authorization,"Bearer " + "v".repeat(43));
  assert.equal(ctx.calls.filter(c => c.path === "/api/jobs").length,1);
});

const storefrontRegistry = JSON.parse(fs.readFileSync("steam_price_polisher/storefronts.json", "utf8"));
const allAlternatives = home => Object.keys(storefrontRegistry).filter(region => region !== home);
function manyCurrencyGame(home = "pl", regions = allAlternatives(home), id = "1") {
  const row = game(id, "Many-currency example");
  row.comparison.home_price = {region:home,currency:storefrontRegistry[home].currency,amount:100,base_amount:200,discount_percent:50};
  row.comparison.alternatives = regions.map((region,index) => ({region,currency:storefrontRegistry[region].currency,original_amount:index+1,amount_in_home:index+1,rate_to_home:1,base_amount:2*(index+1),discount_percent:50}));
  row.comparison.is_fair = false;
  row.best_offers = Object.fromEntries([home,...regions].map(region => [region,{status:"available",kind:"package",id:101,name:`Offer ${region.toUpperCase()}`,source:"cache",price:{region,currency:storefrontRegistry[region].currency,amount:1,base_amount:2,discount_percent:50},amount_in_home:1}]));
  row.best_offer_comparison = JSON.parse(JSON.stringify(row.comparison));
  return row;
}
const fullSetup = (storage = {}, kind = "developer", snapshots = []) => creatorSetup(storage,kind,false,snapshots,false,null,true);

test("the full picker selects all 36 alternatives, searches without deselecting, and clears explicitly", () => {
  const ctx = fullSetup();
  assert.equal(ctx.get("baseline-options").children.length,37);
  assert.equal(ctx.get("comparison-options").children.length,37);
  ctx.get("select-all-currencies").listeners.click();
  assert.equal(ctx.regions.filter(el=>el.checked).length,36);
  assert.equal(ctx.regions.find(el=>el.value==="pl").checked,false);
  assert.match(ctx.get("selection-help").textContent,/36 of 36/);
  ctx.get("currency-search").value = "Japan"; ctx.get("currency-search").listeners.input();
  assert.deepEqual(ctx.get("baseline-options").children.filter(el=>!el.hidden).map(el=>el.dataset.storefront),["jp"]);
  assert.deepEqual(ctx.get("comparison-options").children.filter(el=>!el.hidden).map(el=>el.dataset.storefront),["jp"]);
  assert.equal(ctx.regions.filter(el=>el.checked).length,36);
  ctx.get("clear-currencies").listeners.click();
  assert.equal(ctx.regions.some(el=>el.checked),false);
  ctx.get("currency-search").value = ""; ctx.get("currency-search").listeners.input();
  assert.equal(ctx.get("comparison-options").children.filter(el=>!el.hidden).length,36);
});

test("many-currency restoration preserves order, hidden conflicts and the full selection limit", () => {
  const ctx = fullSetup(), regions = allAlternatives("jp").reverse();
  assert.equal(ctx.run(`restoreRequest({request:{identifier:"example",home:"jp",regions:${JSON.stringify(regions)}}})`),true);
  assert.deepEqual(Array.from(ctx.run("lastRequest.regions")),regions);
  assert.equal(ctx.regions.filter(el=>el.checked).length,36);
  assert.equal(ctx.run(`validCurrencies(${JSON.stringify({home:"jp",regions:[...regions,regions[0]]})})`),false);
  assert.equal(ctx.run(`restoreRequest({request:{identifier:"example",home:"jp",regions:${JSON.stringify([...regions,"jp"])}}})`),false);
  chooseCurrencies(ctx,"us",["jp","de","gb","no"]);
  assert.equal(ctx.regions.filter(el=>el.checked).length,4);
  ctx.run("setBusy(true)");
  assert.equal(ctx.get("select-all-currencies").disabled,true);
  assert.equal(ctx.get("clear-currencies").disabled,true);
});

test("regional slots and best-offer placeholders keep all headers aligned even when offers are absent", () => {
  const ctx = setup(), regions = allAlternatives("pl"), row = manyCurrencyGame();
  delete row.best_offers.jp;
  ctx.run(`showBestOffers = true; lastRequest = {home:"pl",regions:${JSON.stringify(regions)}}; items = ${JSON.stringify([row])}; render();`);
  const rendered = ctx.get("rows").children[0], foreign = rendered.children[2];
  assert.equal(ctx.get("wishlist-storefront-headings").children.length,36);
  assert.equal(ctx.get("wishlist-table").style.getPropertyValue("--region-count"),"36");
  assert.equal(foreign.children[0].children.length,36);
  assert.equal(foreign.children[1].children.length,36);
  assert.deepEqual(foreign.children[0].children.map(el=>el.children[0].children[1].children[1].textContent),regions.map(id=>storefrontRegistry[id].currency));
  assert.match(contentText(foreign.children[1].children[regions.indexOf("jp")]),/Offer unavailable/);
  assert.match(rendered.children[0].className,/pinned-game/);
  assert.match(rendered.children[1].className,/pinned-home/);
  assert.match(rendered.children[3].className,/pinned-difference/);
  assert.match(contentText(rendered.children[3]),/Cheapest: USD/);
  const csv = parseCsv(ctx.run("buildCsv(false)"));
  assert.equal(csv.rows.length,37);
  assert.equal(csv.rows[0].comparison_storefronts,regions.join("; "));
  assert.equal(csv.rows.find(value=>value.storefront==="jp").best_offer_name,"");
});

test("sticky currency titles follow scrolling, refresh their labels, and stop at the comparison boundary", () => {
  const listeners = [];
  const ctx = setup({}, {window:{addEventListener:(name, handler) => { if (name === "scroll") listeners.push(handler); }}});
  const wrap = ctx.get("wishlist-scroll"), rail = ctx.get("wishlist-scrollbar"), shell = new Element("div");
  shell.append(rail);
  const table = wrap.querySelector("table"), source = table.querySelector(".storefront-label-cell .storefront-headings");
  let sourceTop = 200, areaBottom = 1000, clones = 0;
  source.innerHTML = "USD EUR";
  source.cloneNode = () => { clones++; const copy = new Element("div"); copy.setAttribute("id", "wishlist-storefront-headings"); return copy; };
  table.classList.contains = () => false;
  table.style.setProperty("--region-count", "2");
  source.getBoundingClientRect = () => ({top:sourceTop,height:60});
  wrap.getBoundingClientRect = () => ({top:0});
  wrap.closest = () => ({getBoundingClientRect:() => ({bottom:areaBottom})});
  shell.getBoundingClientRect = () => ({bottom:29});
  wrap.clientWidth = 900; wrap.scrollWidth = 2700; rail.clientWidth = 380;
  wrap.refreshScrollControls();
  const titles = shell.children[1];
  assert.equal(titles.hidden, true);
  assert.equal(titles.attributes["aria-hidden"], "true");
  assert.equal(titles.firstElementChild.attributes.id, undefined);
  sourceTop = 20; listeners[0]();
  assert.equal(titles.hidden, false);
  rail.scrollLeft = 340; rail.listeners.scroll();
  assert.equal(titles.firstElementChild.style.transform, "translateX(-340px)");
  assert.equal(clones, 1);
  source.innerHTML = "GBP JPY"; wrap.refreshScrollControls();
  assert.equal(clones, 2);
  assert.equal(titles.style.getPropertyValue("--region-count"), "2");
  areaBottom = 80; listeners[0]();
  assert.equal(titles.hidden, true);
  // Currency context remains sticky even when all selected columns fit.
  areaBottom = 1000; wrap.scrollWidth = wrap.clientWidth; wrap.scrollLeft = 0;
  wrap.refreshScrollControls();
  assert.equal(rail.hidden, true);
  assert.equal(titles.hidden, false);
});

test("top regional scrollbar preserves the table range and synchronizes dragging, table scrolling and layout changes", () => {
  const ctx = setup(), wrap = ctx.get("wishlist-scroll"), rail = ctx.get("wishlist-scrollbar");
  const shell = new Element("div"); shell.append(rail);
  wrap.clientWidth = 900; wrap.scrollWidth = 2700; rail.clientWidth = 380;
  wrap.refreshScrollControls();
  assert.equal(shell.hidden, false);
  assert.equal(ctx.get("wishlist-scrollbar-extent").style.width, "2180px");
  rail.scrollLeft = 650; rail.listeners.scroll();
  assert.equal(wrap.scrollLeft, 650);
  wrap.scrollLeft = 820; wrap.listeners.scroll();
  assert.equal(wrap.scrollLeft, 820);
  assert.equal(rail.scrollLeft, 820);
  // A late event from that assignment must not rewind the table.
  rail.listeners.scroll();
  assert.equal(wrap.scrollLeft, 820);
  wrap.scrollLeft = 1800; wrap.listeners.scroll();
  assert.equal(rail.scrollLeft, 1800);
  // Resizing/selection changes recompute the proxy range from actual overflow.
  wrap.scrollLeft = 0; wrap.scrollWidth = wrap.clientWidth;
  wrap.refreshScrollControls();
  assert.equal(shell.hidden, false);
  assert.equal(rail.hidden, true);
  assert.equal(ctx.get("wishlist-scrollbar-extent").style.width, "380px");
  assert.equal(rail.scrollLeft, 0);
});

for (const kind of ["developer", "publisher"]) test(`${kind} top scrollbar follows catalog drags and optional credit layout`, async () => {
  const ctx = creatorSetup({}, kind, false, [], false, null, true);
  ctx.get("creators-tab").listeners.click(); await settle();
  const wrap = ctx.get("creator-columns-scroll"), rail = ctx.get(kind + "s-scrollbar");
  const shell = new Element("div"); shell.append(rail);
  wrap.clientWidth = 900; wrap.scrollWidth = 2700; rail.clientWidth = 380;
  wrap.refreshScrollControls();
  rail.scrollLeft = 340; rail.listeners.scroll(); wrap.listeners.scroll();
  const catalog = ctx.group().children[1].children[0];
  assert.equal(catalog.scrollLeft, 340);
  catalog.scrollLeft = 680; catalog.listeners.scroll();
  assert.equal(wrap.scrollLeft, 680);
  assert.equal(rail.scrollLeft, 680);
  ctx.get("creator-show-credits").checked = true;
  ctx.get("creator-show-credits").listeners.change();
  assert.equal(rail.scrollLeft, 680);
  // A delayed proxy event remains harmless after catalog synchronization.
  rail.listeners.scroll();
  assert.equal(catalog.scrollLeft, 680);
});

test("uncompared default offers retain 36 separate best-offer slots and pinned difference", () => {
  const ctx = setup(), row = manyCurrencyGame(); delete row.comparison; delete row.best_offer_comparison;
  row.skipped = {category:"temporary_failure",reason:"One storefront failed"};
  ctx.run(`showBestOffers = true; lastRequest = {home:"pl",regions:${JSON.stringify(allAlternatives("pl"))}}; items=${JSON.stringify([row])}; render();`);
  const rendered = ctx.get("rows").children[0];
  assert.equal(rendered.children.length,4);
  assert.equal(rendered.children[2].children[0].children.length,36);
  assert.equal(rendered.children[2].children[1].children.length,36);
  assert.match(rendered.children[3].className,/pinned-difference/);
  assert.equal(parseCsv(ctx.run("buildCsv(false)")).rows.length,37);
});

test("all-currency wishlist updates preserve the old matrix and restore pending credentials on reload", async () => {
  const ctx = fullSetup(); ctx.get("wishlist-order").value = "priority";
  ctx.snapshots.push(wishlistSnapshot()); ctx.ready(); await settle();
  chooseCurrencies(ctx,"jp",allAlternatives("jp"));
  ctx.snapshots.push(wishlistSnapshot("running",{home:"jp",items:[]}));
  ctx.get("update-currencies").listeners.click(); await settle();
  assert.equal(ctx.get("wishlist-storefront-headings").children.length,2);
  assert.equal(ctx.get("wishlist-table").style.getPropertyValue("--region-count"),"2");
  const restored = fullSetup(Object.fromEntries(ctx.storage),"developer",[wishlistSnapshot("running",{home:"jp",items:[]})]); await settle();
  assert.equal(restored.run("resultHome"),"pl");
  assert.equal(restored.regions.filter(el=>el.checked).length,36);
  assert.equal(restored.run("comparisonCoordinator.busy"),true);
  restored.snapshots.push(wishlistSnapshot("complete",{home:"jp",items:[manyCurrencyGame("jp")]}));
  await restored.run("pollWishlistCurrencies()");
  assert.equal(restored.run("resultHome"),"jp");
  assert.equal(restored.get("wishlist-storefront-headings").children.length,36);
  assert.equal(restored.get("wishlist-table").style.getPropertyValue("--region-count"),"36");
  const csv = parseCsv(restored.run("buildCsv(false)"));
  assert.equal(csv.rows.length,37);
  assert.equal(new Set(csv.rows.map(row=>row.baseline_currency)).size,1);
  assert.equal(csv.rows[0].baseline_currency,"JPY");
});

for (const kind of ["developer", "publisher"]) test(`${kind} headers separate fixed group labels from scrolling currencies with either credit layout`, async () => {
  const ctx = creatorSetup({}, kind);
  ctx.get("creators-tab").listeners.click(); await settle();
  for (const credits of [false, true]) {
    ctx.get("creator-show-credits").checked = credits;
    ctx.get("creator-show-credits").listeners.change();
    const foreignIndex = credits ? 3 : 2;
    const head = ctx.get("creator-columns-head");
    assert.equal(head.children.length, 2);
    const group = head.children[0].children[foreignIndex];
    assert.match(group.className, /storefront-group-heading/);
    assert.equal(group.children.length, 1);
    assert.equal(group.children[0].children[0].textContent, "OTHER STOREFRONTS");
    assert.equal(group.children[0].children[1].textContent, "CONVERTED TO PLN");
    const labels = head.children[1];
    assert.equal(labels.className, "storefront-label-row");
    assert.equal(labels.children.length, credits ? 5 : 4);
    assert.deepEqual(labels.children[foreignIndex].children[0].children.map(el => el.textContent), ["USD", "EUR"]);
    assert.equal(labels.children[0].attributes["aria-hidden"], "true");
    // Each catalog keeps the same two-level accessible headings as the shared header.
    const accessibleHead = ctx.group().children[1].children[0].children[0].children[1];
    assert.equal(accessibleHead.children.length, 2);
    assert.equal(accessibleHead.children[1].children.length, labels.children.length);
    assert.equal(accessibleHead.children[1].children[foreignIndex].children[0].children.length, 2);
  }
});

for (const kind of ["developer","publisher"]) test(`${kind} full comparisons preserve statistics, credits, scroll synchronization and exports`, async () => {
  const ctx = fullSetup({},kind); chooseCurrencies(ctx,"pl",allAlternatives("pl"));
  ctx.snapshots.push({state:"complete",message:"Done",items:["1","2","3"].map(id=>manyCurrencyGame("pl",allAlternatives("pl"),id)),rates:[],warnings:[],catalogs:{}});
  ctx.get("creators-tab").listeners.click(); await settle();
  const header = ctx.get("creator-columns-head").children[0];
  assert.equal(header.children[2].children.length,1);
  assert.match(header.children[2].className,/storefront-group-heading/);
  const currencyRow = ctx.get("creator-columns-head").children[1];
  assert.equal(currencyRow.children[2].children[0].children.length,36);
  assert.equal(ctx.body().children[0].children[2].children[0].children.length,36);
  assert.equal(ctx.group().children[0].children[1].children[0].tagName,"details");
  assert.match(ctx.group().children[0].children[1].children[0].children[0].textContent,/36 currencies/);
  ctx.get("creator-show-credits").checked = true; ctx.get("creator-show-credits").listeners.change();
  assert.equal(ctx.body().children[0].children.length,5);
  assert.match(ctx.body().children[0].children[2].className,/pinned-home/);
  ctx.get("creator-columns-scroll").scrollLeft = 170;
  ctx.get("creator-columns-scroll").listeners.scroll();
  assert.equal(ctx.get("creator-columns-scroll").scrollLeft,170);
  assert.equal(ctx.group().children[1].children[0].scrollLeft,170);
  // A follower event can arrive after the next animation frame advances the master.
  ctx.get("creator-columns-scroll").scrollLeft = 175;
  ctx.group().children[1].children[0].listeners.scroll();
  ctx.group().children[1].children[0].listeners.scroll();
  assert.equal(ctx.get("creator-columns-scroll").scrollLeft,175);
  ctx.get("creator-columns-scroll").listeners.scroll();
  assert.equal(ctx.group().children[1].children[0].scrollLeft,175);
  const overview = ctx.group().children[0].children[1].children[0];
  overview.open = true; overview.listeners.toggle();
  ctx.get("creator-show-credits").listeners.change();
  assert.equal(ctx.group().children[0].children[1].children[0].open,true);
  ctx.run('downloadCsv = value => {window.csv = value;}'); ctx.get("creators-export").listeners.click();
  assert.equal(parseCsv(ctx.run("window.csv")).rows.length,111);
  const restored = fullSetup(Object.fromEntries(ctx.storage),kind); restored.get("creators-tab").listeners.click(); await settle();
  assert.equal(restored.get("creator-show-credits").checked,true);
  assert.equal(restored.body().children[0].children[3].children[0].children.length,36);
  assert.equal(restored.group().children[0].children[1].children[0].open,true);
});
