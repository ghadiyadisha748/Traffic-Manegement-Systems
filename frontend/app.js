// =============================================================================
// Junction Console — Premium AI Dashboard JS
// Bug fixes:
//   1. cameraAlive resets to true on WS open & each message
//   2. congestionChart.update('none') — no lag
//   3. Console log: diff-based update (only append new lines)
//   4. Wait gauge formula corrected (0=empty, high=full)
//   5. camInf: toFixed(1) rounding
//   6. Emergency test cleared state preserves <small> element
// =============================================================================

// --- Live Clock ---
(function tick() {
  const el = document.getElementById('clock');
  if (el) el.textContent = new Date().toLocaleTimeString('en-GB');
  setTimeout(tick, 1000);
})();

// --- Cached DOM references (queried once at startup) ---
const D = {
  ledDot: document.getElementById('ledDot'),
  emergencyBanner: document.getElementById('emergencyBanner'),
  emergencyTxt: document.getElementById('emergencyTxt'),
  emergencySub: document.getElementById('emergencySub'),
  roadStatusChip: document.getElementById('roadStatusChip'),
  totalCount: document.getElementById('totalCount'),
  pedCount: document.getElementById('pedCount'),
  waitVal: document.getElementById('waitVal'),
  fuelVal: document.getElementById('fuelVal'),
  co2Val: document.getElementById('co2Val'),
  laneVal: document.getElementById('laneVal'),
  predictMins: document.getElementById('predictMins'),
  signboardPanel: document.getElementById('signboardPanel'),
  weatherIcon: document.getElementById('weatherIcon'),
  weatherTemp: document.getElementById('weatherTemp'),
  weatherCond: document.getElementById('weatherCond'),
  weatherNote: document.getElementById('weatherNote'),
  camFps: document.getElementById('camFps'),
  camConf: document.getElementById('camConf'),
  camInf: document.getElementById('camInf'),
  liveVideo: document.getElementById('liveVideo'),
  consoleScreen: document.getElementById('consoleScreen'),
  toastContainer: document.getElementById('toastContainer'),
};

// Cache vehicle count cells after rows are built
const cntEls = {};

// --- App State ---
let systemOn = true;
let cameraOn = true;
let prevEmergency = false;
let prevCongestion = '';
let cameraAlive = true;
let cameraTimer = null;
let lastLogHash = '';  // Bug #3: diff-based console log
let isDarkMode = localStorage.getItem('junction_theme') === 'dark';

function setTheme(dark, notify = false) {
  isDarkMode = dark;
  localStorage.setItem('junction_theme', dark ? 'dark' : 'light');
  const swNight = document.getElementById('swNight');
  if (swNight) {
    swNight.classList.toggle('on', dark);
    swNight.setAttribute('aria-checked', String(dark));
  }
  const themeToggleBtn = document.getElementById('theme-toggle');
  if (themeToggleBtn) {
    themeToggleBtn.innerHTML = dark ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
  }
  const settingDark = document.getElementById('setting-dark-mode');
  if (settingDark && settingDark.checked !== dark) {
    settingDark.checked = dark;
  }
  if (dark) {
    document.documentElement.classList.add('dark-mode');
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.classList.remove('dark-mode');
    document.documentElement.setAttribute('data-theme', 'light');
  }
  document.body.style.filter = 'none';
  document.documentElement.style.removeProperty('--bg-0');
  if (typeof updateThemeColors === 'function') {
    updateThemeColors(dark);
  }
  if (notify && typeof showToast === 'function') {
    showToast(dark ? 'Futuristic Dark Theme Enabled' : 'Clean Light Theme Enabled', 'info');
  }
}

// --- Toggle helper (power, rockers) ---
function wireToggle(id, initial, cb) {
  const el = document.getElementById(id);
  if (!el) return;
  let state = initial;
  const handle = () => {
    state = !state;
    el.classList.toggle('on', state);
    el.setAttribute('aria-checked', String(state));
    cb(state);
  };
  el.addEventListener('click', handle);
  el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handle(); } });
}

wireToggle('powerToggle', true, v => { systemOn = v; });
wireToggle('swAuto', true, () => { });
wireToggle('swCamera', true, v => {
  cameraOn = v;
  D.liveVideo.style.display = v ? 'block' : 'none';
});
const swNightEl = document.getElementById('swNight');
if (swNightEl) {
  swNightEl.classList.toggle('on', isDarkMode);
  swNightEl.setAttribute('aria-checked', String(isDarkMode));
  const handleNightToggle = () => {
    setTheme(!isDarkMode, true);
  };
  swNightEl.addEventListener('click', handleNightToggle);
  swNightEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleNightToggle();
    }
  });
}

