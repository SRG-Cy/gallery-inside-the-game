# Gallery: the AI producer's desk for match-day studios

Design spec, 2026-10-25. Entry for Microsoft x Premier League "Inside the Game: Developer Hackathon",
challenge "The Synthetic Match Insights Engine for Premier League Studio".
Submission closes **2026-10-27**. Solo build, ~15-20 hours.

## 1. Purpose and positioning

Most of the ~55 public entries are fan-facing "multi-agent explainer" apps. Gallery is built for the
people who put the match on air: agents propose explainable on-screen insights, a human producer
approves, edits or rejects each one, and every step is audited. Approved insights then fan out into
personalized feeds (casual, analyst, follow-a-player, second language).

Target prizes: Best Enterprise Solution (primary), Grand Prize, Best Multi-Agent Orchestration,
Best Use of Microsoft Foundry.

Success criteria:
- All five brief stages work end to end on a synthetic match: ingest, interpret, explain, render, personalize.
- No number, name or minute reaches the on-air output unless verified against the stats engine.
- A full match replays deterministically and runs at zero cost in `replay` mode.
- Deployed on Azure Container Apps with a Foundry model; public GitHub repo; demo video under 2 minutes.

Out of scope: auto-eventing from video, 3D rendering, user accounts, multiple concurrent producers.

## 2. Architecture

One Python service (FastAPI + WebSocket) serving a no-build vanilla JS frontend.

```
Simulator -> Stats engine -> Agent crew -> Proposal queue -> Producer -> On air + fan feeds
                                   \______________ Audit log (SQLite) ______________/
```

### 2.1 Match simulator (`gallery/sim/`, plain code)
- Seeded RNG; two fictional clubs (e.g. Northgate FC vs Harbour Athletic), 11 players each + subs.
- Emits events in match-time order. Event schema:
  `{id, t (match seconds), type, team, player_id, x, y, end_x, end_y, outcome, speed_kmh, under_pressure, meta}`
  Types: pass, carry, shot, tackle, interception, pressure, possession_change, foul, card, substitution,
  goal, sprint, period_start, period_end.
- Scripted "story beats" per seed (a pressing spell, a momentum swing, a milestone, a goal) so the demo
  always has good moments, layered on random play.
- Clock runs at a speed factor (1x / 15x / 30x); 90 minutes at 15x is 6 minutes.

### 2.2 Stats engine (`gallery/stats/`, plain code, no AI)
- Incremental state: score, possession %, pass accuracy, pass distance, pass difficulty rating
  (distance + pressure + progression), ball and shot speed, pressures per minute in the opponent half,
  momentum (rolling weighted threat), control-vs-chaos index (turnover rate vs completion), per-player
  totals (passes, distance, top speed).
- Key-moment detectors emit `Moment{kind, t, team, player_id?, evidence_event_ids, stats_snapshot}`:
  pressing_surge, momentum_swing, milestone, speed_threshold, big_chance, goal, tactical_shift.
- Exposed to agents as read-only tools: `get_team_stats`, `get_player_stats`, `get_events(window)`,
  `compare_windows`.

### 2.3 Agent crew (`gallery/agents/`, Microsoft Agent Framework on a Foundry model)
| Agent | Input | Output |
|---|---|---|
| Analyst | Moment + tools | Insight draft: headline, why_it_matters, claims[], evidence_event_ids |
| Graphics | Approved-shape insight | Overlay packet (lower_third / stat_card / player_tag) with timing |
| Verifier (code) | Draft | pass, or list of exact errors (wrong number, unknown player, bad minute) |
| Personalizer | Approved insight | Variants: casual, analyst, player-focus, language (EN + ES) |
| Recap | Approved items + final stats | Half-time and full-time recaps |

Flow per moment: Analyst -> Verifier -> (on fail, one revision with errors) -> template fallback if still
failing -> Graphics -> queue. All structured output is JSON-schema validated.
Simple moments (speed_threshold, milestone) skip the LLM and use templates.

LLM provider is one env setting, `GALLERY_PROVIDER`:
- `github`: GitHub Models free tier (OpenAI-compatible) for development.
- `foundry`: Microsoft Foundry deployment for the real demo.
- `replay`: responses cached by request hash; zero cost, deterministic.

### 2.4 Producer console and outputs
- Proposal queue sorted by priority, each with a shelf life (e.g. 120 match-seconds); stale items expire.
- Actions: approve, edit (inline text), reject (reason required). Auto-approve toggle applies only to
  low-risk kinds (player_tag, speed readings); insights always need a human.
- On-air preview: 2D canvas pitch with live ball/players, scorebug, clock, control-vs-chaos meter,
  overlay layer rendering approved packets at `t_start` for `duration_s`.
- Fan feeds panel: tabs for each personalization variant; player and language pickers.
- Overlay JSON stream on WebSocket (`/ws`) and `GET /api/overlays` for downstream graphics systems.

### 2.5 Audit log (`gallery/audit/`)
SQLite table of every event in the lifecycle: moment detected, agent step (with model, tokens, latency),
verifier result, producer action (with edit diff / reject reason), on-air time. Viewable live in the
console, exportable as JSON at `GET /api/audit`.

## 3. Error handling
- LLM timeout (8 s) or error: one retry, then template fallback; card shows a "Template" badge.
- Rate limit (429): back off, and degrade to templates while limited; provider badge turns amber.
- Verifier failure: one revision with the error list, then template. Never airs unverified text.
- Stale proposals expire automatically and are logged as `expired`.
- WebSocket reconnect: server sends a full state snapshot, so the console recovers mid-match.
- Missing provider credentials at startup: fall back to `replay`, log a warning.

## 4. Testing
- pytest: simulator determinism (same seed -> same events); stats correctness on hand-built fixtures;
  each detector fires on a crafted sequence; verifier catches wrong numbers/names/minutes;
  orchestration with a fake LLM client (pass, fail-then-fix, fail-twice -> template, timeout).
- API smoke test: start match, receive proposals over WebSocket, approve one, see it in overlays + audit.
- Manual browser check of the console before recording.

## 5. Build order
Day 1 (Oct 25-26): repo + scaffolding; simulator; stats + detectors; verifier; LLM client with replay
cache; agent crew; FastAPI + WebSocket loop.
Day 2 (Oct 26-27): console UI; fan feeds; audit view; record replay cache from Foundry; deploy to Azure
Container Apps; README with architecture diagram; demo video; submit.

Open item: confirm the exact submission cut-off time and time zone on Oct 27.
