// Baseline frontend glue. No browser storage (per spec) — pure in-memory + fetch.

async function follow(matchId, btn) {
  btn.disabled = true;
  btn.textContent = "…";
  try {
    await fetch("/api/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_id: matchId }),
    });
    location.reload();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "+ Follow";
  }
}

async function unsub(subId, ev) {
  ev.preventDefault();
  ev.stopPropagation();
  await fetch("/api/subscriptions/" + subId, { method: "DELETE" });
  location.reload();
}

// M4 will replace this with a real SSE connection to /api/stream.
// For now the "live" pill simply reflects that the page is connected.
(function () {
  const el = document.getElementById("conn");
  if (el) el.textContent = "live";
})();
