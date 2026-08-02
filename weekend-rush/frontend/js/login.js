/* Staff login. */
document.addEventListener("DOMContentLoaded", () => {
  startWallClock("wall-clock");
  if (Auth.token) {
    window.location.href = "dashboard_floors.html";
    return;
  }

  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.getElementById("login-msg");
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;

    if (!username || !password) {
      showMessage(message, "Enter both username and password.", "error");
      return;
    }
    try {
      const result = await API.login(username, password);
      Auth.save(result.token, result.user);
      showMessage(message, "Signed in. Loading the floor...", "success");
      window.location.href = "dashboard_floors.html";
    } catch (error) {
      showMessage(message, error.message, "error");
    }
  });
});
