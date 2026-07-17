const DATA_KEY = "af_personal_data_v2";
const WORKFLOW_KEY = "af_workflow_v2";
const LOG_KEY = "af_application_log_v2";
const MAX_URLS = 5;

const PROFILES = [
  { value: "general", label: "General" },
  { value: "job_application", label: "Job application" },
  { value: "housing", label: "Housing" },
  { value: "registration", label: "Registration" },
];

const EMPTY_INFO = {
  first_name: "",
  last_name: "",
  full_name: "",
  email: "",
  phone: "",
  date_of_birth: "",
  street: "",
  city: "",
  state: "",
  zip: "",
  country: "United States",
  linkedin: "",
  website: "",
  notes: "",
  desired_salary: "",
  years_experience: "",
  work_authorization: "",
  monthly_income: "",
  employer: "",
  move_in_date: "",
};

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
  infoForm: document.getElementById("info-form"),
  infoStatus: document.getElementById("info-status"),
  workflowStatus: document.getElementById("workflow-status"),
  urlRows: document.getElementById("url-rows"),
  urlHint: document.getElementById("url-count-hint"),
  dataEditor: document.getElementById("data-editor"),
  logView: document.getElementById("log-view"),
  workflowName: document.getElementById("workflow-name"),
  defaultProfile: document.getElementById("default-profile"),
};

let urlSlots = [];

function show(view) {
  els.login.hidden = view !== "login";
  els.change.hidden = view !== "change";
  els.app.hidden = view !== "app";
}

function setError(node, msg) {
  node.hidden = !msg;
  node.textContent = msg || "";
}

function flash(node, msg, isError = false) {
  node.hidden = false;
  node.textContent = msg;
  node.style.color = isError ? "var(--danger)" : "";
  setTimeout(() => {
    node.hidden = true;
    node.style.color = "";
  }, 2800);
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
    /* ignore */
  }
  return { res, data };
}

async function bootstrap() {
  try {
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
  } catch {
    show("login");
  }
}

function enterApp(username) {
  els.whoami.textContent = username || "admin";
  show("app");
  loadInfoIntoForm();
  loadWorkflow();
  syncJsonEditor();
  renderLogs();
  loadInbox();
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadInbox() {
  const list = document.getElementById("inbox-list");
  const status = document.getElementById("inbox-status");
  if (!list) return;
  list.innerHTML = '<p class="muted">Loading submissions…</p>';
  try {
    const { res, data } = await api("list-submissions?limit=40", { method: "GET" });
    if (!res.ok) {
      list.innerHTML = `<p class="error">${escapeHtml(data.error || "Could not load inbox")}</p>`;
      return;
    }
    const stats = data.stats || {};
    const setStat = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val ?? "0";
    };
    setStat("stat-total", stats.total);
    setStat("stat-new", stats.new);
    setStat("stat-processing", stats.processing);
    setStat("stat-completed", stats.completed);

    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      list.innerHTML = '<p class="muted">No submissions yet. Share the user intake invite link to receive requests.</p>';
      return;
    }
    list.innerHTML = items
      .map((item) => {
        const name = `${item.firstName || ""} ${item.lastName || ""}`.trim() || "(no name)";
        const statusKey = String(item.status || "new").toLowerCase();
        const idLine = item.issued_id ? `ID ${escapeHtml(item.issued_id)}` : "ID pending";
        const confirm = item.confirmationEmailSent ? "confirm sent" : "confirm pending";
        return `<article class="inbox-card">
          <header>
            <strong>${escapeHtml(name)}</strong>
            <span class="pill ${escapeHtml(statusKey)}">${escapeHtml(statusKey)}</span>
          </header>
          <div class="inbox-meta">
            ${escapeHtml(item.email || "—")} · ${escapeHtml(item.state || "—")}<br />
            ${idLine} · ${confirm}<br />
            ${escapeHtml(item.createdAt || "")}<br />
            <span style="opacity:.75">ref ${escapeHtml(item.id)}</span>
          </div>
        </article>`;
      })
      .join("");
    if (status) {
      status.hidden = false;
      status.textContent = `Loaded ${items.length}`;
      setTimeout(() => {
        status.hidden = true;
      }, 2000);
    }
  } catch (err) {
    list.innerHTML = `<p class="error">${escapeHtml(err.message || "Inbox error")}</p>`;
  }
}

