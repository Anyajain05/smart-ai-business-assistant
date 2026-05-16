/* SMART AI BUSINESS ASSISTANT - FRONTEND */

let token = localStorage.getItem("token") || "";
let currentUser = null;
let conversationId = null;

const API_BASE = "/api";

/* DOM SHORTCUTS */
const $ = (id) => document.getElementById(id);
const show = (el) => el?.classList.remove("hidden");
const hide = (el) => el?.classList.add("hidden");

/* API HELPER */
const api = async (path, options = {}) => {
  const headers = options.headers || {};
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });
  
  if (!res.ok) {
    if (res.status === 401) {
      logout();
      throw new Error("Session expired. Please sign in again.");
    }
    const text = await res.text();
    throw new Error(text || `Error: ${res.status}`);
  }
  
  return res.json();
};

/* ESCAPE HTML */
const escapeHtml = (text) => {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(text ?? "").replace(/[&<>"']/g, (c) => map[c]);
};

/* ===== AUTHENTICATION ===== */

async function login(event) {
  event?.preventDefault();
  const email = $("loginEmail").value.trim();
  const password = $("loginPassword").value;
  const errorDiv = $("loginError");

  errorDiv.textContent = "";
  errorDiv.classList.remove("show");

  if (!email || !password) {
    errorDiv.textContent = "Please enter email and password";
    errorDiv.classList.add("show");
    return;
  }

  try {
    const data = await api(`${API_BASE}/auth/login`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });

    token = data.access_token;
    currentUser = data.user;
    localStorage.setItem("token", token);

    // Switch to app
    show($("appContainer"));
    hide($("loginScreen"));
    updateUserInfo();
    await loadAll();
  } catch (err) {
    errorDiv.textContent = err.message || "Invalid credentials";
    errorDiv.classList.add("show");
  }
}

function logout() {
  token = "";
  currentUser = null;
  localStorage.removeItem("token");
  conversationId = null;

  hide($("appContainer"));
  show($("loginScreen"));
  $("loginEmail").value = "admin@example.com";
  $("loginPassword").value = "admin123";
  $("loginError").textContent = "";
}

function updateUserInfo() {
  if (currentUser) {
    $("userName").textContent = currentUser.name;
    $("userEmail").textContent = currentUser.email;
  }
}

/* ===== CHAT ===== */

function addMessage(role, content) {
  const messagesDiv = $("messages");
  const emptyState = messagesDiv.querySelector(".chat-empty-state");
  if (emptyState) emptyState.remove();
  const msgEl = document.createElement("div");
  msgEl.className = `msg ${role}`;
  
  // Support markdown-style formatting
  let formatted = escapeHtml(content);
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  formatted = formatted.replace(/_(.*?)_/g, '<em>$1</em>');
  formatted = formatted.replace(/\n/g, '<br>');
  
  msgEl.innerHTML = formatted;
  msgEl.style.animation = "slideIn 0.3s ease";
  messagesDiv.appendChild(msgEl);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  return msgEl;
}

function showTypingIndicator() {
  const messagesDiv = $("messages");
  const indicator = document.createElement("div");
  indicator.className = "msg assistant typing-indicator";
  indicator.id = "typingIndicator";
  indicator.innerHTML = '<span></span><span></span><span></span>';
  indicator.style.animation = "slideIn 0.3s ease";
  messagesDiv.appendChild(indicator);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  return indicator;
}

function removeTypingIndicator() {
  const indicator = $("typingIndicator");
  if (indicator) indicator.remove();
}

function applyChatResult(result) {
  conversationId = result.conversation_id;
  if (result.sources && result.sources.length > 0) {
    let sourcesHtml = "<strong>📚 Retrieved Sources:</strong><br>";
    result.sources.forEach((src) => {
      const preview = escapeHtml((src.content || "").substring(0, 100));
      sourcesHtml += `<small>• <strong>${escapeHtml(src.document)}</strong>: ${preview}...</small><br>`;
    });
    $("chatSources").innerHTML = sourcesHtml;
  } else {
    $("chatSources").innerHTML = "<small>📭 No sources retrieved</small>";
  }
  if (result.lead) {
    const lead = result.lead;
    const tempEmoji = { hot: "🔥", warm: "🌡️", cold: "❄️" }[lead.temperature] || "📌";
    let leadHtml = `<strong>👤 Lead Detected ${tempEmoji}</strong><br>`;
    leadHtml += `<strong>${escapeHtml(lead.temperature || "unknown").toUpperCase()}</strong><br>`;
    if (lead.name) leadHtml += `👤 ${escapeHtml(lead.name)}<br>`;
    if (lead.email) leadHtml += `📧 ${escapeHtml(lead.email)}<br>`;
    if (lead.phone) leadHtml += `📱 ${escapeHtml(lead.phone)}<br>`;
    $("chatLead").innerHTML = leadHtml;
  } else {
    $("chatLead").innerHTML = "<small>ℹ️ Share your contact info for lead capture</small>";
  }
}

async function sendChatStream(message) {
  removeTypingIndicator();
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `Error: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let assembled = "";
  const assistantEl = addMessage("assistant", "");
  let finalPayload = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const blocks = buf.split("\n\n");
      buf = blocks.pop() || "";
      for (const block of blocks) {
        if (!block.startsWith("data: ")) continue;
        const payload = JSON.parse(block.slice(6).trim());
        if (payload.type === "start") {
          conversationId = payload.conversation_id;
        }
        if (payload.type === "delta" && payload.text) {
          assembled += payload.text;
          assistantEl.textContent = assembled;
        }
        if (payload.type === "done") finalPayload = payload;
      }
    }
    if (buf.trim().startsWith("data: ")) {
      try {
        const payload = JSON.parse(buf.trim().slice(6).trim());
        if (payload.type === "done") finalPayload = payload;
      } catch {
        /* ignore trailing parse errors */
      }
    }
  if (finalPayload) {
    const merged = {
      conversation_id: conversationId,
      answer: assembled,
      sources: finalPayload.sources,
      validation: finalPayload.validation,
      lead: finalPayload.lead,
    };
    let formatted = escapeHtml(assembled);
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    formatted = formatted.replace(/_(.*?)_/g, "<em>$1</em>");
    formatted = formatted.replace(/\n/g, "<br>");
    assistantEl.innerHTML = formatted;
    applyChatResult(merged);
  }
}

async function sendChat(event) {
  event.preventDefault();
  const input = $("chatInput");
  const message = input.value.trim();
  const useStream = $("useStream")?.checked;

  if (!message) return;

  input.value = "";
  input.disabled = true;
  addMessage("user", message);
  showTypingIndicator();

  try {
    if (useStream) {
      await sendChatStream(message);
    } else {
      const result = await api(`${API_BASE}/chat`, {
        method: "POST",
        body: JSON.stringify({ message, conversation_id: conversationId }),
      });
      removeTypingIndicator();
      addMessage("assistant", result.answer);
      applyChatResult(result);
    }
    await loadAll();
  } catch (err) {
    removeTypingIndicator();
    addMessage("assistant", `❌ Error: ${err.message}`);
  } finally {
    input.disabled = false;
    input.focus();
  }
}

/* ===== LEADS ===== */

let leadsFilter = "all";

async function loadLeads() {
  try {
    const leads = await api(`${API_BASE}/leads`);
    if (leads.length === 0) {
      $("leadList").innerHTML = "<p style='padding: 20px; text-align: center;'>📭 No leads captured yet.<br><small>Share your contact details in chat to be recorded as a lead.</small></p>";
      return;
    }

    // Filter leads
    let filtered = leads;
    if (leadsFilter !== "all") {
      filtered = leads.filter(l => l.temperature === leadsFilter);
    }

    let html = `
      <div style="margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap;">
        <button class="filter-btn ${leadsFilter === 'all' ? 'active' : ''}" onclick="filterLeads('all')">All (${leads.length})</button>
        <button class="filter-btn ${leadsFilter === 'hot' ? 'active' : ''}" onclick="filterLeads('hot')">🔥 Hot (${leads.filter(l => l.temperature === 'hot').length})</button>
        <button class="filter-btn ${leadsFilter === 'warm' ? 'active' : ''}" onclick="filterLeads('warm')">🌡️ Warm (${leads.filter(l => l.temperature === 'warm').length})</button>
        <button class="filter-btn ${leadsFilter === 'cold' ? 'active' : ''}" onclick="filterLeads('cold')">❄️ Cold (${leads.filter(l => l.temperature === 'cold').length})</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Contact</th>
            <th>Company</th>
            <th>Temp</th>
            <th>Follow-up</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
    `;

    filtered.forEach((lead) => {
      const contact = lead.email || lead.phone || "—";
      const temp = lead.temperature || "cold";
      const tempEmoji = {"hot": "🔥", "warm": "🌡️", "cold": "❄️"}[temp] || "📌";
      html += `
        <tr>
          <td><strong>${escapeHtml(lead.name || "Unknown")}</strong></td>
          <td><small>${escapeHtml(contact)}</small></td>
          <td><small>${escapeHtml(lead.company || "—")}</small></td>
          <td><span class="badge ${temp}">${tempEmoji} ${temp}</span></td>
          <td><small style="color: var(--text-muted);">${escapeHtml(lead.follow_up || "—")}</small></td>
          <td>
            <button class="btn-action" onclick="copyToClipboard('${escapeHtml(contact)}')">📋</button>
            <button class="btn-action" onclick="alert('Email draft for ${escapeHtml(lead.name || 'Lead')}')">✉️</button>
          </td>
        </tr>
      `;
    });

    html += "</tbody></table>";
    $("leadList").innerHTML = html;
  } catch (err) {
    $("leadList").innerHTML = `<p style='padding: 20px; color: var(--danger);'>❌ Error: ${err.message}</p>`;
  }
}

function filterLeads(filter) {
  leadsFilter = filter;
  loadLeads();
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text);
  alert("📋 Copied to clipboard!");
}

/* ===== DOCUMENTS ===== */

async function loadDocuments() {
  try {
    const docs = await api(`${API_BASE}/documents`);
    if (docs.length === 0) {
      $("docList").innerHTML = `
        <div style="text-align: center; padding: 40px 20px;">
          <p style="font-size: 2rem; margin-bottom: 10px;">📁</p>
          <strong>No documents uploaded yet</strong>
          <p style="color: var(--text-muted); margin-top: 8px;">Upload knowledge docs to power better answers</p>
        </div>
      `;
      return;
    }

    let html = "<div style='display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;'>";
    docs.forEach((doc) => {
      const date = new Date(doc.created_at).toLocaleDateString();
      const chunks = doc.chunks_count || 0;
      html += `
        <div class="card" style="display: flex; flex-direction: column;">
          <div style="display: flex; align-items: start; justify-content: space-between; margin-bottom: 8px;">
            <div>
              <strong style="display: block; margin-bottom: 4px;">📄 ${escapeHtml(doc.filename)}</strong>
              <small style="color: var(--text-muted);">${date}</small>
            </div>
            <button class="btn-action" onclick="alert('View ${escapeHtml(doc.filename)}')">👁️</button>
          </div>
          <p style="flex-grow: 1; margin: 8px 0; font-size: 13px;">${escapeHtml(doc.summary || 'Knowledge base document')}</p>
          <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 8px; border-top: 1px solid var(--border);">
            <small style="color: var(--text-muted);">📊 ${chunks} chunks indexed</small>
            <div style="display: flex; gap: 4px;">
              <button class="btn-action" onclick="alert('Deleting ${escapeHtml(doc.filename)}...')">🗑️</button>
            </div>
          </div>
        </div>
      `;
    });
    html += "</div>";
    $("docList").innerHTML = html;
  } catch (err) {
    $("docList").innerHTML = `<p style='padding: 20px; color: var(--danger);'>❌ Error: ${err.message}</p>`;
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const file = $("docFile").files[0];
  if (!file) return;

  const input = $("docFile");
  input.disabled = true;
  
  // Show upload progress
  const statusDiv = document.createElement("div");
  statusDiv.style.padding = "10px";
  statusDiv.style.background = "var(--bg-alt)";
  statusDiv.style.borderRadius = "6px";
  statusDiv.style.marginTop = "8px";
  statusDiv.textContent = `📤 Uploading "${file.name}"...`;
  $("docForm").appendChild(statusDiv);

  const form = new FormData();
  form.append("file", file);

  try {
    const result = await api(`${API_BASE}/documents`, { method: "POST", body: form });
    statusDiv.textContent = `✅ "${file.name}" uploaded successfully (${result.chunks_count || 0} chunks indexed)`;
    statusDiv.style.color = "var(--success)";
    input.value = "";
    setTimeout(() => statusDiv.remove(), 3000);
    await loadDocuments();
  } catch (err) {
    statusDiv.textContent = `❌ Upload failed: ${err.message}`;
    statusDiv.style.color = "var(--danger)";
    setTimeout(() => statusDiv.remove(), 5000);
  } finally {
    input.disabled = false;
  }
}

/* ===== WORKFLOWS ===== */

async function runWorkflow(workflowName) {
  try {
    let payload = {};
    const input = $("workflowPayload").value.trim();

    try {
      payload = JSON.parse(input);
    } catch {
      payload = { text: input };
    }

    // Show loading state
    const resultDiv = $("workflowResult");
    resultDiv.textContent = `⏳ Running "${workflowName}" workflow...`;
    resultDiv.style.color = "var(--text-muted)";

    const result = await api(`${API_BASE}/workflows/run`, {
      method: "POST",
      body: JSON.stringify({ workflow: workflowName, payload }),
    });

    const out = result.output ?? result;
    let resultHTML = `Status: ${result.status || "unknown"}\nAttempts: ${result.attempts ?? 1}\n\n`;
    resultHTML += typeof out === "string" ? out : JSON.stringify(out, null, 2);
    resultDiv.textContent = resultHTML;
    resultDiv.style.color = result.status === "success" ? "var(--success)" : "var(--danger)";
    
    await loadAnalytics();
  } catch (err) {
    $("workflowResult").textContent = `❌ Workflow Error: ${err.message}`;
    $("workflowResult").style.color = "var(--danger)";
  }
}

/* ===== ANALYTICS ===== */

async function loadAnalytics() {
  try {
    const data = await api(`${API_BASE}/analytics`);
    const totals = data.totals || {};

    const bonus = data.bonus || {};
    const bonusEl = $("bonusStatus");
    if (bonusEl) {
      bonusEl.innerHTML = `
        <span class="bonus-pill">Redis cache: ${bonus.redis_cache ? "on" : "off"}</span>
        <span class="bonus-pill">Chroma vectors: ${bonus.chroma_vector ? "on" : "off"}</span>
        <span class="bonus-pill">Webhooks: ${bonus.webhooks_registered ?? 0}</span>
      `;
    }

    let metricsHtml = "";
    const metricIcons = {
      conversations: "💬",
      leads: "👥",
      documents: "📄",
      workflow_runs: "⚙️",
      assistant_messages: "🤖",
    };

    for (const [key, value] of Object.entries(totals)) {
      const icon = metricIcons[key] || "📊";
      const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      metricsHtml += `
        <div style="display: flex; flex-direction: column; align-items: center;">
          <div class="metric-value" style="font-size: 2rem; margin-bottom: 4px;">${icon}</div>
          <div class="metric-value" style="font-size: 2rem; color: var(--primary);">${value}</div>
          <div class="metric-label">${label}</div>
        </div>
      `;
    }
    $("metricCards").innerHTML = metricsHtml;

    let agentHtml = "";
    if (data.recent_agent_logs && data.recent_agent_logs.length > 0) {
      data.recent_agent_logs.slice(0, 12).forEach((log) => {
        const agentEmoji = { Planner: "📋", Executor: "⚡", Validator: "✅" }[log.agent] || "🤖";
        const dec = (log.decision || "").substring(0, 180);
        let trace = "";
        try {
          const m = JSON.parse(log.meta || "{}");
          if (m.trace_id) trace = ` · trace ${String(m.trace_id).slice(0, 8)}…`;
        } catch {
          /* ignore */
        }
        const ms = log.latency_ms != null ? `${log.latency_ms}ms` : "";
        agentHtml += `
          <div class="log-item">
            <strong>${agentEmoji} ${escapeHtml(log.agent)}</strong> <small>${escapeHtml(ms)}${escapeHtml(trace)}</small>
            <p>${escapeHtml(dec)}${dec.length >= 180 ? "…" : ""}</p>
            <small style="color: var(--text-muted);">${new Date(log.created_at).toLocaleTimeString()}</small>
          </div>
        `;
      });
    } else {
      agentHtml = "<p style='padding: 12px; text-align: center; color: var(--text-muted);'>🤖 No agent activity yet</p>";
    }
    $("agentLogs").innerHTML = agentHtml;

    let workflowHtml = "";
    if (data.recent_workflows && data.recent_workflows.length > 0) {
      data.recent_workflows.slice(0, 12).forEach((log) => {
        const status = log.status === "success" ? "✅" : "❌";
        const emoji = { email_summary: "📧", crm_sync: "🔄", calendar_booking: "📅" }[log.workflow] || "⚙️";
        let out = log.output;
        if (typeof out === "string") {
          try {
            out = JSON.parse(out);
          } catch {
            /* keep string */
          }
        }
        const preview = escapeHtml(JSON.stringify(out).substring(0, 160));
        workflowHtml += `
          <div class="log-item">
            <strong>${status} ${emoji} ${escapeHtml(log.workflow)}</strong>
            <p style="max-height: 72px; overflow: hidden;">${preview}…</p>
            <small style="color: var(--text-muted);">${new Date(log.created_at).toLocaleTimeString()}</small>
          </div>
        `;
      });
    } else {
      workflowHtml = "<p style='padding: 12px; text-align: center; color: var(--text-muted);'>⚙️ No workflows executed yet</p>";
    }
    $("workflowLogs").innerHTML = workflowHtml;
  } catch (err) {
    $("metricCards").innerHTML = `<p style='padding: 12px; color: var(--danger);'>❌ ${err.message}</p>`;
  }
}

/* ===== LOAD ALL DATA ===== */

async function loadAll() {
  const jobs = [loadLeads(), loadDocuments(), loadAnalytics()];
  if (currentUser?.role === "admin") {
    jobs.push(loadWebhooks(), loadMonitoring());
  }
  await Promise.all(jobs);
}

/* ===== BONUS: WEBHOOKS, MONITORING, BUILDER, VOICE, EVAL ===== */

async function loadWebhooks() {
  if (currentUser?.role !== "admin" || !$("webhookList")) return;
  try {
    const hooks = await api(`${API_BASE}/webhooks`);
    if (!hooks.length) {
      $("webhookList").innerHTML = "<p class='muted'>No webhooks registered.</p>";
      return;
    }
    $("webhookList").innerHTML = hooks
      .map(
        (h) => `
      <div class="card" style="padding:14px;margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <strong>${escapeHtml(h.url)}</strong>
          <button type="button" class="btn-action" onclick="deleteWebhook(${h.id})">🗑️</button>
        </div>
        <small class="muted">events: ${escapeHtml(h.events || "*")}</small>
      </div>`
      )
      .join("");
  } catch {
    $("webhookList").innerHTML = "<p class='muted'>Could not load webhooks (admin only).</p>";
  }
}

async function deleteWebhook(id) {
  if (!confirm("Delete this webhook?")) return;
  await api(`${API_BASE}/webhooks/${id}`, { method: "DELETE" });
  await loadWebhooks();
}

async function loadMonitoring() {
  if (currentUser?.role !== "admin") return;
  try {
    const h = await (await fetch("/health")).json();
    if ($("healthBox")) $("healthBox").textContent = JSON.stringify(h, null, 2);
    const dels = await api(`${API_BASE}/monitoring/deliveries`);
    const box = $("deliveryList");
    if (!box) return;
    if (!dels.length) {
      box.innerHTML = "<p class='muted'>No webhook deliveries recorded yet.</p>";
      return;
    }
    box.innerHTML = dels
      .map(
        (d) => `
      <div class="log-item">
        <strong>${d.success ? "✅" : "❌"} ${escapeHtml(d.event || "")}</strong>
        <p><small>${escapeHtml(d.url || "")}</small> · HTTP ${d.status_code ?? 0}</p>
        <small class="muted">${escapeHtml((d.detail || "").slice(0, 120))}</small>
      </div>`
      )
      .join("");
  } catch (e) {
    if ($("healthBox")) $("healthBox").textContent = String(e);
  }
}

function setupVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = $("voiceBtn");
  if (!SpeechRecognition || !btn) {
    if (btn) btn.title = "Voice not supported in this browser";
    return;
  }
  const rec = new SpeechRecognition();
  rec.lang = "en-US";
  rec.interimResults = false;
  btn.addEventListener("click", () => {
    try {
      rec.start();
    } catch {
      /* already running */
    }
  });
  rec.onresult = (e) => {
    const t = e.results[0][0].transcript;
    const inp = $("chatInput");
    inp.value = `${inp.value} ${t}`.trim();
  };
  rec.onerror = () => {};
}

function setupImageInput() {
  const inp = $("imageInput");
  if (!inp) return;
  inp.addEventListener("change", async (ev) => {
    const f = ev.target.files[0];
    if (!f || !token) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const res = await fetch(`${API_BASE}/media/analyze`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const text = await res.text();
      if (!res.ok) throw new Error(text);
      const data = JSON.parse(text);
      addMessage("user", `[Image upload: ${f.name}]`);
      addMessage("assistant", data.description || JSON.stringify(data, null, 2));
    } catch (err) {
      addMessage("assistant", `Image analysis failed: ${err.message}`);
    }
    ev.target.value = "";
  });
}

function setupBuilder() {
  const drop = $("builderDrop");
  if (!drop) return;
  document.querySelectorAll(".palette-item").forEach((el) => {
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("step", el.dataset.step);
    });
  });
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
  });
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    const step = e.dataTransfer.getData("step");
    if (!step) return;
    const muted = drop.querySelector(".muted");
    if (muted) muted.remove();
    const row = document.createElement("div");
    row.className = "pipeline-step";
    row.dataset.step = step;
    row.innerHTML = `<span>${escapeHtml(step)}</span><button type="button" class="btn-action rm">✕</button>`;
    row.querySelector(".rm").addEventListener("click", () => row.remove());
    drop.appendChild(row);
  });
  $("builderClear")?.addEventListener("click", () => {
    drop.innerHTML = `<p class="muted">Drop steps here in order</p>`;
  });
  $("builderRun")?.addEventListener("click", async () => {
    const steps = [...drop.querySelectorAll(".pipeline-step")].map((r) => r.dataset.step);
    if (!steps.length) {
      $("builderResult").textContent = "Add at least one step to the pipeline.";
      return;
    }
    let payload = { text: "Please summarize this customer email and follow up tomorrow about pricing." };
    try {
      payload = JSON.parse($("workflowPayload").value.trim());
    } catch {
      /* use default */
    }
    try {
      const result = await api(`${API_BASE}/workflows/chain`, {
        method: "POST",
        body: JSON.stringify({ steps, payload }),
      });
      $("builderResult").textContent = JSON.stringify(result, null, 2);
      await loadAnalytics();
    } catch (err) {
      $("builderResult").textContent = `Error: ${err.message}`;
    }
  });
}

function setupWebhookForm() {
  $("webhookForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = $("whUrl").value.trim();
    const secret = $("whSecret").value.trim();
    const raw = $("whEvents").value.trim();
    const events = raw === "*" ? ["*"] : raw.split(",").map((s) => s.trim()).filter(Boolean);
    await api(`${API_BASE}/webhooks`, {
      method: "POST",
      body: JSON.stringify({ url, secret, events: events.length ? events : ["*"] }),
    });
    await loadWebhooks();
  });
}

function setupEvalForm() {
  $("evalForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      question: $("evalQuestion").value,
      answer: $("evalAnswer").value,
      expected_keywords: $("evalKeywords").value.split(",").map((s) => s.trim()).filter(Boolean),
      sources: [],
    };
    const r = await api(`${API_BASE}/evaluate`, { method: "POST", body: JSON.stringify(body) });
    $("evalResult").textContent = JSON.stringify(r, null, 2);
  });
}

/* ===== EVENT LISTENERS ===== */

// Login
$("loginForm").addEventListener("submit", login);

// Chat
$("chatForm").addEventListener("submit", sendChat);

// Documents
$("docForm").addEventListener("submit", uploadDocument);

// Workflows
document.querySelectorAll(".workflow-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    runWorkflow(btn.dataset.workflow);
  });
});

// Navigation
document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const view = btn.dataset.view;
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    $(view).classList.add("active");
    if (currentUser?.role === "admin") {
      if (view === "monitoring") await loadMonitoring();
      if (view === "webhooks") await loadWebhooks();
    }
  });
});

// Logout
$("logoutBtn").addEventListener("click", logout);

/* ===== INIT ===== */

document.addEventListener("DOMContentLoaded", async () => {
  setupVoice();
  setupImageInput();
  setupBuilder();
  setupWebhookForm();
  setupEvalForm();
  if (token) {
    try {
      const user = await api(`${API_BASE}/me`);
      currentUser = user;
      show($("appContainer"));
      hide($("loginScreen"));
      updateUserInfo();
      await loadAll();
    } catch (err) {
      logout();
    }
  }
});
