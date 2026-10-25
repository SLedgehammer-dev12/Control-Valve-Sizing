/**
 * High-Resolution 2D Axial Flow Simulation Viewer for Control Valves & Piping.
 * Renders high-fidelity cross-sectional velocity/pressure heatmaps with offscreen caching
 * and 60 FPS multi-streamline particle advection.
 */

export function createFlow2DViewer(canvasId = "flow2d-canvas", hudId = "flow2d-hud") {
  const canvas = document.getElementById(canvasId);
  const hud = document.getElementById(hudId);
  if (!canvas) return null;

  const ctx = canvas.getContext("2d");
  const offscreenCanvas = document.createElement("canvas");
  const offscreenCtx = offscreenCanvas.getContext("2d");

  let simData = null;
  let activeLayer = "velocity";
  let showParticles = true;
  let particles = [];
  let animId = null;
  let heatmapDirty = true;
  let lastW = 0;
  let lastH = 0;

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(rect.width || 850);
    const h = Math.round(rect.height || 340);
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      heatmapDirty = true;
    }
    return { w, h, dpr };
  }

  function initParticles(count = 280) {
    particles = [];
    if (!simData?.geometry) return;
    const g = simData.geometry;
    for (let k = 0; k < count; k++) {
      particles.push(spawnParticle(g, Math.random()));
    }
  }

  function spawnParticle(g, progress = 0.0) {
    const r1 = g.d1_mm / 2.0;
    const xIn = g.x_inlet_mm;
    const xOut = g.x_outlet_mm;
    const x = xIn + (xOut - xIn) * progress;
    const y = (Math.random() * 1.84 - 0.92) * (r1 * 0.88);
    return {
      x,
      y,
      life: Math.random() * 120,
      maxLife: 90 + Math.random() * 110,
      prevX: x,
      prevY: y,
    };
  }

  function sampleField(x, y) {
    if (!simData?.grid) return { u: 0, v: 0, vm: 0, p: 0, m: 0, cell: 0 };
    const grid = simData.grid;
    const xs = grid.xs;
    const ys = grid.ys;
    const nx = grid.nx;
    const ny = grid.ny;

    if (x < xs[0] || x > xs[nx - 1] || y < ys[0] || y > ys[ny - 1]) {
      return { u: 0, v: 0, vm: 0, p: 0, m: 0, cell: 0 };
    }

    const fx = ((x - xs[0]) / (xs[nx - 1] - xs[0])) * (nx - 1);
    const fy = ((y - ys[0]) / (ys[ny - 1] - ys[0])) * (ny - 1);
    const i = Math.min(nx - 2, Math.max(0, Math.floor(fx)));
    const j = Math.min(ny - 2, Math.max(0, Math.floor(fy)));
    const tx = fx - i;
    const ty = fy - j;

    function bilerp(field) {
      const v00 = field[j][i];
      const v10 = field[j][i + 1];
      const v01 = field[j + 1][i];
      const v11 = field[j + 1][i + 1];
      return (1 - tx) * (1 - ty) * v00 + tx * (1 - ty) * v10 + (1 - tx) * ty * v01 + tx * ty * v11;
    }

    return {
      u: bilerp(grid.u),
      v: bilerp(grid.v),
      vm: bilerp(grid.v_mag),
      p: bilerp(grid.p),
      m: bilerp(grid.mach),
      cell: grid.cell_type[j][i],
    };
  }

  function toScreen(x, y, w, h) {
    if (!simData?.geometry) return { px: 0, py: 0 };
    const g = simData.geometry;
    const padX = 28;
    const padY = 24;
    const plotW = w - padX * 2;
    const plotH = h - padY * 2;
    const maxR = Math.max(g.d1_mm, g.d2_mm, g.dn_mm) * 0.58;
    const spanX = Math.max(1.0, g.x_outlet_mm - g.x_inlet_mm);

    const px = padX + ((x - g.x_inlet_mm) / spanX) * plotW;
    const py = padY + plotH / 2 - (y / maxR) * (plotH / 2);
    return { px, py };
  }

  function toWorld(px, py, w, h) {
    if (!simData?.geometry) return { x: 0, y: 0 };
    const g = simData.geometry;
    const padX = 28;
    const padY = 24;
    const plotW = w - padX * 2;
    const plotH = h - padY * 2;
    const maxR = Math.max(g.d1_mm, g.d2_mm, g.dn_mm) * 0.58;
    const spanX = Math.max(1.0, g.x_outlet_mm - g.x_inlet_mm);

    const x = g.x_inlet_mm + ((px - padX) / plotW) * spanX;
    const y = -((py - (padY + plotH / 2)) / (plotH / 2)) * maxR;
    return { x, y };
  }

  function getColormapColor(val, minVal, maxVal, layer) {
    const t = Math.max(0.0, Math.min(1.0, (val - minVal) / Math.max(0.001, maxVal - minVal)));
    if (layer === "velocity") {
      // 5-stop Turbo continuous colormap: deep navy -> cyan -> green -> amber -> red
      let r = 0;
      let g = 0;
      let b = 0;
      if (t < 0.25) {
        const f = t / 0.25;
        r = Math.round(15 + 15 * f);
        g = Math.round(40 + 140 * f);
        b = Math.round(160 + 75 * f);
      } else if (t < 0.5) {
        const f = (t - 0.25) / 0.25;
        r = Math.round(30 + 30 * f);
        g = Math.round(180 + 55 * f);
        b = Math.round(235 - 135 * f);
      } else if (t < 0.75) {
        const f = (t - 0.5) / 0.25;
        r = Math.round(60 + 185 * f);
        g = Math.round(235 - 45 * f);
        b = Math.round(100 - 80 * f);
      } else {
        const f = (t - 0.75) / 0.25;
        r = Math.round(245 + 10 * f);
        g = Math.round(190 - 150 * f);
        b = Math.round(20 - 10 * f);
      }
      return `rgb(${r}, ${g}, ${b})`;
    }
    if (layer === "pressure") {
      // High-resolution Cool-to-Warm: Deep Blue -> Cyan -> Ivory -> Warm Orange -> Crimson
      let r = 0;
      let g = 0;
      let b = 0;
      if (t < 0.5) {
        const f = t / 0.5;
        r = Math.round(30 + 170 * f);
        g = Math.round(90 + 150 * f);
        b = Math.round(230 - 30 * f);
      } else {
        const f = (t - 0.5) / 0.5;
        r = Math.round(200 + 55 * f);
        g = Math.round(240 - 190 * f);
        b = Math.round(200 - 170 * f);
      }
      return `rgb(${r}, ${g}, ${b})`;
    }
    // Mach / Shock layer
    if (t >= 0.92) return "rgb(239, 68, 68)";
    if (t >= 0.75) return "rgb(249, 115, 22)";
    if (t >= 0.5) return "rgb(234, 179, 8)";
    return `rgb(34, ${Math.round(130 + t * 125)}, 245)`;
  }

  function renderHeatmapOffscreen(w, h, dpr) {
    if (!simData?.grid) return;
    offscreenCanvas.width = w * dpr;
    offscreenCanvas.height = h * dpr;
    offscreenCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const grid = simData.grid;
    let minVal = 0;
    let maxVal = 1;

    if (activeLayer === "velocity") {
      minVal = 0;
      maxVal = simData.summary.vena_contracta_velocity_m_s * 1.05;
    } else if (activeLayer === "pressure") {
      minVal = simData.summary.min_pressure_bar;
      maxVal = simData.summary.p1_bar;
    } else {
      minVal = 0;
      maxVal = Math.max(1.0, simData.summary.max_mach);
    }

    const nx = grid.nx;
    const ny = grid.ny;

    for (let j = 0; j < ny - 1; j++) {
      for (let i = 0; i < nx - 1; i++) {
        const cType = grid.cell_type[j][i];
        if (cType === 0) continue;

        let val = grid.v_mag[j][i];
        if (activeLayer === "pressure") val = grid.p[j][i];
        else if (activeLayer === "mach") val = grid.mach[j][i];

        const p0 = toScreen(grid.xs[i], grid.ys[j], w, h);
        const p1 = toScreen(grid.xs[i + 1], grid.ys[j + 1], w, h);

        const xMin = Math.min(p0.px, p1.px);
        const yMin = Math.min(p0.py, p1.py);
        const cw = Math.abs(p1.px - p0.px) + 0.8;
        const ch = Math.abs(p1.py - p0.py) + 0.8;

        if (cType === 3) {
          offscreenCtx.fillStyle = "rgba(165, 243, 252, 0.92)";
        } else {
          offscreenCtx.fillStyle = getColormapColor(val, minVal, maxVal, activeLayer);
        }
        offscreenCtx.fillRect(xMin, yMin, cw, ch);
      }
    }
    heatmapDirty = false;
  }

  function drawGeometry(w, h) {
    const g = simData.geometry;

    // Centerline
    ctx.beginPath();
    ctx.setLineDash([5, 5]);
    ctx.strokeStyle = "rgba(148, 163, 184, 0.40)";
    ctx.lineWidth = 1;
    const c0 = toScreen(g.x_inlet_mm, 0, w, h);
    const c1 = toScreen(g.x_outlet_mm, 0, w, h);
    ctx.moveTo(c0.px, c0.py);
    ctx.lineTo(c1.px, c1.py);
    ctx.stroke();
    ctx.setLineDash([]);

    // Solid Pipe Walls
    function strokePoly(pts, strokeColor, fillColor = null) {
      if (!pts || pts.length < 2) return;
      ctx.beginPath();
      const pStart = toScreen(pts[0][0], pts[0][1], w, h);
      ctx.moveTo(pStart.px, pStart.py);
      for (let k = 1; k < pts.length; k++) {
        const p = toScreen(pts[k][0], pts[k][1], w, h);
        ctx.lineTo(p.px, p.py);
      }
      if (fillColor) {
        ctx.closePath();
        ctx.fillStyle = fillColor;
        ctx.fill();
      }
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.2;
      ctx.stroke();
    }

    strokePoly(g.top_wall, "#cbd5e1");
    strokePoly(g.bottom_wall, "#cbd5e1");

    const vType = g.valve_type || "globe";
    const rSeat = g.dn_mm * 0.425;
    const yLbl = -(rSeat * 1.15);

    if (vType === "butterfly") {
      strokePoly(g.seat_top, "#64748b", "rgba(51, 65, 85, 0.95)");
      strokePoly(g.seat_bottom, "#64748b", "rgba(51, 65, 85, 0.95)");
      strokePoly(g.plug, "#38bdf8", "rgba(14, 165, 233, 0.92)");

      const pShaft = toScreen(0, 0, w, h);
      ctx.beginPath();
      ctx.arc(pShaft.px, pShaft.py, Math.max(3, 4 * (window.devicePixelRatio || 1)), 0, Math.PI * 2);
      ctx.fillStyle = "#f8fafc";
      ctx.fill();
      ctx.strokeStyle = "#0284c7";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.fillStyle = "#38bdf8";
      ctx.font = "11px ui-monospace, monospace";
      const pLbl = toScreen(g.x_seat_mm, yLbl, w, h);
      ctx.fillText("Döner Disk", pLbl.px - 28, pLbl.py);
      const pVcLbl = toScreen(g.x_vc_mm, yLbl, w, h);
      ctx.fillText("Üst & Alt Çift Jet", pVcLbl.px - 36, pVcLbl.py);

    } else if (vType === "ball") {
      strokePoly(g.seat_top, "#94a3b8", "rgba(51, 65, 85, 0.96)");
      strokePoly(g.seat_bottom, "#94a3b8", "rgba(51, 65, 85, 0.96)");
      strokePoly(g.plug, "#fbbf24", "rgba(217, 119, 6, 0.92)");

      ctx.fillStyle = "#fbbf24";
      ctx.font = "11px ui-monospace, monospace";
      const pLbl = toScreen(g.x_seat_mm, yLbl, w, h);
      ctx.fillText("V-Port Segment", pLbl.px - 36, pLbl.py);
      const pVcLbl = toScreen(g.x_vc_mm, yLbl, w, h);
      ctx.fillText("Asimetrik Jet", pVcLbl.px - 32, pVcLbl.py);

    } else if (vType === "angle_cage") {
      strokePoly(g.seat_top, "#a855f7", "rgba(88, 28, 135, 0.90)");
      strokePoly(g.seat_bottom, "#a855f7", "rgba(88, 28, 135, 0.90)");
      strokePoly(g.plug, "#f43f5e", "rgba(225, 29, 72, 0.92)");

      ctx.fillStyle = "#c084fc";
      ctx.font = "11px ui-monospace, monospace";
      const pLbl = toScreen(g.x_seat_mm, yLbl, w, h);
      ctx.fillText("Kafes Trim", pLbl.px - 28, pLbl.py);
      const pVcLbl = toScreen(g.x_vc_mm, yLbl, w, h);
      ctx.fillText("Dağıtık Mikro-Jet", pVcLbl.px - 38, pVcLbl.py);

    } else {
      // Globe
      strokePoly(g.seat_top, "#94a3b8", "rgba(51, 65, 85, 0.96)");
      strokePoly(g.seat_bottom, "#94a3b8", "rgba(51, 65, 85, 0.96)");
      strokePoly(g.plug, "#f87171", "rgba(71, 85, 105, 0.98)");

      ctx.fillStyle = "#94a3b8";
      ctx.font = "11px ui-monospace, monospace";
      const pSeat = toScreen(g.x_seat_mm, yLbl, w, h);
      ctx.fillText("Sit Boğazı", pSeat.px - 26, pSeat.py);
      const pVc = toScreen(g.x_vc_mm, yLbl, w, h);
      ctx.fillText("Vena Contracta", pVc.px - 36, pVc.py);
    }

    // Dimension callouts showing pipe and valve diameters to scale
    ctx.save();
    ctx.fillStyle = "rgba(203, 213, 225, 0.75)";
    ctx.font = "10px ui-monospace, monospace";
    const pInTop = toScreen(g.x_inlet_mm, g.d1_mm / 2, w, h);
    ctx.fillText(`D1: ⌀${Math.round(g.d1_mm)}mm`, pInTop.px + 4, Math.max(14, pInTop.py - 6));

    const pValveTop = toScreen(g.x_seat_mm, g.dn_mm / 2, w, h);
    ctx.fillText(`Vana: DN${Math.round(g.dn_mm)}`, pValveTop.px - 24, Math.max(14, pValveTop.py - 6));

    const pOutTop = toScreen(g.x_outlet_mm, g.d2_mm / 2, w, h);
    ctx.fillText(`D2: ⌀${Math.round(g.d2_mm)}mm`, pOutTop.px - 62, Math.max(14, pOutTop.py - 6));

    if (Math.abs(g.d1_mm - g.dn_mm) > 1.0) {
      const redText = g.d1_mm > g.dn_mm ? "Redüksiyon (D1→DN)" : "Genişletici (D1→DN)";
      const pMidIn = toScreen((g.x_inlet_mm + g.x_seat_mm) * 0.5, (g.d1_mm + g.dn_mm) * 0.26, w, h);
      ctx.fillStyle = "rgba(148, 163, 184, 0.60)";
      ctx.fillText(redText, pMidIn.px - 45, Math.max(14, pMidIn.py - 4));
    }
    ctx.restore();
  }

  function drawParticles(w, h, dt = 0.016) {
    if (!showParticles || !simData) return;
    const g = simData.geometry;
    const vMax = Math.max(1.0, simData.summary.vena_contracta_velocity_m_s);

    ctx.save();
    for (const p of particles) {
      p.prevX = p.x;
      p.prevY = p.y;

      const f = sampleField(p.x, p.y);
      if (f.cell === 0) {
        Object.assign(p, spawnParticle(g, 0.0));
        continue;
      }

      // Advection scaled to physical domain span
      const domainSpan = Math.max(10.0, g.x_outlet_mm - g.x_inlet_mm);
      const speedScale = (domainSpan / 240.0) * 3.8;
      p.x += f.u * dt * speedScale;
      p.y += f.v * dt * speedScale;
      p.life += 1;

      if (p.x > g.x_outlet_mm || p.life > p.maxLife) {
        Object.assign(p, spawnParticle(g, 0.0));
        continue;
      }

      const p0 = toScreen(p.prevX, p.prevY, w, h);
      const p1 = toScreen(p.x, p.y, w, h);

      const speedRatio = Math.min(1.0, f.vm / vMax);
      ctx.beginPath();
      ctx.moveTo(p0.px, p0.py);
      ctx.lineTo(p1.px, p1.py);

      if (f.cell === 3) {
        ctx.strokeStyle = "#a5f3fc";
        ctx.lineWidth = 2.4;
      } else if (f.cell === 2) {
        ctx.strokeStyle = "rgba(165, 180, 252, 0.85)";
        ctx.lineWidth = 1.4;
      } else if (speedRatio > 0.65) {
        ctx.strokeStyle = "rgba(56, 189, 248, 0.95)";
        ctx.lineWidth = 2.0;
      } else {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.85)";
        ctx.lineWidth = 1.4;
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  function renderFrame() {
    if (document.hidden || !canvas.offsetParent) {
      animId = requestAnimationFrame(renderFrame);
      return;
    }

    const { w, h, dpr } = resizeCanvas();
    if (w !== lastW || h !== lastH) {
      heatmapDirty = true;
      lastW = w;
      lastH = h;
    }

    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, w, h);

    if (simData?.grid) {
      if (heatmapDirty) {
        renderHeatmapOffscreen(w, h, dpr);
      }
      ctx.drawImage(offscreenCanvas, 0, 0, w, h);
      drawGeometry(w, h);
      drawParticles(w, h);
    } else {
      ctx.fillStyle = "#64748b";
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Hesaplama bekleniyor…", w / 2, h / 2);
    }

    animId = requestAnimationFrame(renderFrame);
  }

  function handleMouseMove(evt) {
    if (!simData?.geometry || !hud) return;
    const rect = canvas.getBoundingClientRect();
    const px = evt.clientX - rect.left;
    const py = evt.clientY - rect.top;
    const w = rect.width;
    const h = rect.height;

    const { x, y } = toWorld(px, py, w, h);
    const f = sampleField(x, y);

    let cellName = "Serbest Akış";
    if (f.cell === 0) cellName = "Cidar / Gövde Metali";
    else if (f.cell === 2) cellName = "Resirkülasyon Girdabı (Eddy)";
    else if (f.cell === 3) cellName = "Kavitasyon Buhar Çekirdeği";

    hud.hidden = false;
    hud.style.left = `${Math.min(w - 230, px + 12)}px`;
    hud.style.top = `${Math.min(h - 96, py + 12)}px`;
    hud.innerHTML = `
      <div><b>X:</b> ${x.toFixed(1)} mm | <b>r:</b> ${y.toFixed(1)} mm</div>
      <div><b>Hız:</b> ${f.vm.toFixed(1)} m/s (u: ${f.u.toFixed(1)}, v: ${f.v.toFixed(1)})</div>
      <div><b>Basınç:</b> ${f.p.toFixed(3)} bar(a) | <b>Mach:</b> ${f.m.toFixed(2)}</div>
      <div style="color:#38bdf8;font-size:0.75rem;">${cellName}</div>
    `;
  }

  function handleMouseLeave() {
    if (hud) hud.hidden = true;
  }

  canvas.addEventListener("mousemove", handleMouseMove);
  canvas.addEventListener("mouseleave", handleMouseLeave);

  const layerSel = document.getElementById("flow2d-layer");
  if (layerSel) {
    layerSel.addEventListener("change", (e) => {
      activeLayer = e.target.value;
      heatmapDirty = true;
    });
  }

  const partCheck = document.getElementById("flow2d-particles");
  if (partCheck) {
    partCheck.addEventListener("change", (e) => {
      showParticles = e.target.checked;
    });
  }

  // Start loop
  animId = requestAnimationFrame(renderFrame);

  return {
    update(data) {
      simData = data;
      heatmapDirty = true;
      initParticles(280);
      if (data?.summary) {
        const s = data.summary;
        const setTxt = (id, val) => {
          const el = document.getElementById(id);
          if (el) el.textContent = val;
        };
        setTxt("f2d-v1", `${s.inlet_velocity_m_s} m/s`);
        setTxt("f2d-vt", `${s.throat_velocity_m_s} m/s`);
        setTxt("f2d-vvc", `${s.vena_contracta_velocity_m_s} m/s`);
        setTxt("f2d-v2", `${s.outlet_velocity_m_s} m/s`);
        setTxt("f2d-pvc", `${s.p_vc_bar} bar`);

        let cavStatus = "Normal Subkritik";
        let cavColor = "#22c55e";
        if (s.is_flashing) {
          cavStatus = "Flashing (İki Faz)";
          cavColor = "#f97316";
        } else if (s.is_cavitating) {
          cavStatus = "Kavitasyon Riski";
          cavColor = "#ef4444";
        } else if (s.is_choked) {
          cavStatus = "Choked (Sonik)";
          cavColor = "#eab308";
        }
        const badge = document.getElementById("f2d-cav");
        if (badge) {
          badge.textContent = cavStatus;
          badge.style.color = cavColor;
        }
      }
    },
    destroy() {
      if (animId) cancelAnimationFrame(animId);
      canvas.removeEventListener("mousemove", handleMouseMove);
      canvas.removeEventListener("mouseleave", handleMouseLeave);
    },
  };
}
