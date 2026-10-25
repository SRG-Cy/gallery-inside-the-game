// Producer console: one WebSocket for state, REST for producer actions.
const $ = (id) => document.getElementById(id);
const TEAM_NAME = { NOR: "Northgate FC", HAR: "Harbour Athletic" };
const TEAM_COLOR = { NOR: "#5aa9e6", HAR: "#f4d35e" };
const KIND_LABEL = {
  pressing_surge: "Pressing surge", momentum_swing: "Momentum swing", milestone: "Milestone",
  speed: "Speed", big_chance: "Big chance", goal: "Goal", tactical_shift: "Substitution",
};
const OVERLAY_LABEL = { lower_third: "Lower third", stat_card: "Stat card", player_tag: "Player tag" };
const REJECT_REASONS = ["Not the story right now", "Too late", "Already covered"];
const AUDIT_LABEL = {
  match_start: "Match start", moment: "Detected", agent_step: "Agent step", proposed: "Proposed",
  approved: "Approved", edited: "Edited", override: "Override", aired: "On air", rejected: "Rejected",
  expired: "Expired", dropped: "Dropped", personalized: "Personalized", recap: "Recap",
};

const state = { t: 0, speed: 15, proposals: new Map(), feed: "casual", matchId: null, focus: "NOR-6", deferred: new Set() };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clock = (t) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
const minute = (t) => `${Math.floor(t / 60)}'`;

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3200);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
    throw new Error(detail);
  }
  return res.json();
}

// ---- top bar --------------------------------------------------------------------------------
$("start").addEventListener("click", async () => {
  try { await api("/api/match/start", { seed: Number($("seed").value), speed: state.speed }); }
  catch (e) { toast(`Could not start the match: ${e.message}`); }
});
$("speed").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-speed]");
  if (!b) return;
  state.speed = Number(b.dataset.speed);
  renderSpeed();
  try { await api("/api/match/speed", { speed: state.speed }); } catch (e) { toast(e.message); }
});
$("auto").addEventListener("change", (ev) => api("/api/auto_approve", { on: ev.target.checked }).catch((e) => toast(e.message)));

function renderSpeed() {
  for (const b of $("speed").querySelectorAll("button")) b.setAttribute("aria-pressed", String(Number(b.dataset.speed) === state.speed));
}

function renderProvider(provider, status) {
  const el = $("provider");
  const names = { replay: "Replay (cached)", foundry: "Microsoft Foundry" };
  el.textContent = status === "degraded" ? `${names[provider] || provider}: rate limited, using templates` : names[provider] || provider;
  el.className = `provider ${status === "degraded" ? "degraded" : provider === "replay" ? "" : "ok"}`;
}

// ---- program monitor ------------------------------------------------------------------------
function renderTick(m) {
  state.t = m.t;
  $("score").textContent = `${m.score.NOR}–${m.score.HAR}`;
  $("clock").textContent = m.finished ? "FT" : clock(m.t);
  const nor = m.teams.NOR, har = m.teams.HAR;
  $("mom-bar").style.width = `${nor.momentum}%`;
  $("mom-num").textContent = `${nor.momentum} / ${har.momentum}`;
  const chaos = Math.round((nor.control_chaos + har.control_chaos) / 2);
  $("chaos-mark").style.left = `${chaos}%`;
  $("chaos-num").textContent = chaos < 34 ? "Controlled" : chaos < 67 ? "Open" : "Chaotic";
  $("facts").innerHTML = `
    <span>Possession</span><b>${nor.possession_pct}%</b><b>${har.possession_pct}%</b>
    <span>Shots</span><b>${nor.shots}</b><b>${har.shots}</b>
    <span>Passing</span><b>${nor.pass_accuracy_pct}%</b><b>${har.pass_accuracy_pct}%</b>`;
  renderProvider(m.provider, m.provider_status);
  Pitch.update(m.recent_events);
  updateCountdowns();
}

