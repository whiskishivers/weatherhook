"""
Weatherhook Web UI
A local configuration editor for config.yaml.
Run: python webui.py
Then open: http://localhost:5000
"""

import csv
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
ZONES_CSV_PATH = SCRIPT_DIR / "all_zones.csv"
STATUS_PATH = SCRIPT_DIR / "status.json"

# ─── Status helpers ──────────────────────────────────────────────────────────

def read_status() -> dict:
    """Read bot status.json, returning an offline sentinel if absent or unreadable."""
    try:
        with open(STATUS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"running": False, "as_of": None}

# ─── Load zones from CSV ────────────────────────────────────────────────────

_TYPE_ORDER = ["public", "fire", "county", "coastal", "offshore"]

def load_zones():
    """Load zones grouped by (state, id) so fire/public duplicates on the same ID are merged."""
    raw = {}  # (state, id) -> {name: str, types: set}
    with open(ZONES_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_   = row["id"].strip()
            state = row["state"].strip()
            key = (state, id_)
            if key not in raw:
                raw[key] = {"name": row["name"].strip(), "types": set()}
            raw[key]["types"].add(row["type"].strip())

    zones = []
    for (state, id_), v in sorted(raw.items(), key=lambda x: (x[0][0], x[0][1])):
        types = [t for t in _TYPE_ORDER if t in v["types"]]  # stable display order
        zones.append({
            "id":    id_,
            "state": state,
            "types": types,
            "name":  v["name"],
        })
    return zones

ALL_ZONES = load_zones()

# Flat map: any individual zone ID -> its group, for resolving config.yaml entries
_ID_TO_GROUP = {g["id"]: g for g in ALL_ZONES}

# ─── Config helpers ──────────────────────────────────────────────────────────

def read_config():
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}

def write_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