// --- Toast ---
function showToast(msg, type = 'info', duration = 4000) {
  const icons = { danger: '⚠️', warning: '🟡', success: '✅', info: 'ℹ️' };
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.setAttribute('role', 'alert');
  t.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span>${msg}</span>`;
  D.toastContainer.appendChild(t);
  requestAnimationFrame(() => requestAnimationFrame(() => t.classList.add('toast-show')));
  setTimeout(() => {
    t.classList.remove('toast-show');
    t.addEventListener('transitionend', () => t.remove(), { once: true });
  }, duration);
}

// --- Vehicle Classification Rows ---
const vehicleTypes = [
  { name: 'Car', color: '#00d4ff' },
  { name: 'Motorcycle', color: '#ffb020' },
  { name: 'Bus', color: '#7c3aed' },
  { name: 'Truck', color: '#ff4444' },
  { name: 'Person', color: '#00ff88' },
  { name: 'TrafficSign', color: '#e8eaf6' },
];
const countRowsEl = document.getElementById('countRows');
vehicleTypes.forEach(v => {
  const row = document.createElement('div');
  row.className = 'm-row';
  const label = v.name.replace(/([A-Z])/g, ' $1').trim().toUpperCase();
  row.innerHTML = `<div class="m-label"><span class="m-icon" style="background:${v.color}"></span>${label}</div><div class="m-val" id="cnt-${v.name}">0</div>`;
  countRowsEl.appendChild(row);
  cntEls[v.name] = document.getElementById(`cnt-${v.name}`);
});

// --- Gauge Builder ---
function makeGauge(containerId, color) {
  const c = document.getElementById(containerId);
  if (!c) return null;
  c.innerHTML = `<svg viewBox="0 0 150 90" style="color:${color}"><path d="M15,80 A60,60 0 1,1 135,80" fill="none" stroke="var(--gauge-track)" stroke-width="10" stroke-linecap="round"/><path class="arc" d="M15,80 A60,60 0 1,1 135,80" fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round" stroke-dasharray="264" stroke-dashoffset="264" style="transition:stroke-dashoffset 0.4s ease"/></svg>`;
  return c.querySelector('.arc');
}
const gWait = makeGauge('gaugeWait', '#00d4ff');
const gFuel = makeGauge('gaugeFuel', '#00ff88');
const gCo2 = makeGauge('gaugeCo2', '#00ff88');
const gLane = makeGauge('gaugeLane', '#ffb020');

// Bug #4: wait gauge corrected — 0 wait = empty arc; high wait = full arc
function setGauge(arc, pct) {
  if (!arc) return;
  const clamped = Math.min(100, Math.max(0, pct));
  arc.setAttribute('stroke-dashoffset', String(264 - (264 * clamped / 100)));
}

// --- Prediction Dial ---
document.getElementById('predictDial').innerHTML =
  `<svg viewBox="0 0 180 108" style="width:180px"><path d="M18,96 A72,72 0 1,1 162,96" fill="none" stroke="var(--gauge-track)" stroke-width="12" stroke-linecap="round"/><path id="predictArc" d="M18,96 A72,72 0 1,1 162,96" fill="none" stroke="#ffb020" stroke-width="12" stroke-linecap="round" stroke-dasharray="317" stroke-dashoffset="80" style="transition:stroke-dashoffset 0.5s ease,stroke 0.3s"/><text id="predictText" x="90" y="78" text-anchor="middle" font-family="Orbitron,sans-serif" font-size="24" font-weight="800" fill="var(--text-primary)">0%</text></svg>`;
const predictArc = document.getElementById('predictArc');
const predictText = document.getElementById('predictText');