document.getElementById("btn-refresh-inbox")?.addEventListener("click", () => loadInbox());

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

function formToInfo() {
  const fd = new FormData(els.infoForm);
  const info = { ...EMPTY_INFO };
  for (const key of Object.keys(EMPTY_INFO)) {
    info[key] = String(fd.get(key) || "").trim();
  }
  if (!info.full_name && (info.first_name || info.last_name)) {
    info.full_name = `${info.first_name} ${info.last_name}`.trim();
  }
  return info;
}

function infoToForm(info) {
  const merged = { ...EMPTY_INFO, ...info };
  for (const [key, value] of Object.entries(merged)) {
    const input = els.infoForm.elements.namedItem(key);
    if (input) input.value = value ?? "";
  }
}

function personalDataFromInfo(info) {
  const overrides = {};
  for (const key of [
    "desired_salary",
    "years_experience",
    "work_authorization",
    "monthly_income",
    "employer",
    "move_in_date",
  ]) {
    if (info[key]) overrides[key] = info[key];
  }

  return {
    version: 2,
    defaults: {
      first_name: info.first_name,
      last_name: info.last_name,
      full_name: info.full_name,
      email: info.email,
      phone: info.phone,
      date_of_birth: info.date_of_birth,
      address: {
        street: info.street,
        city: info.city,
        state: info.state,
        zip: info.zip,
        country: info.country || "United States",
      },
      linkedin: info.linkedin,
      website: info.website,
      notes: info.notes,
    },
    profiles: {
      general: { description: "Default / generic forms", overrides: {} },
      job_application: {
        description: "Job / career applications",
        overrides: {
          ...(overrides.desired_salary ? { desired_salary: overrides.desired_salary } : {}),
          ...(overrides.years_experience ? { years_experience: overrides.years_experience } : {}),
          ...(overrides.work_authorization
            ? { work_authorization: overrides.work_authorization }
            : {}),
        },
      },
      housing: {
        description: "Housing / rental applications",
        overrides: {
          ...(overrides.monthly_income ? { monthly_income: overrides.monthly_income } : {}),
          ...(overrides.employer ? { employer: overrides.employer } : {}),
          ...(overrides.move_in_date ? { move_in_date: overrides.move_in_date } : {}),
        },
      },
      registration: {
        description: "Account / membership sign-ups",
        overrides: {},
      },
    },
    custom_fields: {},
  };
}

function infoFromPersonalData(data) {
  const d = data?.defaults || {};
  const addr = d.address || {};
  const job = data?.profiles?.job_application?.overrides || {};
  const housing = data?.profiles?.housing?.overrides || {};
  return {
    ...EMPTY_INFO,
    first_name: d.first_name || "",
    last_name: d.last_name || "",
    full_name: d.full_name || "",
    email: d.email || "",
    phone: d.phone || "",
    date_of_birth: d.date_of_birth || "",
    street: addr.street || "",
    city: addr.city || "",
    state: addr.state || "",
    zip: addr.zip || "",
    country: addr.country || "United States",
    linkedin: d.linkedin || "",
    website: d.website || "",
    notes: d.notes || "",
    desired_salary: job.desired_salary || "",
    years_experience: job.years_experience || "",
    work_authorization: job.work_authorization || "",
    monthly_income: housing.monthly_income || "",
    employer: housing.employer || "",
    move_in_date: housing.move_in_date || "",
  };
}

