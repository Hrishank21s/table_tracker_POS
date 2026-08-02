/* Customer directory: membership and NFC management. */
document.addEventListener("DOMContentLoaded", () => {
  if (!initStaffShell()) return;
  document.getElementById("customer-form").addEventListener("submit", addCustomer);
  loadCustomers();
});

async function loadCustomers() {
  const message = document.getElementById("list-msg");
  const body = document.getElementById("customers-body");
  try {
    const data = await API.getCustomers();
    if (!data.customers.length) {
      body.innerHTML = '<tr><td colspan="5" class="muted">No customers yet.</td></tr>';
      return;
    }

    body.innerHTML = data.customers
      .map(
        (customer) => `
      <tr>
        <td>${customer.name}</td>
        <td>${customer.phone}</td>
        <td>${customer.is_member ? '<b class="lime">Member</b>' : "Guest"}</td>
        <td><input id="nfc-${customer.id}" type="text" value="${customer.nfc_uid || ""}" /></td>
        <td>
          <div class="actions">
            <button class="btn sm" data-toggle="${customer.id}">Toggle member</button>
            <button class="btn sm dark" data-nfc="${customer.id}">Save NFC</button>
            <button class="btn sm danger admin-only" data-delete="${customer.id}">Delete</button>
          </div>
        </td>
      </tr>`
      )
      .join("");

    body.querySelectorAll("[data-toggle]").forEach((button) =>
      button.addEventListener("click", () =>
        runAction(() => API.toggleMember(Number(button.dataset.toggle)), "Membership updated.")
      )
    );
    body.querySelectorAll("[data-nfc]").forEach((button) =>
      button.addEventListener("click", () => {
        const id = Number(button.dataset.nfc);
        const value = document.getElementById(`nfc-${id}`).value.trim();
        runAction(() => API.setNfc(id, value), "NFC UID saved.");
      })
    );
    body.querySelectorAll("[data-delete]").forEach((button) =>
      button.addEventListener("click", () =>
        runAction(() => API.deleteCustomer(Number(button.dataset.delete)), "Customer removed.")
      )
    );

    lockForStaff(body);
    showMessage(message, "", "info");
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}

async function runAction(action, successText) {
  const message = document.getElementById("list-msg");
  try {
    await action();
    showMessage(message, successText, "success");
    loadCustomers();
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}

async function addCustomer(event) {
  event.preventDefault();
  const message = document.getElementById("customer-msg");
  const name = document.getElementById("cust-name").value.trim();
  const phone = document.getElementById("cust-phone").value.trim();
  const nfc = document.getElementById("cust-nfc").value.trim();

  if (!name) {
    showMessage(message, "Name is required.", "error");
    return;
  }
  if (!/^[0-9]{10,}$/.test(phone)) {
    showMessage(message, "Phone must be at least 10 digits.", "error");
    return;
  }

  try {
    await API.addCustomer({
      name,
      phone,
      nfc_uid: nfc,
      is_member: document.getElementById("cust-member").checked,
    });
    showMessage(message, "Customer added.", "success");
    document.getElementById("customer-form").reset();
    loadCustomers();
  } catch (error) {
    showMessage(message, error.message, "error");
  }
}
