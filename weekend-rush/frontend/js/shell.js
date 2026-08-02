/* Shared staff-console shell: auth guard, header clock, identity and logout. */
function initStaffShell() {
  if (!Auth.guard("admin_login.html")) return false;
  const who = document.getElementById("current-user");
  if (who) who.textContent = `${Auth.username} \u00b7 ${Auth.role}`;
  startWallClock("wall-clock");
  const logout = document.getElementById("logout-btn");
  if (logout) {
    logout.addEventListener("click", () => {
      Auth.clear();
      window.location.href = "admin_login.html";
    });
  }
  return true;
}

function lockForStaff(root) {
  if (Auth.isAdmin()) return;
  (root || document).querySelectorAll(".admin-only").forEach((element) => {
    element.disabled = true;
    element.classList.add("locked");
  });
}
