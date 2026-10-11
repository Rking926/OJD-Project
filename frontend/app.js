// OJD OSINT — logique front (vanilla JS, pas de build).
const API = "/api";
let currentInvestigationId = null;
let catalogData = null;

async function api(path, opts = {}) {
  const res = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Erreur API");
  }
  return res.json();
}

// ---------- Système / stats ----------

async function loadStats() {
  try {
    const cat = await api("/catalog");
    document.getElementById("sys-stats").innerHTML =
      `${cat.stats.installed}/${cat.stats.total} outils installés<br/>${cat.stats.runnable} lançables par l'IA`;
  } catch {
    document.getElementById("sys-stats").textContent = "stats indisponibles";
  }
}

// ---------- Investigations ----------

async function loadInvestigations() {
  const list = document.getElementById("investigation-list");
  const items = await api("/investigations");
  list.innerHTML = items.length ? "" : '<div class="dim" style="font-size:11px">aucune enquête</div>';
  for (const inv of items) {
    const div = document.createElement("div");
    div.className = "inv-item" + (inv.id === currentInvestigationId ? " active" : "");
    div.textContent = inv.title;
    div.title = inv.reason;
    div.onclick = () => selectInvestigation(inv.id);
    list.appendChild(div);
  }
}

// Nouveau chat : on vide l'écran et on attend le premier message.
// L'enregistrement est créé automatiquement à l'envoi du premier message.
function newChat() {
  currentInvestigationId = null;
  const ta = document.getElementById("prompt-input");
  ta.disabled = false;
  ta.value = "";
  ta.focus();
  document.getElementById("composer-hint").textContent =
    "Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne";
  document.getElementById("transcript").innerHTML = `
    <div class="welcome">
      <b>✻ Nouveau chat</b>
      <div class="dim">Explique ta recherche en langage naturel. Le chat se nomme tout seul.</div>
    </div>`;
  loadInvestigations();
  renderEntities([]);
  renderAudit([]);
}

async function selectInvestigation(id) {
  currentInvestigationId = id;
  const ta = document.getElementById("prompt-input");
  ta.disabled = false;
  ta.focus();
  document.getElementById("composer-hint").textContent = "Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne";
  document.getElementById("transcript").innerHTML = "";
  await loadInvestigations();
  await refreshDetail();
}

async function refreshDetail() {
  if (!currentInvestigationId) return;
  const d = await api(`/investigations/${currentInvestigationId}`);
  renderEntities(d.entities);
  renderAudit(d.audit);
}

// ---------- Transcript ----------

function addTurn(role, text) {
  const t = document.getElementById("transcript");
  const div = document.createElement("div");
  div.className = "turn " + role;
  const who = role === "user" ? "❯ vous" : role === "assistant" ? "✻ ojd" : "";
  div.innerHTML = who ? `<span class="who">${who}</span>\n${escapeHtml(text)}` : escapeHtml(text);
  t.appendChild(div);
  t.scrollTop = t.scrollHeight;
  return div;
}

function addToolTrace(calls) {
  if (!calls || !calls.length) return;
  const t = document.getElementById("transcript");
  const div = document.createElement("div");
  div.className = "turn tool";
  div.innerHTML = calls.map(c =>
    `<span class="call">⚙ ${c.module}</span>(${escapeHtml(c.input_type)}: ${escapeHtml(c.value)}) <span class="${c.status}">${c.status}</span>`
  ).join("\n");
  t.appendChild(div);
  t.scrollTop = t.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function sendPromptText(text) {
  if (!text.trim()) return;
  // Crée le chat automatiquement au premier message (titre = début du message).
  if (!currentInvestigationId) {
    const title = text.trim().slice(0, 48) + (text.trim().length > 48 ? "…" : "");
    try {
      const inv = await api("/investigations", {
        method: "POST",
        body: JSON.stringify({ title, reason: text.trim() }),
      });
      currentInvestigationId = inv.id;
      document.getElementById("transcript").innerHTML = "";
      loadInvestigations();
    } catch (e) { alert(e.message); return; }
  }
  addTurn("user", text);
  document.getElementById("prompt-input").value = "";
  autoGrow();
  const thinking = addTurn("assistant", "…");
  try {
    const result = await api("/prompt", {
      method: "POST",
      body: JSON.stringify({ investigation_id: currentInvestigationId, prompt: text }),
    });
    thinking.remove();
    addToolTrace(result.tool_calls);
    addTurn("assistant", result.reply || "(pas de réponse)");
    await refreshDetail();
  } catch (e) {
    thinking.innerHTML = `<span class="who">✻ ojd</span>\n<span class="err">Erreur : ${escapeHtml(e.message)}</span>`;
  }
}

// ---------- Composer ----------

const ta = document.getElementById("prompt-input");
function autoGrow() { ta.style.height = "22px"; ta.style.height = Math.min(ta.scrollHeight, 160) + "px"; }
ta.addEventListener("input", autoGrow);
ta.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendPromptText(ta.value); }
});
document.getElementById("send-btn").addEventListener("click", () => sendPromptText(ta.value));

