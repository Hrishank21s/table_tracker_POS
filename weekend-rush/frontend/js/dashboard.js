/* Floor dashboard: live table clocks and inline session controls. */
const TABLE_NAMES = [
  "The Royal",
  "The Cue",
  "Black Ball",
  "The Century",
  "Side Pocket",
  "The Green",
  "The Break",
  "Corner Pocket",
  "The Baize",
];

let activeFloor = "1";
let tablesByFloor = {};
let clockOffsetMs = 0;
const liveState = new Map();
const frozenCards = new Set();
const openSplits = new Set();

document.addEventListener("DOMContentLoaded", () => {
  if (!initStaffShell()) return;

  document.querySelectorAll("[data-floor]").forEach((button) => {
    button.addEventListener("click", () => {
      activeFloor = button.dataset.floor;
      updateTabs();
      renderFloor();
    });
  });

  updateTabs();
  loadTables();
  setInterval(loadTables, 10000);
  setInterval(tickClocks, 1000);
});

function tableName(table) {
  return TABLE_NAMES[(table.table_no - 1) % TABLE_NAMES.length];
}

function updateTabs() {
  document.querySelectorAll("[data-floor]").forEach((button) => {
    button.classList.toggle("on", button.dataset.floor === activeFloor);
  });
}

async function loadTables() {
  const banner = document.getElementById("global-msg");
  try {
    const data = await API.getTables();
    clockOffsetMs = new Date(data.server_time).getTime() - Date.now();
    tablesByFloor = data.floors || {};
    updateMetrics();
    showMessage(banner, "", "info");
    if (frozenCards.size === 0 && openSplits.size === 0) renderFloor();
  } catch (error) {
    showMessage(banner, error.message, "error");
  }
}

function allTables() {
  return Object.keys(tablesByFloor).flatMap((floor) => tablesByFloor[floor]);
}

function updateMetrics() {
  const rows = allTables();
  document.getElementById("metric-live").textContent = rows.filter(
    (table) => table.status === "running"
  ).length;
  document.getElementById("metric-booked").textContent = rows.filter(
    (table) => table.status === "booked"
  ).length;
}

function tickClocks() {
  let total = 0;
  allTables().forEach((table) => {
    const state = liveState.get(table.id) || {
      accumulated: table.accumulated_seconds,
      activeStart: table.active_start ? new Date(table.active_start).getTime() : null,
    };
    let seconds = state.accumulated;
    if (state.activeStart) {
      seconds += Math.max(0, (Date.now() + clockOffsetMs - state.activeStart) / 1000);
    }
    total += seconds;
    const element = document.getElementById(`clock-${table.id}`);
    if (element) element.textContent = formatClock(seconds);
  });
  const metric = document.getElementById("metric-clock");
  if (metric) metric.textContent = formatClock(total);
}

function renderFloor() {
  const grid = document.getElementById("tables-grid");
  const tables = tablesByFloor[activeFloor] || [];
  liveState.clear();

  if (tables.length === 0) {
    grid.innerHTML = '<p class="formmsg">No tables configured on this floor yet.</p>';
    return;
  }

  grid.innerHTML = tables.map(cardMarkup).join("");

  tables.forEach((table) => {
    liveState.set(table.id, {
      accumulated: table.accumulated_seconds,
      activeStart: table.active_start ? new Date(table.active_start).getTime() : null,
    });
    wireCard(table);
  });
  tickClocks();
}

