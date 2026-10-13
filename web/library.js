"use strict";

// Personal library state is independent; row rendering and CSV are shared.
(() => {
  // Keep saved state untouched and make no requests while the feature is deferred.
  if (document.documentElement?.dataset.ownedLibraryEnabled !== "true") return;
  const $ = id => document.getElementById(`library-${id}`);
  const storageKey = "polisher-library-job";
  const terminal = new Set(["complete", "partial", "cancelled", "failed"]);
  let active = false, busy = false, items = [], rates = [], home = "pl";
  let job = null, lastRequest = null, timer = null, state = "ready", message = "";
  let filter = "all", sort = "arrival", direction = 1;
  const rows = new Map();
  const buttons = selector => document.querySelectorAll(selector);
  function notice(text, error = false) {
    $("notice").textContent = text; $("notice").hidden = !text;
    $("notice").classList.toggle("error", error);
  }
  function save() {
    try { sessionStorage.setItem(storageKey, JSON.stringify({job, request:lastRequest, items, rates, home,
      state, message, filter, sort, direction, search:$("search").value,
      showUnavailable:$("show-unavailable").checked, includeOwner:$("export-owner").checked})); } catch (_) {}
  }
  function refreshControls() {
    const locked = busy || running || !!window.creatorPane?.busy;
    $("analyze").disabled = locked; $("analyze").hidden = busy;
    $("identifier").disabled = busy; $("wishlist-order").disabled = busy;
    $("cancel").hidden = !busy; $("cancel").disabled = !job || state === "cancelling";
    $("cancel-label").textContent = state === "cancelling" ? "Cancelling…" : "Cancel comparison";
    $("retry").hidden = busy || !lastRequest; $("retry").disabled = locked;
    $("export-csv").disabled = !items.length;
    $("progress").hidden = !busy; $("progress-label").hidden = !busy;
  }
  function setBusy(value) { busy = value; updateSelections(); }
  function showLibraryRates() {
    if (!active) return;
    const target = document.getElementById("rates");
    if (rates.length || busy) renderRates(rates, target);
    else target.replaceChildren(node("p", "Rates appear when you run a comparison.", "rate-placeholder"));
  }
  function render() {
    $("home-heading").textContent = `PRICE IN ${storefronts[home].name.toUpperCase()}`;
    $("converted-heading").textContent = `CONVERTED TO ${storefronts[home].currency}`;
    $("difference-currency").textContent = storefronts[home].currency;
    $("expensive-label").textContent = `Pricier in ${storefronts[home].name}`;
    $("profile-attribution").textContent = lastRequest ? `Library: ${lastRequest.identifier}` : "";
    $("profile-attribution").hidden = !lastRequest;
    const compared = items.filter(item => item.comparison);
    $("count-total").textContent = items.length || (lastRequest ? "0" : "—");
    $("count-fair").textContent = compared.filter(item => item.comparison.is_fair).length;
    $("count-expensive").textContent = compared.filter(item => !item.comparison.is_fair).length;
    $("filter-help").hidden = filter !== "skipped";
    const unavailable = item => ["no_regional_price", "app_unavailable"].includes(item.skipped?.category);
    const showUnavailable = $("show-unavailable").checked;
    const search = $("search").value.trim().toLocaleLowerCase();
    const visible = items.filter(item => (showUnavailable || !unavailable(item)) && item.name.toLocaleLowerCase().includes(search)
      && (filter === "all" || (filter === "discounts" ? hasDifferentDiscounts(item.comparison)
        : filter === "skipped" ? !item.comparison : item.comparison && item.comparison.is_fair === (filter === "fair"))));
    const value = item => sort === "home" ? item.comparison?.home_price.amount
      : sort === "percentage" ? (item.comparison ? percentageDifference(item.comparison) : null)
      : item.comparison ? item.comparison.home_price.amount - Math.min(...item.comparison.alternatives.map(price => price.amount_in_home)) : null;
    if (sort !== "arrival") visible.sort((a,b) => {
      if (sort === "name") return direction * a.name.localeCompare(b.name);
      const av = value(a), bv = value(b);
      return av == null ? (bv == null ? 0 : 1) : bv == null ? -1 : direction * (av - bv);
    });
    const body = $("rows"), ids = new Set(visible.map(item => item.app_id));
    for (const row of [...body.children]) if (!ids.has(row.dataset.appId)) row.remove();
    const allIds = new Set(items.map(item => item.app_id));
    for (const id of rows.keys()) if (!allIds.has(id)) rows.delete(id);
    visible.forEach((item, index) => {
      const signature = home + JSON.stringify(item);
      let cached = rows.get(item.app_id);
      if (!cached || cached.signature !== signature) {
        cached?.row.remove(); cached = {signature, row:comparisonRow(item, home, true)}; rows.set(item.app_id, cached);
      }
      if (body.children[index] !== cached.row) body.insertBefore(cached.row, body.children[index] || null);
    });
    $("empty").hidden = !!visible.length;
    if (!visible.length && lastRequest) {
      $("empty").querySelector("h3").textContent = items.length ? "No games match these filters." : busy ? "Checking your owned library…" : state === "complete" ? "No owned games to compare." : "No results this time.";
      $("empty").querySelector("p").textContent = items.length ? "Try another filter or game name." : busy ? "Results appear as each game is checked." : message || "Check the profile, public Game details, and server API-key setup.";
    }
    const hiddenCount = showUnavailable ? 0 : items.filter(unavailable).length;
    $("row-count").textContent = `${visible.length} of ${items.length} games${hiddenCount ? ` · ${hiddenCount} unavailable hidden` : ""}`;
    $("arrival-order").setAttribute("aria-pressed", String(sort === "arrival"));
    $("order-note").textContent = sort === "arrival" ? "Loaded games append at the end" : "Sorted results · loaded games follow this sort";
    buttons(".library-sort").forEach(button => {
      button.closest("th").removeAttribute("aria-sort");
      button.setAttribute("aria-pressed", String(button.dataset.sort === sort));
    });
    buttons(".library-sort").forEach(button => { if (button.dataset.sort === sort) button.closest("th").setAttribute("aria-sort", direction === 1 ? "ascending" : "descending"); });
    buttons(".library-filter").forEach(button => { button.classList.toggle("active", button.dataset.filter === filter); button.setAttribute("aria-pressed", String(button.dataset.filter === filter)); });
    refreshControls();
  }
  async function poll() {
    try {
      const data = await request(`/api/jobs/${job.id}`, {headers:{Authorization:`Bearer ${job.token}`}});
      items = data.items; rates = data.rates; home = data.home || "pl"; state = data.state;
      message = data.error || data.message;
      $("status-badge").textContent = state.toUpperCase();
      $("status-badge").classList.toggle("active", !terminal.has(state));
      $("progress-label").textContent = data.message;
      $("progress").max = Math.max(data.total,1); $("progress").value = items.length;
      notice(data.error || (state === "partial" ? "Some games could not be compared. Retry to reuse completed prices and check the remaining games."
        : state === "cancelled" ? "Comparison cancelled. Completed prices remain cached." : data.warnings.join(" ")), !!data.error);
      if (terminal.has(state)) { job = null; setBusy(false); }
      showLibraryRates();
      render(); save();
      if (!terminal.has(state)) timer = setTimeout(poll, 1200);
    } catch (error) {
      if (error.status === 404) {
        job = null; state = "expired"; setBusy(false); message = error.message;
        $("status-badge").textContent = "COMPARISON EXPIRED"; notice(message, true); render(); save();
        $("status-badge").classList.toggle("active", false);
      } else { notice("Connection interrupted. Reconnecting to your library comparison…", true); timer = setTimeout(poll,4000); }
    }
  }
  async function start(body) {
    if (busy || running || window.creatorPane?.busy) { notice("A comparison is running. Wait for it or cancel it on its tab.", true); return; }
    clearTimeout(timer); job = null; items = []; rates = []; home = body.home; lastRequest = body;
    sort = "arrival"; direction = 1; state = "connecting"; message = "Loading owned library…";
    $("search").value = ""; $("identifier").value = body.identifier; $("wishlist-order").value = body.order;
    $("status-badge").textContent = "CONNECTING"; $("status-badge").classList.toggle("active",true);
    $("progress-label").textContent = message; $("progress").value = 0;
    notice(""); setBusy(true); render(); save();
    showLibraryRates();
    try { job = await request("/api/library-jobs", {method:"POST",body:JSON.stringify(body)}); refreshControls(); save(); await poll(); }
    catch (error) { state = "failed"; message = error.message; job = null; setBusy(false); $("status-badge").textContent = "COULD NOT START"; $("status-badge").classList.toggle("active",false); notice(message,true); render(); save(); }
  }
  $("compare-form").addEventListener("submit", event => {
    event.preventDefault();
    const regions = [...document.querySelectorAll('[name="region"]')].filter(el => el.checked).map(el => el.value);
    if (!regions.length || regions.length > 2) { notice("Choose one or two comparison currencies.", true); return; }
    start({identifier:$("identifier").value.trim(), regions, home:selectedHome(), order:$("wishlist-order").value});
  });
  $("retry").addEventListener("click", () => { if (lastRequest) start(lastRequest); });
  $("cancel").addEventListener("click", async () => {
    if (!job) return;
    state = "cancelling"; refreshControls();
    try { await request(`/api/jobs/${job.id}/cancel`, {method:"POST",body:"{}",headers:{Authorization:`Bearer ${job.token}`}}); }
    catch (error) { state = "running"; refreshControls(); notice(error.message,true); }
  });
  for (const id of ["search","show-unavailable"]) $(id).addEventListener(id === "search" ? "input" : "change", () => { render(); save(); });
  $("export-owner").addEventListener("change", save);
  $("arrival-order").addEventListener("click", () => { sort = "arrival"; direction = 1; render(); save(); });
  buttons(".library-filter").forEach(button => button.addEventListener("click", () => { filter = button.dataset.filter; render(); save(); }));
  buttons(".library-sort").forEach(button => button.addEventListener("click", () => { direction = sort === button.dataset.sort ? -direction : 1; sort = button.dataset.sort; render(); save(); }));
  $("export-csv").addEventListener("click", () => downloadCsv(buildPriceCsv(items, home, rates,
    {sourceTab:"library", includeOwner:$("export-owner").checked, profile:lastRequest?.identifier, regions:lastRequest?.regions || [], order:lastRequest?.order}), "steam-library-comparison.csv"));
  window.libraryPane = {get busy() { return busy; }, get active() { return active; }, refreshControls,
    activate(value) { active = value; if (active) { render(); showLibraryRates(); } }};
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null"), body = saved?.request;
    if (body && typeof body.identifier === "string" && body.identifier.length <= 200 && ["name","steam"].includes(body.order)
        && Object.hasOwn(storefronts,body.home) && Array.isArray(body.regions) && body.regions.length >= 1 && body.regions.length <= 2
        && new Set(body.regions).size === body.regions.length && body.regions.every(region => Object.hasOwn(storefronts,region) && region !== body.home)
        && Array.isArray(saved.items) && saved.items.every(item => /^[0-9]{1,12}$/.test(item.app_id) && typeof item.name === "string")) {
      lastRequest = body; items = saved.items; rates = Array.isArray(saved.rates) ? saved.rates : []; home = body.home;
      state = terminal.has(saved.state) ? saved.state : "ready"; message = saved.message || "Restored library comparison.";
      filter = ["all","fair","expensive","discounts","skipped"].includes(saved.filter) ? saved.filter : "all";
      sort = ["arrival","name","home","difference","percentage"].includes(saved.sort) ? saved.sort : "arrival";
      direction = saved.direction === -1 ? -1 : 1; $("search").value = typeof saved.search === "string" ? saved.search : "";
      $("show-unavailable").checked = saved.showUnavailable === true; $("export-owner").checked = saved.includeOwner === true;
      $("identifier").value = body.identifier; $("wishlist-order").value = body.order;
      $("status-badge").textContent = state.toUpperCase(); render();
      if (sessionStorage.getItem("polisher-active-tab") === "library" && !running) {
        preferredComparisons = [...body.regions];
        document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === body.home);
        document.querySelectorAll('[name="region"]').forEach(el => el.checked = body.regions.includes(el.value));
        updateSelections();
      }
      if (saved.job && !terminal.has(saved.state) && /^[A-Za-z0-9_-]{32}$/.test(saved.job.id) && /^[A-Za-z0-9_-]{43}$/.test(saved.job.token)) {
        job = saved.job; setBusy(true); poll();
      } else if (state === "failed") notice(message,true);
    }
  } catch (_) { /* Invalid or unavailable tab storage cannot interrupt the app. */ }
  refreshControls();
})();
