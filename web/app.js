/* ===== Gerenciador de Abas ===== */
class ChatTabManager {
  constructor() {
    this.chats = new Map();
    this.currentChatId = null;
    this.nextChatId = 1;
  }

  createChat(title = null) {
    const id = this.nextChatId++;
    const chat = {
      id,
      title: title || `Conversa ${id}`,
      messages: [],
      timestamp: Date.now(),
    };
    this.chats.set(id, chat);
    this.currentChatId = id;
    return id;
  }

  deleteChat(id) {
    this.chats.delete(id);
    if (this.currentChatId === id) {
      const firstChat = this.chats.entries().next().value;
      this.currentChatId = firstChat ? firstChat[0] : null;
    }
  }

  getChat(id) {
    return this.chats.get(id);
  }

  getCurrentChat() {
    return this.chats.get(this.currentChatId);
  }

  getAllChats() {
    return Array.from(this.chats.values()).sort((a, b) => b.timestamp - a.timestamp);
  }

  addMessage(chatId, role, content) {
    const chat = this.chats.get(chatId);
    if (chat) {
      chat.messages.push({ role, content, timestamp: Date.now() });
      chat.timestamp = Date.now();
    }
  }

  clearChat(id) {
    const chat = this.chats.get(id);
    if (chat) {
      chat.messages = [];
      chat.timestamp = Date.now();
    }
  }
}

/* ===== DOM Elements ===== */
const chatTabs = document.querySelector("#chatTabs");
const newChatBtn = document.querySelector("#newChatBtn");
const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendBtn = document.querySelector("#sendBtn");
const listenBtn = document.querySelector("#listenBtn");
const speakToggleBtn = document.querySelector("#speakToggleBtn");
const clearBtn = document.querySelector("#clearBtn");
const exportBtn = document.querySelector("#exportBtn");
const themeBtn = document.querySelector("#themeBtn");
const settingsBtn = document.querySelector("#settingsBtn");
const settingsModal = document.querySelector("#settingsModal");
const modalBackdrop = document.querySelector("#modalBackdrop");
const closeSettingsBtn = document.querySelector("#closeSettingsBtn");
const cancelSettingsBtn = document.querySelector("#cancelSettingsBtn");
const settingsForm = document.querySelector("#settingsForm");
const chatTitle = document.querySelector("#chatTitle");
const currentModelLabel = document.querySelector("#currentModelLabel");
const connectionStatus = document.querySelector("#connectionStatus");

const providerSelect = document.querySelector("#providerSelect");
const baseUrlInput = document.querySelector("#baseUrlInput");
const apiKeyInput = document.querySelector("#apiKeyInput");
const loadModelsBtn = document.querySelector("#loadModelsBtn");
const modelSearchInput = document.querySelector("#modelSearchInput");
const modelList = document.querySelector("#modelList");
const modelInput = document.querySelector("#modelInput");
const systemPromptInput = document.querySelector("#systemPromptInput");

/* ===== State ===== */
const tabManager = new ChatTabManager();
let providers = [];
let models = [];
let selectedModel = "";
let voiceEnabled = true;
let currentAudio = null;

/* ===== Initialization ===== */
function initializeChat() {
  tabManager.createChat("Conversa 1");
  renderChatTabs();
  displayCurrentChat();
}

/* ===== Theme ===== */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("elyra-theme", theme);
  themeBtn.textContent = theme === "dark" ? "☀️ Claro" : "🌙 Escuro";
}

/* ===== Chat Tabs ===== */
function renderChatTabs() {
  chatTabs.innerHTML = "";
  const chats = tabManager.getAllChats();

  chats.forEach((chat) => {
    const tab = document.createElement("button");
    tab.className = `chat-tab ${chat.id === tabManager.currentChatId ? "active" : ""}`;
    tab.textContent = chat.title;

    const closeBtn = document.createElement("button");
    closeBtn.className = "chat-tab-close";
    closeBtn.textContent = "×";
    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (chats.length > 1) {
        tabManager.deleteChat(chat.id);
        renderChatTabs();
        displayCurrentChat();
      }
    });

    tab.appendChild(closeBtn);
    tab.addEventListener("click", () => {
      tabManager.currentChatId = chat.id;
      renderChatTabs();
      displayCurrentChat();
    });

    chatTabs.appendChild(tab);
  });
}

function displayCurrentChat() {
  const chat = tabManager.getCurrentChat();
  if (!chat) return;

  chatTitle.textContent = chat.title;
  messages.innerHTML = "";

  chat.messages.forEach((msg) => {
    addMessageToDOM(msg.role, msg.content);
  });

  if (messages.scrollHeight > 0) {
    messages.scrollTop = messages.scrollHeight;
  }
}

