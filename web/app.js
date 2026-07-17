const SAMPLE_DATA = {
  version: 2,
  defaults: {
    first_name: "Alex",
    last_name: "Rivera",
    full_name: "Alex Rivera",
    email: "alex.rivera@example.com",
    phone: "+1-555-0100",
    date_of_birth: "1990-01-15",
    address: {
      street: "123 Main St",
      city: "Austin",
      state: "TX",
      zip: "78701",
      country: "United States",
    },
    linkedin: "",
    website: "",
    notes: "Replace sample values with your real personal data before use.",
  },
  profiles: {
    general: { description: "Default profile for generic registrations", overrides: {} },
    job_application: {
      description: "Job / career applications",
      overrides: {
        desired_salary: "85000",
        years_experience: "5",
        work_authorization: "Authorized to work",
        willing_to_relocate: "Yes",
      },
    },
    housing: {
      description: "Housing / rental applications",
      overrides: {
        monthly_income: "6000",
        employment_status: "Employed",
        move_in_date: "2026-08-01",
      },
    },
    registration: {
      description: "Account / membership sign-ups",
      overrides: { username_preference: "alexrivera", newsletter_opt_in: "No" },
    },
  },
  custom_fields: {
    emergency_contact_name: "",
    emergency_contact_phone: "",
  },
};

const DATA_KEY = "af_personal_data_v2";
const LOG_KEY = "af_application_log_v2";

const els = {
  login: document.getElementById("view-login"),
  change: document.getElementById("view-change"),
  app: document.getElementById("view-app"),
  loginForm: document.getElementById("login-form"),
  changeForm: document.getElementById("change-form"),
  loginError: document.getElementById("login-error"),
  changeError: document.getElementById("change-error"),
  whoami: document.getElementById("whoami"),
  logout: document.getElementById("btn-logout"),
  dataEditor: document.getElementById("data-editor"),
  dataStatus: document.getElementById("data-status"),
  logView: document.getElementById("log-view"),
};

function show(view) {
  els.login.hidden = view !== "login";
  els.change.hidden = view !== "change";
  els.app.hidden = view !== "app";
}

function setError(node, msg) {
  if (!msg) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.textContent = msg;
}

async function api(path, options = {}) {
  const res = await fetch(`/api/${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  return { res, data };
}

async function bootstrap() {
  const { res, data } = await api("me", { method: "GET" });
  if (!res.ok || !data.authenticated) {
    show("login");
    return;
  }
  if (data.mustChangePassword) {
    show("change");
    return;
  }
  enterApp(data.username);
}

function enterApp(username) {
  els.whoami.textContent = username || "admin";
  show("app");
  loadEditor();
  renderLogs();
}

els.loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  setError(els.loginError, "");
  const username = document.getElementById("login-user").value.trim();
  const password = document.getElementById("login-pass").value;
  const { res, data } = await api("login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    setError(els.loginError, data.error || "Login failed");
    return;
  }
  if (data.mustChangePassword) {
    show("change");
    return;
  }
  enterApp(data.username);
});

els.changeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  setError(els.changeError, "");
  const newPassword = document.getElementById("new-pass").value;
  const confirmPassword = document.getElementById("confirm-pass").value;
  const { res, data } = await api("change-password", {
    method: "POST",
    body: JSON.stringify({ newPassword, confirmPassword }),
  });
  if (!res.ok) {
    setError(els.changeError, data.error || "Could not change password");
    return;
  }
  enterApp("admin");
});

els.logout.addEventListener("click", async () => {
  await api("logout", { method: "POST", body: "{}" });
  show("login");
});

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach((el) => {
      el.hidden = el.id !== `tab-${tab}`;
    });
  });
});

function loadEditor() {
  const raw = localStorage.getItem(DATA_KEY);
  els.dataEditor.value = raw || JSON.stringify(SAMPLE_DATA, null, 2);
}

function flashStatus(msg) {
  els.dataStatus.hidden = false;
  els.dataStatus.textContent = msg;
  setTimeout(() => {
    els.dataStatus.hidden = true;
  }, 2500);
}

document.getElementById("btn-load-sample").addEventListener("click", () => {
  els.dataEditor.value = JSON.stringify(SAMPLE_DATA, null, 2);
  flashStatus("Sample loaded");
});

document.getElementById("btn-save-data").addEventListener("click", () => {
  try {
    const parsed = JSON.parse(els.dataEditor.value);
    localStorage.setItem(DATA_KEY, JSON.stringify(parsed, null, 2));
    flashStatus("Saved in this browser");
  } catch {
    flashStatus("Invalid JSON — fix before saving");
    els.dataStatus.style.color = "var(--danger)";
    setTimeout(() => {
      els.dataStatus.style.color = "";
    }, 2500);
  }
});

document.getElementById("btn-download-data").addEventListener("click", () => {
  const blob = new Blob([els.dataEditor.value], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "personal_data.json";
  a.click();
  URL.revokeObjectURL(a.href);
});

document.getElementById("upload-data").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  els.dataEditor.value = await file.text();
  flashStatus(`Loaded ${file.name}`);
});

function renderLogs() {
  const raw = localStorage.getItem(LOG_KEY);
  if (!raw) {
    els.logView.innerHTML = '<p class="muted">No logs loaded yet.</p>';
    return;
  }
  try {
    const data = JSON.parse(raw);
    const entries = Array.isArray(data) ? data : data.entries || data.runs || [];
    if (!entries.length) {
      els.logView.innerHTML = '<p class="muted">Log file has no entries.</p>';
      return;
    }
    els.logView.innerHTML = entries
      .slice()
      .reverse()
      .map((entry) => {
        const url = entry.url || entry.normalized_url || "—";
        const status = entry.status || "unknown";
        const ts = entry.timestamp || entry.ts || "";
        const filled = entry.filled_fields || entry.fields_filled || [];
        const count = Array.isArray(filled) ? filled.length : Object.keys(filled || {}).length;
        return `<div class="log-item"><strong>${status}</strong><div class="log-meta">${ts}<br>${url}<br>${count} field(s) filled</div></div>`;
      })
      .join("");
  } catch {
    els.logView.innerHTML = '<p class="muted">Could not parse log JSON.</p>';
  }
}

document.getElementById("upload-log").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const text = await file.text();
  localStorage.setItem(LOG_KEY, text);
  renderLogs();
});

document.getElementById("btn-clear-log").addEventListener("click", () => {
  localStorage.removeItem(LOG_KEY);
  renderLogs();
});

bootstrap();
