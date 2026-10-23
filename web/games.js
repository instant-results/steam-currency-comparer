"use strict";

// One input for profiles and individual games. Pending additions never delay an
// idle worker; only selections already waiting are combined into the next job.
(() => {
  const storageKey = "polisher-game-additions";
  const queued = new Map();
  let batch = null, paused = false, searching = false, searchVersion = 0, pollTimer = null;
  let searchTimer = null, searchDue = false, activeSearch = "";
  function cancelAutoSearch() { clearTimeout(searchTimer); searchTimer = null; searchDue = false; }
  const validId = id => typeof id === "string" && /^[1-9][0-9]{0,9}$/.test(id) && Number(id) <= 4294967295;
  const credentials = value => /^[A-Za-z0-9_-]{32}$/.test(value?.id) && /^[A-Za-z0-9_-]{43}$/.test(value?.token);
  function inputKind(value) {
    const text = value.trim();
    if (!text || /^\d{17}$/.test(text) || /^https?:\/\/(steamcommunity\.com|store\.steampowered\.com\/wishlist)(\/|$)/i.test(text)) return {kind: "profile"};
    if (/^\d+$/.test(text)) return validId(String(Number(text))) ? {kind: "game", id: String(Number(text))} : {kind: "invalid"};
    if (/^https?:\/\//i.test(text)) {
      try {
        const url = new URL(text), match = /^\/app\/(\d+)(?:\/[^/]*)?\/?$/.exec(url.pathname);
        if (url.hostname === "store.steampowered.com" && !url.port && !url.username && !url.password && match && validId(String(Number(match[1])))) return {kind: "game", id: String(Number(match[1]))};
      } catch (_) {}
      return {kind: "invalid"};
    }
    return {kind: "search"};
  }
  function message(text) { $("games-status").textContent = text; }
  function save() {
    try { sessionStorage.setItem(storageKey, JSON.stringify({queued: [...queued], batch, paused})); } catch (_) {}
  }
  function refreshControls() {
    const kind = inputKind($("identifier").value).kind;
    $("identifier").disabled = false;
    $("analyze").hidden = false;
    $("analyze").textContent = kind === "profile" ? "Compare regional prices" : kind === "search" ? "Search games" : "Add";
    $("analyze").disabled = searching || (kind === "profile" && comparisonCoordinator.busy);
    $("games-retry").hidden = !paused || !queued.size;
    $("games-retry").disabled = comparisonCoordinator.busy;
    $("games-pending").replaceChildren();
    for (const [id, name] of queued) {
      const row = node("li"), cancel = node("button", "Remove from queue"); cancel.type = "button";
      row.append(node("span", `${name} · App ID ${id} · ${batch?.ids.includes(id) ? "Checking" : paused ? "Waiting for retry" : "Queued"}`));
      cancel.disabled = Boolean(batch?.ids.includes(id));
      cancel.addEventListener("click", () => { queued.delete(id); save(); refreshControls(); });
      row.append(cancel); $("games-pending").append(row);
    }
  }
  function schedule() {
    if (batch || paused || !queued.size) return;
    if (!comparisonCoordinator.busy) { flush(); return; }
    comparisonCoordinator.whenIdle("wishlist-additions", flush, () => !batch && !paused && queued.size > 0, -1);
  }
  function add(id, name = `Steam app ${id}`) {
    if (!validId(id)) { message("Enter a valid Steam App ID or a Steam /app/ URL."); return; }
    automaticExampleDismissed = true; comparisonCoordinator.cancel("wishlist-example");
    if (queued.has(id) || items.some(item => item.app_id === id) && !wishlistRemovals.has(id)) {
      message("That game is already in this comparison or its queue."); return;
    }
    const ids = new Set([...items.map(item => item.app_id), ...queued.keys(), id]);
    if (ids.size > 1000) { message("This comparison supports up to 1,000 games. Remove a game before adding another."); return; }
    wishlistRemovals.readd(id);
    queued.set(id, name); save(); refreshControls();
    message(comparisonCoordinator.busy ? "Game queued. It will start when the current comparison finishes." : "Starting comparison…");
    schedule();
  }
  async function flush() {
    if (batch || paused || !queued.size || !comparisonCoordinator.claim("wishlist")) return;
    const selection = displayedWishlist?.request || (items.length && lastRequest) || currencySelection();
    if (!validCurrencies(selection)) { comparisonCoordinator.setBusy("wishlist", false); paused = true; message("Choose comparison currencies, then retry the queued games."); save(); refreshControls(); return; }
    const ids = [...queued.keys()];
    const existing = [...items.map(item => item.app_id), ...wishlistRemovals.pendingIds()];
    const appIds = [...new Set([...existing, ...ids])];
    if (appIds.length > 1000) { comparisonCoordinator.setBusy("wishlist", false); paused = true; message("The loaded wishlist and queued games exceed 1,000 games. Remove games, then retry."); save(); refreshControls(); return; }
    const added = new Set([...(lastRequest?.added_app_ids || []), ...items.filter(item => item.manually_added).map(item => item.app_id), ...ids]);
    const body = {identifier: existing.length ? lastRequest?.identifier || "selection" : "selection", home: selection.home,
      regions: [...selection.regions], order: lastRequest?.order || "priority", app_ids: appIds,
      added_app_ids: appIds.filter(id => added.has(id))};
    batch = {ids, request: body, job: null};
    setBusy(true); $("cancel").disabled = true; status("ADDING GAMES", true);
    $("progress").value = 0; $("progress-label").textContent = "Adding games… Current results remain available.";
    save(); refreshControls();
    try {
      batch.job = await request("/api/jobs", {method: "POST", body: JSON.stringify(body)});
      wishlistRemovals.register(batch.job); save(); $("cancel").disabled = false;
      pollBatch();
    } catch (error) { fail(`${error.message} Queued games are saved; retry when ready.`); }
  }
  function fail(text) {
    batch = null; paused = true; save(); setBusy(false); status("ADDITION PAUSED");
    message(text); refreshControls();
  }
  async function pollBatch() {
    const current = batch;
    if (!current?.job) return;
    try {
      const data = await request(`/api/jobs/${current.job.id}`, {headers: {Authorization: `Bearer ${current.job.token}`}});
      if (batch !== current) return;
      $("progress-label").textContent = `Adding games: ${data.message}`;
      $("progress").max = Math.max(data.total, 1); $("progress").value = data.items.length;
      if (!["complete", "partial", "cancelled", "failed"].includes(data.state)) { pollTimer = setTimeout(pollBatch, 1200); return; }
      if (!["complete", "partial"].includes(data.state)) { fail(data.error || "Addition cancelled. Existing results remain available; retry queued games when ready."); return; }
      for (const id of current.ids) queued.delete(id);
      job = current.job; wishlistExpired = false; retryCurrency = null;
      displayedWishlist = {request: current.request, data};
      preserveComparisonScroll(() => { applyWishlistSnapshot(data, current.request); showProfile(current.request.identifier); });
      batch = null; paused = false; save(); saveWishlist(); setBusy(false); status(data.state.toUpperCase());
      notice((data.warnings || []).join(" "));
      message(data.state === "partial" ? "Games added. Some prices failed; Retry comparison checks them again." : "Games added. Products without regional prices remain marked as uncompared.");
      refreshControls(); schedule();
    } catch (error) {
      if (error.status === 404) { fail("This addition expired. Existing results remain available. Retry to compare the saved selection."); return; }
      message("Connection interrupted. Reconnecting to the addition…"); pollTimer = setTimeout(pollBatch, 4000);
    }
  }
  async function submit() {
    cancelAutoSearch();
    const text = $("identifier").value.trim(), choice = inputKind(text);
    if (choice.kind === "profile") {
      if (comparisonCoordinator.busy) { message("Wait for the current comparison before loading another wishlist."); return; }
      if (!validCurrencies(currencySelection())) { message("Choose comparison currencies first."); return; }
      queued.clear(); paused = false; save(); refreshControls();
      message(""); $("game-matches").replaceChildren();
      start({identifier: text, ...currencySelection(), order: $("wishlist-order").value}); return;
    }
    if (choice.kind === "invalid") { message("Use a Steam App ID or an /app/ store URL. Package and bundle links are not supported."); return; }
    if (choice.kind === "game") { add(choice.id); return; }
    if (searching) { searchDue = text !== activeSearch; return; }
    activeSearch = text;
    const version = ++searchVersion; searching = true; refreshControls();
    $("game-matches").replaceChildren(); message("Searching Steam…");
    try {
      const data = await request("/api/games/search", {method: "POST", body: JSON.stringify({query: text, home: displayedWishlist?.request.home || selectedHome()})});
      if (version !== searchVersion) return;
      for (const game of data.games) {
        if (!validId(game.app_id) || typeof game.name !== "string") continue;
        const row = node("li"), button = node("button", "Add"); button.type = "button";
        button.setAttribute("aria-label", `Add ${game.name}, App ID ${game.app_id}`);
        button.addEventListener("click", () => add(game.app_id, game.name));
        row.append(button, node("span", `${game.name} · ${game.kind} · App ID ${game.app_id}`)); $("game-matches").append(row);
      }
      message(data.games.length ? "Choose a game to add to the current comparison." : "No matches. Try another name or paste a Steam App ID.");
    } catch (error) { if (version === searchVersion) message(error.message); }
    finally {
      searching = false; refreshControls();
      if (searchDue) { searchDue = false; submit(); }
    }
  }
  window.gameAdditions = {submit, add, inputKind, refreshControls, get busy() { return Boolean(batch); },
    cancel: async () => {
      if (!batch?.job) return;
      $("cancel").disabled = true;
      try { await request(`/api/jobs/${batch.job.id}/cancel`, {method: "POST", body: "{}", headers: {Authorization: `Bearer ${batch.job.token}`}}); }
      catch (error) { message(error.message); $("cancel").disabled = false; }
    }};
  $("identifier").addEventListener("input", () => {
    cancelAutoSearch(); searchVersion++; $("game-matches").replaceChildren(); message(""); refreshControls();
    const text = $("identifier").value.trim();
    if (inputKind(text).kind === "search" && text.length >= 2 && text.length <= 100) {
      searchTimer = setTimeout(() => { searchTimer = null; submit(); }, 4000);
    }
  });
  $("games-retry").addEventListener("click", () => { paused = false; save(); schedule(); refreshControls(); });
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    for (const [id, name] of Array.isArray(saved?.queued) ? saved.queued.slice(0, 1000) : []) if (validId(id) && typeof name === "string") queued.set(id, name.slice(0, 300));
    paused = saved?.paused === true;
    if (saved?.batch && credentials(saved.batch.job) && validCurrencies(saved.batch.request) && Array.isArray(saved.batch.ids) && saved.batch.ids.every(validId)) {
      batch = saved.batch; setBusy(true); wishlistRemovals.register(batch.job); pollBatch();
    } else if (saved?.batch) paused = true;
  } catch (_) { paused = true; }
  if (queued.size) { automaticExampleDismissed = true; comparisonCoordinator.cancel("wishlist-example"); }
  refreshControls();
  document.addEventListener("DOMContentLoaded", schedule, {once: true});
})();