/* ===== Messages ===== */
function addMessageToDOM(role, content) {
  const item = document.createElement("div");
  item.className = `message ${role}`;

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";
  contentDiv.textContent = content;

  item.appendChild(contentDiv);
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

function addMessage(role, content) {
  const chat = tabManager.getCurrentChat();
  if (chat) {
    tabManager.addMessage(chat.id, role, content);
    addMessageToDOM(role, content);
  }
}

/* ===== Settings Modal ===== */
function openSettings() {
  settingsModal.classList.add("active");
  settingsModal.setAttribute("aria-hidden", "false");
  providerSelect.focus();
}

function closeSettings() {
  settingsModal.classList.remove("active");
  settingsModal.setAttribute("aria-hidden", "true");
  settingsBtn.focus();
}

function parsePayload(raw) {
  return typeof raw === "string" ? JSON.parse(raw) : raw;
}

/* ===== Providers & Models ===== */
function selectedProvider() {
  return providers.find((provider) => provider.id === providerSelect.value);
}

function updateStatus() {
  const provider = selectedProvider();
  const providerName = provider ? provider.name : "Provedor";
  connectionStatus.textContent = selectedModel ? "✓ Pronto" : "⚠ Aguardando modelo";
  currentModelLabel.textContent = selectedModel || "Nenhum modelo";
}

function renderProviders(settings) {
  providerSelect.innerHTML = "";

  providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.name;
    providerSelect.appendChild(option);
  });

  providerSelect.value = settings.provider_id;
  baseUrlInput.value = settings.base_url;
  apiKeyInput.value = settings.api_key;
  modelInput.value = settings.model;
  systemPromptInput.value = settings.system_prompt || "";
  selectedModel = settings.model;

  const provider = selectedProvider();
  apiKeyInput.placeholder = provider && provider.needs_key ? "Obrigatória para este provedor" : "Opcional para local";
  updateStatus();
}

function renderModels() {
  const query = modelSearchInput.value.trim().toLowerCase();
  const filtered = models.filter((model) => model.name.toLowerCase().includes(query));

  modelList.innerHTML = "";

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.style.padding = "12px";
    empty.style.color = "var(--text-tertiary)";
    empty.style.textAlign = "center";
    empty.textContent = models.length ? "Nenhum modelo encontrado." : "Carregue os modelos do provedor.";
    modelList.appendChild(empty);
    return;
  }

  filtered.forEach((model) => {
    const button = document.createElement("button");
    button.className = `model-option ${model.id === selectedModel ? "selected" : ""}`;
    button.type = "button";
    button.textContent = model.name;
    button.title = model.name;

    button.addEventListener("click", () => {
      selectedModel = model.id;
      modelInput.value = model.id;
      renderModels();
      saveSettings(false);
    });

    modelList.appendChild(button);
  });
}

async function loadModels() {
  loadModelsBtn.disabled = true;
  loadModelsBtn.textContent = "Carregando...";

  try {
    const raw = await window.pywebview.api.list_models(
      providerSelect.value,
      baseUrlInput.value,
      apiKeyInput.value,
    );
    const response = parsePayload(raw);

    if (!response.ok) {
      models = [];
      renderModels();
      addMessage("assistant", response.error || "Não consegui carregar os modelos.");
      return;
    }

    models = response.models;
    renderModels();
    addMessage("assistant", `✓ ${models.length} modelo(s) carregado(s).`);
  } catch (error) {
    models = [];
    renderModels();
    addMessage("assistant", "❌ Erro ao carregar modelos. Verifique o terminal.");
  } finally {
    loadModelsBtn.disabled = false;
    loadModelsBtn.textContent = "Carregar modelos";
  }
}

async function saveSettings(showMessage = true) {
  const raw = await window.pywebview.api.save_settings(
    providerSelect.value,
    baseUrlInput.value,
    apiKeyInput.value,
    modelInput.value,
    systemPromptInput.value,
  );
  const response = parsePayload(raw);

  if (!response.ok) {
    addMessage("assistant", response.error || "Não consegui salvar a configuração.");
    return false;
  }

  selectedModel = response.settings.model;
  updateStatus();

  if (showMessage) {
    addMessage("assistant", "✓ Configuração salva.");
    closeSettings();
  }

  return true;
}

/* ===== Voice ===== */
async function speakText(content) {
  if (!voiceEnabled || !content.trim()) {
    return;
  }

  try {
    const raw = await window.pywebview.api.speak_text(content);
    const response = parsePayload(raw);

    if (!response.ok) {
      return;
    }

    if (currentAudio) {
      currentAudio.pause();
    }

    currentAudio = new Audio(`data:${response.mime};base64,${response.audio}`);
    await currentAudio.play();
  } catch (error) {
    console.error("Erro ao tocar áudio:", error);
  }
}

