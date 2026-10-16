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

// Liste en lignes SwipeRow (React Bits) : clic = ouvrir, glisser à gauche =
// Renommer / Supprimer (voir reactbits/src/ConversationList.jsx).
let convList = null;
async function loadInvestigations() {
  const items = await api("/investigations");
  const props = {
    items,
    activeId: currentInvestigationId,
    onSelect: (id) => selectInvestigation(id),
    onRename: (id, title) => renameInvestigation(id, title),
    onDelete: (id) => deleteInvestigation(id),
  };
  if (convList) convList.update(props);
  else convList = ReactBits.mount("ConversationList", document.getElementById("investigation-list"), props);
}

async function renameInvestigation(id, title) {
  try {
    await api(`/investigations/${id}`, { method: "PUT", body: JSON.stringify({ title }) });
  } catch (e) { alert(e.message); }
  loadInvestigations();
}

async function deleteInvestigation(id) {
  try {
    await api(`/investigations/${id}`, { method: "DELETE" });
  } catch (e) { alert(e.message); }
  if (id === currentInvestigationId) newChat();
  else loadInvestigations();
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
  setPrompt(text);
  focusPrompt();
}

// Nouveau chat : on vide l'écran et on attend le premier message.
// L'enregistrement est créé automatiquement à l'envoi du premier message.
function newChat() {
  currentInvestigationId = null;
  setPrompt("");
  focusPrompt();
  renderWelcome();
  loadInvestigations();
  renderEntities([]);
}

async function selectInvestigation(id) {
  currentInvestigationId = id;
  focusPrompt();
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
  const loader = addLoader({ label: "Recherche" });
  const signal = startBusy();
  try {
    const result = await api("/prompt", {
      method: "POST",
      signal,
      body: JSON.stringify({ investigation_id: currentInvestigationId, prompt: text }),
    });
    loader.finish("done");
    addToolTrace(result.tool_calls);
    addTurn("assistant", result.reply || "(pas de réponse)");
    await refreshDetail();
  } catch (e) {
    loader.finish("error", e);
  } finally {
    endBusy();
  }
}

// ---------- Composer : PromptBar (React Bits) ----------
// Le composant gère lui-même son texte ; on passe par le <textarea> qu'il
// rend pour le pré-remplir (exemples, dictée) en simulant une saisie.

const COMMANDS = [
  { key: "enquete", name: "/enquete", description: "Enquête complète automatique (tous les outils)" },
  { key: "graphe", name: "/graphe", description: "Ouvrir le graphe des relations" },
  { key: "resultats", name: "/resultats", description: "Afficher les entités trouvées" },
  { key: "nouveau", name: "/nouveau", description: "Démarrer un nouveau chat" },
];

const ACCEPT_ICONS = { username: "user", email: "mail", domain: "globe", ip: "server", phone: "phone", url: "globe" };

