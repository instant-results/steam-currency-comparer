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
  focus() { this.focused = true; }
}
function setup(selectors = {}, extras = {}) {
  const elements = new Map();
  const get = id => { if(!elements.has(id)) elements.set(id, new Element("div")); return elements.get(id); };
  const context = vm.createContext({Intl, console, document: {getElementById: get, createElement: tag => new Element(tag), querySelectorAll: query => selectors[query] || []}, sessionStorage: {getItem: () => null}, window: {}, ...extras});
  vm.runInContext(fs.readFileSync("web/app.js", "utf8"), context);
  return {get, run: source => vm.runInContext(source, context)};
}
const game = (id, name) => ({app_id:id, name, comparison:{home_price:{amount:10}, alternatives:[{region:"us", original_amount:5, currency:"USD", rate_to_home:4, amount_in_home:20}], is_fair:true}});
const skipped = (id, category) => ({app_id:id, name:id, skipped:{category, reason:category}});

const settle = async () => { for (let i = 0; i < 4; i++) await new Promise(setImmediate); };
function creatorSetup(savedValues = {}, kind = "developer") {
  const examples = [{app_id:"1",name:"First"},{app_id:"2",name:"Second"},{app_id:"3",name:"Third"}];
  const registry = [{id:"studio",name:"Studio",selector:{kind,name:"Studio"},role:kind,homepage:"https://store.steampowered.com/developer/studio/",icon:"https://avatars.fastly.steamstatic.com/icon.jpg",examples}];
  const storage = new Map(Object.entries(savedValues)), calls = [], snapshots = [], searches = [], timers = new Map();
  let timerId = 0;
  const radios = Object.keys({pl:1,us:1,de:1,no:1,gb:1}).map(value => { const el = new Element("input"); el.value = value; el.name = "home"; el.checked = value === "pl"; return el; });
  const regions = radios.map(radio => { const el = new Element("input"); el.value = radio.value; el.name = "region"; el.checked = ["us","de"].includes(el.value); const label = new Element("label"); el.closest = () => label; return el; });
  const selectors = {'[name="home"]':radios,'[name="region"]':regions,'[name="region"]:checked':regions.filter(el => el.checked)};
  const testContext = setup(selectors, {
    sessionStorage:{getItem:key => storage.get(key) || null,setItem:(key,value) => storage.set(key,value)},
    setTimeout:callback => { timers.set(++timerId, callback); return timerId; }, clearTimeout:id => timers.delete(id),
    fetch:async (path, options = {}) => {
      calls.push({path,body:options.body ? JSON.parse(options.body) : null});
      let data;
      if (path === "/api/creators") data = {developers:registry.map(c => ({...c,selector:{kind:"developer",name:c.name}})),
        publishers:registry.map(c => ({...c,selector:{kind:"publisher",name:c.name}}))};
      else if (path === "/api/creators/search") {
        data = searches.shift() || {creators: [], exact_matches: []};
        if (data.error) return {ok:false, json:async () => data};
      }
      else if (path === "/api/creator-jobs") data = {id:"a".repeat(32),token:"b".repeat(43)};
      else if (path.endsWith("/cancel")) data = {state:"cancelling"};
      else data = snapshots.shift() || {state:"complete",message:"Checked 3 games.",catalogs:{},items:examples.map(item => game(item.app_id,item.name)),rates:[],warnings:[]};
      return {ok:true,json:async () => data};
    }
  });
  testContext.run(fs.readFileSync("web/creators.js", "utf8"));
  const get = id => testContext.get(id.replace(/^creators-/, kind + "s-").replace(/^creator-/, kind + "-"));
  const group = () => get("creator-groups").children[0];
  const body = () => group().children[1].children[0].children[0].children[2];
  return {...testContext,get,calls,storage,snapshots,searches,radios,regions,timers,group,body};
}

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
  ctx.run("running = true; window.creatorPane.refreshControls();");
  assert.equal(ctx.get("creator-search-results").children[0].children[1].children[0].disabled,true);
  ctx.run("running = false;");
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
  assert.equal(JSON.parse(ctx.storage.get("polisher-developer-job")).catalogs[0].nextStart, 0);
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
  const comparison = (id, home, usd, eur, fair = false) => ({app_id:id,name:id,comparison:{
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
  const ctx = creatorSetup(); ctx.run("running = true;");
  ctx.get("creators-tab").listeners.click(); await settle();
  assert.ok(!ctx.calls.some(call => call.path === "/api/creator-jobs"));
  assert.match(ctx.get("creators-progress").textContent, /Waiting for the current comparison/);
  ctx.run("running = false;");
  ctx.snapshots.push({state:"running",message:"Checking",catalogs:{},items:[],rates:[],warnings:[]});
  [...ctx.timers.values()][0](); await settle();
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

test("three-tab keyboard navigation wraps and supports Home and End", async () => {
  const ctx = creatorSetup();
  ctx.get("wishlist-tab").listeners.keydown({key:"ArrowLeft",preventDefault(){}}); await settle();
  assert.equal(ctx.get("publishers-tab").attributes["aria-selected"],"true");
  assert.equal(ctx.get("publishers-tab").focused,true);
  ctx.get("publishers-tab").listeners.keydown({key:"Home",preventDefault(){}});
  assert.equal(ctx.get("wishlist-tab").attributes["aria-selected"],"true");
  ctx.get("wishlist-tab").listeners.keydown({key:"ArrowRight",preventDefault(){}}); await settle();
  assert.equal(ctx.get("creators-tab").attributes["aria-selected"],"true");
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