function loadInfoIntoForm() {
  const raw = localStorage.getItem(DATA_KEY);
  if (!raw) {
    infoToForm(EMPTY_INFO);
    return;
  }
  try {
    infoToForm(infoFromPersonalData(JSON.parse(raw)));
  } catch {
    infoToForm(EMPTY_INFO);
  }
}

function saveInfo() {
  const info = formToInfo();
  const personal = personalDataFromInfo(info);
  localStorage.setItem(DATA_KEY, JSON.stringify(personal, null, 2));
  syncJsonEditor();
  flash(els.infoStatus, "Saved");
}

function syncJsonEditor() {
  const raw = localStorage.getItem(DATA_KEY);
  els.dataEditor.value = raw || JSON.stringify(personalDataFromInfo(formToInfo()), null, 2);
}

document.getElementById("btn-save-info").addEventListener("click", saveInfo);

document.getElementById("btn-clear-info").addEventListener("click", () => {
  if (confirm("Clear all personal info fields?")) {
    infoToForm(EMPTY_INFO);
    flash(els.infoStatus, "Form cleared — click Save to keep");
  }
});

/* ---- Workflow URL rows ---- */

function profileOptions(selected) {
  return PROFILES.map(
    (p) =>
      `<option value="${p.value}" ${p.value === selected ? "selected" : ""}>${p.label}</option>`
  ).join("");
}

function renderUrlRows() {
  els.urlRows.innerHTML = urlSlots
    .map(
      (slot, i) => `
    <div class="url-card" data-index="${i}">
      <div class="url-card-head">
        <span class="url-num">App ${i + 1}</span>
        <button type="button" class="btn ghost btn-sm btn-remove" data-index="${i}" ${urlSlots.length <= 1 ? "disabled" : ""}>Remove</button>
      </div>
      <label>Application URL
        <input class="url-input" data-index="${i}" type="url" placeholder="https://…" value="${escapeAttr(slot.url)}" />
      </label>
      <div class="url-card-grid">
        <label>Profile
          <select class="profile-select" data-index="${i}">${profileOptions(slot.profile)}</select>
        </label>
        <label>Notes (optional)
          <input class="notes-input" data-index="${i}" placeholder="e.g. use job profile extras" value="${escapeAttr(slot.notes)}" />
        </label>
      </div>
    </div>`
    )
    .join("");

  els.urlHint.textContent = `${urlSlots.length} of ${MAX_URLS} applications`;
  document.getElementById("btn-add-url").disabled = urlSlots.length >= MAX_URLS;

  els.urlRows.querySelectorAll(".url-input").forEach((el) => {
    el.addEventListener("input", () => {
      urlSlots[+el.dataset.index].url = el.value.trim();
    });
  });
  els.urlRows.querySelectorAll(".profile-select").forEach((el) => {
    el.addEventListener("change", () => {
      urlSlots[+el.dataset.index].profile = el.value;
    });
  });
  els.urlRows.querySelectorAll(".notes-input").forEach((el) => {
    el.addEventListener("input", () => {
      urlSlots[+el.dataset.index].notes = el.value;
    });
  });
  els.urlRows.querySelectorAll(".btn-remove").forEach((el) => {
    el.addEventListener("click", () => {
      if (urlSlots.length <= 1) return;
      urlSlots.splice(+el.dataset.index, 1);
      renderUrlRows();
    });
  });
}

