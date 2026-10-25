# Submission kit: demo video script and pitch

## Before you record

1. Start Gallery locally with Microsoft Foundry so the badge reads **Microsoft Foundry**. Recorded replies play back instantly, and anything new goes live to your deployment:
   ```
   C:\Users\sreer\.venvs\gallery\Scripts\python -m uvicorn gallery.app:create_app --factory --port 8000
   ```
2. Open http://localhost:8000 in a full-screen browser at 1920×1080, with browser zoom at 90% if the queue feels cramped.
3. Set **Match: seed 7**, speed **30×**, and tick **Auto-air tags**.
4. Record with Clipchamp (Windows 11) or Win + Alt + R. Record the narration in the same take, or add a voice-over afterwards.
5. Do one practice run. The match is identical every time, so the moments land at the same points.

**Timing at 30×:** the 3' goal arrives about 7 seconds after you press Start, and the 10' pressing surge about 25 seconds after. Press **1×** to slow the match while you talk over a card, then **30×** to move on.

## Shot list (target 1:50)

| Time | On screen | Say (roughly) |
|---|---|---|
| 0:00–0:10 | The console before kick-off. | "This is Gallery, an AI producer's desk for match-day studios. AI agents watch a live match and propose insights, and a human producer decides what goes on air." |
| 0:10–0:25 | Press **Start match**. The pitch, scorebug and the **Microsoft Foundry** badge are visible. A player speed tag auto-airs top left. | "Synthetic match events stream in. Plain code computes the stats: pass difficulty, shot speed, pressing, momentum, control versus chaos. Low-risk graphics like speed tags can go straight to air." |
| 0:25–0:45 | The **3' goal** card arrives. Press **1×**. Click **Put on air**: the screen flashes, the lower-third slides in and the **ON AIR** badge lights red. | "When something important happens, the agent crew drafts an insight that explains why it matters. The producer reads it and puts it on air." |
| 0:45–1:08 | The **10' pressing surge** card. Click **Details**, then **Agent steps**: the verifier ✗ lists figures that don't match the stats, then the second try passes ✓. Put it on air. | "Every number, name and minute is checked against the stats before a producer sees it. Here the verifier caught figures that didn't match the stats and sent the draft back, and the corrected draft passed. Nothing unverified airs by accident." |
| 1:08–1:20 | Click **Reject** on another card, pick *Already covered*. Open the **Audit trail** tab at the bottom. | "Rejections need a reason. Every proposal, agent step, approval and rejection is in the audit trail, ready to export, which is what a real broadcaster needs." |
| 1:20–1:38 | Switch back to the **Fan feeds** tab and click **Casual**, **Analyst**, **Following** (choose a player), then **Español**. | "The same approved insight is rewritten for each audience: a casual fan, an analyst, someone following one player, and Spanish speakers. Every version is verified too." |
| 1:38–1:50 | Show the README architecture diagram on GitHub, or the console at full time with the recap. | "Built with Microsoft Agent Framework on Microsoft Foundry, deployed on Azure Container Apps, with a read-only MCP endpoint so a broadcaster's own agents can query the match. Gallery: AI that proposes, a producer who decides." |

**Rules check:** under 2:00. No Premier League logos, real club names or music; the clubs are fictional. Show the app actually running.

## Project pitch (for the submission form)

**Gallery: the AI producer's desk for match-day studios**

Gallery turns a live stream of synthetic football events into explainable, broadcast-ready insights, and keeps a human producer in charge of what goes on air. A team of specialised agents built with Microsoft Agent Framework on Microsoft Foundry watches every pass, press and shot. An Analyst agent explains why a moment matters (control vs chaos, pressing surges, momentum swings) using live stats tools. A deterministic verifier checks every number, name and minute, and sends mistakes back for one correction. A Graphics agent turns the result into timed lower-thirds, stat cards and player tags. The producer approves, edits or rejects each one, and every step is written to an audit trail. Approved insights are then personalized by a fourth agent for casual fans, analysts, followers of a single player and Spanish speakers. A read-only MCP endpoint lets a broadcaster's own agents query the same verified data.

**Problem it solves:** studios want AI-generated match storytelling, but cannot put unchecked AI text on air. Gallery makes AI insight trustworthy enough for live broadcast: verified, explainable, auditable and under human control.

**Microsoft and Azure technology:** Microsoft Foundry (gpt-4.1-mini deployment), Microsoft Agent Framework (agents, function tools), Azure Container Apps (scale-to-zero hosting), Azure Container Registry, GitHub Actions (tests and image build), Model Context Protocol.

**Category:** Best Enterprise Solution. It also fits Best Multi-Agent System.

**Links:**
- Live demo: https://gallery.livelywave-ba42e696.westus2.azurecontainerapps.io/
- Code: https://github.com/SRG-Cy/gallery-inside-the-game
- Video: _your YouTube or Vimeo link_

**Testing instructions for judges:** open the live demo, choose a match, and press **Start match** at 15× or 30×. Use **Put on air**, **Edit** and **Reject** on proposals, and switch the fan-feed tabs. No sign-in is needed. The hosted demo replays the agents' recorded Foundry replies, so it is fast and free to run.