// --- Signal Lane Rows ---
const LANES = [
  { name: 'Road A', arm: 'N' }, { name: 'Road B', arm: 'E' },
  { name: 'Road C', arm: 'S' }, { name: 'Road D', arm: 'W' },
];
const SEGS = 12;
const signalRowsEl = document.getElementById('signalRows');
LANES.forEach(l => {
  const id = l.name.replace(' ', '');
  const b = document.createElement('div');
  b.className = 'lane-block';
  let s = '';
  for (let i = 0; i < SEGS; i++) s += `<div class="led-seg" id="seg-${id}-${i}"></div>`;
  b.innerHTML = `<div class="lane-top"><span class="name">${l.name.toUpperCase()} (${l.arm})</span><span class="time" id="time-${id}">0s</span></div><div class="led-track">${s}</div>`;
  signalRowsEl.appendChild(b);
});

function setArmLight(arm, state) {
  const el = document.getElementById('sig-' + arm);
  if (!el) return;
  el.querySelectorAll('i').forEach(i => (i.className = ''));
  if (state === 'green') el.children[2].className = 'on-g';
  else if (state === 'amber') el.children[1].className = 'on-a';
  else el.children[0].className = 'on-r';
}

// --- Radar Canvas ---
const canvas = document.getElementById('radarCanvas');
const ctx = canvas.getContext('2d');
const CW = canvas.width, CH = canvas.height, CX = CW / 2, CY = CH / 2, R = CW / 2 - 6;
let sweepAngle = 0;
let blips = [];
const armAngles = { N: -90, E: 0, S: 90, W: 180 };

function seedBlips() {
  blips = [];
  Object.keys(armAngles).forEach(arm => {
    const n = 3 + Math.floor(Math.random() * 4);
    for (let i = 0; i < n; i++) {
      blips.push({
        arm,
        dist: 0.3 + Math.random() * 0.6,
        angOff: (Math.random() - 0.5) * 18,
        speed: 0.002 + Math.random() * 0.003,
        color: vehicleTypes[Math.floor(Math.random() * (vehicleTypes.length - 1))].color,
      });
    }
  });
}
seedBlips();
setInterval(seedBlips, 4500);

function drawRadar() {
  ctx.clearRect(0, 0, CW, CH);
  // Grid rings
  ctx.strokeStyle = isDarkMode ? 'rgba(0,212,255,0.1)' : 'rgba(2,132,199,0.15)';
  ctx.lineWidth = 1;
  for (let r = R * 0.33; r <= R; r += R * 0.33) {
    ctx.beginPath(); ctx.arc(CX, CY, r, 0, Math.PI * 2); ctx.stroke();
  }
  // Crosshairs
  ctx.strokeStyle = isDarkMode ? 'rgba(0,212,255,0.15)' : 'rgba(2,132,199,0.2)';
  ctx.setLineDash([5, 6]);
  ctx.beginPath();
  ctx.moveTo(CX, 0); ctx.lineTo(CX, CH);
  ctx.moveTo(0, CY); ctx.lineTo(CW, CY);
  ctx.stroke();
  ctx.setLineDash([]);

  // Sweep
  ctx.save();
  ctx.beginPath(); ctx.arc(CX, CY, R, 0, Math.PI * 2); ctx.clip();
  if (ctx.createConicGradient) {
    const g = ctx.createConicGradient(sweepAngle, CX, CY);
    g.addColorStop(0, isDarkMode ? 'rgba(0,212,255,0.28)' : 'rgba(2,132,199,0.3)');
    g.addColorStop(0.07, 'rgba(0,212,255,0)');
    g.addColorStop(1, 'rgba(0,212,255,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, CW, CH);
  }
  sweepAngle += 0.018;

  // Blips
  blips.forEach(b => {
    b.dist -= b.speed;
    if (b.dist < 0.1) b.dist = 0.8 + Math.random() * 0.15;
    const ba = armAngles[b.arm] * Math.PI / 180;
    const ang = ba + (b.angOff * Math.PI / 180);
    const x = CX + Math.cos(ang) * R * b.dist;
    const y = CY + Math.sin(ang) * R * b.dist;
    ctx.fillStyle = b.color;
    ctx.shadowColor = b.color;
    ctx.shadowBlur = 10;
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
  });
  ctx.restore();

  // Center dot
  ctx.fillStyle = isDarkMode ? '#050810' : '#ffffff';
  ctx.beginPath(); ctx.arc(CX, CY, 12, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = isDarkMode ? 'rgba(0,212,255,0.3)' : 'rgba(2,132,199,0.35)';
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(CX, CY, 12, 0, Math.PI * 2); ctx.stroke();

  requestAnimationFrame(drawRadar);
}
drawRadar();

// --- Chart.js Setup ---
const timeLabels = Array.from({ length: 12 }, (_, i) => i === 11 ? 'now' : `-${(11 - i) * 5}m`);
const chartOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: 'rgba(232,234,246,0.35)', font: { family: 'JetBrains Mono', size: 9 } } },
    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: 'rgba(232,234,246,0.35)', font: { family: 'JetBrains Mono', size: 9 } }, beginAtZero: true },
  },
};

