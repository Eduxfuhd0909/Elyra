const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const listenButton = document.querySelector("#listenButton");
const speakToggleButton = document.querySelector("#speakToggleButton");
const clearButton = document.querySelector("#clearButton");
const themeToggleButton = document.querySelector("#themeToggleButton");
const openSettingsButton = document.querySelector("#openSettingsButton");
const closeSettingsButton = document.querySelector("#closeSettingsButton");
const cancelSettingsButton = document.querySelector("#cancelSettingsButton");
const settingsModal = document.querySelector("#settingsModal");
const modalBackdrop = document.querySelector("#modalBackdrop");
const settingsForm = document.querySelector("#settingsForm");
const providerSelect = document.querySelector("#providerSelect");
const baseUrlInput = document.querySelector("#baseUrlInput");
const apiKeyInput = document.querySelector("#apiKeyInput");
const loadModelsButton = document.querySelector("#loadModelsButton");
const modelSearchInput = document.querySelector("#modelSearchInput");
const modelList = document.querySelector("#modelList");
const modelInput = document.querySelector("#modelInput");
const systemPromptInput = document.querySelector("#systemPromptInput");
const connectionStatus = document.querySelector("#connectionStatus");
const currentModelLabel = document.querySelector("#currentModelLabel");

let providers = [];
let models = [];
let selectedModel = "";
let voiceEnabled = true;
let currentAudio = null;

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("elyra-theme", theme);
  themeToggleButton.textContent = theme === "dark" ? "Claro" : "Escuro";
}

function parsePayload(raw) {
  return typeof raw === "string" ? JSON.parse(raw) : raw;
}

function addMessage(role, content) {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = content;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

async function speakText(content) {
  if (!voiceEnabled || !content.trim()) {
    return;
  }

  try {
    const raw = await window.pywebview.api.speak_text(content);
    const response = parsePayload(raw);
    if (!response.ok) {
      addMessage("assistant", response.error || "Não consegui gerar voz.");
      return;
    }

    if (currentAudio) {
      currentAudio.pause();
    }

    currentAudio = new Audio(`data:${response.mime};base64,${response.audio}`);
    await currentAudio.play();
  } catch (error) {
    addMessage("assistant", "Erro ao tocar a voz da Elyra.");
  }
}

function selectedProvider() {
  return providers.find((provider) => provider.id === providerSelect.value);
}

function updateStatus() {
  const provider = selectedProvider();
  const providerName = provider ? provider.name : "Provedor";
  connectionStatus.textContent = `${providerName}${selectedModel ? " pronto" : " aguardando modelo"}`;
  currentModelLabel.textContent = selectedModel || "Nenhum modelo selecionado";
}

function openSettings() {
  settingsModal.classList.add("open");
  settingsModal.setAttribute("aria-hidden", "false");
  providerSelect.focus();
}

function closeSettings() {
  settingsModal.classList.remove("open");
  settingsModal.setAttribute("aria-hidden", "true");
  openSettingsButton.focus();
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
    empty.className = "empty-models";
    empty.textContent = models.length ? "Nenhum modelo encontrado." : "Carregue os modelos do provedor.";
    modelList.appendChild(empty);
    return;
  }

  filtered.forEach((model) => {
    const button = document.createElement("button");
    button.className = model.id === selectedModel ? "model-option active" : "model-option";
    button.type = "button";
    button.title = model.name;

    const label = document.createElement("span");
    label.textContent = model.name;
    button.appendChild(label);

    button.addEventListener("click", () => {
      selectedModel = model.id;
      modelInput.value = model.id;
      renderModels();
      saveSettings(false);
    });
    modelList.appendChild(button);
  });
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
    addMessage("assistant", "Configuração salva.");
    closeSettings();
  }

  return true;
}

