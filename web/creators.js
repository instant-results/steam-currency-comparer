"use strict";

// Each role has independent results, pagination, search, and job access.
(() => {
  const panes = new Map();
  let selectedTab = "wishlist";
  const anyBusy = () => [...panes.values()].some(pane => pane.busy);
  function createPane(kind) {
    const plural = kind + "s";
    const $ = id => document.getElementById(id.replace(/^creators-/, plural + "-").replace(/^creator-/, kind + "-"));
    let active = false, busy = false, initialized = false, initializing = false;
    let creators = [], creatorJob = null, pollTimer = null;
    let creatorHome = "pl", creatorRegions = ["us", "de"], creatorRates = [];
    let savedRequest = null, cancelRequested = false;
    let currencyUpdating = false, currencyRetry = null, completedComparison = false;
    let searching = false, searchChoices = [], searchTimer = null, searchRevision = 0, searchPending = false;
    let catalogSort = "arrival", catalogDirection = 1;
    const groups = new Map(), results = new Map(), defaultIds = new Set();
    const removedCatalogs = new Set(), finalizedCatalogs = new Set(), orphanedProducts = new Set(), catalogSources = new Map(), catalogOrder = new Map();
    let cleanupRunning = false, cleanupTimer = null;
    const catalogOwner = `${kind}-catalog`;
    const pendingCatalog = id => removalNotices.find(catalogOwner, id)?.data;
    function allGroups() {
      const entries = new Map(groups);
      for (const id of removedCatalogs) { const record = pendingCatalog(id); if (record) entries.set(id, record.group); }
      return entries;
    }
    function referencedIds(includePending = false) {
      return new Set([...(includePending ? allGroups() : groups).values()].flatMap(group => group.products.map(product => product.app_id)));
    }
    function cleanupProductIds() {
      const ids = new Set(orphanedProducts), visible = referencedIds();
      for (const id of removedCatalogs) for (const product of pendingCatalog(id)?.group.products || []) {
        if (!visible.has(product.app_id)) ids.add(product.app_id);
      }
      return [...ids];
    }
    function acceptResults(items) {
      const visible = referencedIds();
      for (const item of removals.filter(items)) {
        for (const id of removedCatalogs) {
          const record = pendingCatalog(id);
          if (record?.group.order.has(item.app_id)) record.results.set(item.app_id, item);
        }
        if (visible.has(item.app_id)) results.set(item.app_id, item);
      }
      for (const id of results.keys()) if (!visible.has(id)) results.delete(id);
    }
    function registerCatalogJob(job) {
      if (!job?.id || !job.token || catalogSources.has(job.id)) return;
      if (catalogSources.size >= 120) catalogSources.delete(catalogSources.keys().next().value);
      catalogSources.set(job.id, {token: job.token, catalogs: new Set(), products: new Set()});
      if (finalizedCatalogs.size) syncCatalogCleanup();
    }
    async function syncCatalogCleanup() {
      if (cleanupRunning) return;
      clearTimeout(cleanupTimer); cleanupRunning = true;
      let failed = false, remaining = false;
      try {
        const retained = referencedIds(true);
        await Promise.all([...catalogSources].map(async ([id, source]) => {
          const catalogs = [...finalizedCatalogs].filter(key => !source.catalogs.has(key)).slice(0, 20);
          const appIds = [...orphanedProducts].filter(key => !source.products.has(key) && !retained.has(key)).slice(0, 1000);
          if (!catalogs.length && !appIds.length) return;
          const batch = catalogs.length ? catalogs : [...finalizedCatalogs].slice(0, 1);
          if (!batch.length) return;
          try {
            await request(`/api/jobs/${id}/remove-catalogs`, {method: "POST", keepalive: true,
              headers: {Authorization: `Bearer ${source.token}`}, body: JSON.stringify({catalog_ids: batch, app_ids: appIds})});
            for (const key of catalogs) source.catalogs.add(key);
            for (const key of appIds) source.products.add(key);
          } catch (error) { if (error.status === 404) catalogSources.delete(id); else failed = true; }
          if (catalogSources.has(id)) remaining ||= [...finalizedCatalogs].some(key => !source.catalogs.has(key))
            || [...orphanedProducts].some(key => !source.products.has(key) && !retained.has(key));
        }));
      } finally {
        cleanupRunning = false;
        if (remaining || failed) cleanupTimer = setTimeout(syncCatalogCleanup, failed ? 4000 : 0);
        if (failed) message("Catalog removed locally. Server cleanup will retry when the connection is available.", true);
      }
    }
    function removeCatalog(id) {
      const creator = creators.find(value => value.id === id), group = groups.get(id);
      if (!creator || !group) return;
      if (removedCatalogs.size >= 1000) { message("This tab has reached its 1,000-catalog removal limit. Open a new tab to reset it.", true); return; }
      if (new Set([...cleanupProductIds(), ...group.products.map(product => product.app_id)]).size > 10000) {
        message("This tab has reached its 10,000-product catalog cleanup limit. Open a new tab to reset it.", true); return;
      }
      removedCatalogs.add(id); groups.delete(id); group.section.remove();
      creators = creators.filter(value => value.id !== id);
      const record = {creator, group, results: new Map(group.products.map(product => [product.app_id, results.get(product.app_id)]).filter(([, item]) => item))};
      removalNotices.add(catalogOwner, id, creator.name, record, data => {
        removedCatalogs.delete(id); creators.push(data.creator);
        creators.sort((a, b) => catalogOrder.get(a.id) - catalogOrder.get(b.id)); groups.set(id, data.group);
        for (const value of creators) $("creator-groups").append(groups.get(value.id).section);
        acceptResults([...data.results.values()]); renderGroups(); save();
      }, data => {
        finalizedCatalogs.add(id);
        const retained = referencedIds(true);
        for (const product of data.group.products) if (!retained.has(product.app_id)) orphanedProducts.add(product.app_id);
        data.group.section.replaceChildren(); data.group.rowCache.clear();
        syncCatalogCleanup(); save();
      }, `${kind === "developer" ? "Developer" : "Publisher"} catalog`);
      acceptResults([]); renderGroups(); save();
    }
    const synchronizedScrolls = new WeakMap();
    let defaultsChanged = false;
    const storageKey = `polisher-${kind}-job`;
    const terminal = new Set(["complete", "partial", "cancelled", "failed"]);
    const removals = createTitleRemovals(kind, () => {
      for (const group of allGroups().values()) group.products = group.products.filter(product => !removals.has(product.app_id));
      for (const id of results.keys()) if (removals.has(id)) results.delete(id);
      acceptResults([]);
      renderGroups(); save();
    }, record => {
      if (record.item && !record.item.pending) results.set(record.item.app_id, record.item);
      for (const [id, product] of record.memberships) {
        const group = allGroups().get(id);
        if (!group || group.products.some(value => value.app_id === product.app_id)) continue;
        group.products.push(product);
        group.products.sort((a, b) => group.order.get(a.app_id) - group.order.get(b.app_id));
      }
    }, text => message(text, true));

    function removeTitle(appId) {
      const memberships = new Map();
      for (const [id, group] of allGroups()) {
        const product = group.products.find(value => value.app_id === appId);
        if (product) memberships.set(id, product);
      }
      if (!memberships.size) return;
      const item = results.get(appId) || {...memberships.values().next().value, pending: true};
      removals.remove(appId, item.name, {item, memberships});
    }

    function save() {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify({job: creatorJob, request: savedRequest, creators: creators.filter(c => c.selector),
          featuredIds: [...defaultIds], showCredits: $("creator-show-credits").checked, home: creatorHome, regions: creatorRegions, catalogs: [...groups].map(([id, group]) => ({id,
            products: group.products, nextStart: group.nextStart, hasMore: group.hasMore, total: group.total, expanded: group.expanded, discoveryHome: group.discoveryHome, statisticsExpanded: group.statisticsExpanded})),
          results: [...results.values()], rates: creatorRates, catalogSort, catalogDirection, currencyUpdating, currencyRetry, completedComparison, removals: removals.serialize(),
          removedCatalogs: [...removedCatalogs], orphanedProducts: cleanupProductIds(),
          catalogSources: [...catalogSources].map(([id, source]) => ({id, token: source.token}))}));
      } catch (_) { /* A full or unavailable session store does not interrupt comparisons. */ }
    }

    function message(text, error = false) {
      $("creators-notice").textContent = text;
      $("creators-notice").hidden = !text;
      $("creators-notice").classList.toggle("error", error);
    }

    function refreshControls() {
      $("creators-refresh").textContent = currencyRetry && !busy ? "Retry currency update ↻" : "Refresh comparisons ↻";
      $("creators-export").disabled = ![...groups.values()].some(group => group.products.some(product => results.has(product.app_id)));
      $("creators-refresh").disabled = comparisonCoordinator.busy || !initialized;
      $("creators-cancel").hidden = !busy;
      $("creators-cancel").disabled = !creatorJob || cancelRequested;
      $("creators-cancel").textContent = cancelRequested ? "Cancelling…" : "Cancel comparison ■";
      for (const group of groups.values()) group.more.disabled = comparisonCoordinator.busy;
      $("creator-search-submit").disabled = searching || !initialized;
      for (const {creator, button, action} of searchChoices) {
        const added = groups.has(creator.id);
        button.textContent = added ? "Added" : action;
        button.disabled = added || comparisonCoordinator.busy || !initialized;
      }
    }

    function setCreatorBusy(value) {
      busy = value;
      comparisonCoordinator.setBusy(kind, value);
    }

    function columnNames() {
      return $("creator-show-credits").checked ? ["game", "credit", "home", "foreign", "difference"] : ["game", "home", "foreign", "difference"];
    }

    function tableColumns() {
      return columnNames().map(name => node("col", undefined, `${name}-column`));
    }

    function tableHeading(home, interactive = false) {
      const row = node("tr");
      const buttons = [];
      function sortButton(text, column) {
        const button = node("button", undefined, "sort catalog-sort"); button.type = "button";
        button.dataset.sort = column;
        button.setAttribute("aria-label", `Sort games within each ${kind} catalog by ${text}`);
        const arrow = node("span", "↕", "sort-arrow"); arrow.setAttribute("aria-hidden", "true");
        button.append(node("span", text), arrow);
        button.addEventListener("click", () => {
          ({sort: catalogSort, direction: catalogDirection} = nextTableSort(catalogSort, catalogDirection, column));
          renderGroups(); save();
        });
        buttons.push(button); return button;
      }
      const labels = ["GAME NAME", `PRICE IN ${storefronts[home].name.toUpperCase()}`, "OTHER STOREFRONTS", "DIFFERENCE"];
      if ($("creator-show-credits").checked) labels.splice(1, 0, kind === "developer" ? "PUBLISHER" : "DEVELOPER");
      for (const label of labels) {
        const th = node("th", undefined, label === "OTHER STOREFRONTS" ? "catalog-foreign-heading storefront-group-heading" : ""); th.scope = "col";
        const stack = node("span", undefined, "header-stack");
        if (interactive && label === "GAME NAME") stack.append(sortButton(label, "name"));
        else if (interactive && label.startsWith("PRICE IN ")) stack.append(sortButton(label, "home"));
        else stack.append(node("span", label));
        if (label === "OTHER STOREFRONTS") stack.append(node("small", `CONVERTED TO ${storefronts[home].currency}`));
        if (label === "DIFFERENCE") {
          stack.className += " header-stack-right";
          if (interactive) {
            const controls = node("span", undefined, "difference-sorts");
            controls.append(sortButton(storefronts[home].currency, "difference"), sortButton("%", "percentage"));
            stack.append(controls);
          } else stack.append(node("small", `${storefronts[home].currency} / %`));
        }
        th.append(stack);
        row.append(th);
      }
      if (interactive) updateSortIndicators(buttons, catalogSort, catalogDirection);
      return row;
    }

    function storefrontLabelRow() {
      const row = node("tr", undefined, "storefront-label-row");
      for (const column of columnNames()) {
        const cell = node("td", undefined, {game: "pinned-game", credit: "catalog-credit-cell", home: "pinned-home", difference: "pinned-difference"}[column]);
        if (column === "foreign") {
          cell.className = "storefront-label-cell";
          const headings = node("div", undefined, "foreign storefront-headings");
          headings.append(...regionalHeadings(creatorRegions)); cell.append(headings);
        } else cell.setAttribute("aria-hidden", "true");
        row.append(cell);
      }
      return row;
    }

    function buildGroups() {
      for (const creator of creators) {
        if (removedCatalogs.has(creator.id)) continue;
        if (!catalogOrder.has(creator.id)) catalogOrder.set(creator.id, catalogOrder.size);
        if (groups.has(creator.id)) continue;
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
        const control = node("span", undefined, "game-artwork-control creator-icon-control");
        const iconLink = node("a"); iconLink.href = creator.homepage; iconLink.target = "_blank"; iconLink.rel = "noopener noreferrer";
        iconLink.setAttribute("aria-label", `Open ${creator.name} on Steam`); iconLink.append(icon);
        const remove = node("button", undefined, "remove-title"); remove.type = "button";
        remove.title = `Remove ${creator.name} ${kind} catalog`; remove.setAttribute("aria-label", remove.title);
        const cross = node("span", undefined, "offer-help-close-icon"); cross.setAttribute("aria-hidden", "true"); remove.append(cross);
        remove.addEventListener("click", event => {
          touchRemoval.hide(); removeCatalog(creator.id);
          if (event.detail === 0) $("creator-query").focus({preventScroll: true});
        });
        control.append(iconLink, remove); touchRemoval.bind(control, iconLink);
        title.append(link); identity.append(control, title, node("p", creator.role, "hint"));
        const heading = node("div", undefined, "creator-group-heading");
        const statistics = node("div", undefined, "creator-statistics");
        statistics.setAttribute("aria-label", `${creator.name} statistics for loaded products`);
        heading.append(identity, statistics);
        const catalog = node("div", undefined, "creator-catalog"), wrap = node("div", undefined, "table-wrap comparison-scroll");
        wrap.tabIndex = 0; wrap.setAttribute("aria-label", `Scroll ${creator.name} regional comparisons`);
        const table = node("table"), columns = node("colgroup"), head = node("thead", undefined, "creator-accessible-head"), body = node("tbody");
        table.setAttribute("aria-label", `${creator.name} regional price comparisons`);
        columns.append(...tableColumns());
        head.append(tableHeading(creatorHome), storefrontLabelRow()); table.append(columns, head, body); wrap.append(table);
        const footer = node("div", undefined, "creator-catalog-footer"), count = node("span", "Three featured games");
        const more = node("button", undefined, "creator-load-more"); more.type = "button";
        more.append(node("span", "Load more"));
        more.title = `Load more products from ${creator.name}`;
        more.setAttribute("aria-label", `Load more products from ${creator.name}`);
        more.addEventListener("click", () => loadMore(creator.id));
        footer.append(count, more); catalog.append(wrap, footer); section.append(heading, catalog);
        $("creator-groups").append(section);
        groups.set(creator.id, {products: [...creator.examples], nextStart: 0, hasMore: true, total: null,
          discoveryHome: creatorHome,
          expanded: !creator.examples.length, section, body, head, columns, table, wrap, statistics, count, more, rowCache: new Map(),
          order: new Map(creator.examples.map((product, index) => [product.app_id, index]))});
        wrap.addEventListener("scroll", () => syncColumns(wrap));
      }
      renderGroups();
    }

    function catalogCsv(exportedAt = new Date().toISOString()) {
      const exportItems = creators.flatMap(creator => (groups.get(creator.id)?.products || [])
        .filter(product => results.has(product.app_id))
        .map(product => ({...results.get(product.app_id), catalog_id: creator.id, catalog_role: kind, catalog_name: creator.name})));
      return buildPriceCsv(exportItems, creatorHome, creatorRates, {sourceTab: kind, regions: creatorRegions}, exportedAt);
    }

    function syncColumns(source) {
      // Ignore events caused by our own assignments. A delayed follower event
      // must not rewind a heading that has already advanced in a smooth scroll.
      const expected = synchronizedScrolls.get(source);
      if (expected !== undefined && Math.abs(source.scrollLeft - expected) < 1) return;
      synchronizedScrolls.delete(source);
      // One shared heading follows every catalog when narrow screens require scrolling.
      for (const wrap of [$("creator-columns-scroll"), ...[...groups.values()].map(group => group.wrap)]) {
        if (wrap !== source && wrap.scrollLeft !== source.scrollLeft) {
          synchronizedScrolls.set(wrap, source.scrollLeft);
          wrap.scrollLeft = source.scrollLeft;
          wrap.refreshScrollControls?.();
        }
      }
    }

    function renderStatistics(group) {
      const loaded = [...new Set(group.products.map(product => product.app_id))].map(id => results.get(id));
      const compared = loaded.filter(item => item?.comparison);
      const uncompared = loaded.filter(item => item?.skipped).length;
      const pending = loaded.length - compared.length - uncompared;
      group.statistics.replaceChildren();
      let target = group.statistics;
      if (creatorRegions.length > 4) {
        const overview = node("details", undefined, "regional-statistics-overview");
        overview.open = group.statisticsExpanded === true;
        overview.addEventListener("toggle", () => { group.statisticsExpanded = overview.open; save(); });
        overview.append(node("summary", `Regional statistics · ${creatorRegions.length} currencies`));
        target = node("div", undefined, "regional-statistics-grid"); overview.append(target); group.statistics.append(overview);
      }
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
        target.append(metric);
      }
      const cheaper = compared.filter(item => item.comparison.is_fair).length;
      const coverage = node("p", `${compared.length} of ${loaded.length} compared · ${cheaper} cheaper/equal · ${compared.length - cheaper} pricier · ${uncompared} uncompared${pending ? ` · ${pending} pending` : ""}`, "creator-statistics-coverage");
      coverage.title = "Cheaper/equal means the baseline price is no higher than every selected converted foreign price. Pricier means it exceeds at least one. Counts cover only loaded non-free products.";
      target.append(coverage);
    }

    function renderGroups() {
      $("creators-currencies").hidden = !results.size;
      $("creators-currencies").textContent = `Displayed: ${currencyLabel({home: creatorHome, regions: creatorRegions})}`;
      $("creators-panel").classList.toggle("credit-column-visible", $("creator-show-credits").checked);
      $("creator-columns-colgroup").replaceChildren(...tableColumns());
      $("creator-columns-head").replaceChildren(tableHeading(creatorHome, true), storefrontLabelRow());
      setComparisonLayout($("creator-columns-table"), creatorRegions, $("creator-show-credits").checked);
      for (const group of groups.values()) {
        // Preserve unavailable paid products; missing prices alone do not mean free.
        group.products = group.products.filter(product => {
          const item = results.get(product.app_id);
          return !removals.has(product.app_id) && !item?.is_free && item?.comparison?.home_price?.amount !== 0;
        });
        renderStatistics(group);
        group.columns.replaceChildren(...tableColumns());
        group.head.replaceChildren(tableHeading(creatorHome), storefrontLabelRow());
        setComparisonLayout(group.table, creatorRegions, $("creator-show-credits").checked);
        const displayedIds = new Set(group.products.map(item => item.app_id));
        for (const row of [...group.body.children]) if (!displayedIds.has(row.dataset.appId)) row.remove();
        for (const id of group.rowCache.keys()) if (!displayedIds.has(id)) group.rowCache.delete(id);
        const sortedProducts = [...group.products];
        if (catalogSort !== "arrival") sortedProducts.sort((a, b) => {
          const left = results.get(a.app_id), right = results.get(b.app_id);
          if (catalogSort === "name") return catalogDirection * (left?.name || a.name).localeCompare(right?.name || b.name);
          const value = item => !item?.comparison ? null : catalogSort === "home" ? item.comparison.home_price.amount
            : catalogSort === "percentage" ? percentageDifference(item.comparison)
            : item.comparison.home_price.amount - Math.min(...item.comparison.alternatives.map(price => price.amount_in_home));
          const av = value(left), bv = value(right);
          if (av == null) return bv == null ? 0 : 1;
          if (bv == null) return -1;
          return catalogDirection * (av - bv);
        });
        for (let index = 0; index < sortedProducts.length; index++) {
          const product = sortedProducts[index];
          const item = results.get(product.app_id) || {...product, pending: true};
          const showCredits = $("creator-show-credits").checked;
          const signature = creatorHome + creatorRegions.join(",") + showCredits + showBestOffers + JSON.stringify(item);
          let cached = group.rowCache.get(product.app_id);
          if (!cached || cached.signature !== signature) {
            const row = comparisonRow(item, creatorHome, false, creatorRegions, removeTitle);
            row.children[2].className += " catalog-foreign-price";
            const role = kind === "developer" ? "Publisher" : "Developer";
            const names = item[kind === "developer" ? "publishers" : "developers"];
            const credit = Array.isArray(names) && names.length ? names.join(", ") : item.pending ? "Loading…" : "Unavailable";
            if (showCredits) row.insertBefore(node("td", credit, "catalog-credit-cell"), row.children[1]);
            else row.children[0].append(node("small", `${role}: ${credit}`, "catalog-credit"));
            if (cached) cached.row.remove();
            cached = {row, signature}; group.rowCache.set(product.app_id, cached);
          }
          if (group.body.children[index] !== cached.row) group.body.insertBefore(cached.row, group.body.children[index] || null);
        }
        group.more.hidden = !group.hasMore && group.discoveryHome === creatorHome;
        group.count.textContent = `${group.products.length} products shown${group.total != null && group.discoveryHome === creatorHome ? ` · ${group.total} in Steam catalog` : group.expanded ? "" : " · featured games"}`;
      }
      if (active && creatorRates.length) renderRates(creatorRates, $("rates"));
      refreshControls();
      refreshCurrencyAction();
    }

    function mergeSnapshot(data) {
      for (const [id, page] of Object.entries(data.catalogs || {})) {
        const group = allGroups().get(id);
        if (!group) continue;
        group.expanded = true;
        const known = new Set(group.products.map(item => item.app_id));
        for (const product of page.products) {
          if (!group.order.has(product.app_id)) group.order.set(product.app_id, group.order.size);
          if (removals.has(product.app_id)) {
            removals.pending(product.app_id)?.memberships.set(id, product);
          } else if (!known.has(product.app_id)) {
            group.products.push(product); known.add(product.app_id);
          }
        }
        group.nextStart = page.next_start; group.hasMore = page.has_more; group.total = page.total;
        group.discoveryHome = savedRequest.home;
      }
      acceptResults(data.items);
      if (data.rates?.length) creatorRates = data.rates;
      renderGroups(); save();
    }

    async function pollCreators() {
      if (!creatorJob) return;
      try {
        const data = await request(`/api/jobs/${creatorJob.id}`, {headers: {Authorization: `Bearer ${creatorJob.token}`}});
        const updating = currencyUpdating;
        if (!updating) mergeSnapshot(data);
        $("creators-progress").textContent = updating ? `Updating to ${currencyLabel(savedRequest)}: ${data.message}` : data.message;
        message(updating ? "Displayed results remain available until the currency update finishes." : data.error || (data.warnings || []).join(" "), !updating && !!data.error);
        if (data.state === "cancelling") { cancelRequested = true; refreshControls(); }
        if (terminal.has(data.state)) {
          preserveComparisonScroll(() => {
            if (updating) $("creators-progress").textContent = ["complete", "partial"].includes(data.state)
              ? `Updated to ${currencyLabel(savedRequest)}. ${data.message}` : `Currency update ${data.state}.`;
            if (updating && ["complete", "partial"].includes(data.state)) {
              creatorHome = savedRequest.home; creatorRegions = [...savedRequest.regions]; creatorRates = data.rates || [];
              results.clear(); acceptResults(data.items);
              currencyRetry = null; completedComparison = true; defaultsChanged = false;
              renderGroups();
            } else if (!updating && ["complete", "partial"].includes(data.state)) completedComparison = true;
            currencyUpdating = false;
            setCreatorBusy(false);
            creatorJob = null; save();
            if (defaultsChanged && active && !updating) scheduleFeatured();
            if (updating) message(["complete", "partial"].includes(data.state)
              ? data.state === "partial" ? "Currencies updated. Some products could not be compared; refresh to retry using cached prices." : (data.warnings || []).join(" ")
              : `${data.error || "Currency update " + data.state + "."} Displayed results are unchanged. Use Retry currency update.`, data.state === "failed");
            else if (data.state === "cancelled") message("Comparison cancelled. Use Refresh comparisons to finish checking displayed products.");
            else if (data.state === "partial") message("Some products could not be compared. Refresh comparisons to retry using cached prices.");
            refreshCurrencyAction();
          });
        } else pollTimer = setTimeout(pollCreators, 1200);
      } catch (error) {
        if (error.status === 404) {
          const updating = currencyUpdating; currencyUpdating = false;
          creatorJob = null; setCreatorBusy(false); save();
          message(updating ? "The currency update expired. Displayed results are unchanged. Retry currency update using the saved products." : "This catalog comparison expired. Refresh comparisons to start again.", true);
        } else {
          message("Connection interrupted. Reconnecting to catalog comparisons…", true);
          pollTimer = setTimeout(pollCreators, 4000);
        }
      }
    }

    function selections() {
      return currencySelection();
    }

    async function startCreators(body, preserve = false) {
      if (!body.regions.length) { message("Choose one or more comparison currencies.", true); return; }
      if (!comparisonCoordinator.claim(kind)) return;
      comparisonCoordinator.cancel(`${kind}-featured`);
      clearTimeout(pollTimer); cancelRequested = false; creatorJob = null;
      currencyUpdating = preserve; currencyRetry = preserve ? {home: body.home, regions: body.regions} : null;
      savedRequest = body; setCreatorBusy(true); message("");
      $("creators-progress").textContent = preserve ? `Updating to ${currencyLabel(body)}… Displayed results remain available.` : "Connecting to Steam…";
      save();
      try {
        const excluded = removals.exclusions();
        const memberships = body.mode === "products" ? {catalog_memberships: Object.fromEntries([...allGroups()].map(([id, group]) =>
          [id, group.products.map(product => product.app_id).filter(id => body.app_ids.includes(id))]))} : {};
        creatorJob = await request("/api/creator-jobs", {method: "POST", body: JSON.stringify({...body, ...memberships, ...(excluded.length ? {excluded_app_ids: excluded} : {})})});
        removals.register(creatorJob);
        registerCatalogJob(creatorJob);
        save(); refreshControls(); pollCreators();
      } catch (error) {
        currencyUpdating = false; setCreatorBusy(false); message(`${error.message}${preserve ? " Displayed results are unchanged. Retry the currency update." : ""}`, true); save();
        $("creators-progress").textContent = preserve ? "Currency update could not start." : "Comparison could not start. Refresh comparisons to retry.";
      }
    }

    function updateCurrencies(selected = selections()) {
      if (!initialized || comparisonCoordinator.busy || !validCurrencies(selected)) return;
      const appIds = loadedProductIds();
      if (!appIds.length || appIds.length > 1000) { message("Currency updates support 1 to 1,000 loaded products.", true); return; }
      startCreators({...selected, mode: "products", app_ids: appIds}, true);
    }

    function refreshFeatured() {
      if (comparisonCoordinator.busy) return;
      const selected = selections();
      if (results.size) { updateCurrencies(currencyRetry || selected); return; }
      if (!selected.regions.length) { message("Choose one or more comparison currencies.", true); return; }
      const mode = "products";
      const appIds = loadedProductIds();
      if (!appIds.length) { message("No products loaded yet. Search for a catalog to compare."); return; }
      if (appIds.length > 1000) { message("Refresh supports up to 1,000 displayed products. Open the app in a new tab to start with the featured games.", true); return; }
      if (selected.home !== creatorHome) {
        for (const group of groups.values()) { group.nextStart = 0; group.hasMore = true; group.total = null; }
      }
      creatorHome = selected.home; creatorRegions = selected.regions; creatorRates = []; results.clear();
      if (active) renderRates([], $("rates"));
      defaultsChanged = false;
      renderGroups(); startCreators({...selected, mode, ...(mode === "products" ? {app_ids: appIds} : {})});
    }

    function loadMore(id) {
      // Expanded pages retain the currency choices of their featured comparisons.
      const creator = creators.find(c => c.id === id);
      startCreators({home: creatorHome, regions: creatorRegions, mode: "catalog", creator_id: id,
        ...(creator.selector ? {selector: creator.selector} : {}), start: groups.get(id).discoveryHome === creatorHome ? groups.get(id).nextStart : 0});
    }

    function loadedProductIds() {
      // Pending Undo entries still need fresh offers if currencies change within seven seconds.
      const ids = [...allGroups().values()].flatMap(group => group.products.map(item => item.app_id));
      for (const id of removals.serialize().removed) if (removals.pending(id)) ids.push(id);
      return [...new Set(ids)];
    }

    function safeCreator(value) {
      if (!value || typeof value.name !== "string" || !value.name.trim() || value.name.length > 200) return null;
      const selector = value.selector;
      if (!selector || typeof value.id !== "string") return null;
      let homepage, role;
      if (selector.kind === kind && typeof selector.name === "string" &&
          selector.name.length >= 2 && selector.name.length <= 100 && value.name === selector.name &&
          new RegExp(`^${selector.kind}-[a-f0-9]{24}$`).test(value.id)) {
        homepage = `https://store.steampowered.com/search/?${selector.kind}=${encodeURIComponent(selector.name)}`;
        role = `${selector.kind === "developer" ? "Developer" : "Publisher"}`;
      } else return null;
      return {id: value.id, name: value.name, selector, homepage, role, icon: "", examples: []};
    }

    function scheduleSearch() {
      clearTimeout(searchTimer); searchTimer = null; searchRevision++; searchPending = false;
      searchChoices = []; $("creator-search-results").replaceChildren();
      $("creator-search-status").textContent = "";
      const length = $("creator-query").value.trim().length;
      if (active && length >= 2 && length <= 100) searchTimer = setTimeout(() => {
        searchTimer = null; searchCreators();
      }, 4000);
    }

    async function searchCreators(event) {
      event?.preventDefault();
      clearTimeout(searchTimer); searchTimer = null;
      if (!initialized) return;
      if (searching) { searchPending = true; return; }
      searchPending = false;
      const query = $("creator-query").value.trim();
      if (query.length < 2 || query.length > 100) {
        $("creator-search-status").textContent = "Enter a name between 2 and 100 characters."; return;
      }
      const revision = ++searchRevision, home = selectedHome();
      const current = () => revision === searchRevision && query === $("creator-query").value.trim() && home === selectedHome();
      searching = true; searchChoices = []; $("creator-search-results").replaceChildren(); refreshControls();
      $("creator-search-status").textContent = "Searching Steam…";
      try {
        const data = await request("/api/creators/search", {method: "POST", body: JSON.stringify({query, home, role: kind})});
        if (!current()) return;
        const rows = new Map();
        for (const candidate of data.exact_matches) {
          const creator = creators.find(c => c.id === candidate.id) || safeCreator(candidate);
          if (!creator) continue;
          const key = creator.name.trim().toLowerCase();
          if (!rows.has(key)) {
            const row = node("div", undefined, "creator-search-result");
            const label = node("div"); label.append(node("strong", creator.name));
            const actions = node("div", undefined, "creator-search-actions");
            row.append(actions, label); rows.set(key, {row, actions, ids: new Set()});
            $("creator-search-results").append(row);
          }
          const group = rows.get(key);
          if (group.ids.has(creator.id)) continue;
          group.ids.add(creator.id);
          const action = "Add";
          const button = node("button", action); button.type = "button";
          button.title = `Compare products listing ${creator.name} as ${kind}`;
          button.setAttribute("aria-label", `Add ${creator.name}, ${creator.role}`);
          button.addEventListener("click", () => {
            if (comparisonCoordinator.busy || groups.has(creator.id)) return;
            if (creators.length >= 20) { message("Up to 20 catalogs can be displayed in one tab. Open a new tab to start another selection.", true); return; }
            if (pendingCatalog(creator.id)) { removalNotices.undo(catalogOwner, creator.id); return; }
            removedCatalogs.delete(creator.id); finalizedCatalogs.delete(creator.id);
            creators.push(creator); buildGroups(); save(); loadMore(creator.id);
          });
          searchChoices.push({creator, button, action}); group.actions.append(button);
        }
        $("creator-search-status").textContent = rows.size
          ? `Choose a ${kind} to add and compare.`
          : `No matching ${plural} found. Try the full name from a game's store page.`;
      } catch (error) { if (current()) $("creator-search-status").textContent = error.message; }
      finally {
        searching = false; refreshControls();
        if (searchPending && active) searchCreators();
      }
    }

    function restore(saved) {
      if (!saved || !Object.hasOwn(storefronts, saved.home) || !Array.isArray(saved.regions) ||
          saved.regions.length < 1 || saved.regions.length > maxComparisons || new Set(saved.regions).size !== saved.regions.length ||
          saved.regions.some(id => !Object.hasOwn(storefronts, id) || id === saved.home)) return false;
      const oldDefaults = Array.isArray(saved.featuredIds) ? saved.featuredIds
        : (saved.creators || []).filter(value => value.examples?.length).map(value => value.id);
      defaultsChanged = oldDefaults.length > 0 && (oldDefaults.length !== defaultIds.size ||
        [...defaultIds].some(id => !oldDefaults.includes(id)));
      creatorHome = saved.home; creatorRegions = saved.regions; creatorRates = saved.rates || [];
      for (const id of Array.isArray(saved.removedCatalogs) ? saved.removedCatalogs.slice(0, 1000) : []) {
        if (typeof id === "string" && /^[A-Za-z0-9_-]{1,100}$/.test(id)) { removedCatalogs.add(id); finalizedCatalogs.add(id); }
      }
      for (const id of Array.isArray(saved.orphanedProducts) ? saved.orphanedProducts.slice(0, 10000) : []) {
        if (typeof id === "string" && /^[0-9]{1,12}$/.test(id)) orphanedProducts.add(id);
      }
      creators = creators.filter(creator => !removedCatalogs.has(creator.id));
      for (const [id, group] of groups) if (removedCatalogs.has(id)) { group.section.remove(); groups.delete(id); }
      catalogSort = ["name", "home", "difference", "percentage"].includes(saved.catalogSort) ? saved.catalogSort : "arrival";
      catalogDirection = saved.catalogDirection === -1 ? -1 : 1;
      removals.restore(saved.removals);
      completedComparison = saved.completedComparison ?? !!saved.results?.length;
      currencyRetry = validCurrencies(saved.currencyRetry) ? saved.currencyRetry : null;
      currencyUpdating = saved.currencyUpdating === true && validCurrencies(saved.request) && saved.request.mode === "products";
      for (const value of Array.isArray(saved.creators) ? saved.creators.slice(0, 20) : []) {
        if ((oldDefaults.includes(value.id) || value.examples?.length) && !defaultIds.has(value.id)) continue;
        const creator = safeCreator(value);
        if (creator && !removedCatalogs.has(creator.id) && !creators.some(c => c.id === creator.id)) creators.push(creator);
      }
      buildGroups();
      savedRequest = saved.request;
      if (active && !comparisonCoordinator.active) {
        const selected = currencyUpdating ? savedRequest : {home: creatorHome, regions: creatorRegions};
        preferredComparisons = [...selected.regions];
        document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === selected.home);
        document.querySelectorAll('[name="region"]').forEach(el => el.checked = selected.regions.includes(el.value));
        updateSelections();
      }
      $("creator-show-credits").checked = saved.showCredits === true;
      for (const item of removals.filter(saved.results || [])) if (/^[0-9]{1,12}$/.test(item.app_id)) results.set(item.app_id, item);
      for (const catalog of saved.catalogs || []) {
        const group = groups.get(catalog.id);
        if (!group || !Array.isArray(catalog.products) || !Number.isInteger(catalog.nextStart) || catalog.nextStart < 0) continue;
        group.order = new Map(catalog.products.map((product, index) => [product.app_id, index]));
        group.products = catalog.products.filter(item => !removals.has(item.app_id) && /^[0-9]{1,12}$/.test(item.app_id) && typeof item.name === "string");
        group.nextStart = catalog.nextStart; group.hasMore = catalog.hasMore; group.total = catalog.total;
        group.discoveryHome = Object.hasOwn(storefronts, catalog.discoveryHome) ? catalog.discoveryHome : saved.home;
        group.statisticsExpanded = catalog.statisticsExpanded === true;
        const featuredIds = new Set(creators.find(creator => creator.id === catalog.id).examples.map(product => product.app_id));
        group.expanded = catalog.expanded === true || catalog.nextStart > 0 || catalog.total != null ||
          group.products.some(product => !featuredIds.has(product.app_id));
      }
      acceptResults([]);
      const cleanupSources = saved.catalogSources || saved.removals?.sources;
      for (const source of Array.isArray(cleanupSources) ? cleanupSources.slice(-120) : []) {
        if (/^[A-Za-z0-9_-]{32}$/.test(source.id) && /^[A-Za-z0-9_-]{43}$/.test(source.token)) registerCatalogJob(source);
      }
      if (saved.job && /^[A-Za-z0-9_-]{32}$/.test(saved.job.id) && /^[A-Za-z0-9_-]{43}$/.test(saved.job.token)) {
        removals.register(saved.job);
        registerCatalogJob(saved.job);
        creatorJob = saved.job; savedRequest = saved.request; setCreatorBusy(true); pollCreators();
      } else { currencyUpdating = false; $("creators-progress").textContent = "Restored catalog results. Refresh comparisons for a new price check."; }
      renderGroups(); return true;
    }

    async function initialize() {
      if (initialized || initializing) return;
      initializing = true;
      const release = comparisonCoordinator.hold(`${kind}-initializing`);
      try {
        const data = await request("/api/creators"); creators = data[plural];
        for (const creator of creators) defaultIds.add(creator.id);
        buildGroups(); initialized = true;
        let restored = false;
        try {
          let saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
          if (!saved) {
            const legacy = JSON.parse(sessionStorage.getItem("polisher-creator-job") || "null");
            if (legacy) {
              const compatible = (legacy.creators || []).filter(value => value.selector?.kind === kind);
              const ids = new Set(compatible.map(value => value.id));
              // Homepage catalogs cannot establish either role; keep only exact-role selections.
              saved = {...legacy, job: null, creators: compatible,
                catalogs: (legacy.catalogs || []).filter(catalog => ids.has(catalog.id))};
            }
          }
          restored = restore(saved);
          if (restored) {
            if ([...results.values()].some(item => item.comparison && (!Array.isArray(item.developers) || !Array.isArray(item.publishers)))) defaultsChanged = true;
            save();
          }
        } catch (_) { /* Ignore invalid saved state. */ }
        if (active && (!restored || (defaultsChanged && !creatorJob))) scheduleFeatured();
      } catch (error) { message(error.message, true); }
      finally {
        initializing = false; release(); refreshControls();
        if (active && initialized && !searchTimer && !searching && $("creator-query").value.trim()) scheduleSearch();
      }
    }

    function scheduleFeatured() {
      if (!active) return;
      $("creators-progress").textContent = "Waiting for the current comparison to finish…";
      comparisonCoordinator.whenIdle(`${kind}-featured`, refreshFeatured, () => active && initialized && !busy);
    }

    function activate(value) {
      active = value;
      if (active) {
        $("creator-columns-scroll").refreshScrollControls?.();
        renderRates(creatorRates, $("rates"));
        initialize();
        if (initialized && (!savedRequest || defaultsChanged) && !busy) scheduleFeatured();
      } else {
        comparisonCoordinator.cancel(`${kind}-featured`);
        clearTimeout(searchTimer); searchTimer = null; searchRevision++; searchPending = false;
      }
    }

    $("creator-columns-scroll").addEventListener("scroll", () => syncColumns($("creator-columns-scroll")));
    bindComparisonScroll(plural, $("creator-columns-scroll"));
    $("creators-export").addEventListener("click", () => downloadCsv(catalogCsv(), `steam-${plural}-comparison.csv`));
    $("creators-refresh").addEventListener("click", () => initialized ? refreshFeatured() : initialize());
    $("creator-search-form").addEventListener("submit", searchCreators);
    $("creator-query").addEventListener("input", scheduleSearch);
    $("creator-show-credits").addEventListener("change", () => { renderGroups(); save(); });
    $("creators-cancel").addEventListener("click", async () => {
      if (!creatorJob) return;
      cancelRequested = true; refreshControls();
      try { await request(`/api/jobs/${creatorJob.id}/cancel`, {method: "POST", body: "{}", headers: {Authorization: `Bearer ${creatorJob.token}`}}); }
      catch (error) { cancelRequested = false; refreshControls(); message(error.message, true); }
    });
    return {kind, get busy() { return busy; }, activate, initialize, refreshControls, render: renderGroups, updateCurrencies,
      currencyState: () => completedComparison && [...groups.values()].some(group => group.products.length) ? {home: creatorHome, regions: creatorRegions} : null};
  }

  for (const kind of ["developer", "publisher"]) panes.set(kind, createPane(kind));
  function selectTab(tab) {
    if (tab === "library" && !libraryEnabled) tab = "wishlist";
    selectedTab = tab;
    document.getElementById("currencies-step").textContent = "02 / CURRENCIES";
    document.getElementById("wishlist-panel").hidden = tab !== "wishlist";
    document.getElementById("compare-form").hidden = tab !== "wishlist";
    document.getElementById("game-discovery").hidden = tab !== "wishlist";
    document.getElementById("library-panel").hidden = tab !== "library";
    document.getElementById("library-compare-form").hidden = tab !== "library";
    window.libraryPane?.activate(tab === "library");
    for (const [kind, pane] of panes) {
      document.getElementById(kind + "s-panel").hidden = tab !== kind;
      document.getElementById(kind + "-discovery").hidden = tab !== kind;
      pane.activate(tab === kind);
    }
    if (tab === "wishlist") { renderRates(currentRates, document.getElementById("rates")); document.getElementById("wishlist-scroll").refreshScrollControls?.(); }
    for (const name of ["wishlist", "library", "developer", "publisher"]) {
      const button = document.getElementById(tabId(name));
      button.setAttribute("aria-selected", String(tab === name)); button.tabIndex = tab === name ? 0 : -1;
    }
    try { sessionStorage.setItem("polisher-active-tab", tab); } catch (_) {}
    comparisonCoordinator.wake();
    refreshCurrencyAction();
  }
  window.creatorPane = {get active() { return selectedTab === "developer" || selectedTab === "publisher"; }, get busy() { return anyBusy(); },
    currencyState: () => panes.get(selectedTab)?.currencyState(),
    updateCurrencies: () => panes.get(selectedTab)?.updateCurrencies(),
    refreshControls() { for (const pane of panes.values()) pane.refreshControls(); },
    render() { for (const pane of panes.values()) pane.render(); }};
  const tabId = name => ["wishlist", "library"].includes(name) ? name + "-tab" : name + "s-tab";
  const libraryEnabled = document.documentElement?.dataset.ownedLibraryEnabled === "true";
  document.getElementById("library-tab").hidden = !libraryEnabled;
  const tabs = libraryEnabled ? ["wishlist", "library", "developer", "publisher"] : ["wishlist", "developer", "publisher"];
  for (const [index, name] of tabs.entries()) {
    const button = document.getElementById(tabId(name));
    button.addEventListener("click", () => selectTab(name));
    button.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const targetIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
      selectTab(tabs[targetIndex]);
      document.getElementById(tabId(tabs[targetIndex])).focus();
    });
  }
  // Reconnect saved work even on a hidden tab before permitting automatic jobs.
  for (const [kind, pane] of panes) {
    try {
      const savedJob = JSON.parse(sessionStorage.getItem(`polisher-${kind}-job`) || "null")?.job;
      if (savedJob && /^[A-Za-z0-9_-]{32}$/.test(savedJob.id) && /^[A-Za-z0-9_-]{43}$/.test(savedJob.token)) pane.initialize();
    } catch (_) { /* Invalid storage on one tab must not prevent other restoration. */ }
  }
  try {
    const saved = sessionStorage.getItem("polisher-active-tab");
    if (["library", "developer", "publisher", "creators"].includes(saved)) selectTab(saved === "creators" ? "developer" : saved);
  } catch (_) {}
})();