function promptEl() { return document.querySelector("#prompt-bar .prompt-bar__input"); }
function focusPrompt() { promptEl()?.focus({ preventScroll: true }); }
function setPrompt(text) {
  const el = promptEl();
  if (!el) return;
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(el, text);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function handleSend(text) {
  const m = /^\/(\w+)\s*(.*)$/s.exec(text);
  switch (m && m[1].toLowerCase()) {
    case "enquete": return runPlaybook(m[2]);
    case "graphe": return openGraph();
    case "resultats": return toggleDrawer();
    case "nouveau": return newChat();
    default: return sendPromptText(text);
  }
}

let pending = null; // AbortController de la requête en cours
const promptBar = ReactBits.mount("PromptBar", document.getElementById("prompt-bar"), {
  placeholder: "Décris ta recherche…  (@ outil · / commande)",
  sources: [],
  commands: COMMANDS,
  models: [],
  efforts: [],
  width: 4000,
  onSend: (text) => handleSend(text),
  onStop: () => pending?.abort(),
});

function startBusy() {
  pending = new AbortController();
  promptBar.update({ busy: true });
  return pending.signal;
}
function endBusy() {
  pending = null;
  promptBar.update({ busy: false });
}

// Les modules OSINT deviennent les sources du menu « + » / « @ ».
api("/modules").then((mods) => {
  promptBar.update({
    sources: mods.map((m) => ({
      key: m.name,
      name: m.name,
      description: m.description.length > 46 ? m.description.slice(0, 45) + "…" : m.description,
      icon: ACCEPT_ICONS[m.accepts[0]] || "tool",
    })),
  });
}).catch(() => {});

// ---------- Indicateur de travail : LatticeLoader (React Bits) ----------

function addLoader({ label, pattern = "orbit", grid = 3 }) {
  const t = document.getElementById("transcript");
  const div = document.createElement("div");
  div.className = "turn loader";
  const host = document.createElement("span");
  div.appendChild(host);
  t.appendChild(div);
  t.scrollTop = t.scrollHeight;
  const ll = ReactBits.mount("LatticeLoader", host, {
    label, pattern, grid, doneLabel: "Terminé en", errorLabel: "Échec après", fontSize: 13, color: "#a5d8ff",
  });
  return {
    finish(status, err) {
      const stopped = err && err.name === "AbortError";
      ll.update({ status, errorLabel: stopped ? "Arrêté après" : "Échec après" });
      if (err && !stopped) {
        const e = document.createElement("div");
        e.className = "err";
        e.textContent = "Erreur : " + err.message;
        div.appendChild(e);
      }
    },
  };
}

// ---------- Enquête autonome (playbook) ----------

async function runPlaybook(seed) {
  seed = (seed || "").trim();
  if (!seed) { setPrompt("/enquete "); focusPrompt(); return; }
  if (!currentInvestigationId) {
    try {
      const inv = await api("/investigations", {
        method: "POST",
        body: JSON.stringify({ title: "Enquête: " + seed.slice(0, 40) }),
      });
      currentInvestigationId = inv.id;
      document.getElementById("transcript").innerHTML = "";
      loadInvestigations();
    } catch (e) { alert(e.message); return; }
  }
  addTurn("user", "🔎 Enquête complète sur : " + seed);
  const loader = addLoader({ label: "Enquête autonome", pattern: "sweep", grid: 4 });
  const signal = startBusy();
  try {
    const r = await api("/playbook", {
      method: "POST",
      signal,
      body: JSON.stringify({ investigation_id: currentInvestigationId, seed_value: seed }),
    });
    loader.finish("done");
    addToolTrace(r.tool_calls);
    addTurn("assistant", r.reply || "(pas de dossier)");
    await refreshDetail();
  } catch (e) {
    loader.finish("error", e);
  } finally {
    endBusy();
  }
}

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
    case "g": e.preventDefault(); openGraph(); break;
    case ",": e.preventDefault(); openSettingsDialog(); break;
    case "?": e.preventDefault(); openHelp(); break;
    case "/": e.preventDefault(); focusPrompt(); break;
  }
});

// ---------- Voix : VoicePill (React Bits) + Web Speech API ----------
// Appui court = démarrer/arrêter, appui long = parler tant qu'on maintient,
// glisser à gauche = annuler. Le texte dicté est ajouté dans la barre.

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null, voiceOn = false, voiceCancelled = false, heard = "";
if (SR) {
  recognizer = new SR();
  recognizer.lang = "fr-FR"; recognizer.continuous = true; recognizer.interimResults = false;
  recognizer.onresult = (ev) => {
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      if (ev.results[i].isFinal) heard += (heard ? " " : "") + ev.results[i][0].transcript.trim();
    }
  };
  recognizer.onend = () => {
    if (voiceOn) { try { recognizer.start(); } catch {} return; } // coupure auto du navigateur
    if (!voiceCancelled && heard) {
      const cur = promptEl()?.value.trim() || "";
      setPrompt(cur ? cur + " " + heard : heard);
      focusPrompt();
    }
  };
}

