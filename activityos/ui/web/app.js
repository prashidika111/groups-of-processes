/**
 * ActivityOS Desktop UI Logic
 * Communicates with the Python backend via pywebview JS bridge.
 * Supports live metric updates, activity control, drill-down breakdown, and process selection.
 */

let state = {
  activities: [],
  selectedActivityId: null,
  system: { cpu_percent: 0, memory_percent: 0, memory_total_mb: 0, memory_used_mb: 0 },
  discoveredProcesses: [],
  selectedPids: new Set(),
  pollTimer: null,
};

// Safe bridge caller to talk to Python pywebview.api
async function callPy(method, ...args) {
  if (window.pywebview && window.pywebview.api && typeof window.pywebview.api[method] === 'function') {
    try {
      return await window.pywebview.api[method](...args);
    } catch (err) {
      console.error(`Error calling Python ${method}:`, err);
      return null;
    }
  } else {
    // If testing in standalone browser without pywebview backend
    console.warn(`pywebview.api.${method} not found. Running in mockup mode.`);
    return null;
  }
}

// Initialization
window.addEventListener('DOMContentLoaded', () => {
  // Wait briefly for pywebview bridge initialization
  window.addEventListener('pywebviewready', () => {
    initApp();
  });
  setTimeout(() => {
    initApp();
  }, 300);
});

let isInitialized = false;
function initApp() {
  if (isInitialized) return;
  isInitialized = true;

  refreshData();
  // Poll metrics every 1.5 seconds for live resource accounting
  state.pollTimer = setInterval(pollHeartbeat, 1500);
}

// Periodic polling
async function pollHeartbeat() {
  const data = await callPy('poll_heartbeat');
  if (!data) return;

  state.system = data.system || state.system;
  state.activities = data.activities || [];

  updateSystemRibbon();
  renderActivities();

  // If an activity is currently selected in drill-down, refresh its view
  if (state.selectedActivityId) {
    refreshDrillDown(state.selectedActivityId);
  }
}

async function refreshData() {
  await pollHeartbeat();
  if (state.activities.length > 0 && !state.selectedActivityId) {
    selectActivity(state.activities[0].activity_id);
  }
}

// System Ribbon Updates
function updateSystemRibbon() {
  const sys = state.system;
  document.getElementById('sysCpuVal').textContent = `${(sys.cpu_percent || 0).toFixed(1)}%`;
  document.getElementById('sysMemVal').textContent = `${(sys.memory_percent || 0).toFixed(1)}%`;
  document.getElementById('sysMemSub').textContent = `${(sys.memory_used_mb || 0).toFixed(0)} / ${(sys.memory_total_mb || 0).toFixed(0)} MB`;

  document.getElementById('actCountVal').textContent = state.activities.length;
  const activeCount = state.activities.filter(a => a.state === 'ACTIVE').length;
  document.getElementById('actActiveSub').textContent = `${activeCount} active session${activeCount === 1 ? '' : 's'}`;

  let totalActivePids = 0;
  state.activities.forEach(a => {
    if (a.state === 'ACTIVE' || a.state === 'PAUSED') {
      totalActivePids += (a.member_processes || []).length;
    }
  });
  document.getElementById('procCountVal').textContent = totalActivePids;
  document.getElementById('activitiesTotalLabel').textContent = `${state.activities.length} activit${state.activities.length === 1 ? 'y' : 'ies'}`;
}