// ---------- Voix (Web Speech API, local au navigateur) ----------

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null, recording = false;
if (SR) {
  recognizer = new SR();
  recognizer.lang = "fr-FR"; recognizer.interimResults = false; recognizer.maxAlternatives = 1;
  recognizer.onresult = (ev) => { const tr = ev.results[0][0].transcript; ta.value = tr; sendPromptText(tr); };
  recognizer.onend = () => { recording = false; document.getElementById("mic-btn").classList.remove("recording"); };
  recognizer.onerror = () => { recording = false; document.getElementById("mic-btn").classList.remove("recording"); };
}
document.getElementById("mic-btn").addEventListener("click", () => {
  if (!recognizer) { alert("Reconnaissance vocale non supportée (essaie Chrome)."); return; }
  if (recording) { recognizer.stop(); return; }
  recording = true; document.getElementById("mic-btn").classList.add("recording"); recognizer.start();
});

// ---------- Drawer (entités / audit) ----------

function toggleDrawer() { document.getElementById("drawer").classList.toggle("open"); }

function renderEntities(entities) {
  const c = document.getElementById("entities");
  c.innerHTML = entities && entities.length ? "" : '<div class="dim">aucune entité</div>';
  for (const e of (entities || [])) {
    const div = document.createElement("div");
    div.className = "card";
    let extra = "";
    if (e.extra && e.extra.output) extra = `<div class="dim" style="margin-top:4px;white-space:pre-wrap;max-height:120px;overflow:auto">${escapeHtml(e.extra.output.slice(0, 1500))}</div>`;
    div.innerHTML = `<div class="t">${e.type}</div><div>${escapeHtml(e.value)}</div><div class="dim">via ${e.source_module}</div>${extra}`;
    c.appendChild(div);
  }
}

function renderAudit(audit) {
  const c = document.getElementById("audit");
  c.innerHTML = audit && audit.length ? "" : '<div class="dim">aucun appel</div>';
  for (const a of (audit || []).slice().reverse()) {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<strong>${a.module}</strong> <span class="${a.status}">${a.status}</span><div class="dim">${escapeHtml(a.input_value)}</div><div class="dim" style="font-size:10px">${a.created_at}</div>`;
    c.appendChild(div);
  }
}

// ---------- Catalogue ----------

async function openCatalog() {
  document.getElementById("catalog-dialog").showModal();
  if (!catalogData) catalogData = await api("/catalog");
  renderCatalog();
}

function renderCatalog() {
  if (!catalogData) return;
  const q = document.getElementById("cat-search").value.toLowerCase().trim();
  const tools = catalogData.tools.filter(t =>
    !q || `${t.cmd} ${t.pkg} ${t.cat} ${t.sub} ${t.desc}`.toLowerCase().includes(q));
  document.getElementById("cat-stats").textContent =
    `${tools.length} affichés · ${catalogData.stats.installed}/${catalogData.stats.total} installés · ${catalogData.stats.runnable} lançables par l'IA`;
  const list = document.getElementById("cat-list");
  list.innerHTML = "";
  for (const t of tools.slice(0, 400)) {
    const row = document.createElement("div");
    row.className = "tool-row";
    const pill = t.runnable ? '<span class="pill run">IA</span>'
      : t.installed ? '<span class="pill inst">installé</span>'
      : '<span class="pill no">absent</span>';
    row.innerHTML = `<div class="cmd">${escapeHtml(t.cmd)}<div class="dim" style="font-size:10px">${escapeHtml(t.cat)}</div></div>` +
      `<div class="desc">${escapeHtml(t.desc)}</div>${pill}`;
    list.appendChild(row);
  }
}

// ---------- Paramètres ----------

async function openSettingsDialog() {
  const cfg = await api("/config");
  document.getElementById("cfg-provider").value = cfg.llm_provider;
  document.getElementById("cfg-ollama-model").value = cfg.ollama_model;
  document.getElementById("cfg-ollama-url").value = cfg.ollama_base_url;
  document.getElementById("cfg-anthropic-model").value = cfg.anthropic_model;
  document.getElementById("cfg-anthropic-key").value = "";
  document.getElementById("cfg-anthropic-key").placeholder = cfg.anthropic_api_key || "sk-ant-…";
  document.getElementById("cfg-ig-session").value = "";
  document.getElementById("cfg-ig-session").placeholder = cfg.module_config.instagram_sessionid || "";
  document.getElementById("settings-dialog").showModal();
}

async function saveSettings() {
  const body = {
    llm_provider: document.getElementById("cfg-provider").value,
    ollama_model: document.getElementById("cfg-ollama-model").value,
    ollama_base_url: document.getElementById("cfg-ollama-url").value,
    anthropic_model: document.getElementById("cfg-anthropic-model").value,
    module_config: {},
  };
  const key = document.getElementById("cfg-anthropic-key").value.trim();
  if (key) body.anthropic_api_key = key;
  const ig = document.getElementById("cfg-ig-session").value.trim();
  if (ig) body.module_config.instagram_sessionid = ig;
  try {
    await api("/config", { method: "PUT", body: JSON.stringify(body) });
    document.getElementById("settings-dialog").close();
  } catch (e) { alert(e.message); }
}

// ---------- Init ----------
loadStats();
newChat();