ReactBits.mount("VoicePill", document.getElementById("voice-pill"), {
  reactive: "mic",
  disabled: !SR,
  ariaLabel: SR ? "Dicter (voix)" : "Dictée non supportée (essaie Chrome)",
  onStart: () => {
    voiceOn = true; voiceCancelled = false; heard = "";
    try { recognizer.start(); } catch {}
  },
  onStop: ({ reason }) => {
    voiceOn = false;
    voiceCancelled = ["cancel", "escape", "mic-denied", "unmount", "disabled"].includes(reason);
    if (voiceCancelled) recognizer.abort(); else recognizer.stop();
    if (reason === "mic-denied") alert("Micro refusé : autorise l'accès au micro pour dicter.");
  },
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
    if (e.extra && e.extra.output) extra = `<div class="dim" style="margin-top:6px;white-space:pre-wrap;max-height:120px;overflow:auto;font-family:var(--mono)">${escapeHtml(e.extra.output.slice(0, 1500))}</div>`;
    const conf = (e.confidence >= 0.9) ? '<span class="badge high">fiable</span>' : '<span class="badge med">à vérifier</span>';
    div.innerHTML = `<div class="t">${escapeHtml(e.type)}</div>`
      + `<div style="margin:4px 0;word-break:break-all;font-family:var(--mono)">${escapeHtml(e.value)}</div>`
      + `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><span class="badge">${escapeHtml(e.source_module)}</span>${conf}</div>${extra}`;
    c.appendChild(div);
  }
}

// ---------- Graphe des liens (Cytoscape) ----------

const TYPE_COLORS = {
  username: "#d97757", email: "#7fb069", phone: "#e0a458", domain: "#6db3d9",
  person: "#cc99e0", location: "#e07a9a", ip: "#9a9088", url: "#8fbf9f",
  breach: "#e05c5c", other: "#9a9088",
};
let cyInstance = null;

async function openGraph() {
  document.getElementById("graph-dialog").showModal();
  const cont = document.getElementById("cy");
  if (!currentInvestigationId) {
    cont.innerHTML = '<div class="dim" style="padding:20px">Aucune enquête sélectionnée.</div>';
    return;
  }
  const d = await api(`/investigations/${currentInvestigationId}`);
  renderGraph(d.entities || [], d.relations || []);
}

function renderGraph(entities, relations) {
  const cont = document.getElementById("cy");
  const legend = document.getElementById("graph-legend");
  const ids = new Set(entities.map(e => e.id));
  const elements = [];
  for (const e of entities) {
    elements.push({ data: { id: e.id, label: (e.value || "").slice(0, 30), type: e.type, src: e.source_module } });
  }
  for (const r of relations) {
    if (ids.has(r.from) && ids.has(r.to)) {
      elements.push({ data: { id: r.id, source: r.from, target: r.to, label: r.label } });
    }
  }

  const types = [...new Set(entities.map(e => e.type))];
  legend.innerHTML = types.map(t =>
    `<span style="color:${TYPE_COLORS[t] || "#9a9088"}">● ${escapeHtml(t)}</span>`).join("");

  if (cyInstance) { cyInstance.destroy(); cyInstance = null; }
  if (!elements.length) {
    cont.innerHTML = '<div class="dim" style="padding:20px">Aucune entité à afficher. Lance une recherche d\'abord.</div>';
    return;
  }
  cont.innerHTML = "";
  cyInstance = cytoscape({
    container: cont,
    elements,
    style: [
      { selector: "node", style: {
        "background-color": (ele) => TYPE_COLORS[ele.data("type")] || "#9a9088",
        "label": "data(label)", "color": "#e8e3da", "font-size": "9px",
        "font-family": "monospace", "text-valign": "bottom", "text-margin-y": "4px",
        "width": "18px", "height": "18px", "border-width": 1, "border-color": "#1a1816",
      }},
      { selector: "edge", style: {
        "width": 1, "line-color": "#4a443d", "target-arrow-color": "#4a443d",
        "target-arrow-shape": "triangle", "curve-style": "bezier", "arrow-scale": 0.7,
        "label": "data(label)", "font-size": "7px", "color": "#9a9088", "text-rotation": "autorotate",
      }},
    ],
    layout: { name: "cose", animate: false, padding: 24, nodeRepulsion: 6000, idealEdgeLength: 70 },
  });
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

// ---------- Fond : GradientASCII (React Bits, voir GradientASCII.js) ----------
(function () {
  const el = document.getElementById("ascii-bg");
  if (!el || !window.GradientASCII) return;
  GradientASCII.mount(el, {
    colors: ["#1e3fd8", "#f6f8ff", "#a5d8ff", "#38bdf8"],
    shape: "horizon",
    characters: " =+xX0S8#@",
    cellSize: 18,
    density: 0.8,
  });
})();

// ---------- Init ----------
loadStats();
newChat();