const vehicleChart = new Chart(document.getElementById('vehicleChart'), {
  type: 'line',
  data: {
    labels: timeLabels,
    datasets: [{
      data: [],
      borderColor: '#00d4ff',
      backgroundColor: (scriptable) => {
        // Guard: chart area may not be ready on first render
        const chart = scriptable.chart;
        if (!chart.chartArea) return 'rgba(0,212,255,0.15)';
        const { top, bottom } = chart.chartArea;
        const g = chart.ctx.createLinearGradient(0, top, 0, bottom);
        g.addColorStop(0, 'rgba(0,212,255,0.3)');
        g.addColorStop(1, 'rgba(0,212,255,0)');
        return g;
      },
      fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2,
    }],
  },
  options: { ...chartOpts, animation: { duration: 600, easing: 'easeInOutQuart' } },
});

const congestionChart = new Chart(document.getElementById('congestionChart'), {
  type: 'bar',
  data: {
    labels: timeLabels,
    datasets: [{
      data: [], backgroundColor: [], borderRadius: 4, borderSkipped: false,
    }],
  },
  // Bug #2: use 'none' to prevent animation lag on live data
  options: { ...chartOpts, animation: { duration: 400 } },
});

// --- LED dot (connection state) ---
function setLED(state) {
  D.ledDot.className = 'led-dot ' + state;
}

// --- Camera heartbeat ---
function resetCameraHeartbeat() {
  clearTimeout(cameraTimer);
  cameraAlive = true;  // Bug #1: reset on each frame
  cameraTimer = setTimeout(() => {
    if (cameraOn && cameraAlive) {
      cameraAlive = false;
      showToast('CAMERA FEED DISCONNECTED', 'danger', 6000);
    }
  }, 8000);
}
D.liveVideo.addEventListener('load', resetCameraHeartbeat);
D.liveVideo.addEventListener('error', () => {
  if (cameraOn && cameraAlive) {
    cameraAlive = false;
    showToast('CAMERA FEED UNAVAILABLE', 'danger', 6000);
  }
});

// --- Emergency test button ---
document.getElementById('testEmergencyBtn').addEventListener('click', () => {
  const showing = D.emergencyBanner.classList.toggle('show');
  // Use dedicated span to avoid brittle childNodes[0] dependency
  const msgSpan = document.getElementById('emergencyMsg');
  if (msgSpan) msgSpan.textContent = showing ? 'EMERGENCY TEST MODE ACTIVE' : 'Emergency cleared';
  if (D.emergencySub) D.emergencySub.textContent = showing ? 'Manual override — simulated green corridor' : '';
  showToast(showing ? 'EMERGENCY TEST MODE ACTIVATED' : 'EMERGENCY TEST CLEARED', showing ? 'danger' : 'info', 3000);
});

// --- Bug #3: Diff-based console log update ---
let lastLogLines = [];
function updateConsole(newLines) {
  const hash = newLines.join('|');
  if (hash === lastLogHash) return;
  lastLogHash = hash;

  // Only add truly new lines (those not already rendered)
  const existingCount = D.consoleScreen.children.length;
  const allLines = [...newLines];

  // If the log has completely different content, clear and rebuild
  if (existingCount === 0 || allLines.length < existingCount) {
    D.consoleScreen.innerHTML = '';
    lastLogLines = [];
  }
  // Append only new lines at the end
  allLines.forEach((line, i) => {
    if (line !== lastLogLines[i]) {
      const div = document.createElement('div');
      div.className = 'console-line';
      div.innerHTML = line;
      D.consoleScreen.appendChild(div);
    }
  });
  // Trim to max 6 visible
  while (D.consoleScreen.children.length > 6) {
    D.consoleScreen.removeChild(D.consoleScreen.firstChild);
  }
  lastLogLines = [...allLines];
}

// --- WebSocket with exponential-backoff reconnect ---
let ws = null, reconnectDelay = 1000, firstConnect = true;

