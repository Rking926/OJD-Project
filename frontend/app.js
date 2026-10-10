// Logique front minimale : vanilla JS, pas de build nécessaire.
const API = "/api";
let currentInvestigationId = null;
let investigations = [];

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Erreur API");
  }
  return res.json();
}

// ---------- Investigations ----------

async function loadInvestigations() {
  investigations = await api("/investigations");
  const list = document.getElementById("investigation-list");
  list.innerHTML = "";
  if (investigations.length === 0) {
    list.innerHTML = '<div class="empty" style="margin-top:8px">Aucune enquête encore.</div>';
  }
  for (const inv of investigations) {
    const div = document.createElement("div");
    div.className = "inv-item" + (inv.id === currentInvestigationId ? " active" : "");
    div.textContent = inv.title;
    div.title = inv.reason;
    div.onclick = () => selectInvestigation(inv.id);
    list.appendChild(div);
  }
}

function openNewInvestigationDialog() {
  document.getElementById("inv-title").value = "";
  document.getElementById("inv-reason").value = "";
  document.getElementById("new-inv-dialog").showModal();
}

async function createInvestigation() {
  const title = document.getElementById("inv-title").value.trim() || "Enquête sans titre";
  const reason = document.getElementById("inv-reason").value.trim();
  if (!reason) {
    alert("Le motif de la recherche est obligatoire.");
    return;
  }
  try {
    const inv = await api("/investigations", { method: "POST", body: JSON.stringify({ title, reason }) });
    document.getElementById("new-inv-dialog").close();
    await loadInvestigations();
    selectInvestigation(inv.id);
  } catch (e) {
    alert(e.message);
  }
}

async function selectInvestigation(id) {
  currentInvestigationId = id;
  document.getElementById("chat-empty").style.display = "none";
  document.getElementById("chat").style.display = "flex";
  document.getElementById("prompt-bar").style.display = "flex";
  document.getElementById("chat").innerHTML = "";
  await loadInvestigations();
  await refreshInvestigationDetail();
}

async function refreshInvestigationDetail() {
  if (!currentInvestigationId) return;
  const detail = await api(`/investigations/${currentInvestigationId}`);
  renderEntities(detail.entities);
  renderAudit(detail.audit);
  renderGraph(detail.entities, detail.relations);
}

// ---------- Modules ----------

async function loadModules() {
  const mods = await api("/modules");
  const list = document.getElementById("module-list");
  list.innerHTML = "";
  for (const m of mods) {
    const div = document.createElement("div");
    div.className = "entity-card";
    div.innerHTML = `<div><strong>${m.name}</strong></div><div style="color:var(--muted)">${m.description}</div>` +
      (m.requires_config.length ? `<div class="legal-note">Nécessite config: ${m.requires_config.join(", ")}</div>` : "");
    list.appendChild(div);
  }
}

// ---------- Chat / prompt ----------

function addChatMessage(role, text) {
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function addToolTrace(toolCalls) {
  if (!toolCalls || toolCalls.length === 0) return;
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "msg tool";
  div.innerHTML = toolCalls.map(tc =>
    `→ <strong>${tc.module}</strong>(${tc.input_type}: ${tc.value}) <span class="badge ${tc.status}">${tc.status}</span>`
  ).join("<br/>");
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

async function sendPromptText(text) {
  if (!text.trim() || !currentInvestigationId) return;
  addChatMessage("user", text);
  document.getElementById("prompt-input").value = "";
  const sendBtn = document.getElementById("send-btn");
  sendBtn.disabled = true;
  const thinking = addChatMessage("assistant", "...");
  try {
    const result = await api("/prompt", {
      method: "POST",
      body: JSON.stringify({ investigation_id: currentInvestigationId, prompt: text }),
    });
    thinking.remove();
    addToolTrace(result.tool_calls);
    addChatMessage("assistant", result.reply || "(pas de réponse texte)");
    await refreshInvestigationDetail();
  } catch (e) {
    thinking.textContent = "Erreur: " + e.message;
  } finally {
    sendBtn.disabled = false;
  }
}

document.getElementById("send-btn").addEventListener("click", () => {
  sendPromptText(document.getElementById("prompt-input").value);
});
document.getElementById("prompt-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendPromptText(document.getElementById("prompt-input").value);
  }
});

// ---------- Commande vocale (Web Speech API du navigateur, local au navigateur) ----------

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let isRecording = false;

if (SpeechRecognition) {
  recognizer = new SpeechRecognition();
  recognizer.lang = "fr-FR";
  recognizer.interimResults = false;
  recognizer.maxAlternatives = 1;

  recognizer.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    document.getElementById("prompt-input").value = transcript;
    sendPromptText(transcript);
  };
  recognizer.onend = () => {
    isRecording = false;
    document.getElementById("mic-btn").classList.remove("recording");
  };
  recognizer.onerror = () => {
    isRecording = false;
    document.getElementById("mic-btn").classList.remove("recording");
  };
} else {
  document.getElementById("mic-btn").title = "Reconnaissance vocale non supportée par ce navigateur";
}

