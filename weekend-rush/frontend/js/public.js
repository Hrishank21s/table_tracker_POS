/* Public club page: live floor, live booking dashboard and booking requests. */
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

const FOOTER_TEXT = {
  idle: "Ready now &middot; Book below",
  running: "Playing now",
  paused: "On a break",
  booked: "Reserved tonight",
};

let clockOffsetMs = 0;
let selectedTableId = null;
const liveTables = new Map();

document.addEventListener("DOMContentLoaded", () => {
  startWallClock("wall-clock");
  startWallClock("dash-clock");
  document.getElementById("booking-form").addEventListener("submit", submitBooking);
  loadBoard();
  setInterval(loadBoard, 10000);
  setInterval(tickClocks, 1000);
});

function tableName(table) {
  return TABLE_NAMES[(table.table_no - 1) % TABLE_NAMES.length];
}

async function loadBoard() {
  const banner = document.getElementById("board-msg");
  try {
    const data = await API.getTables();
    clockOffsetMs = new Date(data.server_time).getTime() - Date.now();
    render(data.floors || {});
    showMessage(banner, "", "info");
  } catch (error) {
    showMessage(banner, error.message, "error");
  }
}

function render(floors) {
  const rows = Object.keys(floors)
    .sort()
    .flatMap((floor) => floors[floor]);

  liveTables.clear();
  rows.forEach((table) =>
    liveTables.set(table.id, {
      accumulated: table.accumulated_seconds,
      activeStart: table.active_start ? new Date(table.active_start).getTime() : null,
    })
  );

  document.getElementById("tableList").innerHTML = rows
    .map(
      (table) => `
      <article class="card">
        <span class="tag ${table.status}">${table.status}</span>
        <span class="num">TABLE ${String(table.table_no).padStart(2, "0")} &middot; FLOOR ${table.floor}</span>
        <h3>${tableName(table)}</h3>
        <p>Professional table &middot; ${formatINR(table.current_rate)} per hour</p>
        <p class="live" id="pclock-${table.id}">00:00:00</p>
        <footer>${FOOTER_TEXT[table.status] || table.status}</footer>
      </article>`
    )
    .join("");

  document.getElementById("floor").innerHTML = rows
    .map(
      (table) => `
      <div>
        <span>T-${String(table.table_no).padStart(2, "0")}</span>
        <b class="${table.status === "idle" ? "lime" : ""}">${table.status}</b>
        <time id="fclock-${table.id}">00:00:00</time>
      </div>`
    )
    .join("");

  renderPicker(rows);

  const live = rows.filter((table) => table.status === "running").length;
  const booked = rows.filter((table) => table.status === "booked").length;
  const free = rows.filter((table) => table.status === "idle").length;
  document.getElementById("stat-tables").textContent = rows.length;
  document.getElementById("stat-live").textContent = live;
  document.getElementById("stat-free").textContent = free;
  document.getElementById("metric-live").textContent = live;
  document.getElementById("metric-booked").textContent = booked;

  tickClocks();
}

function renderPicker(rows) {
  const picker = document.getElementById("table-pick");
  const bookable = rows.filter((table) => table.status !== "running");

  if (bookable.length === 0) {
    picker.innerHTML =
      '<p class="formmsg">Every table is in play right now &mdash; check back shortly.</p>';
    selectedTableId = null;
    return;
  }
  if (!bookable.some((table) => table.id === selectedTableId)) {
    selectedTableId = bookable[0].id;
  }

  picker.innerHTML = bookable
    .map(
      (table) => `
      <button type="button" data-table="${table.id}"
        class="${table.id === selectedTableId ? "on" : ""}">
        ${tableName(table)}<br /><small>Table ${String(table.table_no).padStart(2, "0")} &middot; Floor ${table.floor}</small>
      </button>`
    )
    .join("");

  picker.querySelectorAll("button[data-table]").forEach((button) =>
    button.addEventListener("click", () => {
      selectedTableId = Number(button.dataset.table);
      picker
        .querySelectorAll("button[data-table]")
        .forEach((other) => other.classList.remove("on"));
      button.classList.add("on");
    })
  );
}

function tickClocks() {
  let total = 0;
  liveTables.forEach((state, tableId) => {
    let seconds = state.accumulated;
    if (state.activeStart) {
      seconds += Math.max(0, (Date.now() + clockOffsetMs - state.activeStart) / 1000);
    }
    total += seconds;
    const text = formatClock(seconds);
    const card = document.getElementById(`pclock-${tableId}`);
    if (card) card.textContent = text;
    const cell = document.getElementById(`fclock-${tableId}`);
    if (cell) cell.textContent = text;
  });
  const metric = document.getElementById("metric-clock");
  if (metric) metric.textContent = formatClock(total);
}

function showToast(text) {
  const toast = document.getElementById("toast");
  toast.textContent = text;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 5000);
}

async function submitBooking(event) {
  event.preventDefault();
  const message = document.getElementById("booking-msg");
  const name = document.getElementById("booking-name").value.trim();
  const slot = document.getElementById("booking-slot").value;
  const advance = parseFloat(document.getElementById("booking-advance").value);
  const utr = document.getElementById("booking-utr").value.trim();

  if (!name) {
    showMessage(message, "Please enter the name for the booking.", "error");
    return;
  }
  if (!selectedTableId) {
    showMessage(message, "Please select a table.", "error");
    return;
  }
  if (!Number.isFinite(advance) || advance <= 0) {
    showMessage(message, "Advance amount must be greater than 0.", "error");
    return;
  }
  if (!/^[a-zA-Z0-9]{12}$/.test(utr)) {
    showMessage(message, "UPI UTR must be exactly 12 alphanumeric characters.", "error");
    return;
  }

  try {
    const result = await API.requestBooking({
      customer_name: `${name} (${slot})`,
      table_id: selectedTableId,
      advance_amount: advance,
      upi_utr: utr,
    });
    showMessage(
      message,
      `Booking received \u00b7 advance ${formatINR(result.booking.advance_amount)} ` +
        `\u00b7 status ${result.booking.status}. The floor manager will confirm your slot.`,
      "success"
    );
    showToast(`\u2713 Table held for you at ${slot}`);
    document.getElementById("booking-form").reset();
    loadBoard();
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}