function connectWS() {
  setLED('connecting');
  ws = new WebSocket('ws://localhost:8000/ws');

  ws.onopen = () => {
    reconnectDelay = 1000;
    cameraAlive = true;  // Bug #1: reset camera alive on reconnect
    setLED('connected');
    if (firstConnect) {
      showToast('AI SYSTEM ONLINE — BACKEND CONNECTED', 'success');
      firstConnect = false;
    } else {
      showToast('RECONNECTED TO AI BACKEND', 'success', 3000);
    }
  };

  ws.onclose = () => {
    setLED('disconnected');
    const secs = (reconnectDelay / 1000).toFixed(0);
    showToast(`CONNECTION LOST — RETRYING IN ${secs}s`, 'warning', reconnectDelay);
    setTimeout(connectWS, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
  };

  ws.onerror = () => { };  // onclose fires after onerror

  ws.onmessage = handleMessage;
}

// --- Main message handler (all field names unchanged for backend compat) ---
function handleMessage(event) {
  if (!systemOn) return;
  const data = JSON.parse(event.data);

  // 1. Vehicle counts
  vehicleTypes.forEach(v => {
    if (cntEls[v.name]) cntEls[v.name].textContent = data.counts[v.name] ?? 0;
  });
  D.totalCount.textContent = data.total_count;
  D.pedCount.textContent = data.ped_timer;

  // 2. Camera stats — each message resets heartbeat
  D.camFps.textContent = `FPS: ${data.camera.fps}`;
  D.camConf.textContent = `CONF: ${(data.camera.confidence * 100).toFixed(0)}%`;
  // Bug #5: round inference_time properly
  D.camInf.textContent = `INF: ${Number(data.camera.inference_time).toFixed(1)}ms`;
  resetCameraHeartbeat();

  // 3. Road status chip
  const total = data.total_count;
  const cls = total < 55 ? { l: 'LOW', c: 'low' } : total < 85 ? { l: 'MEDIUM', c: 'medium' } : { l: 'HIGH', c: 'high' };
  D.roadStatusChip.textContent = cls.l;
  D.roadStatusChip.className = 'status-chip ' + cls.c;
  if (cls.c === 'high' && prevCongestion !== 'high') showToast('HEAVY CONGESTION DETECTED — ROAD LOAD HIGH', 'warning');
  prevCongestion = cls.c;

  // 4. Gauges — Bug #4: wait gauge now uses 0=empty direction
  D.waitVal.textContent = data.wait_time;
  setGauge(gWait, Math.min(100, (data.wait_time / 95) * 100));
  D.fuelVal.textContent = data.fuel_saved;
  setGauge(gFuel, Math.min(100, data.fuel_saved / 4 * 100));
  D.co2Val.textContent = data.co2_cut;
  setGauge(gCo2, Math.min(100, data.co2_cut / 32 * 100));
  D.laneVal.textContent = data.lane_load;
  setGauge(gLane, data.lane_load);

  // 5. Prediction dial
  predictText.textContent = data.predict_pct + '%';
  predictArc.setAttribute('stroke-dashoffset', String(317 - (317 * data.predict_pct / 100)));
  predictArc.setAttribute('stroke', data.predict_pct > 70 ? '#ff4444' : data.predict_pct > 40 ? '#ffb020' : '#00ff88');
  D.predictMins.textContent = data.predict_mins;

  // 6. Signal lane bars + traffic light LEDs
  data.lanes.forEach(l => {
    const id = l.name.replace(' ', '');
    const te = document.getElementById(`time-${id}`);
    if (te) te.textContent = l.time + 's';
    const filled = Math.round((l.time / 120 * 2.5) * SEGS);
    for (let s = 0; s < SEGS; s++) {
      const seg = document.getElementById(`seg-${id}-${s}`);
      if (seg) seg.className = 'led-seg' + (s < filled ? ' filled ' + l.state : '');
    }
    setArmLight(l.arm, l.state);
  });

  // 7. Emergency banner
  if (data.emergency.active && !prevEmergency) {
    D.emergencyBanner.classList.add('show');
    const msgSpan = document.getElementById('emergencyMsg');
    if (msgSpan) msgSpan.textContent = data.emergency.message;
    if (D.emergencySub) D.emergencySub.textContent = 'Emergency Corridor Active';
    showToast('EMERGENCY VEHICLE DETECTED — GREEN CORRIDOR ACTIVE', 'danger', 6000);
  } else if (!data.emergency.active && prevEmergency) {
    D.emergencyBanner.classList.remove('show');
  }
  prevEmergency = data.emergency.active;

  // 8. Signboard
  D.signboardPanel.innerHTML = data.signboard.map((line, i) =>
    i === data.signboard.length - 1
      ? `<div class="sb-line dim">${line}<span class="blink">_</span></div>`
      : `<div class="sb-line">${line}</div>`
  ).join('');

  // 9. Weather
  D.weatherIcon.textContent = data.weather.icon;
  D.weatherTemp.textContent = data.weather.temp;
  D.weatherCond.textContent = data.weather.cond;
  D.weatherNote.textContent = data.weather.note;

  // 10. Charts — Bug #2: both use 'none' for live data
  vehicleChart.data.datasets[0].data = data.chart_vehicles;
  vehicleChart.update('none');
  congestionChart.data.datasets[0].data = data.chart_congestion;
  congestionChart.data.datasets[0].backgroundColor = data.chart_congestion.map(v =>
    v > 70 ? '#ff4444' : v > 40 ? '#ffb020' : '#00ff88'
  );
  congestionChart.update('none');

  // 11. Console log — Bug #3: diff-based
  updateConsole(data.logs);
}

// --- Theme Update Helper ---
function updateThemeColors(dark) {
  const gridColor = dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)';
  const tickColor = dark ? 'rgba(232,234,246,0.35)' : '#475569';
  
  if (typeof vehicleChart !== 'undefined' && vehicleChart.options) {
    if (vehicleChart.options.scales && vehicleChart.options.scales.x) {
      vehicleChart.options.scales.x.grid.color = gridColor;
      vehicleChart.options.scales.x.ticks.color = tickColor;
    }
    if (vehicleChart.options.scales && vehicleChart.options.scales.y) {
      vehicleChart.options.scales.y.grid.color = gridColor;
      vehicleChart.options.scales.y.ticks.color = tickColor;
    }
    vehicleChart.update('none');
  }
  
  if (typeof congestionChart !== 'undefined' && congestionChart.options) {
    if (congestionChart.options.scales && congestionChart.options.scales.x) {
      congestionChart.options.scales.x.grid.color = gridColor;
      congestionChart.options.scales.x.ticks.color = tickColor;
    }
    if (congestionChart.options.scales && congestionChart.options.scales.y) {
      congestionChart.options.scales.y.grid.color = gridColor;
      congestionChart.options.scales.y.ticks.color = tickColor;
    }
    congestionChart.update('none');
  }
}