document.getElementById("mic-btn").addEventListener("click", () => {
  if (!recognizer) {
    alert("La reconnaissance vocale n'est pas supportée par ce navigateur (essaie Chrome).");
    return;
  }
  if (isRecording) {
    recognizer.stop();
    return;
  }
  isRecording = true;
  document.getElementById("mic-btn").classList.add("recording");
  recognizer.start();
});

// ---------- Entités / audit / graphe ----------

function renderEntities(entities) {
  const container = document.getElementById("entities");
  container.innerHTML = "";
  if (!entities || entities.length === 0) {
    container.innerHTML = '<div class="empty">Aucune entité encore.</div>';
    return;
  }
  for (const e of entities) {
    const div = document.createElement("div");
    div.className = "entity-card";
    div.innerHTML = `<div class="entity-type">${e.type}</div><div>${e.value}</div><div style="color:var(--muted)">via ${e.source_module}</div>`;
    container.appendChild(div);
  }
}

function renderAudit(audit) {
  const container = document.getElementById("audit");
  container.innerHTML = "";
  if (!audit || audit.length === 0) {
    container.innerHTML = '<div class="empty">Aucun appel encore.</div>';
    return;
  }
  for (const a of audit.slice().reverse()) {
    const div = document.createElement("div");
    div.className = "entity-card";
    div.innerHTML = `<strong>${a.module}</strong> <span class="badge ${a.status}">${a.status}</span>` +
      `<div style="color:var(--muted)">${a.input_value}</div>` +
      `<div style="color:var(--muted); font-size:11px">${a.created_at}</div>`;
    container.appendChild(div);
  }
}

// Graphe très simple : noeud central (l'enquête) + une entité par rayon.
// Sera remplacé plus tard par une vraie lib de graphe / carte 3D.
function renderGraph(entities, relations) {
  const svg = document.getElementById("graph");
  const w = svg.clientWidth || 300;
  const h = 260;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML = "";
  if (!entities || entities.length === 0) return;

  const cx = w / 2, cy = h / 2;
  const addEl = (tag, attrs) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    svg.appendChild(el);
    return el;
  };

  addEl("circle", { cx, cy, r: 10, fill: "#4f8cff" });

  const n = entities.length;
  entities.forEach((e, i) => {
    const angle = (2 * Math.PI * i) / n;
    const r = Math.min(w, h) / 2 - 40;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    addEl("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: "#2a2f3a", "stroke-width": 1 });
    addEl("circle", { cx: x, cy: y, r: 6, fill: "#3ddc84" });
    const label = addEl("text", { x: x, y: y - 10, fill: "#e6e8ec", "font-size": 9, "text-anchor": "middle" });
    label.textContent = e.value.length > 18 ? e.value.slice(0, 18) + "…" : e.value;
  });
}

// ---------- Paramètres ----------

async function openSettingsDialog() {
  const cfg = await api("/config");
  document.getElementById("cfg-provider").value = cfg.llm_provider;
  document.getElementById("cfg-anthropic-key").value = "";
  document.getElementById("cfg-anthropic-key").placeholder = cfg.anthropic_api_key || "sk-ant-...";
  document.getElementById("cfg-anthropic-model").value = cfg.anthropic_model;
  document.getElementById("cfg-ollama-model").value = cfg.ollama_model;
  document.getElementById("cfg-ollama-url").value = cfg.ollama_base_url;
  document.getElementById("cfg-ig-session").value = "";
  document.getElementById("cfg-ig-session").placeholder = cfg.module_config.instagram_sessionid || "";
  document.getElementById("settings-dialog").showModal();
}

async function saveSettings() {
  const body = {
    llm_provider: document.getElementById("cfg-provider").value,
    anthropic_model: document.getElementById("cfg-anthropic-model").value,
    ollama_model: document.getElementById("cfg-ollama-model").value,
    ollama_base_url: document.getElementById("cfg-ollama-url").value,
    module_config: {},
  };
  const key = document.getElementById("cfg-anthropic-key").value.trim();
  if (key) body.anthropic_api_key = key;
  const ig = document.getElementById("cfg-ig-session").value.trim();
  if (ig) body.module_config.instagram_sessionid = ig;

  try {
    await api("/config", { method: "PUT", body: JSON.stringify(body) });
    document.getElementById("settings-dialog").close();
  } catch (e) {
    alert(e.message);
  }
}

// ---------- Init ----------

loadInvestigations();
loadModules();