// Render Activities List
function renderActivities() {
  const container = document.getElementById('activitiesList');
  if (state.activities.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📂</div>
        <p><strong>No activities created yet.</strong></p>
        <p style="font-size: 11.5px; margin-top: 4px;">Click <strong>+ Create Activity</strong> to group running processes or configure applications.</p>
      </div>`;
    return;
  }

  container.innerHTML = state.activities.map(act => {
    const isSelected = act.activity_id === state.selectedActivityId;
    const snap = act.resource_snapshot || { cpu_percent: 0, memory_mb: 0 };
    const pids = act.member_processes || [];
    const stateCls = act.state || 'STOPPED';

    // Format memory display
    let memDisplay = `${snap.memory_mb || 0} MB`;
    if (snap.memory_mb >= 1024) {
      memDisplay = `${(snap.memory_mb / 1024).toFixed(2)} GB`;
    }

    return `
      <div class="activity-card ${isSelected ? 'selected' : ''}" onclick="selectActivity('${act.activity_id}')">
        <div class="activity-card-header">
          <div class="activity-name">${escapeHtml(act.name)}</div>
          <span class="status-badge ${stateCls}">
            <span class="status-dot"></span>
            ${stateCls}
          </span>
        </div>

        <div class="activity-stats-row">
          <div class="stat-item">
            <span class="stat-label">CPU Total</span>
            <span class="stat-val">${(snap.cpu_percent || 0).toFixed(1)}%</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Memory Total</span>
            <span class="stat-val">${memDisplay}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Processes</span>
            <span class="stat-val">${pids.length} PIDs</span>
          </div>
        </div>

        <div class="activity-actions-row" onclick="event.stopPropagation()">
          <button class="btn btn-outline btn-sm" onclick="selectActivity('${act.activity_id}')">Inspect</button>
          
          ${act.state === 'STOPPED' ? `
            <button class="btn btn-primary btn-sm" onclick="startActivity('${act.activity_id}')">Start</button>
          ` : ''}

          ${act.state === 'ACTIVE' ? `
            <button class="btn btn-warning btn-sm" onclick="pauseActivity('${act.activity_id}')">Pause</button>
          ` : ''}

          ${act.state === 'PAUSED' ? `
            <button class="btn btn-success btn-sm" onclick="resumeActivity('${act.activity_id}')">Resume</button>
          ` : ''}

          ${act.state !== 'STOPPED' ? `
            <button class="btn btn-danger btn-sm" onclick="stopActivity('${act.activity_id}')">Stop</button>
          ` : ''}

          <button class="btn btn-outline btn-sm" style="margin-left: auto; color: var(--text-dim);" onclick="deleteActivity('${act.activity_id}')" title="Delete Activity">✕</button>
        </div>
      </div>
    `;
  }).join('');
}

// Select an Activity for Drill-Down
function selectActivity(activityId) {
  state.selectedActivityId = activityId;
  renderActivities();
  refreshDrillDown(activityId);
}

// Refresh Drill-Down View
async function refreshDrillDown(activityId) {
  const act = state.activities.find(a => a.activity_id === activityId);
  if (!act) return;

  const titleEl = document.getElementById('drilldownTitle');
  const badgeEl = document.getElementById('drilldownBadge');
  const contentEl = document.getElementById('drilldownContent');

  titleEl.textContent = `ACTIVITY: ${act.name.toUpperCase()}`;
  badgeEl.className = `status-badge ${act.state}`;
  badgeEl.innerHTML = `<span class="status-dot"></span>${act.state}`;
  badgeEl.style.display = 'inline-flex';

  const snap = act.resource_snapshot || { cpu_percent: 0, memory_mb: 0, contributing_processes: [] };
  const processes = snap.contributing_processes || [];
  const events = (act.event_log || []).slice(-8).reverse();

  let memDisplay = `${snap.memory_mb || 0} MB`;
  if (snap.memory_mb >= 1024) {
    memDisplay = `${(snap.memory_mb / 1024).toFixed(2)} GB`;
  }

  contentEl.innerHTML = `
    <div class="drilldown-view">
      
      <!-- Conceptual Contrast Box (University Methodology Core) -->
      <div class="comparison-box">
        <strong>ActivityOS Abstraction:</strong> Aggregating <strong>${processes.length}</strong> Linux processes into 
        <strong>${escapeHtml(act.name)}</strong> (${memDisplay}, ${(snap.cpu_percent || 0).toFixed(1)}% CPU). 
        Activity-level control translates directly to POSIX signals (<code>SIGSTOP</code> / <code>SIGCONT</code>) per process.
      </div>

      <!-- Process Breakdown Table -->
      <div>
        <div style="font-size: 11.5px; font-weight: 600; color: var(--text-dim); margin-bottom: 6px; text-transform: uppercase;">
          Contributing Linux Processes (${processes.length})
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>PID</th>
              <th>Process / Command</th>
              <th>CPU %</th>
              <th>Memory (RSS)</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${processes.length === 0 ? `
              <tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 14px;">No active processes associated with this activity. Click "Start" to launch configured applications.</td></tr>
            ` : processes.map(p => `
              <tr class="${p.is_alive ? '' : 'unavailable'}">
                <td class="mono" style="color: var(--accent-proposed); font-weight: 600;">${p.pid}</td>
                <td>
                  <span class="process-tag">${escapeHtml(p.name)}</span>
                  <span style="font-size: 11px; color: var(--text-dim); margin-left: 6px;" title="${escapeHtml(p.cmdline)}">
                    ${escapeHtml(p.cmdline ? (p.cmdline.length > 35 ? p.cmdline.substring(0, 35) + '...' : p.cmdline) : '')}
                  </span>
                </td>
                <td class="mono">${(p.cpu_percent || 0).toFixed(1)}%</td>
                <td class="mono">${p.memory_mb ? p.memory_mb.toFixed(1) + ' MB' : '0 MB'}</td>
                <td>
                  <span class="mono" style="font-size: 11px; color: ${p.status === 'stopped' ? 'var(--status-paused)' : (p.is_alive ? 'var(--status-active)' : 'var(--status-error)')}">
                    ${p.status}
                  </span>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>

      <!-- Activity Event History (Timeline Logger) -->
      <div style="margin-top: 10px;">
        <div style="font-size: 11.5px; font-weight: 600; color: var(--text-dim); margin-bottom: 6px; text-transform: uppercase;">
          Activity Timeline History (Audit Log)
        </div>
        <div class="timeline-list">
          ${events.length === 0 ? `
            <div style="color: var(--text-dim); font-size: 11.5px; padding: 6px;">No recorded events yet.</div>
          ` : events.map(e => `
            <div class="timeline-entry ${e.action}">
              <span class="timeline-time">${e.iso_time}</span>
              <span class="timeline-msg">
                <strong>[${e.action.toUpperCase()}]</strong> ${escapeHtml(e.details)}
              </span>
            </div>
          `).join('')}
        </div>
      </div>

    </div>
  `;
}

// Activity Control Engine Actions
async function startActivity(activityId) {
  const res = await callPy('start_activity', activityId);
  await pollHeartbeat();
}

async function pauseActivity(activityId) {
  const res = await callPy('pause_activity', activityId);
  await pollHeartbeat();
}

async function resumeActivity(activityId) {
  const res = await callPy('resume_activity', activityId);
  await pollHeartbeat();
}

async function stopActivity(activityId) {
  const res = await callPy('stop_activity', activityId);
  await pollHeartbeat();
}

async function deleteActivity(activityId) {
  if (confirm("Delete this activity definition?")) {
    await callPy('delete_activity', activityId);
    if (state.selectedActivityId === activityId) {
      state.selectedActivityId = null;
    }
    await pollHeartbeat();
  }
}

// Create Activity Modal
async function openCreateModal() {
  document.getElementById('newActName').value = '';
  document.getElementById('newActAppCommand').value = '';
  document.getElementById('procFilter').value = '';
  state.selectedPids.clear();
  updateSelectedPidsSummary();

  document.getElementById('createModal').style.display = 'flex';
  await fetchRunningProcesses();
}

function closeCreateModal() {
  document.getElementById('createModal').style.display = 'none';
}

async function fetchRunningProcesses() {
  const tbody = document.getElementById('processSelectTbody');
  tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 14px;">Scanning Linux process table...</td></tr>`;

  const procs = await callPy('get_available_processes', '');
  state.discoveredProcesses = procs || [];
  renderProcessSelectionTable();
}

function renderProcessSelectionTable() {
  const filter = (document.getElementById('procFilter').value || '').toLowerCase();
  const tbody = document.getElementById('processSelectTbody');

  const filtered = state.discoveredProcesses.filter(p => {
    if (!filter) return true;
    return p.name.toLowerCase().includes(filter) ||
           String(p.pid).includes(filter) ||
           (p.cmdline && p.cmdline.toLowerCase().includes(filter));
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 14px;">No matching processes found.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.slice(0, 100).map(p => {
    const isChecked = state.selectedPids.has(p.pid);
    return `
      <tr onclick="togglePid(${p.pid})">
        <td class="checkbox-col" onclick="event.stopPropagation()">
          <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="togglePid(${p.pid})">
        </td>
        <td class="mono" style="color: var(--accent-proposed); font-weight: 600;">${p.pid}</td>
        <td>
          <span class="process-tag">${escapeHtml(p.name)}</span>
          <span style="font-size: 11px; color: var(--text-dim); margin-left: 6px;">
            ${escapeHtml(p.cmdline ? (p.cmdline.length > 30 ? p.cmdline.substring(0, 30) + '...' : p.cmdline) : '')}
          </span>
        </td>
        <td class="mono">${p.memory_mb ? p.memory_mb.toFixed(1) + ' MB' : '0 MB'}</td>
        <td class="mono" style="font-size: 11px;">${p.status}</td>
      </tr>
    `;
  }).join('');
}

function togglePid(pid) {
  if (state.selectedPids.has(pid)) {
    state.selectedPids.delete(pid);
  } else {
    state.selectedPids.add(pid);
  }
  updateSelectedPidsSummary();
  renderProcessSelectionTable();
}

function toggleSelectAll(checkbox) {
  if (checkbox.checked) {
    state.discoveredProcesses.slice(0, 50).forEach(p => state.selectedPids.add(p.pid));
  } else {
    state.selectedPids.clear();
  }
  updateSelectedPidsSummary();
  renderProcessSelectionTable();
}

function updateSelectedPidsSummary() {
  const pidsArray = Array.from(state.selectedPids);
  const summaryEl = document.getElementById('selectedPidsSummary');
  if (pidsArray.length === 0) {
    summaryEl.textContent = 'None';
  } else {
    summaryEl.textContent = `${pidsArray.length} PIDs (${pidsArray.slice(0, 6).join(', ')}${pidsArray.length > 6 ? '...' : ''})`;
  }
}

async function submitCreateActivity() {
  const name = document.getElementById('newActName').value.trim();
  if (!name) {
    alert("Please enter an activity name (e.g. Study, Coding, Research).");
    return;
  }

  const pids = Array.from(state.selectedPids);
  const appCmd = document.getElementById('newActAppCommand').value.trim();
  const configuredApps = [];
  if (appCmd) {
    configuredApps.push({
      name: name,
      command: appCmd,
      args: []
    });
  }

  const newAct = await callPy('create_activity', name, pids, configuredApps);
  closeCreateModal();
  await pollHeartbeat();
  if (newAct && newAct.activity_id) {
    selectActivity(newAct.activity_id);
  }
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
