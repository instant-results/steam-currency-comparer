"use strict";
const $ = (id) => document.getElementById(id);
let items = [], filter = "all", sort = "arrival", direction = 1, job = null, running = false, demoMode = false, timer = null, lastRequest = null;
let displayedWishlist = null, pendingCurrency = null, retryCurrency = null, wishlistExpired = false;
const money = (value) => new Intl.NumberFormat("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(value);
const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
// One viewport stack across tabs. Row payloads exist only in these short-lived entries.
const removalNotices = (() => {
  const entries = [];
  const key = (owner, id) => `${owner}:${id}`;
  function layout() {
    for (const [index, entry] of entries.entries()) entry.element.classList.toggle("removal-notice-compact", entries.length === 4 && index === 0);
  }
  function finish(entry, undo = false) {
    if (!entries.includes(entry)) return;
    const restore = undo && Date.now() < entry.deadline;
    const focused = entry.element.contains(document.activeElement);
    clearTimeout(entry.timer); entries.splice(entries.indexOf(entry), 1); entry.element.remove();
    const callback = restore ? entry.undo : entry.commit, data = entry.data;
    entry.data = entry.undo = entry.commit = entry.element = null;
    callback(data); layout();
    if (focused) (entries.at(-1)?.button || $("wishlist-tab")).focus({preventScroll: true});
  }
  return {
    undo(owner, id) { const entry = entries.find(entry => entry.key === key(owner, id)); if (entry) finish(entry, true); },
    find(owner, id) { return entries.find(entry => entry.key === key(owner, id)); },
    commitOwner(owner) { for (const entry of [...entries]) if (entry.key.startsWith(`${owner}:`)) finish(entry); },
    commitAll() { for (const entry of [...entries]) finish(entry); },
    add(owner, id, name, data, undo, commit) {
      for (const entry of [...entries]) if (Date.now() >= entry.deadline) finish(entry);
      if (entries.length === 4) finish(entries[0]);
      const element = node("div", undefined, "removal-notice"), text = node("div", undefined, "removal-notice-text");
      const title = node("strong", name || `Steam product ${id}`);
      title.title = name || `Steam product ${id}`;
      text.append(title, node("span", `Removed · App ID ${id}`));
      const button = node("button", "Undo", "removal-undo"); button.type = "button";
      button.setAttribute("aria-label", `Undo removal of ${name || id}, Steam App ID ${id}`);
      const progress = node("span", undefined, "removal-countdown"); progress.setAttribute("aria-hidden", "true");
      element.setAttribute("role", "status"); element.append(text, button, progress);
      const entry = {key: key(owner, id), deadline: Date.now() + 7000, data, undo, commit, element, button};
      button.addEventListener("click", () => finish(entry, true));
      entry.timer = setTimeout(() => finish(entry), 7000); entries.push(entry);
      $("removal-notices").append(element); layout();
    }
  };
})();
window.addEventListener?.("pagehide", () => removalNotices.commitAll());

function createTitleRemovals(owner, changed, restoreRow, reportError) {
  const removed = new Set(), committed = new Set(), sources = new Map();
  let syncing = false, retryTimer = null;
  const validId = id => typeof id === "string" && /^[0-9]{1,12}$/.test(id);
  async function sync() {
    if (syncing) return;
    clearTimeout(retryTimer); retryTimer = null; syncing = true;
    let failed = false;
    try {
      await Promise.all([...sources].map(async ([id, source]) => {
        const appIds = [...committed].filter(value => !source.sent.has(value)).slice(0, 1000);
        if (!appIds.length) return;
        try {
          await request(`/api/jobs/${id}/remove`, {method: "POST", keepalive: true, body: JSON.stringify({app_ids: appIds}), headers: {Authorization: `Bearer ${source.token}`}});
          for (const value of appIds) source.sent.add(value);
        } catch (error) {
          if (error.status === 404) sources.delete(id);
          else failed = true;
        }
      }));
    } finally {
      syncing = false;
      const remaining = [...sources.values()].some(source => [...committed].some(id => !source.sent.has(id)));
      if (remaining) retryTimer = setTimeout(sync, failed ? 4000 : 0);
      if (failed) reportError("Title removed locally. Server cleanup will retry when the connection is available.");
    }
  }
  return {
    get size() { return removed.size; },
    has: id => removed.has(id),
    capture(item) {
      const pending = removalNotices.find(owner, item.app_id);
      if (pending) pending.data.item = item;
    },
    filter(items) {
      return items.filter(item => { if (!removed.has(item.app_id)) return true; this.capture(item); return false; });
    },
    pending: id => removalNotices.find(owner, id)?.data,
    pendingIds: () => [...removed].filter(id => removalNotices.find(owner, id)),
    readd(id) {
      removalNotices.undo(owner, id);
      removed.delete(id); committed.delete(id);
      for (const source of sources.values()) source.sent.delete(id);
      changed();
    },
    remove(id, name, data) {
      if (removed.has(id)) return;
      if (removed.size >= 10000) { reportError("This comparison has reached its 10,000-title removal limit. Start a fresh comparison to reset it."); return; }
      removed.add(id);
      removalNotices.add(owner, id, name, data, record => { removed.delete(id); restoreRow(record); changed(); },
        () => { committed.add(id); queueMicrotask(sync); changed(); });
      changed();
    },
    register(source) {
      if (!source?.id || !source.token || sources.has(source.id)) return;
      // Cover the default 100 completed and 20 active server job slots.
      if (sources.size >= 120) sources.delete(sources.keys().next().value);
      sources.set(source.id, {token: source.token, sent: new Set()}); if (committed.size) sync();
    },
    exclusions: () => [...committed],
    serialize: () => ({removed: [...removed], sources: [...sources].map(([id, source]) => ({id, token: source.token}))}),
    restore(value) {
      for (const id of Array.isArray(value?.removed) ? value.removed.slice(0, 10000) : []) if (validId(id)) { removed.add(id); committed.add(id); }
      for (const source of Array.isArray(value?.sources) ? value.sources.slice(-120) : []) {
        if (/^[A-Za-z0-9_-]{32}$/.test(source.id) && /^[A-Za-z0-9_-]{43}$/.test(source.token)) this.register(source);
      }
    }
  };
}
const wishlistArrivalOrder = new Map();
function newWishlistRemovals() {
  return createTitleRemovals("wishlist", () => {
    items = wishlistRemovals.filter(items);
    if (displayedWishlist) displayedWishlist.data.items = items;
    render();
  }, record => {
    items.push(record.item);
    items.sort((a, b) => (wishlistArrivalOrder.get(a.app_id) ?? Infinity) - (wishlistArrivalOrder.get(b.app_id) ?? Infinity));
  }, message => notice(message, true));
}
let wishlistRemovals = newWishlistRemovals();
function filterWishlistSnapshot(data) {
  for (const item of data.items) if (!wishlistArrivalOrder.has(item.app_id)) wishlistArrivalOrder.set(item.app_id, wishlistArrivalOrder.size);
  const count = data.items.length;
  data.items = wishlistRemovals.filter(data.items);
  data.total = Math.max(data.items.length, (data.total || 0) - count + data.items.length);
  return data;
}
function removeWishlistTitle(appId) {
  const item = items.find(value => value.app_id === appId);
  if (!item) return;
  for (const value of items) if (!wishlistArrivalOrder.has(value.app_id)) wishlistArrivalOrder.set(value.app_id, wishlistArrivalOrder.size);
  wishlistRemovals.remove(appId, item.name, {item});
}
const storefronts = JSON.parse(document.documentElement.dataset.storefronts);
const maxComparisons = Object.keys(storefronts).length - 1;
function buildStorefrontControls() {
  for (const [region, value] of Object.entries(storefronts)) {
    for (const [target, name, type] of [["baseline-options", "home", "radio"], ["comparison-options", "region", "checkbox"]]) {
      const label = node("label", undefined, "region"), input = node("input"), caption = node("span", value.currency);
      input.type = type; input.name = name; input.value = region;
      input.checked = name === "home" ? region === "pl" : ["us", "de"].includes(region);
      caption.append(node("small", `${value.currency_name} · ${value.name}`));
      const flag = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      flag.setAttribute("class", "currency-flag"); flag.setAttribute("aria-hidden", "true");
      flag.setAttribute("focusable", "false"); flag.setAttribute("width", "24"); flag.setAttribute("height", "24");
      const artwork = document.createElementNS("http://www.w3.org/2000/svg", "use");
      artwork.setAttribute("href", `/flags.svg#${value.currency === "EUR" ? "eu" : region}`);
      flag.append(artwork);
      label.dataset.storefront = region; label.append(input, caption, flag); $(target).append(label);
    }
  }
}
function filterStorefrontControls() {
  const query = $("currency-search").value.trim().toLocaleLowerCase();
  for (const label of document.querySelectorAll('[data-storefront]')) {
    const region = label.dataset.storefront, value = storefronts[region];
    label.hidden = (label.parentElement?.id === "comparison-options" && region === selectedHome())
      || !`${value.currency} ${value.name} ${value.currency_name}`.toLocaleLowerCase().includes(query);
  }
}
// Shared scheduling for every comparison tab. Restoring jobs may register while
// initialization is held; new jobs claim the idle worker before changing results.
const comparisonCoordinator = (() => {
  const owners = new Set(), holds = new Set(), pending = new Map(), listeners = new Set();
  let scheduled = false;
  const busy = () => owners.size > 0 || holds.size > 0;
  function wake() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      if (busy()) return;
      for (const [key, task] of [...pending].sort((a, b) => a[1].priority - b[1].priority)) {
        if (busy()) break;
        if (!task.eligible()) continue;
        pending.delete(key);
        task.run();
      }
    });
  }
  function changed() { for (const listener of listeners) listener(); wake(); }
  return {
    get busy() { return busy(); },
    get active() { return owners.size > 0; },
    claim(owner) { if (busy()) return false; owners.add(owner); changed(); return true; },
    setBusy(owner, value) { if (value) owners.add(owner); else owners.delete(owner); changed(); },
    hold(key) { holds.add(key); changed(); return () => { holds.delete(key); changed(); }; },
    whenIdle(key, run, eligible = () => true, priority = 0) { pending.set(key, {run, eligible, priority}); wake(); },
    cancel(key) { pending.delete(key); },
    subscribe(listener) { listeners.add(listener); },
    wake
  };
})();
const wishlistOrders = new Set(["priority", "date_added", "name"]);
let resultHome = "pl", preferredComparisons = null;
let automaticExampleDismissed = false;
const baseline = () => storefronts[resultHome];
const unit = () => baseline().currency === "PLN" ? "zł" : baseline().currency;
const formatProvenance = (source) => {
  if (!source) return "";
  if (source === "cache") return "cached";
  if (source === "stale cache" || source === "stale") return "stale";
  if (source === "live") return "live";
  return source;
};
function selectedHome() { return [...document.querySelectorAll('[name="home"]')].find(el => el.checked)?.value || "pl"; }
function currencySelection() {
  return {home: selectedHome(), regions: [...document.querySelectorAll('[name="region"]')].filter(el => el.checked).map(el => el.value)};
}
function currencyLabel(selection) {
  const currencies = selection.regions.map(id => storefronts[id].currency);
  const alternatives = currencies.length > 4 ? `${currencies.length} storefronts`
    : new Intl.ListFormat("en", {style: "long", type: "conjunction"}).format(currencies);
  return `${storefronts[selection.home].currency} against ${alternatives}`;
}
function sameCurrencies(a, b) { return a.home === b.home && a.regions.join(",") === b.regions.join(","); }
let currencyPanelWasActive = false, currencyPanelUsed = false, currencyPanelRestoreSelection = null;
function displayedCurrencySelection() {
  return window.creatorPane?.active ? window.creatorPane.currencyState() : window.libraryPane?.active ? null : displayedWishlist?.request;
}
function setCurrencyPanelExpanded(expanded, discardChanges = false) {
  const body = $("currency-panel-body"), toggle = $("currency-panel-toggle");
  // Return focus before hiding a control used to start a currency update.
  if (!expanded && body.contains(document.activeElement)) toggle.focus();
  body.hidden = !expanded;
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.textContent = expanded ? "Hide currencies" : "Change currencies";
  if (expanded) {
    const selection = currencySelection();
    currencyPanelRestoreSelection = {home: selection.home, regions: [...selection.regions]};
  } else if (discardChanges && !comparisonCoordinator.busy) {
    const selection = displayedCurrencySelection() || currencyPanelRestoreSelection;
    if (selection) {
      preferredComparisons = [...selection.regions];
      document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === selection.home);
      document.querySelectorAll('[name="region"]').forEach(el => el.checked = selection.regions.includes(el.value));
      updateSelections();
    }
  }
}
function syncCurrencyPanel(hasComparison) {
  const active = comparisonCoordinator.active;
  // Collapse once per run; reopening during a run remains possible.
  if ((active && !currencyPanelWasActive) || (hasComparison && !currencyPanelUsed)) setCurrencyPanelExpanded(false);
  if (active || hasComparison) currencyPanelUsed = true;
  currencyPanelWasActive = active;
}
function preserveComparisonScroll(update) {
  const x = window.scrollX || 0, y = window.scrollY || 0;
  const wraps = [...document.querySelectorAll('.table-wrap')].map(el => [el, el.scrollLeft]);
  update();
  for (const [el, left] of wraps) el.scrollLeft = left;
  window.scrollTo?.({left: x, top: y, behavior: "instant"});
}
function validCurrencies(value) {
  return value && Object.hasOwn(storefronts, value.home) && Array.isArray(value.regions) && value.regions.length >= 1 && value.regions.length <= maxComparisons
    && new Set(value.regions).size === value.regions.length && value.regions.every(id => Object.hasOwn(storefronts, id) && id !== value.home);
}
function refreshCurrencyAction() {
  const catalog = window.creatorPane?.active;
  const displayed = displayedCurrencySelection();
  const selected = currencySelection(), button = $("update-currencies");
  button.disabled = comparisonCoordinator.busy || !validCurrencies(selected) || !displayed || sameCurrencies(selected, displayed);
  $("currency-update-help").hidden = !displayed;
  $("currency-edit-help").hidden = !displayed;
  $("currency-update-help").textContent = displayed ? `Displayed: ${currencyLabel(displayed)}. Updates apply to this tab.${!catalog && wishlistExpired ? " Updating currencies will reload this saved comparison." : ""}` : "";
  syncCurrencyPanel(Boolean(displayed));
  button.hidden = !displayed || $("currency-panel-body").hidden;
  window.gameAdditions?.refreshControls();
}
function updateSelections(event) {
  const home = selectedHome();
  const options = [...document.querySelectorAll('[name="region"]')];
  // Baseline conflicts hide preferences temporarily; explicit checkbox edits replace them.
  if (preferredComparisons === null || event?.target?.name === "region") {
    preferredComparisons = options.filter(el => el.checked && el.value !== home).map(el => el.value);
  }
  for (const el of options) el.checked = el.value !== home && preferredComparisons.includes(el.value);
  const selected = options.filter(el => el.checked);
  const count = selected.length;
  if (currencyPanelRestoreSelection === null) currencyPanelRestoreSelection = {home, regions: selected.map(el => el.value)};
  for (const caption of [$("welcome-currencies"), $("library-welcome-currencies")].filter(Boolean)) {
    caption.replaceChildren(node("span", storefronts[home].currency, "welcome-currency"));
    for (const el of selected) caption.append(node("span", "↔"), node("span", storefronts[el.value].currency, "welcome-currency"));
  }
  for (const el of options) {
    el.disabled = comparisonCoordinator.busy || el.value === home;
    el.closest('label').hidden = el.value === home;
  }
  document.querySelectorAll('[name="home"]').forEach(el => el.disabled = comparisonCoordinator.busy);
  window.creatorPane?.refreshControls();
  window.libraryPane?.refreshControls();
  $("analyze").disabled = comparisonCoordinator.busy;
  $("retry").disabled = comparisonCoordinator.busy;
  $("compare-legend").textContent = `Compare ${storefronts[home].currency} with`;
  $("baseline-legend").textContent = `Baseline currency · ${storefronts[home].currency}`;
  $("selection-help").textContent = `${count} of ${maxComparisons} selected · Choose one or more.`;
  $("currency-selection-summary").textContent = count
    ? `Selected: ${currencyLabel({home, regions: selected.map(el => el.value)})}`
    : `Selected: ${storefronts[home].currency} · no comparison currencies`;
  $("select-all-currencies").disabled = comparisonCoordinator.busy || count === maxComparisons;
  $("clear-currencies").disabled = comparisonCoordinator.busy || count === 0;
  filterStorefrontControls();
  refreshCurrencyAction();
}
function showBaseline(home) {
  resultHome = Object.hasOwn(storefronts, home) ? home : "pl";
  $("home-heading").textContent = `PRICE IN ${baseline().name.toUpperCase()}`;
  $("converted-heading").textContent = `CONVERTED TO ${baseline().currency}`;
  $("difference-currency").textContent = baseline().currency;
  $("expensive-label").textContent = `Pricier in ${baseline().name}`;
}
function comparisonRegions(values, fallbackItems = []) {
  return values?.length ? values : fallbackItems.find(item => item.comparison)?.comparison.alternatives.map(price => price.region) || [];
}
function regionalHeadings(regions) {
  return regions.map(region => {
    const label = node("span", storefronts[region].currency, "storefront-heading");
    label.append(node("small", `${storefronts[region].name} · ${region.toUpperCase()}`)); return label;
  });
}
const offerAlignmentFrames = new WeakMap(), offerAlignmentObservers = new WeakMap();
function alignBestOffers(table) {
  if (!showBestOffers || !table.getBoundingClientRect().width) return;
  const rows = [...table.querySelectorAll("tbody tr")].map(row => ({row,
    blocks: [...row.querySelectorAll(".best-offer")].filter(block => block.querySelector(".offer-label"))
  })).filter(entry => entry.blocks.length);
  // Reset, measure, then write in batches so wrapping can shrink as well as grow.
  for (const {row, blocks} of rows) {
    for (const band of ["label", "value", "name"]) row.style.setProperty(`--offer-${band}-height`, "0px");
    for (const block of blocks) block.style.setProperty("--offer-align-offset", "0px");
  }
  const measured = rows.map(({row, blocks}) => {
    const labels = blocks.map(block => block.querySelector(".offer-label").getBoundingClientRect());
    const height = selector => Math.max(0, ...blocks.map(block => block.querySelector(selector)?.getBoundingClientRect().height || 0));
    return {row, blocks, labels, top: Math.max(...labels.map(label => label.top)),
      label: Math.max(...labels.map(label => label.height)), value: height(".offer-value"), name: height(".offer-name")};
  });
  for (const entry of measured) {
    for (const band of ["label", "value", "name"]) entry.row.style.setProperty(`--offer-${band}-height`, `${entry[band]}px`);
    entry.blocks.forEach((block, index) => block.style.setProperty("--offer-align-offset", `${entry.top - entry.labels[index].top}px`));
  }
}
function scheduleOfferAlignment(table) {
  if (typeof requestAnimationFrame !== "function") return;
  if (!offerAlignmentObservers.has(table) && typeof ResizeObserver !== "undefined") {
    let previousWidth;
    const observer = new ResizeObserver(entries => {
      const width = entries[0].contentRect.width;
      if (width !== previousWidth) { previousWidth = width; scheduleOfferAlignment(table); }
    });
    observer.observe(table);
    offerAlignmentObservers.set(table, observer);
  }
  if (offerAlignmentFrames.has(table)) return;
  offerAlignmentFrames.set(table, requestAnimationFrame(() => {
    offerAlignmentFrames.delete(table);
    alignBestOffers(table);
  }));
}
function setComparisonLayout(table, regions, credits = false) {
  table.classList.toggle("comparison-matrix", true);
  table.classList.toggle("matrix-with-credits", credits);
  const count = String(Math.max(regions.length, 1));
  const area = table.closest?.(".comparison-area");
  area?.classList.toggle("matrix-with-credits", credits);
  area?.style.setProperty("--region-count", count);
  table.style.setProperty("--region-count", count);
  table.parentElement?.refreshScrollControls?.();
  scheduleOfferAlignment(table);
}
function bindComparisonScroll(prefix, wrap) {
  const rail = $(prefix + "-scrollbar"), extent = $(prefix + "-scrollbar-extent");
  let synchronizedLeft, stickyTitles, headingSignature;
  const refreshStickyTitles = () => {
    // The original headings stay in the table for layout and accessibility.
    // Show a visual copy beneath the sticky scrollbar only after reaching it.
    if (typeof wrap.getBoundingClientRect !== "function") return;
    const table = wrap.querySelector("table"), source = table.querySelector(".storefront-label-cell .storefront-headings");
    const area = wrap.closest(".comparison-area"), shell = rail.parentElement;
    if (!source || !area) return;
    if (!stickyTitles) {
      stickyTitles = node("div", undefined, "sticky-storefront-titles comparison-matrix");
      stickyTitles.setAttribute("aria-hidden", "true");
      shell.append(stickyTitles);
    }
    if (headingSignature !== source.innerHTML) {
      const copy = source.cloneNode(true);
      copy.removeAttribute("id");
      stickyTitles.replaceChildren(copy);
      headingSignature = source.innerHTML;
    }
    stickyTitles.classList.toggle("matrix-with-credits", table.classList.contains("matrix-with-credits"));
    const count = table.style.getPropertyValue("--region-count") || "1";
    stickyTitles.style.setProperty("--region-count", count);
    const sourceBox = source.getBoundingClientRect(), shellBox = shell.getBoundingClientRect();
    const wrapBox = wrap.getBoundingClientRect();
    const homeBox = table.querySelector(".storefront-label-row .pinned-home").getBoundingClientRect();
    const differenceBox = table.querySelector(".storefront-label-row .pinned-difference").getBoundingClientRect();
    // Use rendered cell edges: the table can be narrower than its scroll surface,
    // and this copy lives outside the table's container-query sizing context.
    const left = Math.max(sourceBox.left, homeBox.right, wrapBox.left);
    const right = Math.min(sourceBox.right, differenceBox.left, wrapBox.right);
    stickyTitles.style.left = `${left - shellBox.left}px`;
    stickyTitles.style.width = `${Math.max(0, right - left)}px`;
    stickyTitles.style.setProperty("--region-width", `${sourceBox.width / Number(count)}px`);
    stickyTitles.firstElementChild.style.transform = `translateX(${sourceBox.left - left}px)`;
    const top = shellBox.bottom;
    stickyTitles.hidden = wrap.clientWidth === 0 || right <= left || sourceBox.top > top || area.getBoundingClientRect().bottom <= top + sourceBox.height;
  };
  const refresh = () => {
    const overflow = Math.max(0, wrap.scrollWidth - wrap.clientWidth);
    if (!Number.isFinite(overflow)) return;
    rail.hidden = overflow < 1;
    rail.parentElement.hidden = false;
    rail.parentElement.classList.toggle("without-scrollbar", overflow < 1);
    // The proxy covers only the visible regional columns, but has exactly the
    // same scroll range as the table with its pinned columns at either edge.
    extent.style.width = `${rail.clientWidth + overflow}px`;
    if (Math.abs(rail.scrollLeft - wrap.scrollLeft) > .5) {
      synchronizedLeft = wrap.scrollLeft;
      rail.scrollLeft = wrap.scrollLeft;
    }
    refreshStickyTitles();
  };
  rail.addEventListener("scroll", () => {
    // A delayed event from a programmatic update must not rewind a newer drag.
    if (synchronizedLeft !== undefined && Math.abs(rail.scrollLeft - synchronizedLeft) < .5) return;
    synchronizedLeft = undefined;
    wrap.scrollLeft = rail.scrollLeft;
    refresh();
  });
  wrap.addEventListener("scroll", refresh);
  window.addEventListener?.("resize", refresh);
  window.addEventListener?.("scroll", refreshStickyTitles, {passive: true});
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(refresh);
    observer.observe(wrap);
    observer.observe(wrap.querySelector("table"));
  }
  wrap.refreshScrollControls = refresh;
  refresh();
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
  if (profile === "selection") {
    currentProfile = ""; $("profile-attribution").textContent = "Manually selected games";
  } else if (profile === "example") {
    $("profile-attribution").textContent = items.some(item => item.manually_added)
      ? "Curated example wishlist + manually added games" : "Curated example wishlist";
  } else {
    $("profile-attribution").textContent = profile ? `Wishlist: ${profile}` : "Saved comparison · profile was not recorded by the earlier app version";
  }
  $("profile-attribution").hidden = false;
}
function restoreRequest(saved) {
  const request = saved?.request;
  const order = request?.order || "priority";
  if (!request || typeof request.identifier !== "string" || request.identifier.length > 200 || !Array.isArray(request.regions) || !request.regions.length || request.regions.length > maxComparisons || !Object.hasOwn(storefronts, request.home || "pl") || !wishlistOrders.has(order) || new Set(request.regions).size !== request.regions.length || request.regions.some(region => !Object.hasOwn(storefronts, region) || region === (request.home || "pl"))) return false;
  preferredComparisons = [...request.regions];
  lastRequest = {identifier: request.identifier, regions: request.regions, home: request.home || "pl", order,
    ...(Array.isArray(request.app_ids) ? {app_ids: request.app_ids} : {}),
    ...(Array.isArray(request.added_app_ids) ? {added_app_ids: request.added_app_ids} : {})};
  document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === lastRequest.home);
  showBaseline(lastRequest.home);
  $("identifier").value = ["example", "selection"].includes(request.identifier) ? "" : request.identifier;
  $("wishlist-order").value = order;
  document.querySelectorAll('[name="region"]').forEach(el => el.checked = request.regions.includes(el.value));
  updateSelections();
  showProfile(request.identifier);
  return true;
}
function isCalculatedDiscount(price) {
  return price.discount_calculated ?? !Number.isInteger(price.discount_percent);
}
function discountLabel(price, negative = false) {
  const calculated = isCalculatedDiscount(price);
  const percent = calculated ? Math.floor(price.discount_percent) : price.discount_percent;
  return `${calculated ? "≈" : ""}${negative && percent > 0 ? "−" : ""}${percent}%`;
}
function saleNote(price, currency) {
  const note = node("div", undefined, "sale-note");
  if (price.discount_percent == null || price.base_amount == null) {
    note.append(node("small", "Sale details unavailable"));
  } else if (price.discount_percent > 0 || price.discount_calculated && price.base_amount > (price.amount ?? price.original_amount)) {
    const badge = node("span", discountLabel(price, true), "sale-badge");
    badge.title = isCalculatedDiscount(price)
      ? "Calculated by this app from the regular and current prices, rounded down to a whole percentage point."
      : "Discount percentage provided by Steam.";
    note.append(badge, node("s", `${money(price.base_amount)} ${currency}`));
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
function saveWishlist() {
  if (!displayedWishlist && !job) return;
  saveJob({...job, request: lastRequest, displayed: displayedWishlist, pending: pendingCurrency, retryCurrency, expired: wishlistExpired,
    removals: wishlistRemovals.serialize(),
    view: {search: $("search").value, filter, sort, direction, showUnavailable: $("show-unavailable").checked}});
}
function applyWishlistSnapshot(data, body) {
  filterWishlistSnapshot(data);
  lastRequest = body; demoMode = body.identifier === "example";
  showBaseline(body.home); items = data.items; showRates(data.rates);
  $("results-title").textContent = demoMode ? "Example price comparison" : "Your price comparison";
  $("wishlist-currencies").textContent = `Displayed: ${currencyLabel(body)}`;
  $("wishlist-currencies").hidden = false;
  render();
}
async function updateWishlistCurrencies(selection = currencySelection()) {
  if (!displayedWishlist || !validCurrencies(selection) || !comparisonCoordinator.claim("wishlist")) return;
  retryCurrency = selection;
  pendingCurrency = {request: {...displayedWishlist.request, ...selection}, job: null};
  setBusy(true); $("cancel").disabled = true; status("UPDATING CURRENCIES", true);
  $("progress").value = 0; $("progress-label").textContent = `Updating to ${currencyLabel(selection)}… Displayed results remain available.`;
  notice(""); saveWishlist();
  try {
    if (!wishlistExpired) {
      try {
        pendingCurrency.job = await request(`/api/jobs/${job.id}/currencies`, {method: "POST", body: JSON.stringify(selection), headers: {Authorization: `Bearer ${job.token}`}});
      } catch (error) {
        if (error.status !== 404) throw error;
        wishlistExpired = true;
      }
    }
    if (wishlistExpired) {
      const source = pendingCurrency.request.app_ids ? "Recreating the saved selection" : pendingCurrency.request.identifier === "example" ? "Recreating the example" : "Reloading the wishlist";
      $("progress-label").textContent = `${source} with ${currencyLabel(selection)}… Displayed results remain available.`;
      refreshCurrencyAction(); saveWishlist();
      const excluded = wishlistRemovals.exclusions();
      pendingCurrency.job = await request("/api/jobs", {method: "POST", body: JSON.stringify({...pendingCurrency.request, ...(excluded.length ? {excluded_app_ids: excluded} : {})})});
    }
    wishlistRemovals.register(pendingCurrency.job);
    saveWishlist(); $("cancel").disabled = false; pollWishlistCurrencies();
  } catch (error) {
    pendingCurrency = null;
    setBusy(false); status("UPDATE COULD NOT START");
    notice(`${error.message} Displayed results are unchanged. Retry the currency update.`, true);
    $("retry").textContent = "Retry currency update ↻"; saveWishlist();
  }
}
async function pollWishlistCurrencies() {
  const pending = pendingCurrency;
  if (!pending?.job) return;
  try {
    const data = await request(`/api/jobs/${pending.job.id}`, {headers: {Authorization: `Bearer ${pending.job.token}`}});
    const terminal = ["complete", "partial", "cancelled", "failed"].includes(data.state);
    $("progress-label").textContent = `Updating to ${currencyLabel(pending.request)}: ${data.message}`;
    $("progress").max = Math.max(data.total, 1); $("progress").value = data.items.length;
    if (data.state === "cancelling") { $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; }
    if (!terminal) { timer = setTimeout(pollWishlistCurrencies, 1200); return; }
    preserveComparisonScroll(() => {
      pendingCurrency = null;
      if (["complete", "partial"].includes(data.state)) {
        job = pending.job; displayedWishlist = {request: pending.request, data}; retryCurrency = null; wishlistExpired = false;
        applyWishlistSnapshot(data, pending.request);
        notice(data.state === "partial" ? "Currencies updated. Some games could not be compared; retry to check missing prices." : (data.warnings || []).join(" "));
      } else notice(`${data.error || (data.state === "cancelled" ? "Currency update cancelled." : "Currency update failed.")} Displayed results are unchanged. Retry the currency update.`, data.state === "failed");
      setBusy(false); status(data.state.toUpperCase());
      $("retry").textContent = retryCurrency ? "Retry currency update ↻" : "Retry comparison ↻";
      saveWishlist();
    });
  } catch (error) {
    if (error.status === 404) {
      pendingCurrency = null; setBusy(false); status("UPDATE EXPIRED");
      notice("The currency update expired. Displayed results are unchanged. Retry the currency update.", true);
      $("retry").textContent = "Retry currency update ↻"; saveWishlist();
    } else { notice("Connection interrupted. Reconnecting to the currency update; displayed results remain available…", true); timer = setTimeout(pollWishlistCurrencies, 4000); }
  }
}
function notice(text, error = false) { $("notice").textContent = text; $("notice").hidden = !text; $("notice").classList.toggle("error", error); }
function setBusy(value) { running = value; $("analyze").hidden = value; $("cancel").hidden = !value; $("cancel-label").textContent = "Cancel comparison"; $("identifier").disabled = value; $("wishlist-order").disabled = value; comparisonCoordinator.setBusy("wishlist", value); $("progress").hidden = !value; $("progress-label").hidden = !value; $("cancel").disabled = false; $("retry").hidden = value || !lastRequest; window.gameAdditions?.refreshControls(); }
function nextTableSort(sort, direction, column) {
  if (sort !== column) return {sort: column, direction: 1};
  return direction === 1 ? {sort: column, direction: -1} : {sort: "arrival", direction: 1};
}
function updateSortIndicators(buttons, sort, direction) {
  for (const button of buttons) button.closest("th").removeAttribute("aria-sort");
  for (const button of buttons) {
    const active = button.dataset.sort === sort;
    const state = active ? (direction === 1 ? "ascending" : "descending") : "none";
    button.setAttribute("aria-pressed", String(active));
    button.setAttribute("data-sort-direction", state);
    button.setAttribute("title", state === "none" ? "Sort lowest to highest (A–Z)" : state === "ascending" ? "Sort highest to lowest (Z–A)" : "Restore original loading order");
    if (active) button.closest("th").setAttribute("aria-sort", state);
  }
}
function status(text, active = false) {
  const complete = text === "COMPLETE" && !active;
  $("status-badge").textContent = text;
  $("status-badge").classList.toggle("active", active);
  $("progress-area").hidden = complete;
  $("count-completion").hidden = !complete;
}
let currentRates = [], currentProfile = "";
const rowCache = new Map();
let showBestOffers = false;
try { showBestOffers = sessionStorage.getItem("polisher-best-offers") === "true"; } catch (_) {}
function regionalPriceLine(converted, currency, original, originalCurrency) {
  const line = node("span", undefined, "regional-price-line");
  line.append(node("span", `${money(converted)} ${currency}`, "converted-price"));
  const native = node("small", undefined, "original-price");
  native.append(node("span", money(original), "original-price-amount"), node("span", originalCurrency, "original-price-currency"));
  line.append(native);
  return line;
}
function offerPriceBlock(offer, converted, currency, originalPrice = null) {
  const block = node("div", undefined, "best-offer");
  block.append(node("small", "Steam best offer", "offer-label"));
  if (!offer?.price) {
    block.append(node("small", offer?.status === "subscription_unsupported" ? "Subscription offer not compared" : "Offer unavailable", "offer-value offer-unavailable"));
    return block;
  }
  const value = originalPrice ? regionalPriceLine(converted, currency, originalPrice.amount, originalPrice.currency)
    : node("span", `${money(converted)} ${currency}`, "offer-price");
  value.className += " offer-value";
  block.append(value);
  const link = node("a", `${offer.name} (${offer.kind})`, "offer-name");
  if (["bundle", "package"].includes(offer.kind) && Number.isSafeInteger(offer.id) && offer.id > 0) {
    link.href = `https://store.steampowered.com/${offer.kind === "bundle" ? "bundle" : "sub"}/${offer.id}/`;
    link.target = "_blank"; link.rel = "noopener noreferrer";
  }
  block.append(link);
  block.title = `${money(offer.price.amount)} ${offer.price.currency} · ${formatProvenance(offer.source)} · Currency: ${offer.currency_basis || "storefront context"}`;
  if (offer.price.base_amount == null) block.append(node("small", "Regular-price discount unavailable"));
  else block.append(saleNote(offer.price, offer.price.currency));
  return block;
}
function appendBestOffers(tr, item, home, regions) {
  if (!showBestOffers || item.pending) return;
  const offers = item.best_offers, best = item.best_offer_comparison;
  if (!offers) { tr.children[0].append(node("small", "Refresh comparison to load Steam best offers.", "best-offer")); return; }
  const currency = storefronts[home].currency === "PLN" ? "zł" : storefronts[home].currency;
  tr.children[1].append(offerPriceBlock(offers[home], offers[home]?.price?.amount, currency));
  const alternatives = node("div", undefined, "foreign");
  for (const region of regions) {
    const offer = offers[region];
    const converted = best?.alternatives.find(p => p.region === region);
    const hasConversion = offer?.amount_in_home != null || converted != null;
    const block = offerPriceBlock(offer, offer?.amount_in_home ?? converted?.amount_in_home ?? offer?.price?.amount,
      hasConversion ? currency : offer?.price?.currency, hasConversion ? offer?.price : null);
    alternatives.append(block);
  }
  tr.children[2].append(alternatives);
  const delta = node("div", undefined, "best-offer offer-difference" + (best ? best.is_fair ? " offer-fair" : " offer-pricier" : ""));
  delta.append(node("small", "Steam best offers", "offer-label"));
  if (best) {
    const amount = best.home_price.amount - Math.min(...best.alternatives.map(p => p.amount_in_home));
    delta.append(node("span", `${amount > 0 ? "+" : amount < 0 ? "−" : ""}${money(Math.abs(amount))} ${currency}`, "offer-value"));
    delta.append(node("small", percentageLabel(percentageDifference(best))));
    delta.append(node("small", "Offers may include different editions or bundles"));
  } else delta.append(node("small", "Not all storefront offers could be compared", "offer-value offer-unavailable"));
  tr.children[3].append(delta);
}
const touchRemoval = (() => {
  let active = null, cancelHold = null;
  function hide() {
    cancelHold?.(); cancelHold = null;
    active?.classList.toggle("removal-revealed", false); active = null;
  }
  document.addEventListener("pointerdown", event => {
    if (active && !active.contains(event.target)) hide();
  });
  window.addEventListener?.("scroll", hide, true);
  window.addEventListener?.("blur", hide);
  return {hide, bind(control, link) {
    let timer = null, origin = null, suppressClick = false, touch = false;
    const cancel = () => { clearTimeout(timer); timer = null; origin = null; };
    link.addEventListener("pointerdown", event => {
      touch = event.pointerType === "touch" || event.pointerType === "pen";
      if (!touch || event.isPrimary === false) return;
      hide(); suppressClick = false;
      link.setPointerCapture?.(event.pointerId);
      origin = {x:event.clientX,y:event.clientY,id:event.pointerId}; cancelHold = cancel;
      timer = setTimeout(() => {
        timer = null; suppressClick = true; active = control;
        control.classList.toggle("removal-revealed", true);
        $("touch-removal-hint").hidden = true;
        try { sessionStorage.setItem("polisher-touch-removal-hint", "seen"); } catch (_) {}
      }, 500);
    });
    link.addEventListener("pointermove", event => {
      if (origin && Math.hypot(event.clientX-origin.x,event.clientY-origin.y) > 10) {
        suppressClick = true; hide();
      }
    });
    link.addEventListener("pointerup", cancel);
    link.addEventListener("pointercancel", () => { suppressClick = true; hide(); });
    link.addEventListener("click", event => {
      if (suppressClick) { event.preventDefault(); event.stopPropagation(); suppressClick = false; }
    });
    link.addEventListener("contextmenu", event => { if (touch) event.preventDefault(); });
    if (window.matchMedia?.("(hover: none), (pointer: coarse)").matches) {
      try { $("touch-removal-hint").hidden = sessionStorage.getItem("polisher-touch-removal-hint") === "seen"; } catch (_) {}
    }
  }};
})();
function comparisonRow(item, resultHome, showWishlistCredits = false, selectedRegions = null, onRemove = null) {
  const regions = selectedRegions?.length ? selectedRegions : item.comparison?.alternatives.map(p => p.region)
    || Object.keys(item.best_offers || {}).filter(region => region !== resultHome);
  const baseline = () => storefronts[resultHome];
  const unit = () => baseline().currency === "PLN" ? "zł" : baseline().currency;
  const diff = item => item.comparison.home_price.amount - Math.min(...item.comparison.alternatives.map(p => p.amount_in_home));
  const tr = node("tr"), title = node("td");
  tr.dataset.appId = item.app_id;
  const link = node("a", undefined, "game-name"), artwork = gameArtwork(item.app_id), gameTitle = node("span", (item.name || `Steam product ${item.app_id}`) + " ↗", "game-title"), appIdTooltip = `Steam App ID: ${item.app_id}`;
  artwork.title = appIdTooltip; gameTitle.title = appIdTooltip; link.append(artwork, gameTitle); link.href = `https://store.steampowered.com/app/${encodeURIComponent(item.app_id)}/`; link.target = "_blank"; link.rel = "noopener noreferrer";
  if (item.manually_added) gameTitle.append(node("small", "Manually added", "manual-game-label"));
  if (onRemove) {
    const identity = node("div", undefined, "game-name"), control = node("span", undefined, "game-artwork-control");
    const artworkLink = node("a"); artworkLink.href = link.href; artworkLink.target = link.target; artworkLink.rel = link.rel;
    artworkLink.setAttribute("aria-label", `Open ${item.name || item.app_id} on Steam`); artworkLink.append(artwork);
    const button = node("button", undefined, "remove-title"); button.type = "button";
    button.title = `Remove ${item.name || item.app_id} from comparison`;
    button.setAttribute("aria-label", button.title);
    button.append(node("span", undefined, "offer-help-close-icon")); button.children[0].setAttribute("aria-hidden", "true");
    button.addEventListener("click", event => {
      const keyboard = event.detail === 0;
      const siblings = [...tr.parentElement.children], index = siblings.indexOf(tr);
      const next = siblings[index + 1] || siblings[index - 1];
      touchRemoval.hide();
      onRemove(item.app_id);
      if (keyboard) (next?.querySelector(".remove-title") || $("wishlist-tab")).focus({preventScroll: true});
    });
    control.append(artworkLink, button); touchRemoval.bind(control, artworkLink); link.className = "game-title-link"; link.replaceChildren(gameTitle);
    identity.append(control, link); title.append(identity);
  } else title.append(link);
  tr.append(title);
  if (showWishlistCredits) {
    const credits = node("small", undefined, "catalog-credit wishlist-credits");
    for (const [field, label] of [["developers", "Developer"], ["publishers", "Publisher"]]) {
      const names = item[field];
      const credit = Array.isArray(names) && names.length ? names.join(", ") : item.pending ? "Loading…" : "Unavailable";
      credits.append(node("span", `${label}: `, "credit-label"), node("span", credit, "credit-names"));
    }
    if (item.metadata_source) credits.title = `Credits: ${formatProvenance(item.metadata_source)}`;
    title.append(credits);
  }
  if(item.comparison) {
    const c = item.comparison;
    if (hasDifferentDiscounts(c)) {
      const badge = node("span", "Different regional discounts", "regional-discount-badge");
      const values = [{...c.home_price, region: c.home_price.region || resultHome}, ...c.alternatives].map(price =>
        `${price.region.toUpperCase()}: ${Number.isFinite(price.discount_percent) ? discountLabel(price) + " off" : "sale details unavailable"}`);
      badge.title = values.join(" · ") + ". Observed discounts differ; regional prices may have been checked at different times.";
      title.append(badge);
    }
    const home = node("td", `${money(c.home_price.amount)} ${unit()}`, "price");
    const homeProvenance = formatProvenance(c.home_price.source);
    if (homeProvenance) home.title = homeProvenance;
    home.append(saleNote(c.home_price, baseline().currency)); tr.append(home);
    const td = node("td"), alternatives = node("div", undefined, "foreign");
    for (const region of regions) {
      const p = c.alternatives.find(value => value.region === region);
      if (!p) { alternatives.append(node("span", "Price unavailable")); continue; }
      const price = node("span");
      price.append(regionalPriceLine(p.amount_in_home, unit(), p.original_amount, p.currency));
      const altProvenance = formatProvenance(p.source);
      price.title = `${money(p.original_amount)} ${p.currency} × ${p.rate_to_home}${altProvenance ? ` · ${altProvenance}` : ""}`;
      price.append(saleNote(p, p.currency));
      alternatives.append(price);
    }
    td.append(alternatives); tr.append(td);
    const delta = diff(item), difference = node("td", `${delta > 0 ? "+" : delta < 0 ? "−" : ""}${money(Math.abs(delta))} ${unit()}`, "difference" + (c.is_fair ? " fair" : "")); const percentage = node("span", percentageLabel(percentageDifference(c)), "difference-percent");
    percentage.title = percentageDifference(c) == null ? "Cannot calculate a percentage against a zero reference price." : `Compared with the cheapest selected foreign price, converted to ${baseline().currency}.`;
    difference.append(percentage); difference.append(node("small", c.is_fair ? "Cheaper / equal" : `Pricier in ${baseline().name}`)); tr.append(difference);
    const cheapest = c.alternatives.reduce((best, value) => value.amount_in_home < best.amount_in_home ? value : best);
    const cheapestCaption = node("small", "Cheapest:", "cheapest-storefront");
    cheapestCaption.append(node("span", `${cheapest.currency} · ${storefronts[cheapest.region]?.name || cheapest.region.toUpperCase()}`, "cheapest-storefront-name"));
    difference.append(cheapestCaption);
  } else {
    tr.append(node("td", item.pending ? "Waiting for regional prices…" : item.skipped?.reason || "Could not compare this game.", "skip-reason"));
    const foreign = node("td"), placeholders = node("div", undefined, "foreign");
    for (const region of regions) placeholders.append(node("span", item.pending ? "Waiting…" : "Not compared", "skip-reason"));
    foreign.append(placeholders); tr.append(foreign, node("td", item.pending ? "Waiting…" : "Not compared", "skip-reason"));
  }
  appendBestOffers(tr, item, resultHome, regions);
  for (const [index, name] of [[0,"pinned-game"],[1,"pinned-home"],[2,"scrolling-storefronts"],[3,"pinned-difference"]]) tr.children[index].className = `${tr.children[index].className || ""} ${name}`.trim();
  return tr;
}
function render() {
  const manualGames = items.some(item => item.manually_added);
  $("results-title").textContent = demoMode ? (manualGames ? "Example + added games" : "Example price comparison") : "Your price comparison";
  if (lastRequest) showProfile(lastRequest.identifier);
  const regions = comparisonRegions(lastRequest?.regions, items);
  setComparisonLayout($("wishlist-table"), regions);
  $("wishlist-storefront-headings").replaceChildren(...regionalHeadings(regions));
  $("export-csv").disabled = !items.length;
  $("filter-help").hidden = filter !== "skipped";
  const comparable = items.filter(item => item.comparison);
  $("count-total").textContent = items.length || (running || demoMode || wishlistRemovals.size ? "0" : "—");
  $("count-fair").textContent = comparable.filter(item => item.comparison.is_fair).length;
  $("count-expensive").textContent = comparable.filter(item => !item.comparison.is_fair).length;
  const search = $("search").value.trim().toLocaleLowerCase();
  const hiddenUnavailable = item => !item.manually_added && ["no_regional_price", "app_unavailable"].includes(item.skipped?.category);
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
    const signature = resultHome + regions.join(",") + showBestOffers + JSON.stringify(item);
    let cached = rowCache.get(item.app_id);
    if (!cached || cached.signature !== signature) {
    const tr = comparisonRow(item, resultHome, true, regions, removeWishlistTitle);
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
  if (!items.length && wishlistRemovals.size && !running) {
    $("empty").querySelector("h3").textContent = "All titles removed from this comparison.";
    $("empty").querySelector("p").textContent = "Use Undo while its notice is available, or start a new comparison.";
  }
  if(!visible.length && (items.length || running)) { $("empty").querySelector("h3").textContent = items.length ? "No games match these filters." : demoMode ? "Checking the example wishlist…" : "Checking your wishlist…"; $("empty").querySelector("p").textContent = items.length ? "Try another filter or game name." : "Results appear as each game is checked. Steam requests are paced to respect its limits."; }
  $("row-count").textContent = `${visible.length} of ${items.length} games${hiddenCount ? ` · ${hiddenCount} unavailable hidden` : ""}${demoMode ? manualGames ? " · example + added games" : " · curated example" : ""}`;
  updateSortIndicators(document.querySelectorAll('.sort:not(.library-sort):not(.catalog-sort)'), sort, direction);
  saveWishlist();
}
function formatRateTime(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch (_) {
    return "";
  }
}
function showRates(rates) {
  currentRates = rates;
  if (!window.creatorPane?.active && !window.libraryPane?.active) renderRates(rates, $("rates"));
}
function renderRates(rates, target) {
  target.replaceChildren();
  for(const rate of rates) {
    const row = node("div", undefined, "rate-line"), label = node("span", `1 ${rate.currency}`);
    const time = formatRateTime(rate.retrieved_at_utc || rate.checked_at_utc);
    const dateText = rate.effective_date ? `${rate.effective_date}${time ? ` ${time}` : ""}` : "Date unknown";
    label.append(node("small", `${dateText} · ${rate.cache_status}`));
    if (rate.retrieved_at_utc) {
      try { row.title = `Retrieved: ${new Date(rate.retrieved_at_utc).toLocaleString([], {hour12: false})}. Publication date: ${rate.effective_date || "unknown"}.`; } catch (_) {}
    }
    row.append(label, node("span", `${money(rate.rate_to_pln)} PLN`));
    target.append(row);
  }
  if(!rates.length) target.append(node("p", "Loading exchange rates…", "rate-placeholder"));
}
async function request(path, options = {}) { const response = await fetch(path, {cache: "no-store", ...options, headers: {"Content-Type": "application/json", ...(options.headers || {})}}); const data = await response.json(); if(!response.ok) { const error = new Error(data.error || "The request could not be completed."); error.status = response.status; throw error; } return data; }
async function start(body, preserveRemovals = false) {
  automaticExampleDismissed = true;
  comparisonCoordinator.cancel("wishlist-example");
  if (!comparisonCoordinator.claim("wishlist")) { notice("A comparison is running. Wait for it or cancel it on its tab.", true); return; }
  if (!preserveRemovals) {
    removalNotices.commitOwner("wishlist"); wishlistRemovals = newWishlistRemovals(); wishlistArrivalOrder.clear();
  }
  displayedWishlist = null; pendingCurrency = null; retryCurrency = null; wishlistExpired = false;
  $("wishlist-currencies").hidden = true; $("retry").textContent = "Retry comparison ↻";
  clearTimeout(timer); sort = "arrival"; job = null; saveJob(null); demoMode = body.identifier === "example"; items = []; lastRequest = body; showBaseline(body.home || "pl"); showProfile(body.identifier); $("search").value = ""; notice(""); setBusy(true); $("cancel").disabled = true; $("cancel-label").textContent = "Connecting…"; status("CONNECTING", true); $("results-title").textContent = demoMode ? "Example price comparison" : "Your price comparison"; $("progress-label").textContent = "Loading wishlist…"; $("progress").value = 0; showRates([]); render();
  try {
    const excluded = wishlistRemovals.exclusions();
    job = await request("/api/jobs", {method: "POST", body: JSON.stringify({...body, ...(excluded.length ? {excluded_app_ids: excluded} : {})})});
    wishlistRemovals.register(job); saveWishlist(); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; poll();
  } catch(error) { setBusy(false); status("COULD NOT START"); notice(error.message, true); }
}
async function poll() {
  try {
    const data = await request(`/api/jobs/${job.id}`, {headers: {Authorization: `Bearer ${job.token}`}});
    filterWishlistSnapshot(data);
    if (data.profile && !lastRequest) {
      restoreRequest({request: {identifier: data.profile, regions: data.regions, home: data.home || "pl", order: data.order || "priority"}});
      saveJob({...job, request: lastRequest});
    }
    demoMode = data.profile === "example" || lastRequest?.identifier === "example";
    $("results-title").textContent = demoMode ? "Example price comparison" : "Your price comparison";
    showBaseline(data.home || "pl"); items = data.items; showRates(data.rates); render();
    const complete = ["complete", "partial", "cancelled", "failed"].includes(data.state);
    if (["complete", "partial"].includes(data.state) && lastRequest && items.length) {
      displayedWishlist = {request: {...lastRequest, home: data.home || lastRequest.home || "pl"}, data};
      $("wishlist-currencies").textContent = `Displayed: ${currencyLabel(displayedWishlist.request)}`;
      $("wishlist-currencies").hidden = false; saveWishlist();
    }
    status(data.state.toUpperCase(), !complete); if (data.state === "cancelling") { $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; } $("progress-label").textContent = data.message; $("progress").max = Math.max(data.total, 1); $("progress").value = data.items.length;
    if(data.error) notice(data.error, true); else if(data.state === "partial") notice("Some games could not be compared because a request failed. Retry to reuse completed prices and check the remaining games."); else if(data.warnings.length) notice(data.warnings.join(" ")); else if(data.state === "cancelled") notice("Comparison cancelled. Completed regional prices are cached for your next attempt."); else if(demoMode && complete) notice("Example comparison: showing live Steam prices and official NBP exchange rates for a curated sample of games. Run your own wishlist for personal data."); else notice("");
    if(complete) { setBusy(false); if(!items.length) { $("empty").querySelector("h3").textContent = data.state === "cancelled" ? "Comparison cancelled." : "No results this time."; $("empty").querySelector("p").textContent = demoMode ? "Use Retry comparison to check the example again, or enter your public Steam profile above." : "Check your profile and make sure your wishlist is public, then try again."; } } else timer = setTimeout(poll, 1200);
  } catch(error) { if(error.status === 404) { saveJob(null); setBusy(false); status("COMPARISON EXPIRED"); notice(error.message, true); return; } status("CONNECTION INTERRUPTED"); notice("Connection interrupted. Reconnecting to your comparison…", true); timer = setTimeout(poll, 4000); }
}
// Quote every field and neutralize spreadsheet formulas in untrusted text.
function csvCell(value) {
  let text = value == null ? "" : String(value);
  if (typeof value === "string" && /^[\s]*[=+@-]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
// Schema 1 is fixed across all tabs, including exports with no results or owner opt-in.
// Keep the original price columns first so existing column names remain usable.
const priceCsvHeaders = Object.freeze([
  "exported_at_utc", "example_data", "game_id", "game", "status", "storefront", "currency",
  "final_price", "base_price", "discount_percent", "rate_to_pln", "rate_publication_date",
  "rate_retrieved_at_utc", "rate_checked_at_utc", "rate_source", "rate_cache_status",
  "final_price_baseline", "baseline_difference", "baseline_difference_percent",
  "different_regional_discounts", "price_provenance", "baseline_storefront", "baseline_currency",
  "rate_to_baseline", "baseline_rate_to_pln", "baseline_rate_publication_date",
  "baseline_rate_retrieved_at_utc", "baseline_rate_checked_at_utc", "baseline_rate_cache_status",
  "wishlist_profile", "catalog_role", "catalog_name", "developers", "publishers",
  "csv_schema_version", "source_tab", "catalog_id", "steam_url", "comparison_storefronts",
  "comparison_currencies", "wishlist_loading_order", "checked_index", "baseline_final_price",
  "cheapest_alternative_storefront", "cheapest_alternative_currency",
  "cheapest_alternative_final_price_baseline", "baseline_is_cheaper_or_equal",
  "storefront_difference_baseline", "storefront_difference_percent", "base_price_baseline",
  "storefront_price_source", "baseline_rate_source", "skipped_reason", "skipped_storefront",
  "skipped_retryable", "cache_hits", "stale_cache_hits", "live_price_requests",
  "developers_known", "publishers_known", "library_profile", "library_loading_order",
  "best_offer_status", "best_offer_kind", "best_offer_id", "best_offer_name", "best_offer_final_price",
  "best_offer_currency", "best_offer_currency_basis", "best_offer_regular_price", "best_offer_discount_percent",
  "best_offer_final_price_baseline", "best_offer_source", "best_offer_difference_baseline", "best_offer_difference_percent", "discount_calculated", "best_offer_discount_calculated", "manually_added"
]);
function buildPriceCsv(exportItems, home, rates, options = {}, exportedAt = new Date().toISOString()) {
  const baseline = () => storefronts[home];
  const {example = false, includeOwner = false, profile = null, sourceTab = "wishlist", regions = [], order = null} = options;
  const homeIdentity = baseline().currency === "PLN";
  const homeRate = homeIdentity ? {} : rates.find(value => value.currency === baseline().currency) || {};
  const rows = [priceCsvHeaders];
  for (const item of exportItems) {
    const c = item.comparison;
    const prices = c ? [{...c.home_price, region:home, currency:baseline().currency, original_amount:c.home_price.amount, amount_in_home:c.home_price.amount}, ...c.alternatives] : item.best_offers ? Object.keys(item.best_offers).map(region => ({region})) : [{}];
    const cheapest = c ? c.alternatives.reduce((best, price) => price.amount_in_home < best.amount_in_home ? price : best) : null;
    const reference = cheapest?.amount_in_home;
    const comparisonRegions = c ? c.alternatives.map(price => price.region) : regions;
    for (const price of prices) {
      const identity = price.currency === "PLN";
      const rate = identity ? {} : rates.find(value => value.currency === price.currency) || {};
      const factor = c ? (price.region === home ? 1 : price.rate_to_home) : null;
      const foreign = c && price.region !== home;
      const row = [exportedAt, example && !item.manually_added, item.app_id, item.name, c ? "compared" : item.skipped?.category,
        price.region, price.currency, price.original_amount, price.base_amount, price.discount_percent,
        identity ? 1 : rate.rate_to_pln, rate.effective_date, rate.retrieved_at_utc, rate.checked_at_utc,
        identity ? "Identity conversion" : rate.source, identity ? "identity" : rate.cache_status,
        price.amount_in_home, c ? c.home_price.amount - reference : null, c ? percentageDifference(c) : null,
        c ? hasDifferentDiscounts(c) : null, item.source_summary];
      row.push(home, baseline().currency, factor,
        homeIdentity ? 1 : homeRate.rate_to_pln, homeRate.effective_date,
        homeRate.retrieved_at_utc, homeRate.checked_at_utc, homeIdentity ? "identity" : homeRate.cache_status,
        sourceTab === "wishlist" && includeOwner && !item.manually_added ? profile : null,
        item.catalog_role, item.catalog_name, (item.developers || []).join("; "), (item.publishers || []).join("; "),
        1, sourceTab, item.catalog_id, `https://store.steampowered.com/app/${item.app_id}/`,
        comparisonRegions.join("; "), comparisonRegions.map(region => storefronts[region].currency).join("; "),
        sourceTab === "wishlist" ? order : null, item.index, c?.home_price.amount,
        cheapest?.region, cheapest?.currency, reference, c?.is_fair,
        foreign ? c.home_price.amount - price.amount_in_home : null,
        foreign && price.amount_in_home > 0 ? (c.home_price.amount - price.amount_in_home) / price.amount_in_home * 100 : null,
        price.base_amount != null && factor != null ? price.base_amount * factor : null,
        price.source, homeIdentity ? "Identity conversion" : homeRate.source,
        item.skipped?.reason, item.skipped?.region, item.skipped?.retryable,
        item.cache_hits, item.stale_cache_hits, item.live_requests,
        Array.isArray(item.developers), Array.isArray(item.publishers),
        sourceTab === "library" && includeOwner ? profile : null, sourceTab === "library" ? order : null);
      const offer = item.best_offers?.[price.region], best = item.best_offer_comparison;
      const bestPrice = best && (price.region === home ? {amount_in_home:best.home_price.amount} : best.alternatives.find(p => p.region === price.region));
      row.push(offer?.status, offer?.kind, offer?.id, offer?.name, offer?.price?.amount,
        offer?.price?.currency, offer?.currency_basis, offer?.price?.base_amount, offer?.price?.discount_percent,
        offer?.amount_in_home ?? bestPrice?.amount_in_home, offer?.source,
        best ? best.home_price.amount - Math.min(...best.alternatives.map(p => p.amount_in_home)) : null,
        best ? percentageDifference(best) : null, price.discount_calculated, offer?.price?.discount_calculated, item.manually_added === true);
      rows.push(row);
    }
  }
  return "\uFEFF" + rows.map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
function buildCsv(includeOwner, exportedAt = new Date().toISOString()) {
  return buildPriceCsv(items, resultHome, currentRates,
    {example: demoMode, includeOwner, profile: currentProfile, regions: lastRequest?.regions || [], order: lastRequest?.order || null}, exportedAt);
}
function downloadCsv(contents, filename) {
  const url = URL.createObjectURL(new Blob([contents], {type:"text/csv;charset=utf-8"}));
  const link = node("a"); link.href = url; link.download = filename;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("export-csv").addEventListener("click", () => downloadCsv(buildCsv($("export-owner").checked), "steam-price-comparison.csv"));
$("compare-form").addEventListener("submit", event => { event.preventDefault(); if (window.gameAdditions) { window.gameAdditions.submit(); return; } const regions = [...document.querySelectorAll('[name="region"]:checked')].map(el => el.value); if(!regions.length || regions.length > maxComparisons) return notice("Choose one or more comparison currencies.", true); start({identifier: $("identifier").value.trim(), regions, home: selectedHome(), order: $("wishlist-order").value}); });
buildStorefrontControls();
$("currency-panel-toggle").addEventListener("click", () => {
  const expanded = $("currency-panel-body").hidden;
  setCurrencyPanelExpanded(expanded, !expanded);
  refreshCurrencyAction();
});
bindComparisonScroll("wishlist", $("wishlist-table").parentElement || $("wishlist-scroll"));
bindComparisonScroll("library", $("library-table").parentElement || $("library-scroll"));
$("currency-search").addEventListener("input", filterStorefrontControls);
for (const [id, checked] of [["select-all-currencies", true], ["clear-currencies", false]]) {
  $(id).addEventListener("click", () => {
    if (comparisonCoordinator.busy) return;
    document.querySelectorAll('[name="region"]').forEach(el => el.checked = checked && el.value !== selectedHome());
    updateSelections({target: {name: "region"}});
  });
}
document.querySelectorAll('[name="home"], [name="region"]').forEach(el => el.addEventListener("change", updateSelections));
updateSelections();
comparisonCoordinator.subscribe(updateSelections);
$("update-currencies").addEventListener("click", () => {
  if (window.creatorPane?.active) window.creatorPane.updateCurrencies();
  else if (!window.libraryPane?.active) updateWishlistCurrencies();
});
$("cancel").addEventListener("click", async () => { if (window.gameAdditions?.busy) { await window.gameAdditions.cancel(); return; } const target = pendingCurrency?.job || job; if(!target) return; $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; try { await request(`/api/jobs/${target.id}/cancel`, {method: "POST", body: "{}", headers: {Authorization: `Bearer ${target.token}`}}); $("progress-label").textContent = "Cancelling — waiting for the current request to finish…"; } catch(error) { notice(error.message, true); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; } });
$("retry").addEventListener("click", () => {
  if (displayedWishlist && retryCurrency) updateWishlistCurrencies(retryCurrency);
  else if(lastRequest) start(lastRequest);
});
$("search").addEventListener("input", render);
$("show-unavailable").addEventListener("change", render);
let openOfferHelp = null, offerHelpObserver = null;
function closeOfferHelp(returnFocus = false) {
  if (!openOfferHelp) return;
  const {button, popup} = openOfferHelp;
  popup.hidden = true; button.setAttribute("aria-expanded", "false"); openOfferHelp = null;
  offerHelpObserver?.disconnect(); offerHelpObserver = null;
  if (returnFocus) button.focus();
}
function toggleOfferHelp(button, popup) {
  const wasOpen = openOfferHelp?.button === button;
  closeOfferHelp();
  if (wasOpen) return;
  popup.hidden = false; button.setAttribute("aria-expanded", "true");
  openOfferHelp = {button, popup};
  positionOfferHelp(button, popup, true);
  if (typeof ResizeObserver !== "undefined") {
    offerHelpObserver = new ResizeObserver(() => positionOfferHelp(button, popup));
    offerHelpObserver.observe(document.body);
  }
  $(popup.id + "-close").focus({preventScroll: true});
}
function positionOfferHelp(button, popup, fitViewport = false) {
  if (openOfferHelp?.button !== button) return;
  // Reserve room for the close circle extending beyond the bubble's corner.
  const edge = 24, gap = 16, viewportWidth = document.documentElement.clientWidth || window.innerWidth;
  popup.style.width = `${Math.min(380, viewportWidth - edge * 2)}px`;
  const anchor = button.getBoundingClientRect(), box = popup.getBoundingClientRect();
  const centeredLeft = anchor.left + anchor.width / 2 - box.width / 2;
  const left = Math.max(edge, Math.min(centeredLeft, viewportWidth - box.width - edge));
  const help = openOfferHelp;
  // Fit when opening or resizing a visible anchor. Layout shifts should carry
  // the bubble with its button, including when that button moves offscreen.
  if (!help.placement || (fitViewport && anchor.bottom > 0 && anchor.top < window.innerHeight)) {
    help.placement = anchor.bottom + gap + box.height <= window.innerHeight - edge ? "below" : "above";
    const preferredTop = help.placement === "below" ? anchor.bottom + gap : anchor.top - box.height - gap;
    help.verticalShift = Math.max(edge, Math.min(preferredTop, window.innerHeight - box.height - edge)) - preferredTop;
  }
  const top = (help.placement === "below" ? anchor.bottom + gap : anchor.top - box.height - gap) + help.verticalShift;
  popup.style.left = `${left + (window.scrollX || 0)}px`;
  popup.style.top = `${top + (window.scrollY || 0)}px`;
}
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && openOfferHelp) { closeOfferHelp(true); event.preventDefault(); }
});
function refreshOfferHelpPosition() {
  if (openOfferHelp) positionOfferHelp(openOfferHelp.button, openOfferHelp.popup, true);
}
window.addEventListener?.("resize", refreshOfferHelpPosition);
const bestOfferControls = ["show-best-offers", "developers-show-best-offers", "publishers-show-best-offers", "library-show-best-offers"].map($);
for (const control of bestOfferControls) {
  const button = $(control.id + "-info"), popup = $(control.id.replace("show-best-offers", "best-offers-help"));
  popup.hidden = true; button.setAttribute("aria-expanded", "false");
  button.addEventListener("click", () => toggleOfferHelp(button, popup));
  $(popup.id + "-close").addEventListener("click", () => closeOfferHelp(true));
  control.checked = showBestOffers;
  control.addEventListener("change", () => {
    showBestOffers = control.checked;
    for (const other of bestOfferControls) other.checked = showBestOffers;
    try { sessionStorage.setItem("polisher-best-offers", String(showBestOffers)); } catch (_) {}
    render(); window.creatorPane?.render(); window.libraryPane?.render();
  });
}
document.querySelectorAll('.filter:not(.library-filter)').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; document.querySelectorAll('.filter:not(.library-filter)').forEach(el => { el.classList.toggle('active', el === button); el.setAttribute('aria-pressed', String(el === button)); }); render(); }));
document.querySelectorAll('.sort:not(.library-sort):not(.catalog-sort)').forEach(button => button.addEventListener('click', () => { ({sort, direction} = nextTableSort(sort, direction, button.dataset.sort)); render(); }));
$("identifier").addEventListener("input", () => { automaticExampleDismissed = true; comparisonCoordinator.cancel("wishlist-example"); });

// Deferred scripts restore their tabs before DOMContentLoaded. Catalog restoration
// can continue asynchronously under a coordinator hold. The example has lower
// priority than catalog work and only starts while the wishlist is visible.
document.addEventListener("DOMContentLoaded", () => {
  if (job || lastRequest || automaticExampleDismissed) return;
  $("empty").querySelector("h3").textContent = "An example comparison loads automatically.";
  $("empty").querySelector("p").textContent = "Enter your public Steam profile above to compare your own wishlist.";
  comparisonCoordinator.whenIdle("wishlist-example", () => {
    const home = selectedHome();
    const selected = [...document.querySelectorAll('[name="region"]')].filter(el => el.checked).map(el => el.value);
    const regions = selected.length ? selected : Object.keys(storefronts).filter(region => region !== home).slice(0, 2);
    start({identifier: "example", regions, home, order: $("wishlist-order").value});
  }, () => !job && !lastRequest && !items.length && !$("identifier").value.trim()
    && !window.creatorPane?.active && !window.libraryPane?.active, 10);
}, {once: true});

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
    job = {id: saved.id, token: saved.token};
    wishlistRemovals.restore(saved.removals); wishlistRemovals.register(job);
    if (saved.displayed && validCurrencies(saved.displayed.request) && typeof saved.displayed.request.identifier === "string"
        && Array.isArray(saved.displayed.data?.items) && Array.isArray(saved.displayed.data?.rates)) {
      restoreRequest({request: saved.displayed.request});
      displayedWishlist = saved.displayed; wishlistExpired = saved.expired === true;
      retryCurrency = validCurrencies(saved.retryCurrency) ? saved.retryCurrency : null;
      const view = saved.view || {};
      $("search").value = typeof view.search === "string" ? view.search : "";
      filter = ["all", "fair", "expensive", "discounts", "skipped"].includes(view.filter) ? view.filter : "all";
      sort = ["arrival", "name", "home", "percentage", "difference"].includes(view.sort) ? view.sort : "arrival";
      direction = view.direction === -1 ? -1 : 1; $("show-unavailable").checked = view.showUnavailable === true;
      document.querySelectorAll('.filter:not(.library-filter)').forEach(el => { el.classList.toggle("active", el.dataset.filter === filter); el.setAttribute("aria-pressed", String(el.dataset.filter === filter)); });
      applyWishlistSnapshot(displayedWishlist.data, displayedWishlist.request);
      if (saved.pending && validCurrencies(saved.pending.request) && /^[A-Za-z0-9_-]{32}$/.test(saved.pending.job?.id) && /^[A-Za-z0-9_-]{43}$/.test(saved.pending.job?.token)) {
        pendingCurrency = saved.pending; retryCurrency = {home: pendingCurrency.request.home, regions: pendingCurrency.request.regions};
        preferredComparisons = [...pendingCurrency.request.regions];
        document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === pendingCurrency.request.home);
        setBusy(true); status("RECONNECTING", true); saveWishlist(); pollWishlistCurrencies();
      } else { setBusy(false); status(displayedWishlist.data.state.toUpperCase()); $("retry").textContent = retryCurrency ? "Retry currency update ↻" : "Retry comparison ↻"; saveWishlist(); }
    } else { if (!restoreRequest(saved)) showProfile(null); setBusy(true); status("RECONNECTING", true); poll(); }
  }
} catch (_) { saveJob(null); }