# ─── HTML template ───────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Weatherhook Config</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --c0: #0a0c10;
    --c1: #12161e;
    --c2: #1c2230;
    --c3: #2a3347;
    --c4: #3d4f6b;
    --accent: #4a9eff;
    --accent-dim: #2a5fa0;
    --warn: #f0a030;
    --danger: #e05050;
    --success: #40c080;
    --text: #c8d4e8;
    --text-dim: #6a7a98;
    --text-bright: #e8f0ff;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'IBM Plex Sans', sans-serif;
    --radius: 4px;
    --border: 1px solid var(--c3);
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--c0);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -20%, rgba(74,158,255,0.07) 0%, transparent 60%);
  }

  /* ── Layout ── */
  .shell {
    max-width: 960px;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }

  header {
    display: flex;
    align-items: baseline;
    gap: 16px;
    margin-bottom: 40px;
    border-bottom: 1px solid var(--c3);
    padding-bottom: 20px;
  }
  header h1 {
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 600;
    color: var(--text-bright);
    letter-spacing: -0.5px;
  }
  header h1 span { color: var(--accent); }
  .header-sub {
    font-size: 12px;
    color: var(--text-dim);
    font-family: var(--mono);
  }

  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }
  @media (max-width: 680px) { .grid { grid-template-columns: 1fr; } }

  /* ── Panels ── */
  .panel {
    background: var(--c1);
    border: var(--border);
    border-radius: 6px;
    overflow: hidden;
  }
  .panel-full { grid-column: 1 / -1; }

  .panel-header {
    background: var(--c2);
    border-bottom: var(--border);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .panel-header .label {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text-dim);
  }
  .panel-header .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--accent);
    flex-shrink: 0;
  }
  .panel-body { padding: 16px; }

  /* ── Zone search ── */
  .search-row {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }
  .search-row input {
    flex: 1;
  }

  input[type="text"], input[type="number"], select {
    background: var(--c2);
    border: var(--border);
    border-radius: var(--radius);
    color: var(--text-bright);
    font-family: var(--mono);
    font-size: 13px;
    padding: 8px 12px;
    width: 100%;
    outline: none;
    transition: border-color 0.15s;
  }
  input[type="text"]:focus, input[type="number"]:focus {
    border-color: var(--accent);
  }
  input::placeholder { color: var(--text-dim); }

  .results-box {
    background: var(--c0);
    border: var(--border);
    border-radius: var(--radius);
    max-height: 220px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--c4) transparent;
    display: none;
  }
  .results-box.visible { display: block; }

  .result-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 7px 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--c2);
    transition: background 0.1s;
    gap: 8px;
  }
  .result-item:last-child { border-bottom: none; }
  .result-item:hover { background: var(--c2); }
  .result-item .zone-id {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    flex-shrink: 0;
    max-width: 160px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .result-item .zone-name {
    flex: 1;
    color: var(--text);
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .result-item .zone-meta {
    font-size: 11px;
    color: var(--text-dim);
    font-family: var(--mono);
    flex-shrink: 0;
  }
  .result-item .add-btn {
    font-size: 16px;
    color: var(--success);
    padding: 0 4px;
    flex-shrink: 0;
  }

  /* ── Active zones ── */
  .zones-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 40px;
  }
  .zone-tag {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--c2);
    border: 1px solid var(--c3);
    border-radius: var(--radius);
    padding: 7px 12px;
    gap: 8px;
    animation: slideIn 0.15s ease;
  }
  @keyframes slideIn {
    from { opacity:0; transform: translateY(-4px); }
    to   { opacity:1; transform: translateY(0); }
  }
  .zone-tag .zt-id {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    flex-shrink: 0;
    max-width: 160px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .zone-tag .zt-name {
    flex: 1;
    font-size: 13px;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .zone-tag .zt-meta {
    font-size: 11px;
    color: var(--text-dim);
    font-family: var(--mono);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 3px;
  }
  .zt-type {
    font-size: 10px;
    font-family: var(--mono);
    padding: 1px 5px;
    border-radius: 20px;
    font-weight: 600;
  }
  .zt-type-public   { background: #1f3d2a; color: #56d364; }
  .zt-type-fire     { background: #3a2010; color: #ffa657; }
  .zt-type-county   { background: #162030; color: #79c0ff; }
  .zt-type-coastal  { background: #161e30; color: #a5d6ff; }
  .zt-type-offshore { background: #22163a; color: #d2a8ff; }
  .zone-tag .remove-btn {
    background: none;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    padding: 0 0 0 8px;
    transition: color 0.15s;
    flex-shrink: 0;
  }
  .zone-tag .remove-btn:hover { color: var(--danger); }

  .empty-hint {
    color: var(--text-dim);
    font-size: 12px;
    font-family: var(--mono);
    padding: 8px 4px;
    font-style: italic;
  }

  /* ── Severity checkboxes ── */
  .sev-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .sev-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: var(--c2);
    border: var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .sev-row:hover { border-color: var(--c4); }
  .sev-row input[type="checkbox"] {
    width: 15px; height: 15px;
    cursor: pointer;
    accent-color: var(--accent);
  }
  .sev-row .sev-label {
    font-family: var(--mono);
    font-size: 13px;
    flex: 1;
  }
  .sev-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .sev-Unknown  .sev-dot { background: #888; }
  .sev-Minor    .sev-dot { background: #60b8ff; }
  .sev-Moderate .sev-dot { background: var(--warn); }
  .sev-Severe   .sev-dot { background: #ff8040; }
  .sev-Extreme  .sev-dot { background: var(--danger); }

  /* ── Number inputs ── */
  .num-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 12px;
  }
  .num-row:last-child { margin-bottom: 0; }
  .num-row label {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--text-dim);
    letter-spacing: 0.5px;
  }
  .num-row input { width: 100%; }

  /* ── Log level ── */
  .log-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .log-row label {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--text-dim);
    letter-spacing: 0.5px;
  }
  select {
    cursor: pointer;
  }
  select option { background: var(--c2); }

  /* ── Save bar ── */
  .save-bar {
    position: sticky;
    bottom: 0;
    background: linear-gradient(to top, var(--c0) 70%, transparent);
    padding: 24px 0 0;
    margin-top: 28px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .btn-save {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.5px;
    padding: 10px 28px;
    cursor: pointer;
    transition: background 0.15s, transform 0.1s;
  }
  .btn-save:hover { background: #5db0ff; }
  .btn-save:active { transform: scale(0.97); }
  .btn-save:disabled { background: var(--c4); cursor: not-allowed; }

  #status-msg {
    font-family: var(--mono);
    font-size: 12px;
    transition: opacity 0.4s;
  }
  #status-msg.ok   { color: var(--success); }
  #status-msg.err  { color: var(--danger); }
  #status-msg.fade { opacity: 0; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--c4); border-radius: 3px; }

  .section-note {
    font-size: 11px;
    color: var(--text-dim);
    font-family: var(--mono);
    margin-top: 10px;
  }

  /* ── Status panel ── */
  .status-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-bottom: 12px;
  }
  @media (max-width: 680px) { .status-grid { grid-template-columns: 1fr 1fr; } }

  .stat-box {
    background: var(--c2);
    border: var(--border);
    border-radius: var(--radius);
    padding: 10px 14px;
  }
  .stat-label {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 4px;
  }
  .stat-value {
    font-family: var(--mono);
    font-size: 15px;
    font-weight: 600;
    color: var(--text-bright);
  }
  .stat-value.ok     { color: var(--success); }
  .stat-value.warn   { color: var(--warn); }
  .stat-value.danger { color: var(--danger); }
  .stat-value.dim    { color: var(--text-dim); font-weight: 400; font-size: 12px; }

  .alert-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 8px 12px;
    background: var(--c2);
    border: var(--border);
    border-radius: var(--radius);
    margin-bottom: 6px;
    font-size: 13px;
  }
  .alert-row:last-child { margin-bottom: 0; }
  .alert-event {
    font-family: var(--mono);
    font-size: 11px;
    flex-shrink: 0;
    padding: 2px 7px;
    border-radius: 20px;
    font-weight: 600;
  }
  .sev-Extreme  .alert-event { background: #3a1010; color: var(--danger); }
  .sev-Severe   .alert-event { background: #3a2010; color: #ff8040; }
  .sev-Moderate .alert-event { background: #2e2410; color: var(--warn); }
  .sev-Minor    .alert-event { background: #102030; color: #60b8ff; }
  .sev-Unknown  .alert-event { background: var(--c3); color: var(--text-dim); }
  .alert-headline {
    flex: 1;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .alert-ends {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    flex-shrink: 0;
  }

  /* ── Footer ── */
  footer {
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid var(--c2);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  footer a {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 11px;
    text-decoration: none;
    letter-spacing: 0.3px;
    transition: color 0.15s;
  }
  footer a:hover { color: var(--accent); }
  footer a svg { flex-shrink: 0; }
</style>
</head>
<body>
<div class="shell">
  <header>
    <h1><span>//</span> weatherhook</h1>
    <span class="header-sub">config editor</span>
  </header>

  <div class="grid">

    <!-- Bot status -->
    <div class="panel panel-full" id="status-panel">
      <div class="panel-header">
        <div class="dot" id="status-dot" style="background:var(--text-dim)"></div>
        <span class="label">Bot Status</span>
        <span style="margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--text-dim)" id="status-age"></span>
      </div>
      <div class="panel-body">
        <div class="status-grid">
          <div class="stat-box">
            <div class="stat-label">State</div>
            <div class="stat-value dim" id="stat-state">—</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Next Poll</div>
            <div class="stat-value" id="stat-next">—</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Tracking</div>
            <div class="stat-value" id="stat-tracking">—</div>
          </div>
        </div>
        <div id="alert-list"></div>
        <label class="sev-row" style="margin-top:12px;" id="status-api-row">
          <input type="checkbox" id="status-api" checked onchange="updateStatusApiNote()">
          <div class="sev-dot" style="background:var(--success)"></div>
          <span class="sev-label">Enable status API</span>
        </label>
        <p class="section-note" id="status-api-note">Bot writes status.json so the web UI can display live status.</p>
      </div>
    </div>

    <!-- Zone search -->
    <div class="panel panel-full">
      <div class="panel-header"><div class="dot"></div><span class="label">Zones</span></div>
      <div class="panel-body">
        <div class="search-row">
          <input type="text" id="zone-search" placeholder="Search by name, ID, or state…" autocomplete="off">
        </div>
        <div class="results-box" id="results-box"></div>
        <div style="margin-top:14px;">
          <div class="zones-list" id="zones-list"></div>
        </div>
        <p class="section-note">Click a result to add. At least one zone is required.</p>
      </div>
    </div>

    <!-- Severity -->
    <div class="panel">
      <div class="panel-header"><div class="dot" style="background:var(--warn)"></div><span class="label">Severity Filter</span></div>
      <div class="panel-body">
        <div class="sev-grid" id="sev-grid"></div>
        <p class="section-note">Uncheck all to receive every severity level.</p>
      </div>
    </div>

    <!-- Intervals + Log -->
    <div class="panel">
      <div class="panel-header"><div class="dot" style="background:var(--success)"></div><span class="label">Poll Intervals & Logging</span></div>
      <div class="panel-body">
        <div class="num-row">
          <label>NORMAL INTERVAL (seconds)</label>
          <input type="number" id="sleep-normal" min="30" step="10" value="300">
        </div>
        <div class="num-row">
          <label>URGENT INTERVAL (seconds)</label>
          <input type="number" id="sleep-urgent" min="10" step="5" value="60">
        </div>
        <div class="log-row" style="margin-top:14px;">
          <label>LOG LEVEL</label>
          <select id="log-level">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING" selected>WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
      </div>
    </div>

  </div>

  <div class="save-bar">
    <button class="btn-save" id="save-btn" onclick="saveConfig()">Save config.yaml</button>
    <span id="status-msg"></span>
  </div>
</div>

<script>
// ── Data injected from server ──
const ALL_ZONES = __ZONES_JSON__;
const SEVERITIES = ["Unknown","Minor","Moderate","Severe","Extreme"];

// Map from primary ID -> group, and from any member ID -> group
const zoneMap = {};
ALL_ZONES.forEach(g => zoneMap[g.id] = g);

// ── State ──
// activeZones holds group primary IDs (g.id), not raw zone IDs
let activeZones = __ACTIVE_ZONES_JSON__;
let activeSev   = __ACTIVE_SEV_JSON__;

const TYPE_SHORT = {public:'pub', fire:'fire', county:'county', coastal:'coastal', offshore:'offshore'};

// ── Render active zones ──
function renderZones() {
  const list = document.getElementById('zones-list');
  list.innerHTML = '';
  if (activeZones.length === 0) {
    list.innerHTML = '<div class="empty-hint">No zones added yet.</div>';
    return;
  }
  activeZones.forEach(primaryId => {
    const g = zoneMap[primaryId] || { id: primaryId, name: primaryId, state: '', types: [] };
    const tag = document.createElement('div');
    tag.className = 'zone-tag';
    const idStr   = g.id;
    const typeStr = g.types.map(t => `<span class="zt-type zt-type-${t}">${TYPE_SHORT[t] || t}</span>`).join('');
    tag.innerHTML = `
      <span class="zt-id">${idStr}</span>
      <span class="zt-name">${g.name}</span>
      <span class="zt-meta">${g.state}&thinsp;${typeStr}</span>
      <button class="remove-btn" title="Remove" onclick="removeZone('${g.id}')">×</button>
    `;
    list.appendChild(tag);
  });
}

function addZone(primaryId) {
  if (!activeZones.includes(primaryId)) {
    activeZones.push(primaryId);
    renderZones();
  }
  document.getElementById('zone-search').value = '';
  document.getElementById('results-box').classList.remove('visible');
  document.getElementById('results-box').innerHTML = '';
}

function removeZone(primaryId) {
  activeZones = activeZones.filter(z => z !== primaryId);
  renderZones();
}

// ── Zone search ──
const searchInput = document.getElementById('zone-search');
const resultsBox  = document.getElementById('results-box');

searchInput.addEventListener('input', () => {
  const q = searchInput.value.trim().toLowerCase();
  if (q.length < 1) {
    resultsBox.classList.remove('visible');
    resultsBox.innerHTML = '';
    return;
  }
  const matches = ALL_ZONES.filter(g =>
    g.id.toLowerCase().startsWith(q) ||
    g.name.toLowerCase().includes(q) ||
    g.state.toLowerCase() === q
  ).slice(0, 60);

  if (matches.length === 0) {
    resultsBox.innerHTML = '<div class="result-item"><span class="zone-name" style="color:var(--text-dim);font-style:italic">No results</span></div>';
  } else {
    resultsBox.innerHTML = matches.map(g => {
      const idStr   = g.id;
      const typeStr = g.types.map(t => `<span class="zt-type zt-type-${t}">${TYPE_SHORT[t] || t}</span>`).join('');
      return `
        <div class="result-item" onclick="addZone('${g.id}')">
          <span class="zone-id">${idStr}</span>
          <span class="zone-name">${g.name}</span>
          <span class="zone-meta">${g.state}&thinsp;${typeStr}</span>
          <span class="add-btn">+</span>
        </div>
      `;
    }).join('');
  }
  resultsBox.classList.add('visible');
});

document.addEventListener('click', e => {
  if (!e.target.closest('#zone-search') && !e.target.closest('#results-box')) {
    resultsBox.classList.remove('visible');
  }
});

// ── Severity checkboxes ──
function renderSev() {
  const grid = document.getElementById('sev-grid');
  grid.innerHTML = '';
  SEVERITIES.forEach(s => {
    const checked = activeSev.includes(s) ? 'checked' : '';
    const row = document.createElement('label');
    row.className = `sev-row sev-${s}`;
    row.innerHTML = `
      <input type="checkbox" value="${s}" ${checked} onchange="toggleSev('${s}', this.checked)">
      <div class="sev-dot"></div>
      <span class="sev-label">${s}</span>
    `;
    grid.appendChild(row);
  });
}

function toggleSev(s, on) {
  if (on && !activeSev.includes(s)) activeSev.push(s);
  if (!on) activeSev = activeSev.filter(x => x !== s);
}

function updateStatusApiNote() {
  const on = document.getElementById('status-api').checked;
  document.getElementById('status-api-note').textContent = on
    ? 'Bot writes status.json so the web UI can display live status.'
    : 'Status API disabled — bot will not write status.json.';
}

// ── Save ──
async function saveConfig() {
  const btn = document.getElementById('save-btn');
  const msg = document.getElementById('status-msg');
  btn.disabled = true;
  msg.textContent = '';
  msg.className = '';

  const payload = {
    zones:        activeZones,
    severity:     activeSev,
    log_level:    document.getElementById('log-level').value,
    sleep_normal:  parseFloat(document.getElementById('sleep-normal').value),
    sleep_urgent:  parseFloat(document.getElementById('sleep-urgent').value),
    status_api:    document.getElementById('status-api').checked,
  };

  try {
    const r = await fetch('/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await r.json();
    if (r.ok) {
      msg.textContent = '✓ Saved successfully';
      msg.className = 'ok';
    } else {
      msg.textContent = '✗ ' + (data.error || 'Save failed');
      msg.className = 'err';
    }
  } catch(e) {
    msg.textContent = '✗ Network error';
    msg.className = 'err';
  }

  btn.disabled = false;
  setTimeout(() => { msg.classList.add('fade'); }, 2800);
  setTimeout(() => { msg.textContent = ''; msg.className = ''; }, 3400);
}

// ── Bot status ──
let statusData = null;
let countdownTimer = null;

function fmtCountdown(secondsLeft) {
  if (secondsLeft <= 0) return 'now';
  const m = Math.floor(secondsLeft / 60);
  const s = Math.floor(secondsLeft % 60);
  return m > 0 ? `${m}m ${s.toString().padStart(2,'0')}s` : `${s}s`;
}


function fmtEnds(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return 'until ' + d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
}

function renderStatus(d) {
  const dot        = document.getElementById('status-dot');
  const statState  = document.getElementById('stat-state');
  const statNext   = document.getElementById('stat-next');
  const statTrack  = document.getElementById('stat-tracking');
  const alertList  = document.getElementById('alert-list');
  const ageEl      = document.getElementById('status-age');

  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }

  if (!d || !d.running) {
    dot.style.background = 'var(--text-dim)';
    statState.textContent = d ? 'offline' : '—';
    statState.className = 'stat-value dim';
    statNext.textContent = '—';
    statNext.className = 'stat-value dim';
    statTrack.textContent = '—';
    statTrack.className = 'stat-value dim';
    alertList.innerHTML = '';
    ageEl.textContent = '';
    return;
  }

  // State + dot color
  const stateColors = {normal: 'var(--success)', urgent: 'var(--danger)', error: 'var(--warn)'};
  dot.style.background = stateColors[d.poll_status] || 'var(--text-dim)';
  statState.textContent = d.poll_status;
  statState.className = 'stat-value ' + (d.poll_status === 'normal' ? 'ok' : d.poll_status === 'urgent' ? 'danger' : 'warn');

  // Age label
  if (d.as_of) {
    const ageSec = Math.round(Date.now() / 1000 - d.as_of);
    ageEl.textContent = `updated ${ageSec}s ago`;
  }

  // Tracking count
  const count = (d.tracked || []).length;
  statTrack.textContent = count === 0 ? 'none' : `${count} alert${count !== 1 ? 's' : ''}`;
  statTrack.className = 'stat-value ' + (count > 0 ? (d.poll_status === 'urgent' ? 'danger' : 'warn') : 'ok');

  // Live countdown
  let earlyRefreshScheduled = false;
  function tickCountdown() {
    if (!d.next_poll) { statNext.textContent = '—'; return; }
    const left = d.next_poll - Date.now() / 1000;
    statNext.textContent = left > 0 ? fmtCountdown(left) : 'polling…';
    statNext.className = 'stat-value ' + (left < 15 ? 'warn' : '');
    if (left <= 0 && !earlyRefreshScheduled) {
      earlyRefreshScheduled = true;
      setTimeout(fetchStatus, 1000);
    }
  }
  tickCountdown();
  countdownTimer = setInterval(tickCountdown, 1000);

  // Alert list
  alertList.innerHTML = '';
  if (d.tracked && d.tracked.length > 0) {
    d.tracked.forEach(alert => {
      const row = document.createElement('div');
      row.className = `alert-row sev-${alert.severity || 'Unknown'}`;
      row.innerHTML = `
        <span class="alert-event">${escHtml(alert.event || '—')}</span>
        <span class="alert-headline">${escHtml(alert.headline || '—')}</span>
        <span class="alert-ends">${fmtEnds(alert.ends)}</span>
      `;
      alertList.appendChild(row);
    });
  }
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function fetchStatus() {
  try {
    const r = await fetch('/status');
    if (r.ok) {
      statusData = await r.json();
      renderStatus(statusData);
    }
  } catch(_) { /* webui server is the same process; ignore transient errors */ }
}

// Poll every 15 seconds; also refresh age label every second
fetchStatus();
setInterval(fetchStatus, 15000);
setInterval(() => {
  if (!statusData || !statusData.as_of) return;
  const el = document.getElementById('status-age');
  if (el) el.textContent = `updated ${Math.round(Date.now()/1000 - statusData.as_of)}s ago`;
}, 1000);

// ── Init ──
renderZones();
renderSev();
document.getElementById('sleep-normal').value = __SLEEP_NORMAL__;
document.getElementById('sleep-urgent').value = __SLEEP_URGENT__;
document.getElementById('log-level').value    = '__LOG_LEVEL__';
document.getElementById('status-api').checked = __STATUS_API__;
updateStatusApiNote();
</script>

  <footer>
    <a href="https://github.com/whiskishivers/weatherhook" target="_blank" rel="noopener">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
      </svg>
      whiskishivers/weatherhook
    </a>
  </footer>

</body>
</html>
"""


# ─── HTTP Server ─────────────────────────────────────────────────────────────

def build_html(cfg: dict) -> str:
    zones_list   = cfg.get("zones", []) or []
    severity     = cfg.get("severity", []) or []
    sleep_normal = cfg.get("sleep_interval", {}).get("normal", 300.0)
    sleep_urgent = cfg.get("sleep_interval", {}).get("urgent", 60.0)
    log_level    = cfg.get("log_level", "WARNING")
    status_api   = bool(cfg.get("status_api", True))

    # Resolve each saved zone ID to its group's primary ID, deduplicated
    seen = set()
    active_group_ids = []
    for id_ in zones_list:
        group = _ID_TO_GROUP.get(id_)
        primary = group["id"] if group else id_
        if primary not in seen:
            seen.add(primary)
            active_group_ids.append(primary)

    html = HTML
    html = html.replace("__ZONES_JSON__",        json.dumps(ALL_ZONES))
    html = html.replace("__ACTIVE_ZONES_JSON__",  json.dumps(active_group_ids))
    html = html.replace("__ACTIVE_SEV_JSON__",   json.dumps(severity))
    html = html.replace("__SLEEP_NORMAL__",      str(sleep_normal))
    html = html.replace("__SLEEP_URGENT__",      str(sleep_urgent))
    html = html.replace("'__LOG_LEVEL__'",       json.dumps(str(log_level)))
    html = html.replace("__STATUS_API__",         "true" if status_api else "false")
    return html


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress default access log spam

    def _send(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            data = read_status()
            body = json.dumps(data).encode()
            self._send(200, "application/json", body)
            return
        cfg  = read_config()
        html = build_html(cfg)
        self._send(200, "text/html; charset=utf-8", html.encode())

    def do_POST(self):
        if self.path != "/save":
            self._send(404, "text/plain", b"Not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            resp = json.dumps({"error": f"Bad JSON: {e}"}).encode()
            self._send(400, "application/json", resp)
            return

        try:
            cfg = {
                "zones":      data.get("zones", []),
                "severity":   data.get("severity", []) or None,
                "log_level":  str(data.get("log_level", "WARNING")),
                "sleep_interval": {
                    "normal": float(data.get("sleep_normal", 300.0)),
                    "urgent": float(data.get("sleep_urgent", 60.0)),
                },
                "status_api": bool(data.get("status_api", True)),
            }
            write_config(cfg)
            resp = json.dumps({"ok": True}).encode()
            self._send(200, "application/json", resp)
        except Exception as e:
            resp = json.dumps({"error": str(e)}).encode()
            self._send(500, "application/json", resp)


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST, PORT = "127.0.0.1", 5001
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Weatherhook Config UI")
    print(f"  → http://{HOST}:{PORT}")
    print(f"  Config : {CONFIG_PATH}")
    print(f"  Zones  : {len(ALL_ZONES):,} groups loaded (merged fire/public duplicates)")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")