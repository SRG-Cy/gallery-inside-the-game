"""Record the under-2-minute demo video by driving the live console in Chromium.

Usage (with Gallery running locally, e.g. on port 8001):
    python scripts/record_demo.py http://localhost:8001 demo/gallery-demo.mp4

Captions narrate each shot; a visible cursor glides to every button before it is clicked.
"""
import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import imageio_ffmpeg
from playwright.async_api import async_playwright

W, H = 1920, 1080

OVERLAY_JS = """
(() => {
  const css = document.createElement('style');
  css.textContent = `
    #rec-cursor { position: fixed; z-index: 99999; width: 26px; height: 26px; left: 960px; top: 540px;
      pointer-events: none; transition: left .7s cubic-bezier(.3,.8,.3,1), top .7s cubic-bezier(.3,.8,.3,1); }
    #rec-cursor svg { width: 100%; height: 100%; filter: drop-shadow(0 2px 4px rgba(0,0,0,.6)); }
    #rec-cursor.press::after { content: ''; position: absolute; left: -14px; top: -14px; width: 28px; height: 28px;
      border-radius: 50%; border: 3px solid #ff2d46; animation: ripple .5s ease-out forwards; }
    @keyframes ripple { from { transform: scale(.3); opacity: 1 } to { transform: scale(1.6); opacity: 0 } }
    #rec-caption { position: fixed; z-index: 99998; right: 34px; bottom: 34px;
      max-width: 640px; padding: 14px 26px 14px 22px; background: rgba(6,10,20,.94); color: #fff;
      font: 700 25px/1.3 Archivo, sans-serif; border-left: 7px solid #ff2d46; box-shadow: 0 16px 40px rgba(0,0,0,.6);
      transition: opacity .35s; }
    #rec-caption:empty { opacity: 0; }
    #rec-card { position: fixed; inset: 0; z-index: 100000; display: grid; place-items: center; text-align: center;
      background: radial-gradient(900px 500px at 50% 40%, #13203a, #060a14); color: #fff; transition: opacity .6s; }
    #rec-card.hide { opacity: 0; pointer-events: none; }
    #rec-card .mark { display: inline-block; font: italic 900 96px Archivo, sans-serif; padding: 4px 48px 4px 36px;
      background: linear-gradient(100deg, #ff2d46, #c3122b); clip-path: polygon(0 0,100% 0,calc(100% - 28px) 100%,0 100%); }
    #rec-card h1 { font: 800 44px/1.2 Archivo, sans-serif; margin: 34px 0 10px; }
    #rec-card p { font: 500 26px/1.5 Archivo, sans-serif; color: #c2cbdc; margin: 6px 0; }
  `;
  document.head.appendChild(css);
  const cur = document.createElement('div');
  cur.id = 'rec-cursor';
  cur.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 2l16 9-7 2-3 7z" fill="#fff" stroke="#060a14" stroke-width="1.5"/></svg>';
  const cap = document.createElement('div'); cap.id = 'rec-caption';
  const card = document.createElement('div'); card.id = 'rec-card'; card.className = 'hide';
  document.body.append(cur, cap, card);
})();
"""


class Director:
    def __init__(self, page, base):
        self.page, self.base = page, base

    async def caption(self, text: str):
        await self.page.evaluate("t => document.getElementById('rec-caption').textContent = t", text)

    async def card(self, html: str | None):
        if html is None:
            await self.page.evaluate("document.getElementById('rec-card').classList.add('hide')")
        else:
            await self.page.evaluate("h => { const c = document.getElementById('rec-card'); c.innerHTML = h; c.classList.remove('hide'); }", html)

    async def click(self, locator, pause: float = 0.6):
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        await self.page.evaluate("([x, y]) => { const c = document.getElementById('rec-cursor'); c.style.left = x + 'px'; c.style.top = y + 'px'; }", [x, y])
        await asyncio.sleep(0.8)
        await self.page.evaluate("() => { const c = document.getElementById('rec-cursor'); c.classList.remove('press'); void c.offsetWidth; c.classList.add('press'); }")
        await locator.click()
        await asyncio.sleep(pause)

    async def api(self, path: str, body: dict):
        async with httpx.AsyncClient(timeout=10) as c:
            (await c.post(self.base + path, json=body)).raise_for_status()

    async def wait_for_card(self, kind: str, timeout: float = 60):
        sel = f'#queue .card[data-status="pending"] .kind-icon + .kind'
        deadline = time.time() + timeout
        while time.time() < deadline:
            cards = self.page.locator('#queue .card[data-status="pending"]')
            for i in range(await cards.count()):
                c = cards.nth(i)
                if (await c.locator(".kind").inner_text()).strip().lower() == kind:
                    return c
            await asyncio.sleep(0.25)
        raise TimeoutError(f"no pending {kind} card ({sel})")


