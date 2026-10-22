"use strict";
const $ = (id) => document.getElementById(id);
let items = [], filter = "all", sort = "arrival", direction = 1, job = null, running = false, demoMode = false, timer = null, lastRequest = null;
let displayedWishlist = null, pendingCurrency = null, retryCurrency = null, wishlistExpired = false;
const money = (value) => new Intl.NumberFormat("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(value);
const node = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
const storefronts = JSON.parse(document.documentElement.dataset.storefronts);
const maxComparisons = Object.keys(storefronts).length - 1;
function buildStorefrontControls() {
  for (const [region, value] of Object.entries(storefronts)) {
    for (const [target, name, type] of [["baseline-options", "home", "radio"], ["comparison-options", "region", "checkbox"]]) {
      const label = node("label", undefined, "region"), input = node("input"), caption = node("span", value.currency);
      input.type = type; input.name = name; input.value = region;
      input.checked = name === "home" ? region === "pl" : ["us", "de"].includes(region);
      caption.append(node("small", `${value.currency_name} · ${value.name}`));
      label.dataset.storefront = region; label.append(input, caption); $(target).append(label);
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
  return `${storefronts[selection.home].currency} against ${selection.regions.length > 4 ? `${selection.regions.length} storefronts` : selection.regions.map(id => storefronts[id].currency).join(" and ")}`;
}
function sameCurrencies(a, b) { return a.home === b.home && a.regions.join(",") === b.regions.join(","); }
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
  const displayed = catalog ? window.creatorPane.currencyState() : window.libraryPane?.active ? null : displayedWishlist?.request;
  const selected = currencySelection(), button = $("update-currencies");
  button.hidden = !displayed;
  button.disabled = comparisonCoordinator.busy || !validCurrencies(selected) || !displayed || sameCurrencies(selected, displayed);
  $("currency-update-help").hidden = !displayed;
  $("currency-update-help").textContent = displayed ? `Displayed: ${currencyLabel(displayed)}. Updates apply to this tab.${!catalog && wishlistExpired ? " Updating currencies will reload this saved comparison." : ""}` : "";
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
  table.closest?.(".comparison-area")?.classList.toggle("matrix-with-credits", credits);
  table.style.setProperty("--region-count", String(Math.max(regions.length, 1)));
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
    stickyTitles.style.setProperty("--region-count", table.style.getPropertyValue("--region-count"));
    stickyTitles.firstElementChild.style.transform = `translateX(${-wrap.scrollLeft}px)`;
    const sourceBox = source.getBoundingClientRect(), top = shell.getBoundingClientRect().bottom;
    stickyTitles.hidden = wrap.clientWidth === 0 || sourceBox.top > top || area.getBoundingClientRect().bottom <= top + sourceBox.height;
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
  if (profile === "example") {
    $("profile-attribution").textContent = "Curated example wishlist · 7 popular Steam games";
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
  lastRequest = {identifier: request.identifier, regions: request.regions, home: request.home || "pl", order};
  document.querySelectorAll('[name="home"]').forEach(el => el.checked = el.value === lastRequest.home);
  showBaseline(lastRequest.home);
  $("identifier").value = request.identifier === "example" ? "" : request.identifier;
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
  if (!displayedWishlist) return;
  saveJob({...job, request: lastRequest, displayed: displayedWishlist, pending: pendingCurrency, retryCurrency, expired: wishlistExpired,
    view: {search: $("search").value, filter, sort, direction, showUnavailable: $("show-unavailable").checked}});
}
function applyWishlistSnapshot(data, body) {
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
      const source = pendingCurrency.request.identifier === "example" ? "Recreating the example" : "Reloading the wishlist";
      $("progress-label").textContent = `${source} with ${currencyLabel(selection)}… Displayed results remain available.`;
      refreshCurrencyAction(); saveWishlist();
      pendingCurrency.job = await request("/api/jobs", {method: "POST", body: JSON.stringify(pendingCurrency.request)});
    }
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
function setBusy(value) { running = value; $("analyze").hidden = value; $("cancel").hidden = !value; $("cancel-label").textContent = "Cancel comparison"; $("identifier").disabled = value; $("wishlist-order").disabled = value; comparisonCoordinator.setBusy("wishlist", value); $("progress").hidden = !value; $("progress-label").hidden = !value; $("cancel").disabled = false; $("retry").hidden = value || !lastRequest; }
function status(text, active = false) { $("status-badge").textContent = text; $("status-badge").classList.toggle("active", active); }
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
function comparisonRow(item, resultHome, showWishlistCredits = false, selectedRegions = null) {
  const regions = selectedRegions?.length ? selectedRegions : item.comparison?.alternatives.map(p => p.region)
    || Object.keys(item.best_offers || {}).filter(region => region !== resultHome);
  const baseline = () => storefronts[resultHome];
  const unit = () => baseline().currency === "PLN" ? "zł" : baseline().currency;
  const diff = item => item.comparison.home_price.amount - Math.min(...item.comparison.alternatives.map(p => p.amount_in_home));
  const tr = node("tr"), title = node("td");
  tr.dataset.appId = item.app_id;
  const link = node("a", undefined, "game-name"), artwork = gameArtwork(item.app_id), gameTitle = node("span", (item.name || `Steam product ${item.app_id}`) + " ↗", "game-title"), appIdTooltip = `Steam App ID: ${item.app_id}`;
  artwork.title = appIdTooltip; gameTitle.title = appIdTooltip; link.append(artwork, gameTitle); link.href = `https://store.steampowered.com/app/${encodeURIComponent(item.app_id)}/`; link.target = "_blank"; link.rel = "noopener noreferrer"; title.append(link); tr.append(title);
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
  const regions = comparisonRegions(lastRequest?.regions, items);
  setComparisonLayout($("wishlist-table"), regions);
  $("wishlist-storefront-headings").replaceChildren(...regionalHeadings(regions));
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
    const signature = resultHome + regions.join(",") + showBestOffers + JSON.stringify(item);
    let cached = rowCache.get(item.app_id);
    if (!cached || cached.signature !== signature) {
    const tr = comparisonRow(item, resultHome, true, regions);
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
  if(!visible.length && (items.length || running)) { $("empty").querySelector("h3").textContent = items.length ? "No games match these filters." : demoMode ? "Checking the example wishlist…" : "Checking your wishlist…"; $("empty").querySelector("p").textContent = items.length ? "Try another filter or game name." : "Results appear as each game is checked. Steam requests are paced to respect its limits."; }
  $("row-count").textContent = `${visible.length} of ${items.length} games${hiddenCount ? ` · ${hiddenCount} unavailable hidden` : ""}${demoMode ? " · curated example" : ""}`;
  $("arrival-order").setAttribute("aria-pressed", String(sort === "arrival"));
  $("order-note").textContent = sort === "arrival" ? "Loaded games append at the end" : "Sorted results · loaded games follow this sort";
  document.querySelectorAll('.sort:not(.library-sort)').forEach(button => {
    button.closest('th').removeAttribute('aria-sort');
    button.setAttribute('aria-pressed', String(button.dataset.sort === sort));
  });
  document.querySelectorAll('.sort:not(.library-sort)').forEach(button => {
    if (button.dataset.sort === sort) button.closest('th').setAttribute('aria-sort', direction === 1 ? 'ascending' : 'descending');
  });
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
async function start(body) {
  automaticExampleDismissed = true;
  comparisonCoordinator.cancel("wishlist-example");
  if (!comparisonCoordinator.claim("wishlist")) { notice("A comparison is running. Wait for it or cancel it on its tab.", true); return; }
  displayedWishlist = null; pendingCurrency = null; retryCurrency = null; wishlistExpired = false;
  $("wishlist-currencies").hidden = true; $("retry").textContent = "Retry comparison ↻";
  clearTimeout(timer); sort = "arrival"; job = null; saveJob(null); demoMode = body.identifier === "example"; items = []; lastRequest = body; showBaseline(body.home || "pl"); showProfile(body.identifier); $("search").value = ""; notice(""); setBusy(true); $("cancel").disabled = true; $("cancel-label").textContent = "Connecting…"; status("CONNECTING", true); $("results-title").textContent = demoMode ? "Example price comparison" : "Your price comparison"; $("progress-label").textContent = "Loading wishlist…"; $("progress").value = 0; showRates([]); render();
  try { job = await request("/api/jobs", {method: "POST", body: JSON.stringify(body)}); saveJob({...job, request: body}); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; poll(); } catch(error) { setBusy(false); status("COULD NOT START"); notice(error.message, true); }
}
async function poll() {
  try {
    const data = await request(`/api/jobs/${job.id}`, {headers: {Authorization: `Bearer ${job.token}`}});
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
  "best_offer_final_price_baseline", "best_offer_source", "best_offer_difference_baseline", "best_offer_difference_percent", "discount_calculated", "best_offer_discount_calculated"
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
      const row = [exportedAt, example, item.app_id, item.name, c ? "compared" : item.skipped?.category,
        price.region, price.currency, price.original_amount, price.base_amount, price.discount_percent,
        identity ? 1 : rate.rate_to_pln, rate.effective_date, rate.retrieved_at_utc, rate.checked_at_utc,
        identity ? "Identity conversion" : rate.source, identity ? "identity" : rate.cache_status,
        price.amount_in_home, c ? c.home_price.amount - reference : null, c ? percentageDifference(c) : null,
        c ? hasDifferentDiscounts(c) : null, item.source_summary];
      row.push(home, baseline().currency, factor,
        homeIdentity ? 1 : homeRate.rate_to_pln, homeRate.effective_date,
        homeRate.retrieved_at_utc, homeRate.checked_at_utc, homeIdentity ? "identity" : homeRate.cache_status,
        sourceTab === "wishlist" && includeOwner ? profile : null,
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
        best ? percentageDifference(best) : null, price.discount_calculated, offer?.price?.discount_calculated);
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
$("compare-form").addEventListener("submit", event => { event.preventDefault(); const regions = [...document.querySelectorAll('[name="region"]:checked')].map(el => el.value); if(!regions.length || regions.length > maxComparisons) return notice("Choose one or more comparison currencies.", true); start({identifier: $("identifier").value.trim(), regions, home: selectedHome(), order: $("wishlist-order").value}); });
buildStorefrontControls();
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
$("cancel").addEventListener("click", async () => { const target = pendingCurrency?.job || job; if(!target) return; $("cancel").disabled = true; $("cancel-label").textContent = "Cancelling…"; try { await request(`/api/jobs/${target.id}/cancel`, {method: "POST", body: "{}", headers: {Authorization: `Bearer ${target.token}`}}); $("progress-label").textContent = "Cancelling — waiting for the current request to finish…"; } catch(error) { notice(error.message, true); $("cancel").disabled = false; $("cancel-label").textContent = "Cancel comparison"; } });
$("retry").addEventListener("click", () => {
  if (displayedWishlist) updateWishlistCurrencies(retryCurrency || {home: displayedWishlist.request.home, regions: displayedWishlist.request.regions});
  else if(lastRequest) start(lastRequest);
});
$("search").addEventListener("input", render);
$("show-unavailable").addEventListener("change", render);
const bestOfferControls = ["show-best-offers", "developers-show-best-offers", "publishers-show-best-offers", "library-show-best-offers"].map($);
for (const control of bestOfferControls) {
  control.checked = showBestOffers;
  control.addEventListener("change", () => {
    showBestOffers = control.checked;
    for (const other of bestOfferControls) other.checked = showBestOffers;
    try { sessionStorage.setItem("polisher-best-offers", String(showBestOffers)); } catch (_) {}
    render(); window.creatorPane?.render(); window.libraryPane?.render();
  });
}
$("arrival-order").addEventListener("click", () => { sort = "arrival"; direction = 1; render(); });
document.querySelectorAll('.filter:not(.library-filter)').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; document.querySelectorAll('.filter:not(.library-filter)').forEach(el => { el.classList.toggle('active', el === button); el.setAttribute('aria-pressed', String(el === button)); }); render(); }));
document.querySelectorAll('.sort:not(.library-sort)').forEach(button => button.addEventListener('click', () => { direction = sort === button.dataset.sort ? -direction : 1; sort = button.dataset.sort; render(); }));
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