// Initialize theme state at startup
setTheme(isDarkMode, false);

// ============================================================================
// CONTROL ROOM MULTI-PAGE NAVIGATION & INTERACTION SCRIPTS
// ============================================================================

// 1. Sidebar Navigation View Switching
document.querySelectorAll('.menu-item').forEach(item => {
  const activate = () => {
    document.querySelectorAll('.menu-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.view-section').forEach(v => {
      v.classList.remove('active');
      v.classList.add('hidden');
    });
    item.classList.add('active');
    const viewId = 'view-' + item.dataset.view;
    const view = document.getElementById(viewId);
    if (view) {
      view.classList.remove('hidden');
      view.classList.add('active');
      // Trigger chart resize when entering a view with charts
      if (typeof vehicleChart !== 'undefined' && vehicleChart) vehicleChart.resize();
      if (typeof congestionChart !== 'undefined' && congestionChart) congestionChart.resize();
      if (typeof historyCountChart !== 'undefined' && historyCountChart) historyCountChart.resize();
      if (typeof historySpeedChart !== 'undefined' && historySpeedChart) historySpeedChart.resize();
    }
  };
  item.addEventListener('click', activate);
  item.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      activate();
    }
  });
});

// 2. New Theme Toggle Controls Wiring
const themeToggleBtn = document.getElementById('theme-toggle');
if (themeToggleBtn) {
  themeToggleBtn.addEventListener('click', () => setTheme(!isDarkMode, true));
}
const settingDarkMode = document.getElementById('setting-dark-mode');
if (settingDarkMode) {
  settingDarkMode.addEventListener('change', e => setTheme(e.target.checked, true));
}

