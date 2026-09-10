"use strict";
const $ = (id) => document.getElementById(id);
let items = [], filter = "all", sort = "arrival", direction = 1, job = null, running = false, demoMode = false, timer = null, lastRequest = null;
const money = (value) => new Intl.NumberFormat("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(value);
const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
const storefronts = {pl:{currency:"PLN",name:"Poland"},us:{currency:"USD",name:"United States"},de:{currency:"EUR",name:"Germany"},no:{currency:"NOK",name:"Norway"},gb:{currency:"GBP",name:"United Kingdom"}};
let resultHome = "pl";
const baseline = () => storefronts[resultHome];
const unit = () => baseline().currency === "PLN" ? "zł" : baseline().currency;
function selectedHome() { return [...document.querySelectorAll('[name="home"]')].find(el => el.checked)?.value || "pl"; }
function updateSelections() {
  const home = selectedHome();
  const options = [...document.querySelectorAll('[name="region"]')];
  for (const el of options) if (el.value === home) el.checked = false;
  const count = options.filter(el => el.checked).length;
  for (const el of options) {
    el.disabled = running || el.value === home || (!el.checked && count >= 2);
    el.closest('label').hidden = el.value === home;
  }
  document.querySelectorAll('[name="home"]').forEach(el => el.disabled = running);
  $("compare-legend").textContent = `Compare ${storefronts[home].currency} with`;
  $("selection-help").textContent = `${count} of 2 selected · Uncheck one to choose another.`;
}
function showBaseline(home) {
  resultHome = Object.hasOwn(storefronts, home) ? home : "pl";
  $("home-heading").textContent = `PRICE IN ${baseline().name.toUpperCase()}`;
  $("converted-heading").textContent = `CONVERTED TO ${baseline().currency}`;
  $("difference-currency").textContent = baseline().currency;
  $("expensive-label").textContent = `Pricier in ${baseline().name}`;
}
function gameArtwork(appId) {
  const frame = node("span", undefined, "game-artwork");
  frame.setAttribute("aria-hidden", "true");
  frame.append(node("span", "No artwork", "artwork-fallback"));
  if (!/^[0-9]{1,12}$/.test(String(appId))) return frame;
  const img = node("img");
  img.alt = ""; img.width = 120; img.height = 56;
  img.loading = "lazy"; img.decoding = "async"; img.referrerPolicy = "no-referrer";
  img.addEventListener("error", () => { img.hidden = true; }, {once: true});
  img.src = `https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/${appId}/header.jpg`;
  frame.append(img);
  return frame;
}
function showProfile(profile) {
  currentProfile = profile || "";
  $("profile-attribution").textContent = profile ? `Wishlist: ${profile}` : "Saved comparison · profile was not recorded by the earlier app version";
  $("profile-attribution").hidden = false;
}
function restoreRequest(saved) {
  const request = saved?.request;
  if (!request || typeof request.identifier !== "string" || request.identifier.length > 200 || !Array.isArray(request.regions) || !request.regions.length || request.regions.length > 2 || !Object.hasOwn(storefronts, request.home || "pl") || new Set(request.regions).size !== request.regions.length || request.regions.some(region => !Object.hasOwn(storefronts, region) || region === (request.home || "pl"))) return false;
  lastRequest = {identifier: request.identifier, regions: request.regions, home: request.home || "pl"};
  document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === lastRequest.home);
  showBaseline(lastRequest.home);
  $("identifier").value = request.identifier;
  document.querySelectorAll('[name="region"]').forEach(el => el.checked = request.regions.includes(el.value));
  updateSelections();
  showProfile(request.identifier);
  return true;
}
function saleNote(price, currency) {
  const note = node("div", undefined, "sale-note");
  if (price.discount_percent == null || price.base_amount == null) {
    note.append(node("small", "Sale details unavailable"));
  } else if (price.discount_percent > 0) {
    note.append(node("span", `−${price.discount_percent}%`, "sale-badge"), node("s", `${money(price.base_amount)} ${currency}`));
  } else { note.append(node("small", "Base price · no sale")); }
  return note;
}
function hasDifferentDiscounts(comparison) {
  if (!comparison) return false;
  const known = [comparison.home_price, ...comparison.alternatives]
    .map(price => price.discount_percent).filter(value => Number.isFinite(value));
  return new Set(known).size > 1;
}
function percentageDifference(comparison) {
  const reference = Math.min(...comparison.alternatives.map(price => price.amount_in_home));
  return reference > 0 ? (comparison.home_price.amount - reference) / reference * 100 : null;
}
function percentageLabel(value) {
  if (value == null) return "Percentage unavailable";
  const rounded = Math.round(value * 10) / 10;
  return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${Math.abs(rounded).toFixed(1)}%`;
}
function saveJob(value) { try { if(value) sessionStorage.setItem("polisher-job", JSON.stringify(value)); else sessionStorage.removeItem("polisher-job"); } catch (_) {} }
function notice(text, error = false) { $("notice").textContent = text; $("notice").hidden = !text; $("notice").classList.toggle("error", error); }
function setBusy(value) { running = value; $("analyze").disabled = value; $("analyze").hidden = value; $("cancel").hidden = !value; $("cancel-label").textContent = "Cancel comparison"; $("demo").disabled = value; $("identifier").disabled = value; updateSelections(); $("progress").hidden = !value; $("progress-label").hidden = !value; $("cancel").disabled = false; $("retry").hidden = value || !lastRequest; }
function status(text, active = false) { $("status-badge").textContent = text; $("status-badge").classList.toggle("active", active); }
let currentRates = [], currentProfile = "";
const rowCache = new Map();
function render() {
  $("export-csv").disabled = !items.length;
  $("filter-help").hidden = filter !== "skipped";
  const comparable = items.filter(item => item.comparison);
  $("count-total").textContent = items.length || (running || demoMode ? "0" : "—");
  $("count-fair").textContent = comparable.filter(item => item.comparison.is_fair).length;
  $("count-expensive").textContent = comparable.filter(item => !item.comparison.is_fair).length;
  const search = $("search").value.trim().toLocaleLowerCase();
  const hiddenUnavailable = item => ["no_regional_price", "app_unavailable"].includes(item.skipped?.category);
  const showUnavailable = $("show-unavailable").checked;
  const hiddenCount = showUnavailable ? 0 : items.filter(hiddenUnavailable).length;
  const visible = items.filter(item => (showUnavailable || !hiddenUnavailable(item)) && item.name.toLocaleLowerCase().includes(search) && (filter === "all" || (filter === "discounts" ? hasDifferentDiscounts(item.comparison) : filter === "skipped" ? !item.comparison : item.comparison && item.comparison.is_fair === (filter === "fair"))));
  const diff = item => item.comparison ? item.comparison.home_price.amount - Math.min(...item.comparison.alternatives.map(p => p.amount_in_home)) : null;
  if (sort !== "arrival") visible.sort((a, b) => { if(sort === "name") return direction * a.name.localeCompare(b.name); const value = item => sort === "home" ? item.comparison?.home_price.amount : sort === "percentage" ? (item.comparison ? percentageDifference(item.comparison) : null) : diff(item); const av = value(a), bv = value(b); if(av == null) return bv == null ? 0 : 1; if(bv == null) return -1; return direction * (av - bv); });
  const rows = $("rows");
  const visibleIds = new Set(visible.map(item => item.app_id));
  for (const row of [...rows.children]) {
    if (!visibleIds.has(row.dataset.appId)) row.remove();
  }
  const currentIds = new Set(items.map(item => item.app_id));
  for (const id of rowCache.keys()) if (!currentIds.has(id)) rowCache.delete(id);
  let position = 0;
  for (const item of visible) {
    const signature = resultHome + JSON.stringify(item);
    let cached = rowCache.get(item.app_id);
    if (!cached || cached.signature !== signature) {
    const tr = node("tr"), title = node("td");
    tr.dataset.appId = item.app_id;
    const link = node("a", undefined, "game-name"); link.append(gameArtwork(item.app_id), node("span", item.name + " ↗", "game-title")); link.href = `https://store.steampowered.com/app/${encodeURIComponent(item.app_id)}/`; link.target = "_blank"; link.rel = "noopener noreferrer"; title.append(link, node("div", item.source_summary || "", "game-meta")); tr.append(title);
    if(item.comparison) {
      const c = item.comparison;
      if (hasDifferentDiscounts(c)) {
        const badge = node("span", "Different regional discounts", "regional-discount-badge");
        const values = [{...c.home_price, region: c.home_price.region || resultHome}, ...c.alternatives].map(price =>
          `${price.region.toUpperCase()}: ${Number.isFinite(price.discount_percent) ? price.discount_percent + "% off" : "sale details unavailable"}`);
        badge.title = values.join(" · ") + ". Observed discounts differ; regional prices may have been checked at different times.";
        title.append(badge);
      }
      const home = node("td", `${money(c.home_price.amount)} ${unit()}`, "price"); home.append(saleNote(c.home_price, baseline().currency)); tr.append(home);
      const td = node("td"), alternatives = node("div", undefined, "foreign");
      for (const p of c.alternatives) { const price = node("span"); price.append(node("small", p.region.toUpperCase()), node("span", money(p.amount_in_home) + " " + unit())); price.title = `${money(p.original_amount)} ${p.currency} × ${p.rate_to_home}`; price.append(saleNote(p, p.currency)); alternatives.append(price); } td.append(alternatives); tr.append(td);
      const delta = diff(item), difference = node("td", `${delta > 0 ? "+" : delta < 0 ? "−" : ""}${money(Math.abs(delta))} ${unit()}`, "difference" + (c.is_fair ? " fair" : "")); const percentage = node("span", percentageLabel(percentageDifference(c)), "difference-percent");
      percentage.title = percentageDifference(c) == null ? "Cannot calculate a percentage against a zero reference price." : `Compared with the cheapest selected foreign price, converted to ${baseline().currency}.`;
      difference.append(percentage); difference.append(node("small", c.is_fair ? "Cheaper / equal" : `Pricier in ${baseline().name}`)); tr.append(difference);
    } else { const td = node("td", item.skipped?.reason || "Could not compare this game.", "skip-reason"); td.colSpan = 3; tr.append(td); }
    if (cached) cached.row.remove();
    cached = {row: tr, signature};
    rowCache.set(item.app_id, cached);
    }
    // Keep existing DOM nodes in place on each poll; only insert new/moved rows.
    const current = rows.children[position];
    if (current !== cached.row) rows.insertBefore(cached.row, current || null);
    position++;
  }
  $("empty").hidden = visible.length > 0;
  if(!visible.length && (items.length || running)) { $("empty").querySelector("h3").textContent = items.length ? "No games match these filters." : "Checking your wishlist…"; $("empty").querySelector("p").textContent = items.length ? "Try another filter or game name." : "Results appear as each game is checked. Steam requests are paced to respect its limits."; }
  $("row-count").textContent = `${visible.length} of ${items.length} games${hiddenCount ? ` · ${hiddenCount} unavailable hidden` : ""}${demoMode ? " · illustrative example" : ""}`;
  $("arrival-order").setAttribute("aria-pressed", String(sort === "arrival"));
  $("order-note").textContent = sort === "arrival" ? "New games append at the end" : "Sorted results · new games follow this sort";
  document.querySelectorAll('.sort').forEach(button => {
    button.closest('th').removeAttribute('aria-sort');
    button.setAttribute('aria-pressed', String(button.dataset.sort === sort));
  });
  document.querySelectorAll('.sort').forEach(button => {
    if (button.dataset.sort === sort) button.closest('th').setAttribute('aria-sort', direction === 1 ? 'ascending' : 'descending');
  });
}
function showRates(rates) { currentRates = rates; const target = $("rates"); target.replaceChildren(); for(const rate of rates) { const row = node("div", undefined, "rate-line"), label = node("span", `1 ${rate.currency}`); label.append(node("small", `${rate.effective_date || "Date unknown"} · ${rate.cache_status}`)); row.append(label, node("span", `${money(rate.rate_to_pln)} PLN`)); target.append(row); } if(!rates.length) target.append(node("p", "Loading exchange rates…", "rate-placeholder")); }
async function request(path, options = {}) { const response = await fetch(path, {cache: "no-store", ...options, headers: {"Content-Type": "application/json", ...(options.headers || {})}}); const data = await response.json(); if(!response.ok) { const error = new Error(data.error || "The request could not be completed."); error.status = response.status; throw error; } return data; }
async function start(body) {
  clearTimeout(timer); sort = "arrival"; job = null; saveJob(null); demoMode = false; items = []; lastRequest = body; showBaseline(body.home || "pl"); showProfile(body.identifier); $("search").value = ""; notice(""); setBusy(true); $("cancel").disabled = true; $("cancel-label").textContent = "Connecting…"; status("CONNECTING", true); $("results-title").textContent = "Your price comparison"; $("progress-label").textContent = "Loading wishlist…"; $("progress").value = 0; showRates([]); render();
  try { job = await request("/api/jobs", {method: "POST", body: JSON.stringify(body)}); saveJob({...job, request: body}); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; poll(); } catch(error) { setBusy(false); status("COULD NOT START"); notice(error.message, true); }
}
async function poll() {
  try {
    const data = await request(`/api/jobs/${job.id}`, {headers: {Authorization: `Bearer ${job.token}`}});
    if (data.profile && !lastRequest) {
      restoreRequest({request: {identifier: data.profile, regions: data.regions, home: data.home || "pl"}});
      saveJob({...job, request: lastRequest});
    }
    showBaseline(data.home || "pl"); items = data.items; showRates(data.rates); render();
    const complete = ["complete", "partial", "cancelled", "failed"].includes(data.state);
    status(data.state.toUpperCase(), !complete); if (data.state === "cancelling") { $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; } $("progress-label").textContent = data.message; $("progress").max = Math.max(data.total, 1); $("progress").value = data.items.length;
    if(data.error) notice(data.error, true); else if(data.state === "partial") notice("Some games could not be compared because a request failed. Retry to reuse completed prices and check the remaining games."); else if(data.warnings.length) notice(data.warnings.join(" ")); else if(data.state === "cancelled") notice("Comparison cancelled. Completed regional prices are cached for your next attempt."); else notice("");
    if(complete) { setBusy(false); if(!items.length) { $("empty").querySelector("h3").textContent = data.state === "cancelled" ? "Comparison cancelled." : "No results this time."; $("empty").querySelector("p").textContent = "Check your profile and make sure your wishlist is public, then try again."; } } else timer = setTimeout(poll, 1200);
  } catch(error) { if(error.status === 404) { saveJob(null); setBusy(false); status("COMPARISON EXPIRED"); notice(error.message, true); return; } status("CONNECTION INTERRUPTED"); notice("Connection interrupted. Reconnecting to your comparison…", true); timer = setTimeout(poll, 4000); }
}
// Quote every field and neutralize spreadsheet formulas in untrusted text.
function csvCell(value) {
  let text = value == null ? "" : String(value);
  if (typeof value === "string" && /^[\s]*[=+@-]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
function buildCsv(includeOwner, exportedAt = new Date().toISOString()) {
  const headers = ["exported_at_utc", "example_data", "game_id", "game", "status", "storefront", "currency", "final_price", "base_price", "discount_percent", "rate_to_pln", "rate_publication_date", "rate_retrieved_at_utc", "rate_checked_at_utc", "rate_source", "rate_cache_status", "final_price_baseline", "baseline_difference", "baseline_difference_percent", "different_regional_discounts", "price_provenance", "baseline_storefront", "baseline_currency", "rate_to_baseline", "baseline_rate_to_pln", "baseline_rate_publication_date", "baseline_rate_retrieved_at_utc", "baseline_rate_checked_at_utc", "baseline_rate_cache_status"];
  if (includeOwner) headers.push("wishlist_profile");
  const rows = [headers];
  for (const item of items) {
    const c = item.comparison;
    const prices = c ? [{...c.home_price, region:resultHome, currency:baseline().currency, original_amount:c.home_price.amount, amount_in_home:c.home_price.amount}, ...c.alternatives] : [{}];
    for (const price of prices) {
      const rate = currentRates.find(value => value.currency === price.currency) || {};
      const identity = price.currency === "PLN";
      const reference = c ? Math.min(...c.alternatives.map(value => value.amount_in_home)) : null;
      const row = [exportedAt, demoMode, item.app_id, item.name, c ? "compared" : item.skipped?.category,
        price.region, price.currency, price.original_amount, price.base_amount, price.discount_percent,
        identity ? 1 : rate.rate_to_pln, rate.effective_date, rate.retrieved_at_utc, rate.checked_at_utc,
        identity ? "Identity conversion" : rate.source, identity ? "identity" : rate.cache_status,
        price.amount_in_home, c ? c.home_price.amount - reference : null, c ? percentageDifference(c) : null,
        c ? hasDifferentDiscounts(c) : null, item.source_summary];
      const homeRate = currentRates.find(value => value.currency === baseline().currency) || {};
      row.push(resultHome, baseline().currency, c ? (price.region === resultHome ? 1 : price.rate_to_home) : null,
        baseline().currency === "PLN" ? 1 : homeRate.rate_to_pln, homeRate.effective_date,
        homeRate.retrieved_at_utc, homeRate.checked_at_utc, baseline().currency === "PLN" ? "identity" : homeRate.cache_status);
      if (includeOwner) row.push(currentProfile);
      rows.push(row);
    }
  }
  return "\uFEFF" + rows.map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
$("export-csv").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([buildCsv($("export-owner").checked)], {type:"text/csv;charset=utf-8"}));
  const link = node("a"); link.href = url; link.download = "steam-price-comparison.csv";
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("compare-form").addEventListener("submit", event => { event.preventDefault(); const regions = [...document.querySelectorAll('[name="region"]:checked')].map(el => el.value); if(!regions.length || regions.length > 2) return notice("Choose one or two comparison currencies.", true); start({identifier: $("identifier").value.trim(), regions, home: selectedHome()}); });
document.querySelectorAll('[name="home"], [name="region"]').forEach(el => el.addEventListener("change", updateSelections));
updateSelections();
$("cancel").addEventListener("click", async () => { if(!job) return; $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; try { await request(`/api/jobs/${job.id}/cancel`, {method: "POST", body: "{}", headers: {Authorization: `Bearer ${job.token}`}}); $("progress-label").textContent = "Cancelling — waiting for the current request to finish…"; } catch(error) { notice(error.message, true); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; } });
$("retry").addEventListener("click", () => { if(lastRequest) start(lastRequest); });
$("search").addEventListener("input", render);
$("show-unavailable").addEventListener("change", render);
$("arrival-order").addEventListener("click", () => { sort = "arrival"; direction = 1; render(); });
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; document.querySelectorAll('.filter').forEach(el => { el.classList.toggle('active', el === button); el.setAttribute('aria-pressed', String(el === button)); }); render(); }));
document.querySelectorAll('.sort').forEach(button => button.addEventListener('click', () => { direction = sort === button.dataset.sort ? -direction : 1; sort = button.dataset.sort; render(); }));
$("demo").addEventListener("click", () => {
  clearTimeout(timer); job = null; saveJob(null); lastRequest = null; currentProfile = ""; $("profile-attribution").textContent = "Illustrative wishlist · not linked to a Steam profile"; $("profile-attribution").hidden = false; demoMode = true; setBusy(false); $("retry").hidden = true; $("search").value = ""; status("EXAMPLE · NOT LIVE"); $("results-title").textContent = "A wishlist, in perspective";
  notice("Illustrative example: these prices and exchange rates are invented to show how the comparison works. Run your wishlist for actual data.");
  const examples = [["413150", "Stardew Valley", 53.99, 14.99, 13.99], ["1145360", "Hades", 114.99, 24.99, 24.50], ["1091500", "Cyberpunk 2077", 199.99, 59.99, 59.99], ["640820", "Pathfinder: Kingmaker", 89.99, 19.99, 19.99], ["1245620", "ELDEN RING", 249, 59.99, 59.99], ["367520", "Hollow Knight", 67.99, 14.99, 14.79]];
  showBaseline(selectedHome());
  const demoRates = {PLN:1,USD:4,EUR:4.3,NOK:0.37,GBP:5.1};
  const selected = [...document.querySelectorAll('[name="region"]')].filter(el => el.checked).map(el => el.value);
  const regions = selected.length ? selected : Object.keys(storefronts).filter(region => region !== resultHome).slice(0,2);
  items = examples.map(([app_id, name, amount, usd, eur]) => {
    const prices = {pl:amount,us:usd,de:eur,no:Math.round(eur*11.5),gb:Math.round(usd*0.8*100)/100};
    const homeAmount = prices[resultHome];
    const alternatives = regions.map(region => { const currency = storefronts[region].currency; const rate_to_home = demoRates[currency]/demoRates[baseline().currency]; return {region,currency,original_amount:prices[region],rate_to_home,amount_in_home:prices[region]*rate_to_home}; });
    return {app_id,name,source_summary:"Illustrative prices",comparison:{home_price:{region:resultHome,amount:homeAmount,currency:baseline().currency},alternatives,is_fair:alternatives.every(price => homeAmount <= price.amount_in_home)}};
  });
  showRates([resultHome,...regions].map(region => ({currency:storefronts[region].currency,rate_to_pln:demoRates[storefronts[region].currency],effective_date:"Illustrative",cache_status:"example"}))); render();
});