function cardMarkup(table) {
  const running = table.status === "running";
  const paused = table.status === "paused";
  return `
  <article class="tcard" id="card-${table.id}">
    <span class="tag ${table.status}" id="status-${table.id}">${table.status}</span>
    <span class="num">TABLE ${String(table.table_no).padStart(2, "0")} &middot; FLOOR ${table.floor}</span>
    <h3>${tableName(table)}</h3>
    <p class="muted">${formatINR(table.current_rate)} per hour</p>
    <p class="clock" id="clock-${table.id}">00:00:00</p>
    <div class="controls">
      <button class="btn sm" data-action="play" data-id="${table.id}" ${running ? "disabled" : ""}>Play</button>
      <button class="btn sm warn" data-action="pause" data-id="${table.id}" ${running ? "" : "disabled"}>Pause</button>
      <button class="btn sm danger" data-action="stop" data-id="${table.id}" ${
    running || paused ? "" : "disabled"
  }>Stop</button>
    </div>
    <div class="split hidden" id="split-${table.id}">
      <label for="split-input-${table.id}">Ways to split?</label>
      <div class="row">
        <input id="split-input-${table.id}" type="number" min="1" value="1" />
        <button class="btn sm danger" data-action="confirm-stop" data-id="${table.id}">Confirm stop</button>
        <button class="btn sm dark" data-action="cancel-stop" data-id="${table.id}">Cancel</button>
      </div>
    </div>
    <p class="formmsg" id="msg-${table.id}"></p>
  </article>`;
}

function wireCard(table) {
  const card = document.getElementById(`card-${table.id}`);
  if (!card) return;
  card.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => handleAction(button.dataset.action, table.id));
  });
}

async function handleAction(action, tableId) {
  const message = document.getElementById(`msg-${tableId}`);
  const splitBox = document.getElementById(`split-${tableId}`);

  if (action === "stop") {
    openSplits.add(tableId);
    splitBox.classList.remove("hidden");
    showMessage(message, "Enter how many ways to split, then confirm.", "info");
    return;
  }
  if (action === "cancel-stop") {
    openSplits.delete(tableId);
    splitBox.classList.add("hidden");
    showMessage(message, "", "info");
    return;
  }

  try {
    if (action === "play") {
      const result = await API.play(tableId);
      applyTable(result.table);
      showMessage(message, "Session running.", "success");
    } else if (action === "pause") {
      const result = await API.pause(tableId);
      applyTable(result.table);
      showMessage(message, "Session paused.", "success");
    } else if (action === "confirm-stop") {
      const input = document.getElementById(`split-input-${tableId}`);
      const splitWays = parseInt(input.value, 10);
      if (!Number.isInteger(splitWays) || splitWays < 1) {
        showMessage(message, "Split must be a whole number of at least 1.", "error");
        return;
      }

      const result = await API.stop(tableId, splitWays);
      openSplits.delete(tableId);
      splitBox.classList.add("hidden");
      applyTable(result.table);
      showMessage(
        message,
        `Total ${formatINR(result.total_amount)} \u00b7 ${result.split_ways} way(s) \u00b7 ` +
          `${formatINR(result.split_amount)} each`,
        "success"
      );
      frozenCards.add(tableId);
      setTimeout(() => {
        frozenCards.delete(tableId);
        showMessage(document.getElementById(`msg-${tableId}`), "", "info");
        loadTables();
      }, 10000);
    }
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}

function applyTable(table) {
  const floorTables = tablesByFloor[String(table.floor)] || [];
  const index = floorTables.findIndex((row) => row.id === table.id);
  if (index >= 0) floorTables[index] = table;

  liveState.set(table.id, {
    accumulated: table.accumulated_seconds,
    activeStart: table.active_start ? new Date(table.active_start).getTime() : null,
  });

  const badge = document.getElementById(`status-${table.id}`);
  if (badge) {
    badge.textContent = table.status;
    badge.className = `tag ${table.status}`;
  }
  const card = document.getElementById(`card-${table.id}`);
  if (card) {
    const running = table.status === "running";
    const paused = table.status === "paused";
    card.querySelector('[data-action="play"]').disabled = running;
    card.querySelector('[data-action="pause"]').disabled = !running;
    card.querySelector('[data-action="stop"]').disabled = !(running || paused);
  }
  updateMetrics();
  tickClocks();
}
