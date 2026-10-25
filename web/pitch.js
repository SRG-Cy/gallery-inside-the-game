// Draws the 105 x 68 pitch, the recent run of play and any highlighted evidence.
const Pitch = (() => {
  const canvas = document.getElementById("pitch");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height, S = W / 105;
  const TEAM = { NOR: "#5aa9e6", HAR: "#f4d35e" };
  let recent = [];
  let evidence = [];
  let evidenceUntil = 0;

  const px = (x) => x * S;
  const py = (y) => y * S;

  function field() {
    for (let i = 0; i < 12; i++) {
      ctx.fillStyle = i % 2 ? "#2e6b47" : "#2a6342";
      ctx.fillRect((W / 12) * i, 0, W / 12 + 1, H);
    }
    ctx.strokeStyle = "rgba(255,255,255,.55)";
    ctx.lineWidth = 2;
    ctx.strokeRect(px(1), py(1), px(103), py(66));
    ctx.beginPath(); ctx.moveTo(px(52.5), py(1)); ctx.lineTo(px(52.5), py(67)); ctx.stroke();
    ctx.beginPath(); ctx.arc(px(52.5), py(34), px(9.15), 0, Math.PI * 2); ctx.stroke();
    for (const side of [0, 1]) {
      const x0 = side ? 105 - 1 - 16.5 : 1;
      ctx.strokeRect(px(x0), py(34 - 20.16), px(16.5), py(40.32));
      const x1 = side ? 105 - 1 - 5.5 : 1;
      ctx.strokeRect(px(x1), py(34 - 9.16), px(5.5), py(18.32));
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    field();
    // run of play
    ctx.lineWidth = 3;
    for (let i = 1; i < recent.length; i++) {
      const a = recent[i - 1], b = recent[i];
      ctx.strokeStyle = (TEAM[b.team] || "#ffffff") + "88";
      ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
    }
    for (const e of recent.slice(0, -1)) {
      ctx.fillStyle = TEAM[e.team] || "#fff";
      ctx.beginPath(); ctx.arc(px(e.x), py(e.y), 5, 0, Math.PI * 2); ctx.fill();
    }
    const last = recent[recent.length - 1];
    if (last) {
      const bx = px(last.end_x ?? last.x), by = py(last.end_y ?? last.y);
      ctx.fillStyle = "#fff";
      ctx.beginPath(); ctx.arc(bx, by, 8, 0, Math.PI * 2); ctx.fill();
      if (last.player_name) {
        ctx.font = "600 22px 'Barlow Semi Condensed', sans-serif";
        const label = last.player_name;
        const w = ctx.measureText(label).width + 16;
        const lx = Math.min(Math.max(bx - w / 2, 8), W - w - 8), ly = Math.max(by - 44, 8);
        ctx.fillStyle = "rgba(14,18,26,.85)"; ctx.fillRect(lx, ly, w, 28);
        ctx.fillStyle = TEAM[last.team] || "#fff"; ctx.fillRect(lx, ly, 4, 28);
        ctx.fillStyle = "#fff"; ctx.fillText(label, lx + 10, ly + 21);
      }
    }
    // evidence
    if (performance.now() < evidenceUntil) {
      const pulse = 10 + 4 * Math.sin(performance.now() / 160);
      ctx.lineWidth = 3;
      for (const e of evidence) {
        ctx.strokeStyle = "#e5383b";
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