async def record(base: str, out: Path):
    raw_dir = out.parent / "raw"
    shutil.rmtree(raw_dir, ignore_errors=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(raw_dir),
                                        record_video_size={"width": W, "height": H})
        page = await ctx.new_page()
        await page.goto(base + "/?rec=1")
        await page.wait_for_selector("#start")
        await page.evaluate(OVERLAY_JS)
        await page.evaluate("document.fonts.ready")
        d = Director(page, base)
        q = page.locator

        # 0:00 title card
        await d.card('<div><span class="mark">GALLERY</span><h1>The AI producer\'s desk for match-day studios</h1>'
                     '<p>Synthetic match data · Microsoft Foundry · Microsoft Agent Framework</p></div>')
        await asyncio.sleep(4.5)
        await d.card(None)
        await d.caption("AI agents watch a live match and propose insights. A human producer decides what goes on air.")
        await asyncio.sleep(4.5)

        # kick-off at 30x with player tags on auto-air
        await d.click(q("#speed [data-speed='30']"), 0.2)
        if not await q("#auto").is_checked():
            await d.click(q("label.toggle"), 0.2)
        await d.click(q("#start"), 0.2)
        await d.caption("Synthetic events stream in. Plain code computes every stat: pass difficulty, shot speed, pressing, momentum.")
        goal = await d.wait_for_card("goal")
        await d.api("/api/match/speed", {"speed": 1})
        await d.caption("A key moment. The agent crew explains why it matters, and every number is checked before you see it.")
        await asyncio.sleep(3.5)
        await d.caption("The producer reads it and puts it on air.")
        await d.click(goal.locator("[data-act='approve']"), 5.5)

        # the verifier catch on the 10' pressing surge
        await d.api("/api/match/speed", {"speed": 30})
        await d.caption("Graphics appear as broadcast overlays, timed and machine-readable for any renderer.")
        press = await d.wait_for_card("pressing surge")
        await d.api("/api/match/speed", {"speed": 1})
        await d.click(press.locator("[data-act='details']"), 0.3)
        await d.click(press.locator("[data-act='trace']"), 0.3)
        await d.caption("Nothing unverified airs by accident. The verifier caught figures that didn't match the stats and sent the draft back; the corrected draft passed.")
        await asyncio.sleep(6.5)
        await d.click(press.locator("[data-act='approve']"), 4.5)

        # reject with a reason, then the audit trail
        await d.api("/api/match/speed", {"speed": 30})
        nxt = q('#queue .card[data-status="pending"]').first
        await nxt.wait_for(timeout=60000)
        await d.api("/api/match/speed", {"speed": 1})
        await d.caption("Rejections need a reason, and every step lands in the audit trail.")
        await d.click(nxt.locator("[data-act='reject']"), 0.3)
        await d.click(nxt.locator("[data-reason='Already covered']"), 0.2)
        await d.click(nxt.locator("[data-act='reject-confirm']"), 0.8)
        await d.click(q(".view-tabs [data-view='audit']"), 4.5)

        # personalized fan feeds
        await d.click(q(".view-tabs [data-view='feeds']"), 0.3)
        await d.caption("The same verified insight, rewritten for every audience.")
        for feed, label in [("casual", "Casual fans"), ("analyst", "Analysts"), ("player", "Following one player"), ("es", "Spanish speakers")]:
            await d.caption(f"The same verified insight, rewritten for every audience: {label}.")
            await d.click(q(f".tabs [data-feed='{feed}']"), 2.2)

        # momentum and control vs chaos while the match runs on
        await page.mouse.move(10, 10)
        await page.evaluate("window.scrollTo(0, 0)")
        await d.api("/api/match/speed", {"speed": 30})
        await d.caption("Momentum, control versus chaos and live stats update with every event.")
        await asyncio.sleep(7)

        # outro
        await d.caption("")
        await d.card('<div><span class="mark">GALLERY</span><h1>AI that proposes. A producer who decides.</h1>'
                     '<p>Microsoft Agent Framework · Microsoft Foundry · Azure Container Apps · MCP</p>'
                     '<p>github.com/SRG-Cy/gallery-inside-the-game</p></div>')
        await asyncio.sleep(5)
        video = page.video
        await ctx.close()
        await browser.close()
        raw = Path(await video.path())

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "0.6", "-i", str(raw), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", "-movflags", "+faststart", str(out)],
                   check=True)
    print("wrote", out)


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "demo/gallery-demo.mp4")
    asyncio.run(record(base, out))