// 3. Floating AI Chatbot Assistant Interactivity
const chatbotContainer = document.getElementById('chatbot-container');
const chatbotHeader = document.getElementById('chatbot-header');
if (chatbotHeader && chatbotContainer) {
  chatbotHeader.addEventListener('click', () => chatbotContainer.classList.toggle('collapsed'));
}
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const chatMsgs = document.getElementById('chatbot-messages');

function sendChatMessage() {
  if (!chatInput || !chatMsgs) return;
  const text = chatInput.value.trim();
  if (!text) return;
  chatMsgs.insertAdjacentHTML('beforeend', `<div class="chat-message user"><div class="bubble">${text.replace(/</g, '&lt;')}</div></div>`);
  chatInput.value = '';
  chatMsgs.scrollTop = chatMsgs.scrollHeight;
  setTimeout(() => {
    let reply = "All monitored roads are operating within normal capacity. No critical anomalies detected.";
    if (text.toLowerCase().includes('wait') || text.toLowerCase().includes('delay')) {
      reply = "Average wait time across all approaches is stable. Signal adaptive RL engine is actively optimizing green splits.";
    } else if (text.toLowerCase().includes('emergency') || text.toLowerCase().includes('green')) {
      reply = "To engage green corridor override, use the Operations panel or trigger the Emergency override button in the dashboard.";
    } else if (text.toLowerCase().includes('speed') || text.toLowerCase().includes('flow')) {
      reply = "Average velocity across Sector 4 and North Approach is currently maintaining 38 km/h.";
    }
    chatMsgs.insertAdjacentHTML('beforeend', `<div class="chat-message bot"><div class="bubble">${reply}</div></div>`);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
  }, 600);
}
if (chatSendBtn) chatSendBtn.addEventListener('click', sendChatMessage);
if (chatInput) chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendChatMessage(); });

// 4. Interactive Button Feeds & Toast Notifications
const btnRefreshRoads = document.getElementById('btn-refresh-roads');
if (btnRefreshRoads) {
  btnRefreshRoads.addEventListener('click', () => {
    showToast('Camera feeds and YOLOv8 detection streams synchronized', 'success');
  });
}
const btnLoadHistory = document.getElementById('btn-load-history');
if (btnLoadHistory) {
  btnLoadHistory.addEventListener('click', () => {
    showToast('Historical traffic telemetry and AI forecasts refreshed', 'info');
  });
}
document.querySelectorAll('.pill-btn').forEach(btn => {
  btn.addEventListener('click', () => showToast('Service telemetry pinged — Status Nominal', 'success'));
});
const roadSelector = document.getElementById('road-selector');
if (roadSelector) {
  roadSelector.addEventListener('change', e => {
    const nameEl = document.getElementById('video-road-name');
    if (nameEl) nameEl.textContent = e.target.options[e.target.selectedIndex].text.split('(')[0].trim();
    showToast(`Focused camera stream on ${e.target.options[e.target.selectedIndex].text}`, 'info');
  });
}

// 5. Analytics View Historical Charts (Demo Data)
let historyCountChart = null;
let historySpeedChart = null;
const historyCountCtx = document.getElementById('history-count-chart');
if (historyCountCtx && typeof Chart !== 'undefined') {
  historyCountChart = new Chart(historyCountCtx, {
    type: 'bar',
    data: {
      labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      datasets: [{
        label: 'Daily Volume',
        data: [12400, 13800, 14200, 15100, 16800, 11200, 9800],
        backgroundColor: 'rgba(2, 132, 199, 0.35)',
        borderColor: '#0284c7',
        borderWidth: 1,
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { family: "'JetBrains Mono', monospace", size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { font: { family: "'JetBrains Mono', monospace", size: 10 } } }
      }
    }
  });
}
const historySpeedCtx = document.getElementById('history-speed-chart');
if (historySpeedCtx && typeof Chart !== 'undefined') {
  historySpeedChart = new Chart(historySpeedCtx, {
    type: 'line',
    data: {
      labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
      datasets: [{
        label: 'Avg Speed (km/h)',
        data: [48, 52, 22, 35, 18, 38],
        borderColor: '#059669',
        backgroundColor: 'rgba(5, 150, 105, 0.15)',
        fill: true,
        tension: 0.4,
        pointRadius: 3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { font: { family: "'JetBrains Mono', monospace", size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { font: { family: "'JetBrains Mono', monospace", size: 10 } } }
      }
    }
  });
}

// Boot WebSocket
connectWS();