function showOverlay(item, teamCode) {
  const o = item.overlay;
  const el = document.createElement("div");
  el.className = `ov ov-${o.kind}`;
  el.style.setProperty("--team", TEAM_COLOR[teamCode] || TEAM_COLOR.NOR);
  if (o.kind === "lower_third") {
    el.innerHTML = `<div class="stripe"></div><div class="txt"><div class="ov-title">${esc(o.title)}</div><div class="ov-body">${esc(o.body)}</div></div>`;
  } else if (o.kind === "stat_card") {
    el.innerHTML = `<div class="ov-title">${esc(o.title)}</div><dl>${o.stats.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  } else {
    el.innerHTML = `<div class="ov-title">${esc(o.title)}</div>`;
  }
  const layer = $("overlays");
  layer.querySelectorAll(`.ov-${o.kind}`).forEach((old) => old.remove());
  layer.appendChild(el);
  $("monitor").classList.add("live");
  $("tally").textContent = "On air";
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => {
      el.remove();
      if (!layer.children.length) { $("monitor").classList.remove("live"); $("tally").textContent = "Program"; }
    }, 400);
  }, Math.max(4, o.duration_s) * 1000);
}

// ---- proposal queue -------------------------------------------------------------------------
function statusLine(p) {
  if (p.status === "aired") return `On air at ${minute(p.overlay.t_start)}`;
  if (p.status === "rejected") return "Rejected";
  if (p.status === "expired") return "Expired before anyone approved it";
  return "";
}

function traceHtml(p) {
  const name = { analyst: "Analyst", verifier: "Verifier", graphics: "Graphics", template: "Template", personalizer: "Personalizer" };
  return p.trace.map((s) => `<li><span class="${s.ok ? "ok" : "bad"}">${s.ok ? "✓" : "✗"}</span>
    <span>${name[s.agent] || s.agent}${s.attempt ? ` (try ${s.attempt})` : ""}</span>
    <span>${s.ms ? `${s.ms} ms` : ""}</span>
    <span>${esc((s.errors || []).slice(0, 2).join("; "))}</span></li>`).join("");
}

function cardHtml(p) {
  const m = p.moment;
  const team = TEAM_NAME[m.team] || "";
  return `
    <div class="card-head">
      <span class="kind">${KIND_LABEL[m.kind] || m.kind}</span>
      <span>${minute(m.t)}</span><span>${esc(team)}</span>
      <span class="badge ${p.source}">${p.source === "agent" ? "Agent, verified" : "Template"}</span>
      <span class="ttl" data-ttl></span>
    </div>
    <h3>${esc(p.insight.headline)}</h3>
    <p>${esc(p.insight.why_it_matters)}</p>
    <div class="ovk">Airs as: ${OVERLAY_LABEL[p.overlay.kind]} · “${esc(p.overlay.title)}”</div>
    <div class="row">
      <button class="chip" data-act="evidence">Show ${m.evidence_event_ids.length} events on pitch</button>
      <button class="chip" data-act="trace">Agent steps (${p.trace.length})</button>
    </div>
    <ol class="trace" hidden>${traceHtml(p)}</ol>
    <div class="row actions">
      <button class="btn btn-air" data-act="approve">Put on air</button>
      <button class="btn" data-act="edit">Edit</button>
      <button class="btn btn-quiet" data-act="reject">Reject</button>
    </div>
    <div class="editor" hidden>
      <textarea aria-label="On-air text">${esc(p.overlay.kind === "lower_third" ? p.overlay.body : p.overlay.title)}</textarea>
      <div class="warn">Edits are checked against the stats. Anything unverified is logged as an override.</div>
      <div class="row"><button class="btn btn-air" data-act="approve-edit">Put edited version on air</button>
      <button class="btn btn-quiet" data-act="cancel">Cancel</button></div>
    </div>
    <div class="rejecter" hidden>
      <div class="row">${REJECT_REASONS.map((r) => `<button class="chip" data-reason="${esc(r)}">${esc(r)}</button>`).join("")}</div>
      <div class="row"><input type="text" aria-label="Reason" placeholder="Reason (required)" style="flex:1">
      <button class="btn" data-act="reject-confirm">Reject</button></div>
    </div>
    <div class="status-line"></div>`;
}

function upsertProposal(p) {
  state.proposals.set(p.id, p);
  let card = document.querySelector(`.card[data-id="${CSS.escape(p.id)}"]`);
  if (!card) {
    card = document.createElement("article");
    card.className = "card";
    card.dataset.id = p.id;
    card.innerHTML = cardHtml(p);
  }
  // Pending cards are appended oldest-first so nothing moves under the producer's cursor;
  // handled cards go to the history list, newest first.
  const pendingNow = p.status === "pending";
  if (pendingNow && card.parentElement !== $("queue")) {
    const later = [...$("queue").querySelectorAll(".card")].find((c) => state.proposals.get(c.dataset.id).moment.t > p.moment.t);
    $("queue").insertBefore(card, later || null);
  } else if (!pendingNow && card.parentElement !== $("history")) {
    if (queueBusy()) state.deferred.add(card);  // don't shift cards under the producer's cursor
    else $("history").prepend(card);
  }
  $("history-head").hidden = !$("history").children.length;
  card.dataset.status = p.status;
  card.querySelector(".actions").hidden = p.status !== "pending";
  if (p.status !== "pending") {
    card.querySelector(".editor").hidden = true;
    card.querySelector(".rejecter").hidden = true;
  }
  card.querySelector(".status-line").textContent = statusLine(p);
  card.querySelector(".trace").innerHTML = traceHtml(p);
  const waiting = [...state.proposals.values()].filter((x) => x.status === "pending").length;
  $("queue-empty").hidden = waiting > 0;
  $("queue-empty").textContent = state.proposals.size
    ? "Nothing waiting. New insights land here as the match develops."
    : "Start a match. The agent crew watches every event and sends insights here for you to put on air.";
  $("qcount").textContent = `${waiting} waiting`;
  const done = $("history").querySelectorAll(".card");
  for (let i = 25; i < done.length; i++) done[i].remove();
  if (p.status === "aired") renderFeed();
}

function queueBusy() {
  const scroll = document.querySelector(".queue-scroll");
  return scroll.matches(":hover") || !!scroll.querySelector(".editor:not([hidden]), .rejecter:not([hidden])");
}

function flushDeferred() {
  if (queueBusy()) return;
  for (const card of state.deferred) if (card.isConnected) $("history").prepend(card);
  state.deferred.clear();
  $("history-head").hidden = !$("history").children.length;
}
document.querySelector(".queue-scroll").addEventListener("mouseleave", () => setTimeout(flushDeferred, 50));

function updateCountdowns() {
  for (const card of document.querySelectorAll('.card[data-status="pending"]')) {
    const p = state.proposals.get(card.dataset.id);
    const left = Math.max(0, p.expires_at - state.t);
    const el = card.querySelector("[data-ttl]");
    el.textContent = `${clock(left)} left`;
    el.classList.toggle("urgent", left < 30);
  }
}

document.querySelector(".queue-scroll").addEventListener("click", async (ev) => {
  const card = ev.target.closest(".card");
  if (!card) return;
  const id = card.dataset.id;
  const p = state.proposals.get(id);
  const act = ev.target.closest("[data-act]")?.dataset.act;
  const reason = ev.target.closest("[data-reason]")?.dataset.reason;
  try {
    if (reason) card.querySelector(".rejecter input").value = reason;
    if (act === "evidence") {
      const evs = await api(`/api/events?ids=${p.moment.evidence_event_ids.join(",")}`);
      Pitch.highlight(evs);
    } else if (act === "trace") {
      const t = card.querySelector(".trace"); t.hidden = !t.hidden;
    } else if (act === "approve") {
      await api(`/api/proposals/${encodeURIComponent(id)}/approve`, {});
    } else if (act === "edit") {
      card.querySelector(".editor").hidden = false; card.querySelector(".rejecter").hidden = true;
      card.querySelector("textarea").focus();
    } else if (act === "approve-edit") {
      await api(`/api/proposals/${encodeURIComponent(id)}/approve`, { text: card.querySelector("textarea").value });
    } else if (act === "cancel") {
      card.querySelector(".editor").hidden = true;
    } else if (act === "reject") {
      card.querySelector(".rejecter").hidden = false; card.querySelector(".editor").hidden = true;
      card.querySelector(".rejecter input").focus();
    } else if (act === "reject-confirm") {
      const r = card.querySelector(".rejecter input").value.trim();
      if (!r) { toast("Add a reason so the audit trail shows why this was rejected."); return; }
      await api(`/api/proposals/${encodeURIComponent(id)}/reject`, { reason: r });
    }
  } catch (e) {
    toast(e.message.includes("is ") ? `Too late: ${e.message.replace("proposal ", "this ")}.` : e.message);
  }
});

// ---- fan feeds ------------------------------------------------------------------------------
document.querySelector(".tabs").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-feed]");
  if (!b) return;
  state.feed = b.dataset.feed;
  for (const t of document.querySelectorAll(".tabs button")) t.setAttribute("aria-selected", String(t === b));
  $("focus").hidden = state.feed !== "player";
  renderFeed();
});

$("focus").addEventListener("change", async (ev) => {
  try {
    await api("/api/focus", { player_id: ev.target.value });
    toast("New approvals will follow this player.");
  } catch (e) { toast(e.message); }
});

async function loadSquads() {
  const squads = await api("/api/squads");
  $("focus").innerHTML = Object.entries(squads).map(([team, players]) =>
    `<optgroup label="${TEAM_NAME[team]}">${players.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</optgroup>`).join("");
  $("focus").value = state.focus;
}

function renderFeed() {
  const aired = [...state.proposals.values()].filter((p) => p.status === "aired")
    .sort((a, b) => b.overlay.t_start - a.overlay.t_start);
  $("feed").innerHTML = aired.length
    ? aired.map((p) => `<li><span class="min">${minute(p.overlay.t_start)}</span>
        <span class="${p.variants[state.feed] ? "" : "pending"}">${esc(p.variants[state.feed] || "Personalizing for this audience…")}</span></li>`).join("")
    : `<li class="empty">Approved insights appear here, rewritten for each audience.</li>`;
}

function renderRecaps(recaps) {
  $("recaps").innerHTML = ["FT", "HT"].filter((k) => recaps[k])
    .map((k) => `<div class="recap"><b>${k === "HT" ? "Half-time recap" : "Full-time recap"}.</b> ${esc(recaps[k])}</div>`).join("");
}

// ---- audit ----------------------------------------------------------------------------------
function auditText(r) {
  const d = r.data || {};
  const p = r.proposal_id && state.proposals.get(r.proposal_id);
  const head = p ? p.insight.headline : "";
  switch (r.kind) {
    case "moment": return `${KIND_LABEL[d.kind] || d.kind} ${TEAM_NAME[d.team] ? `· ${TEAM_NAME[d.team]}` : ""}`;
    case "agent_step": return `${d.agent} ${d.ok ? "passed" : "failed"}${d.ms ? ` in ${d.ms} ms` : ""}${d.errors?.length ? `: ${d.errors[0]}` : ""}`;
    case "proposed": return `${d.headline} (${d.source})`;
    case "rejected": return `${head}: “${d.reason}”`;
    case "edited": return `${head}: text changed`;
    case "override": return `${head}: aired with ${d.errors.length} unverified item(s)`;
    case "dropped": return `${KIND_LABEL[d.kind] || d.kind}: ${d.reason}`;
    case "recap": return `${d.period} recap written`;
    case "match_start": return `Seed ${d.seed} at ${d.speed}× on ${d.provider}`;
    case "approved": return `${head} (${d.by})`;
    default: return head;
  }
}

function addAudit(r, prepend = true) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="min">${minute(r.t)}</span><span class="k k-${r.kind}">${AUDIT_LABEL[r.kind] || r.kind}</span><span>${esc(auditText(r))}</span>`;
  const list = $("audit");
  if (prepend) list.prepend(li); else list.appendChild(li);
  while (list.children.length > 150) list.lastChild.remove();
}

// ---- socket ---------------------------------------------------------------------------------
function applySnapshot(s) {
  if (s.match_id !== state.matchId) {
    state.proposals.clear();
    document.querySelectorAll(".queue-scroll .card").forEach((c) => c.remove());
    $("overlays").innerHTML = "";
    $("monitor").classList.remove("live");
  }
  state.matchId = s.match_id;
  state.speed = s.speed;
  state.focus = s.focus_player;
  $("focus").value = s.focus_player;
  $("auto").checked = s.auto_approve;
  renderSpeed();
  for (const p of [...s.proposals].reverse()) upsertProposal(p);
  $("audit").innerHTML = "";
  for (const r of [...s.audit].reverse()) addAudit(r, false);
  state.recaps = s.recaps;
  renderRecaps(s.recaps);
  renderFeed();
  renderTick(s);
}

function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "snapshot") applySnapshot(m);
    else if (m.type === "tick") {
      if (m.match_id !== state.matchId) return;
      renderTick(m);
    } else if (m.type === "proposal" || m.type === "proposal_update") upsertProposal(m.proposal);
    else if (m.type === "on_air") {
      const p = state.proposals.get(m.item.proposal_id);
      showOverlay(m.item, p?.moment.team);
    } else if (m.type === "audit") {
      if (m.row.match_id === state.matchId) addAudit(m.row);
    } else if (m.type === "recap") {
      state.recaps = { ...(state.recaps || {}), [m.period]: m.text };
      renderRecaps(state.recaps);
    }
  };
  ws.onclose = () => setTimeout(connect, 1000);
}

renderSpeed();
loadSquads().catch(() => {});
connect();
