"use strict";
const $ = (id) => document.getElementById(id);
let items = [], filter = "all", sort = "arrival", direction = 1, job = null, running = false, demoMode = false, timer = null, lastRequest = null;
const money = (value) => new Intl.NumberFormat("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(value);
const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
function showProfile(profile) {
  $("profile-attribution").textContent = profile ? `Wishlist: ${profile}` : "Saved comparison · profile was not recorded by the earlier app version";
  $("profile-attribution").hidden = false;
}
function restoreRequest(saved) {
  const request = saved?.request;
  if (!request || typeof request.identifier !== "string" || request.identifier.length > 200 || !Array.isArray(request.regions) || !request.regions.length || request.regions.some(region => !["us", "de"].includes(region))) return false;
  lastRequest = {identifier: request.identifier, regions: request.regions};
  $("identifier").value = request.identifier;
  document.querySelectorAll('[name="region"]').forEach(el => el.checked = request.regions.includes(el.value));
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
function saveJob(value) { try { if(value) sessionStorage.setItem("polisher-job", JSON.stringify(value)); else sessionStorage.removeItem("polisher-job"); } catch (_) {} }
function notice(text, error = false) { $("notice").textContent = text; $("notice").hidden = !text; $("notice").classList.toggle("error", error); }
function setBusy(value) { running = value; $("analyze").disabled = value; $("analyze").hidden = value; $("cancel").hidden = !value; $("cancel-label").textContent = "Cancel comparison"; $("demo").disabled = value; $("identifier").disabled = value; document.querySelectorAll('[name="region"]').forEach(el => el.disabled = value); $("progress").hidden = !value; $("progress-label").hidden = !value; $("cancel").disabled = false; $("retry").hidden = value || !lastRequest; }
function status(text, active = false) { $("status-badge").textContent = text; $("status-badge").classList.toggle("active", active); }
const rowCache = new Map();
function render() {
  const comparable = items.filter(item => item.comparison);
  $("count-total").textContent = items.length || (running || demoMode ? "0" : "—");
  $("count-fair").textContent = comparable.filter(item => item.comparison.is_fair).length;
  $("count-expensive").textContent = comparable.filter(item => !item.comparison.is_fair).length;
  const search = $("search").value.trim().toLocaleLowerCase();
  const hiddenUnavailable = item => ["no_regional_price", "app_unavailable"].includes(item.skipped?.category);
  const showUnavailable = $("show-unavailable").checked;
  const hiddenCount = showUnavailable ? 0 : items.filter(hiddenUnavailable).length;
  const visible = items.filter(item => (showUnavailable || !hiddenUnavailable(item)) && item.name.toLocaleLowerCase().includes(search) && (filter === "all" || (filter === "skipped" ? !item.comparison : item.comparison && item.comparison.is_fair === (filter === "fair"))));
  const diff = item => item.comparison ? item.comparison.home_price.amount - Math.min(...item.comparison.alternatives.map(p => p.amount_in_home)) : null;
  if (sort !== "arrival") visible.sort((a, b) => { if(sort === "name") return direction * a.name.localeCompare(b.name); const av = sort === "home" ? a.comparison?.home_price.amount : diff(a); const bv = sort === "home" ? b.comparison?.home_price.amount : diff(b); if(av == null) return bv == null ? 0 : 1; if(bv == null) return -1; return direction * (av - bv); });
  const rows = $("rows");
  const visibleIds = new Set(visible.map(item => item.app_id));
  for (const row of [...rows.children]) {
    if (!visibleIds.has(row.dataset.appId)) row.remove();
  }
  const currentIds = new Set(items.map(item => item.app_id));
  for (const id of rowCache.keys()) if (!currentIds.has(id)) rowCache.delete(id);
  let position = 0;
  for (const item of visible) {
    const signature = JSON.stringify(item);
    let cached = rowCache.get(item.app_id);
    if (!cached || cached.signature !== signature) {
    const tr = node("tr"), title = node("td");
    tr.dataset.appId = item.app_id;
    const link = node("a", item.name + " ↗", "game-name"); link.href = `https://store.steampowered.com/app/${encodeURIComponent(item.app_id)}/`; link.target = "_blank"; link.rel = "noopener noreferrer"; title.append(link, node("div", item.source_summary || "", "game-meta")); tr.append(title);
    if(item.comparison) {
      const c = item.comparison; const home = node("td", `${money(c.home_price.amount)} zł`, "price"); home.append(saleNote(c.home_price, "PLN")); tr.append(home);
      const td = node("td"), alternatives = node("div", undefined, "foreign");
      for (const p of c.alternatives) { const price = node("span"); price.append(node("small", p.region.toUpperCase()), node("span", money(p.amount_in_home) + " zł")); price.title = `${money(p.original_amount)} ${p.currency} × ${p.rate_to_home}`; price.append(saleNote(p, p.currency)); alternatives.append(price); } td.append(alternatives); tr.append(td);
      const delta = diff(item), difference = node("td", `${delta > 0 ? "+" : delta < 0 ? "−" : ""}${money(Math.abs(delta))} zł`, "difference" + (c.is_fair ? " fair" : "")); difference.append(node("small", c.is_fair ? "Cheaper / equal" : "Pricier in Poland")); tr.append(difference);
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
  document.querySelectorAll('.sort').forEach(button => { const th = button.closest('th'); th.removeAttribute('aria-sort'); if(button.dataset.sort === sort) th.setAttribute('aria-sort', direction === 1 ? 'ascending' : 'descending'); });
}
function showRates(rates) { const target = $("rates"); target.replaceChildren(); for(const rate of rates) { const row = node("div", undefined, "rate-line"), label = node("span", `1 ${rate.currency}`); label.append(node("small", `${rate.effective_date || "Date unknown"} · ${rate.cache_status}`)); row.append(label, node("span", `${money(rate.rate_to_pln)} PLN`)); target.append(row); } if(!rates.length) target.append(node("p", "Loading exchange rates…", "rate-placeholder")); }
async function request(path, options = {}) { const response = await fetch(path, {cache: "no-store", ...options, headers: {"Content-Type": "application/json", ...(options.headers || {})}}); const data = await response.json(); if(!response.ok) { const error = new Error(data.error || "The request could not be completed."); error.status = response.status; throw error; } return data; }
async function start(body) {
  clearTimeout(timer); sort = "arrival"; job = null; saveJob(null); demoMode = false; items = []; lastRequest = body; showProfile(body.identifier); $("search").value = ""; notice(""); setBusy(true); $("cancel").disabled = true; $("cancel-label").textContent = "Connecting…"; status("CONNECTING", true); $("results-title").textContent = "Your price comparison"; $("progress-label").textContent = "Loading wishlist…"; $("progress").value = 0; showRates([]); render();
  try { job = await request("/api/jobs", {method: "POST", body: JSON.stringify(body)}); saveJob({...job, request: body}); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; poll(); } catch(error) { setBusy(false); status("COULD NOT START"); notice(error.message, true); }
}
async function poll() {
  try {
    const data = await request(`/api/jobs/${job.id}`, {headers: {Authorization: `Bearer ${job.token}`}});
    if (data.profile && !lastRequest) {
      restoreRequest({request: {identifier: data.profile, regions: data.regions}});
      saveJob({...job, request: lastRequest});
    }
    items = data.items; showRates(data.rates); render();
    const complete = ["complete", "partial", "cancelled", "failed"].includes(data.state);
    status(data.state.toUpperCase(), !complete); if (data.state === "cancelling") { $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; } $("progress-label").textContent = data.message; $("progress").max = Math.max(data.total, 1); $("progress").value = data.items.length;
    if(data.error) notice(data.error, true); else if(data.state === "partial") notice("Some games could not be compared because a request failed. Retry to reuse completed prices and check the remaining games."); else if(data.warnings.length) notice(data.warnings.join(" ")); else if(data.state === "cancelled") notice("Comparison cancelled. Completed regional prices are cached for your next attempt."); else notice("");
    if(complete) { setBusy(false); if(!items.length) { $("empty").querySelector("h3").textContent = data.state === "cancelled" ? "Comparison cancelled." : "No results this time."; $("empty").querySelector("p").textContent = "Check your profile and make sure your wishlist is public, then try again."; } } else timer = setTimeout(poll, 1200);
  } catch(error) { if(error.status === 404) { saveJob(null); setBusy(false); status("COMPARISON EXPIRED"); notice(error.message, true); return; } status("CONNECTION INTERRUPTED"); notice("Connection interrupted. Reconnecting to your comparison…", true); timer = setTimeout(poll, 4000); }
}
$("compare-form").addEventListener("submit", event => { event.preventDefault(); const regions = [...document.querySelectorAll('[name="region"]:checked')].map(el => el.value); if(!regions.length) return notice("Choose at least one comparison storefront.", true); start({identifier: $("identifier").value.trim(), regions}); });
$("cancel").addEventListener("click", async () => { if(!job) return; $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; try { await request(`/api/jobs/${job.id}/cancel`, {method: "POST", body: "{}", headers: {Authorization: `Bearer ${job.token}`}}); $("progress-label").textContent = "Cancelling — waiting for the current request to finish…"; } catch(error) { notice(error.message, true); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; } });
$("retry").addEventListener("click", () => { if(lastRequest) start(lastRequest); });
$("search").addEventListener("input", render);
$("show-unavailable").addEventListener("change", render);
$("arrival-order").addEventListener("click", () => { sort = "arrival"; direction = 1; render(); });
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; document.querySelectorAll('.filter').forEach(el => { el.classList.toggle('active', el === button); el.setAttribute('aria-pressed', String(el === button)); }); render(); }));
document.querySelectorAll('.sort').forEach(button => button.addEventListener('click', () => { direction = sort === button.dataset.sort ? -direction : 1; sort = button.dataset.sort; render(); }));
$("demo").addEventListener("click", () => {
  clearTimeout(timer); job = null; saveJob(null); lastRequest = null; $("profile-attribution").textContent = "Illustrative wishlist · not linked to a Steam profile"; $("profile-attribution").hidden = false; demoMode = true; setBusy(false); $("retry").hidden = true; $("search").value = ""; status("EXAMPLE · NOT LIVE"); $("results-title").textContent = "A wishlist, in perspective";
  notice("Illustrative example: these prices and exchange rates are invented to show how the comparison works. Run your wishlist for actual data.");
  const examples = [["413150", "Stardew Valley", 53.99, 14.99, 13.99], ["1145360", "Hades", 114.99, 24.99, 24.50], ["1091500", "Cyberpunk 2077", 199.99, 59.99, 59.99], ["640820", "Pathfinder: Kingmaker", 89.99, 19.99, 19.99], ["1245620", "ELDEN RING", 249, 59.99, 59.99], ["367520", "Hollow Knight", 67.99, 14.99, 14.79]];
  items = examples.map(([app_id, name, amount, usd, eur]) => { const alternatives = [{region:"us",currency:"USD",original_amount:usd,rate_to_home:4,amount_in_home:usd*4},{region:"de",currency:"EUR",original_amount:eur,rate_to_home:4.3,amount_in_home:eur*4.3}]; return {app_id, name, source_summary:"Illustrative prices",comparison:{home_price:{amount,currency:"PLN"},alternatives,is_fair:alternatives.every(p => amount <= p.amount_in_home)}}; });
  showRates([{currency:"USD",rate_to_pln:4,effective_date:"Illustrative",cache_status:"example"},{currency:"EUR",rate_to_pln:4.3,effective_date:"Illustrative",cache_status:"example"}]); render();
});

// Optional agent controls share the same visible result filters.
if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  window.addEventListener("pagehide", () => lifecycle.abort(), {once: true});
  try {
    Promise.resolve(document.modelContext.registerTool({
      name: "filter_wishlist_results", title: "Filter wishlist results",
      description: "Filter the current comparison by game name and price category, updating the visible table.",
      inputSchema: {type: "object", properties: {search: {type: "string", maxLength: 200}, category: {type: "string", enum: ["all", "fair", "expensive", "skipped"]}}, required: ["search", "category"], additionalProperties: false},
      annotations: {readOnlyHint: false, untrustedContentHint: true},
      execute(input) {
        if (!input || typeof input.search !== "string" || input.search.length > 200 || !["all", "fair", "expensive", "skipped"].includes(input.category)) throw new Error("Invalid result filter");
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
