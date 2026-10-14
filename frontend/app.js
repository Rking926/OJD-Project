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

const EXAMPLES = [
  "cherche le pseudo johndoe42 sur les réseaux",
  "reconnaissance du domaine exemple.com",
  "l'email test@exemple.com a-t-il fuité ?",
  "quels comptes existent pour cet email ?",
];

function renderWelcome() {
  const chips = EXAMPLES.map(e =>
    `<button class="chip" onclick="useExample('${escapeHtml(e).replace(/'/g, "\\'")}')">${escapeHtml(e)}</button>`
  ).join("");
  document.getElementById("transcript").innerHTML = `
    <div class="welcome">
      <b>✻ Nouveau chat</b>
      <div class="sub dim">Décris ta recherche en langage naturel — l'assistant choisit les bons outils. Le chat se nomme tout seul.</div>
      <div class="examples">${chips}</div>
    </div>`;
}

// Remplit le champ avec un exemple et place le curseur, prêt à envoyer.
function useExample(text) {
  const ta = document.getElementById("prompt-input");
  ta.value = text;
  ta.focus();
  autoGrow();
}

// Nouveau chat : on vide l'écran et on attend le premier message.
// L'enregistrement est créé automatiquement à l'envoi du premier message.
function newChat() {
  currentInvestigationId = null;
  const ta = document.getElementById("prompt-input");
  ta.value = "";
  ta.focus();
  renderWelcome();
  loadInvestigations();
  renderEntities([]);
}

async function selectInvestigation(id) {
  currentInvestigationId = id;
  document.getElementById("prompt-input").focus();
  document.getElementById("transcript").innerHTML = "";
  await loadInvestigations();
  await refreshDetail();
}

async function refreshDetail() {
  if (!currentInvestigationId) return;
  const d = await api(`/investigations/${currentInvestigationId}`);
  renderEntities(d.entities);
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
        body: JSON.stringify({ title }),
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

// ---------- Raccourcis clavier ----------

function openHelp() { document.getElementById("help-dialog").showModal(); }

function anyDialogOpen() {
  return [...document.querySelectorAll("dialog")].some(d => d.open);
}

document.addEventListener("keydown", (e) => {
  const el = document.activeElement;
  const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);

  // Échap : ferme le panneau résultats (les dialogs se ferment nativement).
  if (e.key === "Escape") {
    document.getElementById("drawer").classList.remove("open");
    return;
  }

  // Ctrl/Cmd+K : nouveau chat, même en cours de frappe.
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault(); newChat(); return;
  }

  // Les raccourcis à touche unique ne s'activent pas pendant la frappe
  // ni quand une fenêtre est ouverte.
  if (typing || anyDialogOpen() || e.ctrlKey || e.metaKey || e.altKey) return;

  switch (e.key) {
    case "n": e.preventDefault(); newChat(); break;
    case "k": e.preventDefault(); openCatalog(); break;
    case "t": e.preventDefault(); openTools(); break;
    case "r": e.preventDefault(); toggleDrawer(); break;
    case ",": e.preventDefault(); openSettingsDialog(); break;
    case "?": e.preventDefault(); openHelp(); break;
    case "/": e.preventDefault(); document.getElementById("prompt-input").focus(); break;
  }
});

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

// ---------- Mes outils (plugins) ----------

async function openTools() {
  document.getElementById("tools-dialog").showModal();
  await renderTools();
}

async function renderTools() {
  const listEl = document.getElementById("tools-list");
  const sbEl = document.getElementById("sandbox-status");
  try {
    const sb = await api("/sandbox");
    const iso = sb.isolated ? "✅ isolé" : "⚠ exécution directe (installe Docker pour isoler)";
    sbEl.innerHTML = `Sandbox : <b>${sb.backend}</b> — ${iso} · périmètre ${sb.enforce_scope ? "imposé" : "libre"}`;
  } catch { sbEl.textContent = ""; }

  const tools = await api("/tools");
  listEl.innerHTML = tools.length ? "" : '<div class="dim">aucun outil ajouté</div>';
  for (const t of tools) {
    const div = document.createElement("div");
    div.className = "cat-item";
    const warn = t.binary_installed ? "" : ' <span class="error">binaire absent</span>';
    div.innerHTML =
      `<div><b>${escapeHtml(t.name)}</b> <span class="dim">${escapeHtml(t.category)}</span>` +
      `${t.active ? ' <span class="dim">[actif]</span>' : ""}${warn}` +
      `<div class="dim" style="font-size:11px">${escapeHtml(t.description)}</div>` +
      `<div class="dim" style="font-size:10px">${escapeHtml(t.argv.join(" "))}</div></div>` +
      `<button class="ghost" onclick="deleteTool('${encodeURIComponent(t.name)}')">supprimer</button>`;
    listEl.appendChild(div);
  }
}

async function addTool() {
  const err = document.getElementById("t-error");
  err.textContent = "";
  const body = {
    name: document.getElementById("t-name").value.trim(),
    description: document.getElementById("t-desc").value.trim(),
    category: document.getElementById("t-cat").value.trim(),
    argv: document.getElementById("t-argv").value.trim(),
    active: document.getElementById("t-active").checked,
  };
  try {
    await api("/tools", { method: "POST", body: JSON.stringify(body) });
    document.getElementById("t-name").value = "";
    document.getElementById("t-desc").value = "";
    document.getElementById("t-cat").value = "";
    document.getElementById("t-argv").value = "";
    await renderTools();
  } catch (e) { err.textContent = e.message; }
}

async function deleteTool(name) {
  await api("/tools/" + name, { method: "DELETE" });
  await renderTools();
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
  document.getElementById("cfg-hibp-key").value = "";
  document.getElementById("cfg-hibp-key").placeholder = cfg.module_config.hibp_api_key || "clé HIBP…";
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
  const hibp = document.getElementById("cfg-hibp-key").value.trim();
  if (hibp) body.module_config.hibp_api_key = hibp;
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
