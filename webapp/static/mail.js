const state = {
  folder: "INBOX",
  messages: [],
  current: null,
  selectedUid: null,
  sending: false,
};

const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const statusEl = document.getElementById("status");
const previewFrame = document.getElementById("preview-frame");
const attachmentBar = document.getElementById("attachment-bar");

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.style.color = isError ? "#a00000" : "#404040";
}

function setActiveFolder(folder) {
  document.querySelectorAll("#folder-list li").forEach((item) => {
    item.classList.toggle("active", item.dataset.folder === folder);
  });
}

function previewPlaceholder(text) {
  return (
    "<!doctype html><html><body style='margin:0; background:#ffffff; "
    + "font-family:MS Sans Serif, Tahoma, Arial, sans-serif; font-size:13px; "
    + "color:#404040; padding:16px;'>"
    + text
    + "</body></html>"
  );
}

function renderLoadingRow(text = "Loading...") {
  const tbody = document.querySelector("#message-table tbody");
  tbody.innerHTML = "";

  const row = document.createElement("tr");
  row.classList.add("loading-row");

  const cell = document.createElement("td");
  cell.colSpan = 4;
  cell.textContent = text;

  row.appendChild(cell);
  tbody.appendChild(row);
}

async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = new Headers(options.headers || {});
  if (method !== "GET") {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    window.location.href = "/";
    throw new Error("Not authenticated");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return response.json();
}

async function loadFolders() {
  const data = await api("/api/folders");
  const list = document.getElementById("folder-list");
  list.innerHTML = "";

  for (const folder of data.folders) {
    const item = document.createElement("li");
    item.textContent = folder;
    item.dataset.folder = folder;
    if (folder === state.folder) {
      item.classList.add("active");
    }
    item.addEventListener("click", () => {
      state.folder = folder;
      state.selectedUid = null;
      state.current = null;
      setActiveFolder(folder);
      previewFrame.srcdoc = previewPlaceholder("Select a message.");
      attachmentBar.innerHTML = "";
      loadMessages(folder);
    });
    list.appendChild(item);
  }

  if (!data.folders.includes(state.folder) && data.folders.length > 0) {
    state.folder = data.folders[0];
  }
}

async function loadMessages(folder) {
  state.folder = folder;
  setStatus(`Loading ${folder}...`);
  state.messages = [];
  renderLoadingRow(`Loading ${folder}...`);

  try {
    const data = await api(`/api/messages?folder=${encodeURIComponent(folder)}`);
    state.messages = data.messages;
    renderMessages();
    setStatus(`${state.messages.length} message(s)`);
  } catch (error) {
    renderLoadingRow("Failed to load messages.");
    setStatus(`Failed to load messages: ${error.message}`, true);
  }
}

function renderMessages() {
  const tbody = document.querySelector("#message-table tbody");
  tbody.innerHTML = "";

  for (const message of state.messages) {
    const row = document.createElement("tr");
    if (message.uid === state.selectedUid) {
      row.classList.add("selected");
    }

    const statusCell = document.createElement("td");
    statusCell.textContent = message.seen ? "" : "●";
    statusCell.className = message.seen ? "" : "unread";

    const fromCell = document.createElement("td");
    fromCell.textContent = message.sender;

    const subjectCell = document.createElement("td");
    subjectCell.textContent = message.subject;

    const dateCell = document.createElement("td");
    dateCell.textContent = formatDate(message.date_iso || message.date);

    row.appendChild(statusCell);
    row.appendChild(fromCell);
    row.appendChild(subjectCell);
    row.appendChild(dateCell);

    row.addEventListener("click", () => showMessage(message.uid));
    tbody.appendChild(row);
  }
}

async function showMessage(uid, loadImages = false) {
  state.selectedUid = uid;
  renderMessages();
  previewFrame.srcdoc = previewPlaceholder(
    loadImages ? "Loading remote images..." : "Loading message..."
  );
  attachmentBar.innerHTML = "";
  setStatus(loadImages ? "Loading remote images..." : "Loading message...");

  try {
    const data = await api(
      `/api/messages/${uid}?folder=${encodeURIComponent(state.folder)}&load_images=${loadImages ? "1" : "0"}`
    );
    state.current = data;
    const existing = state.messages.find((message) => message.uid === uid);
    if (existing) {
      existing.seen = data.seen;
    }

    const dateText = formatDate(data.date_iso || data.date);
    const previewHtml = data.html.replace(
      /<b>Date:<\/b> [^<]*<br>/,
      `<b>Date:</b> ${dateText}<br>`
    );
    previewFrame.srcdoc = previewHtml;
    renderMessages();
    renderAttachments(data);
    setStatus("Message loaded");
  } catch (error) {
    previewFrame.srcdoc = previewPlaceholder("Failed to load message.");
    setStatus(`Failed to load message: ${error.message}`, true);
  }
}

