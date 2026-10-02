"use strict";

// Creator comparisons have their own results and job token; wishlist state stays intact.
(() => {
  let active = false, busy = false, initialized = false, initializing = false;
  let creators = [], creatorJob = null, pollTimer = null, autoTimer = null;
  let creatorHome = "pl", creatorRegions = ["us", "de"], creatorRates = [];
  let savedRequest = null, cancelRequested = false;
  const groups = new Map(), results = new Map();
  const storageKey = "polisher-creator-job";
  const terminal = new Set(["complete", "partial", "cancelled", "failed"]);

  function save() {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({job: creatorJob, request: savedRequest,
        home: creatorHome, regions: creatorRegions, catalogs: [...groups].map(([id, group]) => ({id,
          products: group.products, nextStart: group.nextStart, hasMore: group.hasMore, total: group.total})),
        results: [...results.values()], rates: creatorRates}));
    } catch (_) { /* A full or unavailable session store does not interrupt comparisons. */ }
  }

  function message(text, error = false) {
    $("creators-notice").textContent = text;
    $("creators-notice").hidden = !text;
    $("creators-notice").classList.toggle("error", error);
  }

  function refreshControls() {
    $("creators-refresh").disabled = busy || running || !initialized;
    $("creators-cancel").hidden = !busy;
    $("creators-cancel").disabled = !creatorJob || cancelRequested;
    $("creators-cancel").textContent = cancelRequested ? "Cancelling…" : "Cancel comparison ■";
    for (const group of groups.values()) group.more.disabled = busy || running;
  }

  function setCreatorBusy(value) {
    busy = value;
    updateSelections();
  }

  function tableHeading(home) {
    const row = node("tr");
    for (const label of ["GAME NAME", `PRICE IN ${storefronts[home].name.toUpperCase()}`, "OTHER STOREFRONTS", "DIFFERENCE"]) {
      const th = node("th"); th.scope = "col";
      const stack = node("span", undefined, "header-stack");
      stack.append(node("span", label));
      if (label === "OTHER STOREFRONTS") stack.append(node("small", `CONVERTED TO ${storefronts[home].currency}`));
      if (label === "DIFFERENCE") {
        stack.className += " header-stack-right";
        stack.append(node("small", `${storefronts[home].currency} / %`));
      }
      th.append(stack); row.append(th);
    }
    return row;
  }

  function buildGroups() {
    $("creator-groups").replaceChildren();
    for (const creator of creators) {
      const section = node("section", undefined, "creator-group");
      section.setAttribute("aria-labelledby", `creator-${creator.id}`);
      const identity = node("div", undefined, "creator-identity");
      const icon = node("img");
      icon.alt = `${creator.name} icon`; icon.width = 64; icon.height = 64;
      icon.loading = "lazy"; icon.referrerPolicy = "no-referrer";
      icon.addEventListener("error", () => { icon.src = "/steam-logo.svg"; }, {once: true});
      icon.src = creator.icon || "/steam-logo.svg";
      const title = node("h3"); title.id = `creator-${creator.id}`;
      const link = node("a", creator.name + " ↗");
      link.href = creator.homepage; link.target = "_blank"; link.rel = "noopener noreferrer";
      title.append(link); identity.append(icon, title, node("p", creator.role, "hint"));
      const heading = node("div", undefined, "creator-group-heading");
      const statistics = node("div", undefined, "creator-statistics");
      statistics.setAttribute("aria-label", `${creator.name} statistics for loaded products`);
      heading.append(identity, statistics);
      const catalog = node("div", undefined, "creator-catalog"), wrap = node("div", undefined, "table-wrap");
      const table = node("table"), columns = node("colgroup"), head = node("thead", undefined, "creator-accessible-head"), body = node("tbody");
      table.setAttribute("aria-label", `${creator.name} regional price comparisons`);
      for (const name of ["game", "home", "foreign", "difference"]) columns.append(node("col", undefined, `${name}-column`));
      head.append(tableHeading(creatorHome)); table.append(columns, head, body); wrap.append(table);
      const footer = node("div", undefined, "creator-catalog-footer"), count = node("span", "Three featured games");
      const more = node("button", undefined, "creator-load-more"); more.type = "button";
      more.append(node("span", "Load more"));
      more.title = `Load more products from ${creator.name}`;
      more.setAttribute("aria-label", `Load more products from ${creator.name}`);
      more.addEventListener("click", () => loadMore(creator.id));
      footer.append(count, more); catalog.append(wrap, footer); section.append(heading, catalog);
      $("creator-groups").append(section);
      groups.set(creator.id, {products: [...creator.examples], nextStart: 0, hasMore: true, total: null,
        body, head, wrap, statistics, count, more, rowCache: new Map()});
      wrap.addEventListener("scroll", () => syncColumns(wrap));
    }
    renderGroups();
  }

  function syncColumns(source) {
    // One shared heading follows every catalog when narrow screens require scrolling.
    for (const wrap of [$("creator-columns-scroll"), ...[...groups.values()].map(group => group.wrap)]) {
      if (wrap.scrollLeft !== source.scrollLeft) wrap.scrollLeft = source.scrollLeft;
    }
  }

  function renderStatistics(group) {
    const loaded = [...new Set(group.products.map(product => product.app_id))].map(id => results.get(id));
    const compared = loaded.filter(item => item?.comparison);
    const uncompared = loaded.filter(item => item?.skipped).length;
    const pending = loaded.length - compared.length - uncompared;
    group.statistics.replaceChildren();
    for (const region of creatorRegions) {
      const differences = [];
      for (const item of compared) {
        const home = item.comparison.home_price.amount;
        const reference = item.comparison.alternatives.find(price => price.region === region)?.amount_in_home;
        if (!Number.isFinite(home) || !Number.isFinite(reference) || reference <= 0) continue;
        const difference = (home - reference) / reference * 100;
        if (Number.isFinite(difference)) differences.push(difference);
      }
      const average = differences.length ? differences.reduce((sum, value) => sum + value / differences.length, 0) : null;
      const sorted = [...differences].sort((a, b) => a - b);
      const middle = Math.floor(sorted.length / 2);
      const median = !sorted.length ? null : sorted.length % 2 ? sorted[middle]
        : sorted[middle - 1] / 2 + sorted[middle] / 2;
      const metric = node("div", undefined, "creator-statistic");
      metric.append(node("span", `Average ${storefronts[creatorHome].currency} vs ${storefronts[region].currency}`, "creator-statistic-label"));
      metric.title = `Mean of each product's (baseline price − ${storefronts[region].name} price converted to ${storefronts[creatorHome].currency}) / converted price × 100. Each product has equal weight. Zero reference prices are excluded.`;
      const value = node("strong", average == null ? "—" : percentageLabel(average),
        "creator-statistic-value" + (average == null ? "" : average > 0 ? " pricier" : " cheaper"));
      metric.append(value, node("small", `${differences.length} ${differences.length === 1 ? "product" : "products"} compared`));
      const medianRow = node("div", undefined, "creator-statistic-median");
      medianRow.title = "Middle product percentage difference after sorting; for an even number of products, the mean of the two middle differences. Uses the same products as the average.";
      medianRow.append(node("span", "Median"), node("strong", median == null ? "—" : percentageLabel(median),
        "creator-statistic-value" + (median == null ? "" : median > 0 ? " pricier" : " cheaper")));
      metric.append(medianRow);
      group.statistics.append(metric);
    }
    const cheaper = compared.filter(item => item.comparison.is_fair).length;
    const coverage = node("p", `${compared.length} of ${loaded.length} compared · ${cheaper} cheaper/equal · ${compared.length - cheaper} pricier · ${uncompared} uncompared${pending ? ` · ${pending} pending` : ""}`, "creator-statistics-coverage");
    coverage.title = "Cheaper/equal means the baseline price is no higher than every selected converted foreign price. Pricier means it exceeds at least one. Counts cover only loaded non-free products.";
    group.statistics.append(coverage);
  }

  function renderGroups() {
    $("creator-columns-head").replaceChildren(tableHeading(creatorHome));
    for (const group of groups.values()) {
      // Preserve unavailable paid products; missing prices alone do not mean free.
      group.products = group.products.filter(product => {
        const item = results.get(product.app_id);
        return !item?.is_free && item?.comparison?.home_price?.amount !== 0;
      });
      renderStatistics(group);
      group.head.replaceChildren(tableHeading(creatorHome));
      const displayedIds = new Set(group.products.map(item => item.app_id));
      for (const row of [...group.body.children]) if (!displayedIds.has(row.dataset.appId)) row.remove();
      for (const id of group.rowCache.keys()) if (!displayedIds.has(id)) group.rowCache.delete(id);
      for (let index = 0; index < group.products.length; index++) {
        const product = group.products[index];
        const item = results.get(product.app_id) || {...product, pending: true};
        const signature = creatorHome + JSON.stringify(item);
        let cached = group.rowCache.get(product.app_id);
        if (!cached || cached.signature !== signature) {
          const row = comparisonRow(item, creatorHome);
          if (cached) cached.row.remove();
          cached = {row, signature}; group.rowCache.set(product.app_id, cached);
        }
        if (group.body.children[index] !== cached.row) group.body.insertBefore(cached.row, group.body.children[index] || null);
      }
      group.more.hidden = !group.hasMore;
      group.count.textContent = `${group.products.length} products shown${group.total == null ? " · featured games" : ` · ${group.total} in Steam catalog`}`;
    }
    if (active && creatorRates.length) renderRates(creatorRates, $("rates"));
    refreshControls();
  }

  function mergeSnapshot(data) {
    for (const [id, page] of Object.entries(data.catalogs || {})) {
      const group = groups.get(id);
      if (!group) continue;
      const known = new Set(group.products.map(item => item.app_id));
      for (const product of page.products) if (!known.has(product.app_id)) {
        group.products.push(product); known.add(product.app_id);
      }
      group.nextStart = page.next_start; group.hasMore = page.has_more; group.total = page.total;
    }
    for (const item of data.items) results.set(item.app_id, item);
    creatorRates = data.rates;
    renderGroups(); save();
  }

  async function pollCreators() {
    if (!creatorJob) return;
    try {
      const data = await request(`/api/jobs/${creatorJob.id}`, {headers: {Authorization: `Bearer ${creatorJob.token}`}});
      mergeSnapshot(data);
      $("creators-progress").textContent = data.message;
      message(data.error || (data.warnings || []).join(" "), !!data.error);
      if (data.state === "cancelling") { cancelRequested = true; refreshControls(); }
      if (terminal.has(data.state)) {
        setCreatorBusy(false);
        creatorJob = null; save();
        if (data.state === "cancelled") message("Comparison cancelled. Use Refresh comparisons to finish checking displayed products.");
        else if (data.state === "partial") message("Some products could not be compared. Refresh comparisons to retry using cached prices.");
      } else pollTimer = setTimeout(pollCreators, 1200);
    } catch (error) {
      if (error.status === 404) {
        creatorJob = null; setCreatorBusy(false); save();
        message("This creator comparison expired. Refresh comparisons to start again.", true);
      } else {
        message("Connection interrupted. Reconnecting to creator comparisons…", true);
        pollTimer = setTimeout(pollCreators, 4000);
      }
    }
  }

  function selections() {
    return {home: selectedHome(), regions: [...document.querySelectorAll('[name="region"]:checked')].map(el => el.value)};
  }

  async function startCreators(body) {
    if (busy || running) return;
    if (!body.regions.length) { message("Choose one or two comparison currencies.", true); return; }
    clearTimeout(pollTimer); cancelRequested = false; creatorJob = null;
    savedRequest = body; setCreatorBusy(true); message("");
    $("creators-progress").textContent = "Connecting to Steam…";
    try {
      creatorJob = await request("/api/creator-jobs", {method: "POST", body: JSON.stringify(body)});
      save(); refreshControls(); pollCreators();
    } catch (error) {
      setCreatorBusy(false); message(error.message, true);
      $("creators-progress").textContent = "Comparison could not start. Refresh comparisons to retry.";
    }
  }

  function refreshFeatured() {
    if (busy || running) return;
    const selected = selections();
    if (!selected.regions.length) { message("Choose one or two comparison currencies.", true); return; }
    const mode = savedRequest ? "products" : "featured";
    const appIds = [...new Set([...groups.values()].flatMap(group => group.products.map(item => item.app_id)))];
    if (appIds.length > 1000) { message("Refresh supports up to 1,000 displayed products. Open the app in a new tab to start with the featured games.", true); return; }
    if (selected.home !== creatorHome) {
      for (const group of groups.values()) { group.nextStart = 0; group.hasMore = true; group.total = null; }
    }
    creatorHome = selected.home; creatorRegions = selected.regions; creatorRates = []; results.clear();
    if (active) renderRates([], $("rates"));
    renderGroups(); startCreators({...selected, mode, ...(mode === "products" ? {app_ids: appIds} : {})});
  }

  function loadMore(id) {
    // Expanded pages retain the currency choices of their featured comparisons.
    startCreators({home: creatorHome, regions: creatorRegions, mode: "catalog", creator_id: id, start: groups.get(id).nextStart});
  }

  function restore(saved) {
    if (!saved || !Object.hasOwn(storefronts, saved.home) || !Array.isArray(saved.regions) ||
        saved.regions.length < 1 || saved.regions.length > 2 || new Set(saved.regions).size !== saved.regions.length ||
        saved.regions.some(id => !Object.hasOwn(storefronts, id) || id === saved.home)) return false;
    creatorHome = saved.home; creatorRegions = saved.regions; creatorRates = saved.rates || [];
    savedRequest = saved.request;
    if (active) {
      preferredComparisons = [...creatorRegions];
      document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === creatorHome);
      document.querySelectorAll('[name="region"]').forEach(el => el.checked = creatorRegions.includes(el.value));
      updateSelections();
    }
    for (const item of saved.results || []) if (/^[0-9]{1,12}$/.test(item.app_id)) results.set(item.app_id, item);
    for (const catalog of saved.catalogs || []) {
      const group = groups.get(catalog.id);
      if (!group || !Array.isArray(catalog.products) || !Number.isInteger(catalog.nextStart) || catalog.nextStart < 0) continue;
      group.products = catalog.products.filter(item => /^[0-9]{1,12}$/.test(item.app_id) && typeof item.name === "string");
      group.nextStart = catalog.nextStart; group.hasMore = catalog.hasMore; group.total = catalog.total;
    }
    if (saved.job && /^[A-Za-z0-9_-]{32}$/.test(saved.job.id) && /^[A-Za-z0-9_-]{43}$/.test(saved.job.token)) {
      creatorJob = saved.job; savedRequest = saved.request; setCreatorBusy(true); pollCreators();
    } else $("creators-progress").textContent = "Restored creator results. Refresh comparisons for a new price check.";
    renderGroups(); return true;
  }

  async function initialize() {
    if (initialized || initializing) return;
    initializing = true;
    try {
      const data = await request("/api/creators"); creators = data.creators; buildGroups(); initialized = true;
      let restored = false;
      try { restored = restore(JSON.parse(sessionStorage.getItem(storageKey) || "null")); } catch (_) { /* Ignore invalid saved state. */ }
      if (!restored) {
        if (running) {
          $("creators-progress").textContent = "Waiting for your wishlist comparison to finish…";
          waitForWishlist();
        } else refreshFeatured();
      }
    } catch (error) { message(error.message, true); }
    finally { initializing = false; refreshControls(); }
  }

  function waitForWishlist() {
    clearTimeout(autoTimer);
    if (!active) return;
    if (running) autoTimer = setTimeout(waitForWishlist, 1200); else refreshFeatured();
  }

  function selectTab(creatorTab) {
    active = creatorTab;
    $("currencies-step").textContent = active ? "01 / CURRENCIES" : "02 / CURRENCIES";
    $("creators-panel").hidden = !active; $("wishlist-panel").hidden = active;
    $("compare-form").hidden = active;
    for (const [id, selected] of [["wishlist-tab", !active], ["creators-tab", active]]) {
      $(id).setAttribute("aria-selected", String(selected)); $(id).tabIndex = selected ? 0 : -1;
    }
    renderRates(active ? creatorRates : currentRates, $("rates"));
    if (active) {
      initialize();
      if (initialized && !savedRequest && !busy) waitForWishlist();
    } else clearTimeout(autoTimer);
    try { sessionStorage.setItem("polisher-active-tab", active ? "creators" : "wishlist"); } catch (_) {}
  }

  window.creatorPane = {get active() { return active; }, get busy() { return busy; }, refreshControls};
  $("creator-columns-scroll").addEventListener("scroll", () => syncColumns($("creator-columns-scroll")));
  $("wishlist-tab").addEventListener("click", () => selectTab(false));
  $("creators-tab").addEventListener("click", () => selectTab(true));
  for (const [id, creatorTab] of [["wishlist-tab", false], ["creators-tab", true]]) {
    $(id).addEventListener("keydown", event => {
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        event.preventDefault(); const target = event.key === "Home" ? false : event.key === "End" ? true : !creatorTab;
        selectTab(target); $(target ? "creators-tab" : "wishlist-tab").focus();
      }
    });
  }
  $("creators-refresh").addEventListener("click", () => initialized ? refreshFeatured() : initialize());
  $("creators-cancel").addEventListener("click", async () => {
    if (!creatorJob) return;
    cancelRequested = true; refreshControls();
    try { await request(`/api/jobs/${creatorJob.id}/cancel`, {method: "POST", body: "{}", headers: {Authorization: `Bearer ${creatorJob.token}`}}); }
    catch (error) { cancelRequested = false; refreshControls(); message(error.message, true); }
  });
  try { if (sessionStorage.getItem("polisher-active-tab") === "creators") selectTab(true); } catch (_) {}
})();
