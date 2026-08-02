/* Centralised API wrapper for the Weekend Rush POS frontend. */
const API_BASE = "http://localhost:5000/api";

const Auth = {
  get token() {
    return localStorage.getItem("wr_token");
  },
  get role() {
    return localStorage.getItem("wr_role") || "";
  },
  get username() {
    return localStorage.getItem("wr_username") || "";
  },
  save(token, user) {
    localStorage.setItem("wr_token", token);
    localStorage.setItem("wr_role", user.role);
    localStorage.setItem("wr_username", user.username);
  },
  clear() {
    localStorage.removeItem("wr_token");
    localStorage.removeItem("wr_role");
    localStorage.removeItem("wr_username");
  },
  isAdmin() {
    return this.role === "admin";
  },
  guard(redirectTo) {
    if (!this.token) {
      window.location.href = redirectTo || "admin_login.html";
      return false;
    }
    return true;
  },
};

async function apiRequest(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (Auth.token) {
    headers.Authorization = `Bearer ${Auth.token}`;
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch (networkError) {
    throw new Error("Cannot reach the API server at http://localhost:5000");
  }

  let payload = {};
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (parseError) {
      payload = { error: text };
    }
  }

  if (response.status === 401 && Auth.token) {
    Auth.clear();
  }
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  return payload;
}

const API = {
  login: (username, password) =>
    apiRequest("/auth/login", { method: "POST", body: { username, password } }),
  me: () => apiRequest("/auth/me"),

  getTables: () => apiRequest("/tables/"),
  play: (id) => apiRequest(`/tables/${id}/play`, { method: "POST" }),
  pause: (id) => apiRequest(`/tables/${id}/pause`, { method: "POST" }),
  stop: (id, splitWays) =>
    apiRequest(`/tables/${id}/stop`, { method: "POST", body: { split_ways: splitWays } }),

  getCustomers: () => apiRequest("/customers/"),
  addCustomer: (body) => apiRequest("/customers/", { method: "POST", body }),
  updateCustomer: (id, body) => apiRequest(`/customers/${id}`, { method: "PUT", body }),
  toggleMember: (id) => apiRequest(`/customers/${id}/toggle-member`, { method: "POST" }),
  setNfc: (id, nfcUid) =>
    apiRequest(`/customers/${id}/nfc`, { method: "POST", body: { nfc_uid: nfcUid } }),
  deleteCustomer: (id) => apiRequest(`/customers/${id}`, { method: "DELETE" }),

  settingsTables: () => apiRequest("/settings/tables"),
  addTable: (body) => apiRequest("/settings/tables", { method: "POST", body }),
  updateTable: (id, body) => apiRequest(`/settings/tables/${id}`, { method: "PUT", body }),
  deleteTable: (id) => apiRequest(`/settings/tables/${id}`, { method: "DELETE" }),
  getUsers: () => apiRequest("/settings/users"),
  addUser: (body) => apiRequest("/settings/users", { method: "POST", body }),
  deleteUser: (id) => apiRequest(`/settings/users/${id}`, { method: "DELETE" }),

  requestBooking: (body) => apiRequest("/booking/request", { method: "POST", body }),
  getBookings: () => apiRequest("/booking/"),
};

function formatClock(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hh = String(Math.floor(seconds / 3600)).padStart(2, "0");
  const mm = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function formatINR(amount) {
  return `₹${Number(amount).toFixed(2)}`;
}

function showMessage(element, text, kind) {
  if (!element) return;
  element.textContent = text;
  element.classList.remove("wr-msg-error", "wr-msg-success", "wr-msg-info");
  element.classList.add(`wr-msg-${kind || "info"}`);
}

function startWallClock(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;
  const tick = () => {
    element.textContent = new Date().toLocaleTimeString();
  };
  tick();
  setInterval(tick, 1000);
}
