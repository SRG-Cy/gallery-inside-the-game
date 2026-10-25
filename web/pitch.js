// Draws the 105 x 68 pitch, the recent run of play and any highlighted evidence.
const Pitch = (() => {
  const canvas = document.getElementById("pitch");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height, S = W / 105;
  const TEAM = { NOR: "#2f8bff", HAR: "#ffc21a" };
  let recent = [];
  let evidence = [];
  let evidenceUntil = 0;

  const px = (x) => x * S;
  const py = (y) => y * S;

  function field() {
    const base = ctx.createLinearGradient(0, 0, 0, H);
    base.addColorStop(0, "#247a48");
    base.addColorStop(1, "#1b6a3c");
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, W, H);
    for (let i = 0; i < 18; i += 2) {
      ctx.fillStyle = "rgba(255,255,255,0.06)";
      ctx.fillRect((W / 18) * i, 0, W / 18, H);
    }
    ctx.strokeStyle = "rgba(255,255,255,.85)";
    ctx.lineWidth = 2.5;
    ctx.strokeRect(px(1.5), py(1.5), px(102), py(65));
    ctx.beginPath(); ctx.moveTo(px(52.5), py(1.5)); ctx.lineTo(px(52.5), py(66.5)); ctx.stroke();
    ctx.beginPath(); ctx.arc(px(52.5), py(34), px(9.15), 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,.6)";
    ctx.beginPath(); ctx.arc(px(52.5), py(34), 4, 0, Math.PI * 2); ctx.fill();
    for (const side of [0, 1]) {
      const x0 = side ? 105 - 1.5 - 16.5 : 1.5;
      ctx.strokeRect(px(x0), py(34 - 20.16), px(16.5), py(40.32));
      const x1 = side ? 105 - 1.5 - 5.5 : 1.5;
      ctx.strokeRect(px(x1), py(34 - 9.16), px(5.5), py(18.32));
      ctx.beginPath(); ctx.arc(px(side ? 105 - 12.5 : 12.5), py(34), 4, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath();
      ctx.arc(px(side ? 105 - 12.5 : 12.5), py(34), px(9.15), side ? Math.PI * 0.705 : -Math.PI * 0.295,
              side ? Math.PI * 1.295 : Math.PI * 0.295);
      ctx.stroke();
    }
    const vignette = ctx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, W * 0.75);
    vignette.addColorStop(0, "rgba(0,0,0,0)");
    vignette.addColorStop(1, "rgba(0,0,0,.35)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, W, H);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    field();
    ctx.lineCap = "round";
    for (let i = 1; i < recent.length; i++) {
      const a = recent[i - 1], b = recent[i];
      ctx.globalAlpha = 0.25 + 0.75 * (i / recent.length);
      ctx.strokeStyle = TEAM[b.team] || "#ffffff";
      ctx.lineWidth = 3.5;
      ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
    }
    recent.slice(0, -1).forEach((e, i) => {
      ctx.globalAlpha = 0.35 + 0.65 * ((i + 1) / recent.length);
      ctx.fillStyle = TEAM[e.team] || "#fff";
      ctx.beginPath(); ctx.arc(px(e.x), py(e.y), 7, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "rgba(8,12,22,.8)"; ctx.lineWidth = 2; ctx.stroke();
    });
    ctx.globalAlpha = 1;
    const last = recent[recent.length - 1];
    if (last) {
      const bx = px(last.end_x ?? last.x), by = py(last.end_y ?? last.y);
      ctx.shadowColor = "rgba(255,255,255,.9)"; ctx.shadowBlur = 18;
      ctx.fillStyle = "#fff";
      ctx.beginPath(); ctx.arc(bx, by, 9, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
      if (last.player_name) {
        ctx.font = "italic 900 30px Archivo, sans-serif";
        const label = last.player_name;
        const w = ctx.measureText(label.toUpperCase()).width + 30;
        const lx = Math.min(Math.max(bx - w / 2, 10), W - w - 10), ly = Math.max(by - 54, 10);
        ctx.fillStyle = "rgba(8,12,22,.88)";
        ctx.beginPath(); ctx.roundRect(lx, ly, w, 42, 4); ctx.fill();
        ctx.fillStyle = TEAM[last.team] || "#fff";
        ctx.beginPath(); ctx.roundRect(lx, ly, 8, 42, [4, 0, 0, 4]); ctx.fill();
        ctx.fillStyle = "#fff"; ctx.fillText(label.toUpperCase(), lx + 18, ly + 31);
      }
    }
    if (performance.now() < evidenceUntil) {
      const pulse = 12 + 5 * Math.sin(performance.now() / 160);
      ctx.lineWidth = 3.5;
      for (const e of evidence) {
        ctx.strokeStyle = "#ff3b4a";
        ctx.beginPath(); ctx.arc(px(e.x), py(e.y), pulse, 0, Math.PI * 2); ctx.stroke();
      }
      requestAnimationFrame(draw);
    }
  }

  return {
    update(events) { recent = events || []; draw(); },
    highlight(events) {
      evidence = events;
      evidenceUntil = performance.now() + 6000;
      draw();
    },
    draw,
  };
})();
Pitch.draw();
