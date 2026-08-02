/* Club setup: tables, floors, hourly rates and user accounts. */
document.addEventListener("DOMContentLoaded", () => {
  if (!initStaffShell()) return;

  document.getElementById("table-form").addEventListener("submit", addTable);
  document.getElementById("user-form").addEventListener("submit", addUser);

  if (!Auth.isAdmin()) {
    showMessage(
      document.getElementById("role-msg"),
      "Staff role: rates and user management are read-only.",
      "info"
    );
    document.getElementById("users-section").classList.add("hidden");
  }

  lockForStaff();
  loadTables();
  loadUsers();
});

async function loadTables() {
  const message = document.getElementById("tables-msg");
  const body = document.getElementById("tables-body");
  try {
    const data = await API.settingsTables();
    body.innerHTML = data.tables
      .map(
        (table) => `
      <tr>
        <td>${String(table.table_no).padStart(2, "0")}</td>
        <td>
          <select id="floor-${table.id}" class="admin-only">
            ${[1, 2, 3]
              .map(
                (floor) =>
                  `<option value="${floor}" ${floor === table.floor ? "selected" : ""}>${floor}</option>`
              )
              .join("")}
          </select>
        </td>
        <td>
          <input id="rate-${table.id}" class="admin-only" type="number" min="0.5" step="0.5"
            value="${table.current_rate}" />
        </td>
        <td><span class="tag ${table.status}">${table.status}</span></td>
        <td>
          <div class="actions">
            <button class="btn sm admin-only" data-save="${table.id}">Save</button>
            <button class="btn sm danger admin-only" data-remove="${table.id}">Remove</button>
          </div>
        </td>
      </tr>`
      )
      .join("");

    body.querySelectorAll("[data-save]").forEach((button) =>
      button.addEventListener("click", async () => {
        const id = Number(button.dataset.save);
        const floor = Number(document.getElementById(`floor-${id}`).value);
        const rate = parseFloat(document.getElementById(`rate-${id}`).value);
        if (!Number.isFinite(rate) || rate <= 0) {
          showMessage(message, "Rate must be greater than zero.", "error");
          return;
        }
        try {
          await API.updateTable(id, { floor, current_rate: rate });
          showMessage(message, "Table updated.", "success");
          loadTables();
        } catch (error) {
          showMessage(message, error.message, "error");
        }
      })
    );

    body.querySelectorAll("[data-remove]").forEach((button) =>
      button.addEventListener("click", async () => {
        try {
          await API.deleteTable(Number(button.dataset.remove));
          showMessage(message, "Table removed.", "success");
          loadTables();
        } catch (error) {
          showMessage(message, error.message, "error");
        }
      })
    );

    lockForStaff(body);
    showMessage(message, "", "info");
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}

async function addTable(event) {
  event.preventDefault();
  const message = document.getElementById("tables-msg");
  if (!Auth.isAdmin()) {
    showMessage(message, "Only admins can add tables.", "error");
    return;
  }

  const tableNo = parseInt(document.getElementById("new-table-no").value, 10);
  const floor = Number(document.getElementById("new-table-floor").value);
  const rate = parseFloat(document.getElementById("new-table-rate").value);

  if (!Number.isInteger(tableNo) || tableNo < 1) {
    showMessage(message, "Enter a valid table number.", "error");
    return;
  }
  if (!Number.isFinite(rate) || rate <= 0) {
    showMessage(message, "Rate must be greater than zero.", "error");
    return;
  }

  try {
    await API.addTable({ table_no: tableNo, floor, current_rate: rate });
    showMessage(message, "Table added.", "success");
    document.getElementById("table-form").reset();
    loadTables();
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}

async function loadUsers() {
  if (!Auth.isAdmin()) return;
  const message = document.getElementById("users-msg");
  const body = document.getElementById("users-body");
  try {
    const data = await API.getUsers();
    body.innerHTML = data.users
      .map(
        (user) => `
      <tr>
        <td>${user.username}</td>
        <td>${user.role === "admin" ? '<b class="lime">admin</b>' : "staff"}</td>
        <td><button class="btn sm danger" data-user="${user.id}">Remove</button></td>
      </tr>`
      )
      .join("");

    body.querySelectorAll("[data-user]").forEach((button) =>
      button.addEventListener("click", async () => {
        try {
          await API.deleteUser(Number(button.dataset.user));
          showMessage(message, "User removed.", "success");
          loadUsers();
        } catch (error) {
          showMessage(message, error.message, "error");
        }
      })
    );
    showMessage(message, "", "info");
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}

async function addUser(event) {
  event.preventDefault();
  const message = document.getElementById("users-msg");
  if (!Auth.isAdmin()) {
    showMessage(message, "Only admins can add users.", "error");
    return;
  }

  const username = document.getElementById("new-username").value.trim();
  const password = document.getElementById("new-password").value;
  const role = document.getElementById("new-role").value;

  if (!username) {
    showMessage(message, "Username is required.", "error");
    return;
  }
  if (password.length < 4) {
    showMessage(message, "Password must be at least 4 characters.", "error");
    return;
  }

  try {
    await API.addUser({ username, password, role });
    showMessage(message, "User added.", "success");
    document.getElementById("user-form").reset();
    loadUsers();
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}