async function listenOnce() {
  listenBtn.disabled = true;
  listenBtn.textContent = "🔴 Ouvindo...";

  try {
    const raw = await window.pywebview.api.listen_once();
    const response = parsePayload(raw);

    if (!response.ok) {
      addMessage("assistant", response.error || "Não consegui ouvir.");
      return;
    }

    input.value = response.text;
    await sendMessage(response.text);
  } catch (error) {
    addMessage("assistant", "❌ Erro ao acessar o microfone.");
  } finally {
    listenBtn.disabled = false;
    listenBtn.textContent = "🎤";
  }
}

/* ===== Chat ===== */
async function sendMessage(content) {
  const saved = await saveSettings(false);
  if (!saved) {
    return;
  }

  addMessage("user", content);
  input.value = "";
  input.disabled = true;
  sendBtn.disabled = true;
  sendBtn.textContent = "Enviando...";

  try {
    const raw = await window.pywebview.api.send_message(content);
    const response = parsePayload(raw);
    const reply = response.reply || "Não consegui responder agora.";
    addMessage("assistant", reply);
    if (response.ok) {
      speakText(reply);
    }
  } catch (error) {
    addMessage("assistant", "❌ Erro ao falar com o Python. Verifique o terminal.");
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    sendBtn.textContent = "Enviar";
    input.focus();
  }
}

/* ===== Export ===== */
function exportChat() {
  const chat = tabManager.getCurrentChat();
  if (!chat || !chat.messages.length) {
    addMessage("assistant", "Nenhuma conversa para exportar.");
    return;
  }

  const content = [
    `# ${chat.title}`,
    `Data: ${new Date(chat.timestamp).toLocaleString("pt-BR")}`,
    `Modelo: ${selectedModel}`,
    "",
  ];

  chat.messages.forEach((msg) => {
    content.push(`**${msg.role === "user" ? "Você" : "Elyra"}:**`);
    content.push(msg.content);
    content.push("");
  });

  const blob = new Blob([content.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `elyra-${chat.id}-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);

  addMessage("assistant", "✓ Conversa exportada como Markdown.");
}

/* ===== Event Listeners ===== */
newChatBtn.addEventListener("click", () => {
  tabManager.createChat();
  renderChatTabs();
  displayCurrentChat();
  input.focus();
});

clearBtn.addEventListener("click", async () => {
  if (!tabManager.getCurrentChat().messages.length) return;
  tabManager.clearChat(tabManager.currentChatId);
  messages.innerHTML = "";
  await window.pywebview.api.clear_chat();
  addMessage("assistant", "✓ Conversa limpa.");
});

exportBtn.addEventListener("click", exportChat);

themeBtn.addEventListener("click", () => {
  const currentTheme = document.documentElement.dataset.theme || "light";
  applyTheme(currentTheme === "dark" ? "light" : "dark");
});

settingsBtn.addEventListener("click", openSettings);
closeSettingsBtn.addEventListener("click", closeSettings);
cancelSettingsBtn.addEventListener("click", closeSettings);
modalBackdrop.addEventListener("click", closeSettings);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && settingsModal.classList.contains("active")) {
    closeSettings();
  }
});

providerSelect.addEventListener("change", () => {
  const provider = selectedProvider();
  baseUrlInput.value = provider ? provider.base_url : "";
  apiKeyInput.placeholder = provider && provider.needs_key ? "Obrigatória" : "Opcional";
  models = [];
  modelSearchInput.value = "";
  selectedModel = "";
  modelInput.value = "";
  renderModels();
  updateStatus();
});

modelSearchInput.addEventListener("input", renderModels);
loadModelsBtn.addEventListener("click", loadModels);
listenBtn.addEventListener("click", listenOnce);

speakToggleBtn.addEventListener("click", () => {
  voiceEnabled = !voiceEnabled;
  speakToggleBtn.classList.toggle("active", voiceEnabled);
  speakToggleBtn.textContent = voiceEnabled ? "🔊" : "🔇";
});

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveSettings(true);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (content) {
    sendMessage(content);
  }
});

/* ===== Initialization on Ready ===== */
window.addEventListener("pywebviewready", async () => {
  initializeChat();

  const savedTheme = localStorage.getItem("elyra-theme") || "light";
  applyTheme(savedTheme);

  try {
    const raw = await window.pywebview.api.get_providers();
    const response = parsePayload(raw);
    providers = response.providers;
    renderProviders(response.settings);
    renderModels();

    const historyRaw = await window.pywebview.api.get_history();
    const historyResponse = parsePayload(historyRaw);
    if (historyResponse.ok && historyResponse.history.length) {
      const chat = tabManager.getCurrentChat();
      historyResponse.history.forEach((message) => {
        tabManager.addMessage(chat.id, message.role, message.content);
        addMessageToDOM(message.role, message.content);
      });
    } else {
      addMessage("assistant", "Bem-vindo à Elyra! Configure um provedor e selecione um modelo para começar.");
    }
  } catch (error) {
    console.error("Erro ao carregar configurações:", error);
    addMessage("assistant", "❌ Erro ao carregar configurações. Verifique o terminal.");
  }

  input.focus();
});