async function loadModels() {
  loadModelsButton.disabled = true;
  loadModelsButton.textContent = "Carregando...";
  modelList.innerHTML = '<div class="empty-models">Buscando modelos...</div>';

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
    addMessage("assistant", `${models.length} modelo(s) carregado(s). Use a busca para encontrar o modelo exato.`);
  } catch (error) {
    models = [];
    renderModels();
    addMessage("assistant", "Erro ao carregar modelos. Verifique o terminal.");
  } finally {
    loadModelsButton.disabled = false;
    loadModelsButton.textContent = "Carregar modelos";
  }
}

async function sendMessage(content) {
  const saved = await saveSettings(false);
  if (!saved) {
    return;
  }

  addMessage("user", content);
  input.value = "";
  input.disabled = true;
  sendButton.disabled = true;
  sendButton.textContent = "Aguardando...";

  try {
    const raw = await window.pywebview.api.send_message(content);
    const response = parsePayload(raw);
    const reply = response.reply || "Não consegui responder agora.";
    addMessage("assistant", reply);
    if (response.ok) {
      speakText(reply);
    }
  } catch (error) {
    addMessage("assistant", "Erro ao falar com o Python. Verifique o terminal.");
  } finally {
    input.disabled = false;
    sendButton.disabled = false;
    sendButton.textContent = "Enviar";
    input.focus();
  }
}

async function listenOnce() {
  listenButton.disabled = true;
  listenButton.textContent = "Ouvindo...";
  input.placeholder = "Fale agora...";

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
    addMessage("assistant", "Erro ao acessar o microfone.");
  } finally {
    listenButton.disabled = false;
    listenButton.textContent = "Mic";
    input.placeholder = "Digite sua mensagem...";
  }
}

providerSelect.addEventListener("change", () => {
  const provider = selectedProvider();
  baseUrlInput.value = provider ? provider.base_url : "";
  apiKeyInput.placeholder = provider && provider.needs_key ? "Obrigatória para este provedor" : "Opcional para local";
  models = [];
  modelSearchInput.value = "";
  selectedModel = "";
  modelInput.value = "";
  renderModels();
  updateStatus();
});

modelSearchInput.addEventListener("input", renderModels);

modelInput.addEventListener("input", () => {
  selectedModel = modelInput.value.trim();
  renderModels();
  updateStatus();
});

loadModelsButton.addEventListener("click", loadModels);
listenButton.addEventListener("click", listenOnce);

themeToggleButton.addEventListener("click", () => {
  const currentTheme = document.documentElement.dataset.theme || "light";
  applyTheme(currentTheme === "dark" ? "light" : "dark");
});

speakToggleButton.addEventListener("click", () => {
  voiceEnabled = !voiceEnabled;
  speakToggleButton.classList.toggle("active", voiceEnabled);
  speakToggleButton.textContent = voiceEnabled ? "Voz" : "Mudo";
});

openSettingsButton.addEventListener("click", openSettings);
closeSettingsButton.addEventListener("click", closeSettings);
cancelSettingsButton.addEventListener("click", closeSettings);
modalBackdrop.addEventListener("click", closeSettings);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && settingsModal.classList.contains("open")) {
    closeSettings();
  }
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

clearButton.addEventListener("click", async () => {
  messages.innerHTML = "";
  await window.pywebview.api.clear_chat();
  addMessage("assistant", "Conversa limpa. Podemos começar de novo.");
});

window.addEventListener("pywebviewready", async () => {
  const savedTheme = localStorage.getItem("elyra-theme") || "light";
  applyTheme(savedTheme);

  const raw = await window.pywebview.api.get_providers();
  const response = parsePayload(raw);
  providers = response.providers;
  renderProviders(response.settings);
  renderModels();

  const historyRaw = await window.pywebview.api.get_history();
  const historyResponse = parsePayload(historyRaw);
  if (historyResponse.ok && historyResponse.history.length) {
    historyResponse.history.forEach((message) => addMessage(message.role, message.content));
  } else {
    addMessage("assistant", "Escolha um provedor, carregue os modelos e selecione o modelo que quer usar.");
  }

  input.focus();
});
