const IMPORT_PREFIX =
    document.body?.dataset.importPrefix || "__PYLOGUE_IMPORT__:";
const API_BASE = document.body?.dataset.apiBase || "";
if (document.body) {
    document.body.dataset.disableCoreDownload = "true";
}
let chatIndex = [];
const MOBILE_QUERY = "(max-width: 920px)";
let deleteDialogResolver = null;
let deleteDialogLastFocus = null;

const TRASH_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M3 6h18"/>
  <path d="M8 6V4h8v2"/>
  <path d="M6 6l1 14h10l1-14"/>
  <path d="M10 11v6"/>
  <path d="M14 11v6"/>
</svg>`;

const PENCIL_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M12 20h9"/>
  <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z"/>
</svg>`;

const api = {
    async listChats() {
        const res = await fetch(`${API_BASE}/api/chats`);
        return res.ok ? res.json() : [];
    },
    async createChat() {
        const res = await fetch(`${API_BASE}/api/chats`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: "New chat" }),
        });
        return res.ok ? res.json() : null;
    },
    async getChat(chatId) {
        const res = await fetch(`${API_BASE}/api/chats/${chatId}`);
        return res.ok ? res.json() : { cards: [] };
    },
    async saveChat(chatId, payload, title) {
        const res = await fetch(`${API_BASE}/api/chats/${chatId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ payload, title }),
        });
        return res.ok ? res.json() : null;
    },
    async deleteChat(chatId) {
        const res = await fetch(`${API_BASE}/api/chats/${chatId}`, { method: "DELETE" });
        return res.ok;
    },
};

const setActiveChatId = (chatId) => {
    document.body.dataset.activeChat = chatId;
};

const getActiveChatId = () => document.body.dataset.activeChat || "";

const setActiveChatTitle = (title) => {
    document.body.dataset.activeChatTitle = title || "";
};

const getActiveChatTitle = () => {
    const activeId = getActiveChatId();
    if (!activeId) return "";
    const chat = getChatById(activeId);
    return chat?.title || "";
};

const isMobile = () => window.matchMedia(MOBILE_QUERY).matches;

const openHistory = () => {
    document.body.classList.add("history-open");
};

const closeHistory = () => {
    document.body.classList.remove("history-open");
};

const toggleHistory = () => {
    document.body.classList.toggle("history-open");
};

const openProfile = () => {
    document.body.classList.add("profile-open");
};

const closeProfile = () => {
    document.body.classList.remove("profile-open");
};

const toggleProfile = () => {
    document.body.classList.toggle("profile-open");
};

const getDeleteModal = () => document.getElementById("delete-chat-modal");

const isDeleteModalOpen = () => {
    const modal = getDeleteModal();
    return !!modal && modal.classList.contains("is-open");
};

const closeDeleteDialog = (confirmed) => {
    const modal = getDeleteModal();
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    if (
        deleteDialogLastFocus &&
        typeof deleteDialogLastFocus.focus === "function"
    ) {
        deleteDialogLastFocus.focus();
    }
    deleteDialogLastFocus = null;
    if (deleteDialogResolver) {
        deleteDialogResolver(Boolean(confirmed));
        deleteDialogResolver = null;
    }
};

const openDeleteDialog = (title) =>
    new Promise((resolve) => {
        const modal = getDeleteModal();
        const nameEl = document.getElementById("delete-chat-name");
        if (!modal || !nameEl) {
            resolve(false);
            return;
        }
        deleteDialogLastFocus = document.activeElement;
        nameEl.textContent = `"${title}"`;
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        deleteDialogResolver = resolve;
        const cancelBtn = document.getElementById("delete-chat-cancel-btn");
        cancelBtn?.focus();
    });

const renderChatList = (index) => {
    const list = document.getElementById("chat-list");
    if (!list) return;

    const searchInput = document.getElementById("chat-search");
    const searchTerm = searchInput
        ? searchInput.value.toLowerCase().trim()
        : "";

    const filteredIndex = searchTerm
        ? index.filter((chat) =>
              (chat.title || "").toLowerCase().includes(searchTerm),
          )
        : index;

    list.innerHTML = "";

    if (filteredIndex.length === 0 && searchTerm) {
        const noResults = document.createElement("div");
        noResults.style.cssText =
            "text-align: center; padding: 40px 20px; color: #6B7280; font-size: 0.9rem;";
        noResults.textContent = "No chats found";
        list.appendChild(noResults);
        return;
    }

    const active = getActiveChatId();
    filteredIndex.forEach((chat) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chat-item" + (chat.id === active ? " is-active" : "");
        btn.dataset.chatId = chat.id;
        btn.innerHTML = `
      <div class="chat-item-main">
        <div class="chat-item-title" data-chat-title="true">${chat.title}</div>
        <div class="chat-item-meta">${formatTime(chat.updated_at)}</div>
      </div>
      <div class="chat-item-actions">
        <span class="chat-item-edit" title="Edit title" aria-label="Edit title">${PENCIL_SVG}</span>
        <span class="chat-item-delete" title="Delete chat" aria-label="Delete chat">${TRASH_SVG}</span>
      </div>
    `;
        btn.addEventListener("click", () => selectChat(chat.id));
        const titleEl = btn.querySelector('[data-chat-title="true"]');
        const edit = btn.querySelector(".chat-item-edit");
        edit?.addEventListener("click", (event) => {
            event.stopPropagation();
            beginTitleEdit(chat.id, titleEl);
        });
        const del = btn.querySelector(".chat-item-delete");
        del?.addEventListener("click", (event) => {
            event.stopPropagation();
            confirmDelete(chat.id, chat.title || "this chat");
        });
        list.appendChild(btn);
    });
};

const formatTime = (iso) => {
    if (!iso) return "";
    try {
        const date = new Date(iso);
        return date.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch (err) {
        return "";
    }
};

const getChatById = (chatId) => chatIndex.find((c) => c.id === chatId);

const deriveTitle = (cards, currentTitle) => {
    if (currentTitle && currentTitle !== "New chat") return currentTitle;
    if (!cards || !cards.length) return currentTitle || "New chat";
    const first = cards[0]?.question || "";
    return first ? first.slice(0, 48) : currentTitle || "New chat";
};

const beginTitleEdit = (chatId, titleEl) => {
    if (!titleEl) return;
    const current = getChatById(chatId);
    if (!current) return;

    // Find the parent button and disable it during edit
    const parentButton = titleEl.closest("button");
    const wasDisabled = parentButton ? parentButton.disabled : false;
    if (parentButton) {
        parentButton.disabled = true;
        parentButton.style.pointerEvents = "none";
    }

    const input = document.createElement("input");
    input.className = "chat-title-input";
    input.type = "text";
    input.value = current.title || "New chat";
    input.setAttribute("aria-label", "Edit chat title");
    input.style.pointerEvents = "auto"; // Ensure input is still interactive
    titleEl.replaceWith(input);
    input.focus();
    input.setSelectionRange(0, input.value.length);

    const finish = async (commit) => {
        // Re-enable the button
        if (parentButton) {
            parentButton.disabled = wasDisabled;
            parentButton.style.pointerEvents = "";
        }

        const nextTitle = commit
            ? input.value.trim()
            : current.title || "New chat";
        const finalTitle = nextTitle || "New chat";
        if (commit && finalTitle !== current.title) {
            const payload = await api.getChat(chatId);
            const saved = await api.saveChat(chatId, payload, finalTitle);
            if (saved) {
                const idx = chatIndex.findIndex((c) => c.id === chatId);
                if (idx !== -1) {
                    chatIndex[idx] = { ...chatIndex[idx], ...saved };
                }
            }
        }
        if (chatId === getActiveChatId()) {
            setActiveChatTitle(finalTitle);
        }
        renderChatList(chatIndex);
    };

    // Stop all events from bubbling to parent button
    input.addEventListener("click", (event) => {
        event.stopPropagation();
    });
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            event.stopPropagation();
            finish(true);
        } else if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            finish(false);
        }
        // Don't stop propagation for other keys - let them work normally
    });
    input.addEventListener("blur", () => finish(true));
};

const sendImport = (payload) => {
    const form = document.getElementById("form");
    const msg = document.getElementById("msg");
    if (!form || !msg) return;
    const previous = msg.value;
    msg.value = IMPORT_PREFIX + JSON.stringify(payload || []);
    htmx.trigger(form, "submit");
    // Reset the value after a short delay to allow htmx to read it
    setTimeout(() => {
        msg.value = previous;
    }, 50);
};

const selectChat = async (chatId) => {
    const chat = getChatById(chatId);
    if (!chat) return;
    setActiveChatId(chatId);
    setActiveChatTitle(chat.title || "New chat");
    renderChatList(chatIndex);
    const payload = await api.getChat(chatId);
    sendImport(payload);
    // Allow time for htmx to swap content before scrolling
    setTimeout(() => {
        scrollToBottom();
    }, 100);
    closeHistory();
    closeProfile();
};

const createChat = async () => {
    const chat = await api.createChat();
    if (!chat) return;
    chatIndex = [chat, ...chatIndex];
    setActiveChatId(chat.id);
    setActiveChatTitle(chat.title || "New chat");
    renderChatList(chatIndex);
    sendImport({ cards: [] });
    setTimeout(() => {
        scrollToBottom();
    }, 100);
    closeHistory();
    closeProfile();
};

const confirmDelete = async (chatId, title) => {
    const ok = await openDeleteDialog(title);
    if (!ok) return;
    const success = await api.deleteChat(chatId);
    if (!success) return;
    chatIndex = chatIndex.filter((c) => c.id !== chatId);
    const active = getActiveChatId();
    if (active === chatId) {
        const next = chatIndex[0]?.id || "";
        if (next) {
            setActiveChatId(next);
            renderChatList(chatIndex);
            await selectChat(next);
        } else {
            setActiveChatId("");
            renderChatList(chatIndex);
            sendImport({ cards: [] });
        }
        return;
    }
    renderChatList(chatIndex);
};

const saveCurrentChat = async () => {
    const chatId = getActiveChatId();
    if (!chatId) return;
    const exportEl = document.getElementById("chat-export");
    if (!exportEl || !exportEl.value) return;
    let payload = null;
    try {
        payload = JSON.parse(exportEl.value);
    } catch (err) {
        return;
    }
    const current = getChatById(chatId);
    const title = deriveTitle(payload.cards || [], current?.title);
    const saved = await api.saveChat(chatId, payload, title);
    if (saved) {
        const idx = chatIndex.findIndex((c) => c.id === chatId);
        if (idx !== -1) {
            chatIndex[idx] = { ...chatIndex[idx], ...saved };
            renderChatList(chatIndex);
        }
        if (chatId === getActiveChatId()) {
            setActiveChatTitle(saved.title || title || "New chat");
        }
    }
};

const init = async () => {
    chatIndex = await api.listChats();
    if (!chatIndex.length) {
        const chat = await api.createChat();
        if (chat) chatIndex = [chat];
    }
    const active = chatIndex[0]?.id;
    if (active) {
        setActiveChatId(active);
        const initial = getChatById(active);
        setActiveChatTitle(initial?.title || "New chat");
    }
    renderChatList(chatIndex);
    if (active) await selectChat(active);
    // Always hide history dropdown by default
    closeHistory();
    // Ensure scroll to bottom after initial load
    setTimeout(() => {
        scrollToBottom();
    }, 200);
};

// History toggle button
document.getElementById("history-toggle-btn")?.addEventListener("click", () => {
    toggleHistory();
});

// History close button
document.getElementById("history-close-btn")?.addEventListener("click", () => {
    closeHistory();
});

// Profile toggle button
document.getElementById("profile-toggle-btn")?.addEventListener("click", () => {
    toggleProfile();
});

// Profile close button
document.getElementById("profile-close-btn")?.addEventListener("click", () => {
    closeProfile();
});

// New chat buttons
document
    .getElementById("new-chat-header-btn")
    ?.addEventListener("click", () => {
        createChat();
    });

// Search functionality
document.getElementById("chat-search")?.addEventListener("input", () => {
    renderChatList(chatIndex);
});

// Close dropdown when clicking backdrop
document.getElementById("sidebar-backdrop")?.addEventListener("click", () => {
    closeHistory();
    closeProfile();
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        if (isDeleteModalOpen()) {
            closeDeleteDialog(false);
            return;
        }
        closeHistory();
        closeProfile();
    }
});

document
    .getElementById("delete-chat-cancel-btn")
    ?.addEventListener("click", () => {
        closeDeleteDialog(false);
    });

document
    .getElementById("delete-chat-confirm-btn")
    ?.addEventListener("click", () => {
        closeDeleteDialog(true);
    });

document
    .getElementById("delete-chat-modal")
    ?.addEventListener("click", (event) => {
        if (event.target.id === "delete-chat-modal") {
            closeDeleteDialog(false);
        }
    });

const scrollToBottom = () => {
    const scrollAnchor = document.getElementById("scroll-anchor");
    if (scrollAnchor) {
        scrollAnchor.scrollIntoView({ behavior: "smooth", block: "end" });
    }
};

document.body.addEventListener("htmx:wsAfterMessage", () => {
    saveCurrentChat();
    scrollToBottom();
});

document.body.addEventListener("htmx:afterSwap", () => {
    saveCurrentChat();
    scrollToBottom();
});

document.addEventListener("click", (event) => {
    const btn = event.target.closest(".copy-chat-btn");
    if (!btn) return;
    if (btn.classList.contains("upload-chat-btn")) return;
    console.log("[chat_app] download override handler fired");
    event.preventDefault();
    event.stopImmediatePropagation();
    const exportInput = document.getElementById("chat-export");
    const input = exportInput || document.getElementById("chat-data");
    if (!input) return;
    const text = input.value || "[]";
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const rawTitle = getActiveChatTitle();
    const slug = String(rawTitle)
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    link.href = url;
    link.download = `${slug || "pylogue-conversation"}-${timestamp}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    btn.dataset.copied = "true";
    setTimeout(() => {
        btn.dataset.copied = "false";
    }, 1200);
});

init();