function escapeAttr(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function loadWorkflow() {
  const raw = localStorage.getItem(WORKFLOW_KEY);
  if (raw) {
    try {
      const wf = JSON.parse(raw);
      els.workflowName.value = wf.name || "";
      const apps = Array.isArray(wf.applications) ? wf.applications : [];
      urlSlots = apps.slice(0, MAX_URLS).map((a) => ({
        url: a.url || "",
        profile: a.profile || "general",
        notes: a.notes || a.extra_instructions || "",
      }));
    } catch {
      urlSlots = [];
    }
  }
  if (!urlSlots.length) {
    urlSlots = [{ url: "", profile: els.defaultProfile.value || "general", notes: "" }];
  }
  renderUrlRows();
}

function buildWorkflow() {
  const applications = urlSlots
    .map((s) => ({
      url: (s.url || "").trim(),
      profile: s.profile || "general",
      notes: (s.notes || "").trim(),
      extra_instructions: (s.notes || "").trim(),
    }))
    .filter((a) => a.url);

  return {
    version: 1,
    name: (els.workflowName.value || "").trim() || "My workflow",
    created_at: new Date().toISOString(),
    applications,
  };
}

function saveWorkflow() {
  const wf = buildWorkflow();
  if (!wf.applications.length) {
    flash(els.workflowStatus, "Add at least one URL", true);
    return false;
  }
  if (wf.applications.length > MAX_URLS) {
    flash(els.workflowStatus, `Max ${MAX_URLS} URLs`, true);
    return false;
  }
  // Keep empty slots in UI state but only persist filled apps + current slots
  localStorage.setItem(WORKFLOW_KEY, JSON.stringify(wf, null, 2));
  flash(els.workflowStatus, `Saved ${wf.applications.length} application(s)`);
  return true;
}

document.getElementById("btn-add-url").addEventListener("click", () => {
  if (urlSlots.length >= MAX_URLS) return;
  urlSlots.push({
    url: "",
    profile: els.defaultProfile.value || "general",
    notes: "",
  });
  renderUrlRows();
});

document.getElementById("btn-save-workflow").addEventListener("click", saveWorkflow);

function download(filename, text) {
  const blob = new Blob([text], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

document.getElementById("btn-dl-personal").addEventListener("click", () => {
  saveInfo();
  const personal = personalDataFromInfo(formToInfo());
  download("personal_data.json", JSON.stringify(personal, null, 2));
});

document.getElementById("btn-dl-workflow").addEventListener("click", () => {
  if (!saveWorkflow()) return;
  download("workflow.json", JSON.stringify(buildWorkflow(), null, 2));
});

document.getElementById("btn-sync-from-json").addEventListener("click", () => {
  try {
    const data = JSON.parse(els.dataEditor.value);
    infoToForm(infoFromPersonalData(data));
    localStorage.setItem(DATA_KEY, JSON.stringify(data, null, 2));
    flash(els.infoStatus, "Loaded into form");
  } catch {
    alert("Invalid JSON");
  }
});

document.getElementById("btn-sync-to-json").addEventListener("click", () => {
  const personal = personalDataFromInfo(formToInfo());
  els.dataEditor.value = JSON.stringify(personal, null, 2);
});

document.getElementById("upload-data").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const text = await file.text();
  try {
    const data = JSON.parse(text);
    localStorage.setItem(DATA_KEY, JSON.stringify(data, null, 2));
    infoToForm(infoFromPersonalData(data));
    syncJsonEditor();
    flash(els.infoStatus, `Loaded ${file.name}`);
  } catch {
    alert("Invalid JSON file");
  }
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
        const url = entry.url || "—";
        const status = entry.status || "unknown";
        const ts = entry.timestamp || "";
        const filled = entry.filled_fields || entry.fields_filled || [];
        const count = Array.isArray(filled) ? filled.length : Object.keys(filled || {}).length;
        return `<div class="log-item"><strong>${status}</strong><div class="log-meta">${ts}<br>${url}<br>${count} field(s)</div></div>`;
      })
      .join("");
  } catch {
    els.logView.innerHTML = '<p class="muted">Could not parse log JSON.</p>';
  }
}

document.getElementById("upload-log").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  localStorage.setItem(LOG_KEY, await file.text());
  renderLogs();
});

document.getElementById("btn-clear-log").addEventListener("click", () => {
  localStorage.removeItem(LOG_KEY);
  renderLogs();
});

bootstrap();