function renderAttachments(data) {
  attachmentBar.innerHTML = "";

  for (const attachment of data.attachments) {
    const link = document.createElement("a");
    link.href = `/api/messages/${data.uid}/attachments/${attachment.index}?folder=${encodeURIComponent(state.folder)}`;
    link.textContent = attachment.filename;
    attachmentBar.appendChild(link);
  }

  const loadImagesBtn = document.createElement("button");
  loadImagesBtn.type = "button";
  loadImagesBtn.textContent = "Load Remote Images";
  loadImagesBtn.addEventListener("click", () => showMessage(data.uid, true));
  attachmentBar.appendChild(loadImagesBtn);

  const replyBtn = document.createElement("button");
  replyBtn.type = "button";
  replyBtn.textContent = "Reply";
  replyBtn.addEventListener("click", replyToCurrent);
  attachmentBar.appendChild(replyBtn);

  const unreadBtn = document.createElement("button");
  unreadBtn.type = "button";
  unreadBtn.textContent = "Mark Unread";
  unreadBtn.addEventListener("click", markUnread);
  attachmentBar.appendChild(unreadBtn);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", deleteCurrent);
  attachmentBar.appendChild(deleteBtn);
}

async function markUnread() {
  if (!state.current) return;
  try {
    await api(
      `/api/messages/${state.current.uid}/unseen?folder=${encodeURIComponent(state.folder)}`,
      { method: "POST" }
    );
    await loadMessages(state.folder);
  } catch (error) {
    setStatus(`Failed to mark unread: ${error.message}`, true);
  }
}

async function deleteCurrent() {
  if (!state.current) return;
  if (!confirm("Delete this message?")) return;

  try {
    await api(
      `/api/messages/${state.current.uid}?folder=${encodeURIComponent(state.folder)}`,
      { method: "DELETE" }
    );
    state.current = null;
    state.selectedUid = null;
    previewFrame.srcdoc = "";
    attachmentBar.innerHTML = "";
    await loadMessages(state.folder);
  } catch (error) {
    setStatus(`Delete failed: ${error.message}`, true);
  }
}

function replyToCurrent() {
  if (!state.current) return;

  const subject = state.current.subject.toLowerCase().startsWith("re:")
    ? state.current.subject
    : `Re: ${state.current.subject}`;

  const quoted = state.current.body_text
    ? state.current.body_text.split("\n").map((line) => `> ${line}`).join("\n")
    : "";

  const body =
    `\n\nOn ${formatDate(state.current.date_iso || state.current.date)}, ${state.current.sender} wrote:\n${quoted}`;

  openCompose({
    to: state.current.sender,
    subject,
    body,
    in_reply_to: state.current.message_id,
    references: state.current.message_id,
  });
}

function openCompose(prefill = {}) {
  const modal = document.getElementById("compose-modal");
  const form = document.getElementById("compose-form");

  form.querySelector("[name=to]").value = prefill.to || "";
  form.querySelector("[name=cc]").value = prefill.cc || "";
  form.querySelector("[name=subject]").value = prefill.subject || "";
  form.querySelector("[name=body]").value = prefill.body || "";
  document.getElementById("in_reply_to").value = prefill.in_reply_to || "";
  document.getElementById("references").value = prefill.references || "";

  modal.classList.remove("hidden");
}

function closeCompose() {
  document.getElementById("compose-modal").classList.add("hidden");
  document.getElementById("compose-form").reset();
  document.getElementById("in_reply_to").value = "";
  document.getElementById("references").value = "";
}

document.getElementById("new-btn").addEventListener("click", () => openCompose());
document.getElementById("refresh-btn").addEventListener("click", () => loadMessages(state.folder));
document.getElementById("compose-cancel").addEventListener("click", closeCompose);

document.getElementById("compose-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const sendButton = form.querySelector('button[type="submit"]');

  if (state.sending) return;

  state.sending = true;
  sendButton.disabled = true;
  sendButton.textContent = "Sending...";

  try {
    await api("/api/send", { method: "POST", body: new FormData(form) });
    closeCompose();
    setStatus("Message sent.");
    await loadMessages(state.folder);
  } catch (error) {
    setStatus(`Send failed: ${error.message}`, true);
  } finally {
    state.sending = false;
    sendButton.disabled = false;
    sendButton.textContent = "Send";
  }
});

loadFolders()
  .then(() => loadMessages(state.folder))
  .catch((error) => setStatus(error.message, true));