// Optional agent controls share the same visible result filters.
if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  window.addEventListener("pagehide", () => lifecycle.abort(), {once: true});
  try {
    Promise.resolve(document.modelContext.registerTool({
      name: "filter_wishlist_results", title: "Filter wishlist results",
      description: "Filter the current comparison by game name and price category, updating the visible table.",
      inputSchema: {type: "object", properties: {search: {type: "string", maxLength: 200}, category: {type: "string", enum: ["all", "fair", "expensive", "discounts", "skipped"]}}, required: ["search", "category"], additionalProperties: false},
      annotations: {readOnlyHint: false, untrustedContentHint: true},
      execute(input) {
        if (!input || typeof input.search !== "string" || input.search.length > 200 || !["all", "fair", "expensive", "discounts", "skipped"].includes(input.category)) throw new Error("Invalid result filter");
        $("search").value = input.search;
        document.querySelector(`[data-filter="${input.category}"]`).click();
        return {summary: $("row-count").textContent, example: demoMode};
      }
    }, {signal: lifecycle.signal})).catch(() => {});
  } catch (_) { /* Unsupported experimental API does not affect the app. */ }
}

try {
  const saved = JSON.parse(sessionStorage.getItem("polisher-job") || "null");
  if(saved && /^[A-Za-z0-9_-]{32}$/.test(saved.id) && /^[A-Za-z0-9_-]{43}$/.test(saved.token)) {
    job = {id: saved.id, token: saved.token}; if (!restoreRequest(saved)) showProfile(null); setBusy(true); status("RECONNECTING", true); poll();
  }
} catch (_) { saveJob(null); }
