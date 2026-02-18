document.documentElement.classList.remove("dark");
const STOP_PREFIX = "__PYLOGUE_STOP__:";
const IMPORT_PREFIX = "__PYLOGUE_IMPORT__:";
const decodeCopyB64 = (value) => {
    if (!value) return "";
    try {
        const binary = atob(value);
        const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
        return new TextDecoder("utf-8").decode(bytes);
    } catch {
        return "";
    }
};
document.addEventListener("click", async (event) => {
    const btn = event.target.closest(".copy-btn");
    if (!btn) return;
    const targetId = btn.getAttribute("data-copy-target");
    if (!targetId) return;
    const el = document.getElementById(targetId);
    if (!el) return;
    const rawB64 = el.getAttribute("data-raw-b64");
    const text = rawB64
        ? decodeCopyB64(rawB64)
        : el.getAttribute("data-raw") || el.innerText;
    try {
        await navigator.clipboard.writeText(text);
        btn.dataset.copied = "true";
        setTimeout(() => {
            btn.dataset.copied = "false";
        }, 1200);
    } catch (err) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        btn.dataset.copied = "true";
        setTimeout(() => {
            btn.dataset.copied = "false";
        }, 1200);
    }
});
document.addEventListener("click", async (event) => {
    const btn = event.target.closest(".copy-chat-btn");
    if (!btn) return;
    if (event.defaultPrevented) return;
    if (document.body?.dataset?.disableCoreDownload === "true") return;
    console.log("[pylogue-core] download handler fired");
    const exportInput = document.getElementById("chat-export");
    const input = exportInput || document.getElementById("chat-data");
    if (!input) return;
    const text = input.value || "[]";
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const rawTitle =
        document.body?.dataset?.activeChatTitle ||
        document.querySelector('.chat-item.is-active [data-chat-title="true"]')
            ?.textContent ||
        "";
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
document.addEventListener("click", (event) => {
    const btn = event.target.closest(".upload-chat-btn");
    if (!btn) return;
    const input = document.getElementById("chat-upload");
    if (!input) return;
    input.click();
});
document.addEventListener("change", async (event) => {
    const input = event.target;
    if (!input || input.id !== "chat-upload") return;
    const file = input.files && input.files[0];
    if (!file) return;
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        const payload = JSON.stringify(data);
        const msgInput = document.getElementById("msg");
        const form = document.getElementById("form");
        if (!msgInput || !form) return;
        msgInput.value = `${IMPORT_PREFIX}${payload}`;
        form.requestSubmit();
    } finally {
        input.value = "";
    }
});
document.body.addEventListener("htmx:wsAfterSend", () => {
    const input = document.getElementById("msg");
    if (!input) return;
    input.value = "";
});
const setSendMode = (mode) => {
    const btn = document.getElementById("chat-send-btn");
    if (!btn) return;
    if (mode === "stop") {
        btn.dataset.mode = "stop";
        btn.textContent = "Stop";
    } else {
        btn.dataset.mode = "send";
        btn.textContent = "Send";
    }
};
// Initialize button to Send mode immediately and on page load
setSendMode("send");
document.addEventListener("DOMContentLoaded", () => {
    setSendMode("send");
});
// Also handle WebSocket open event
document.body.addEventListener("htmx:wsOpen", () => {
    setSendMode("send");
});
document.body.addEventListener("htmx:wsBeforeSend", (event) => {
    const form = event.detail && event.detail.elt;
    if (!form || form.id !== "form") return;
    const input = document.getElementById("msg");
    if (input && input.value) {
        if (
            input.value.startsWith(STOP_PREFIX) ||
            input.value.startsWith(IMPORT_PREFIX)
        ) {
            setSendMode("send");
            return;
        }
    }
    setSendMode("stop");
});
document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail && event.detail.target;
    if (target && (target.id === "chat-export" || target.id === "chat-data")) {
        setSendMode("send");
    }
});
// Also handle out-of-band swaps
document.body.addEventListener("htmx:oobAfterSwap", (event) => {
    const target = event.detail && event.detail.target;
    if (target && (target.id === "chat-export" || target.id === "chat-data")) {
        setSendMode("send");
    }
});
document.addEventListener("click", (event) => {
    const btn = event.target.closest("#chat-send-btn");
    if (!btn) return;
    if (btn.dataset.mode !== "stop") return;
    event.preventDefault();
    event.stopPropagation();
    const form = document.getElementById("form");
    const input = document.getElementById("msg");
    if (!form || !input) return;
    input.value = STOP_PREFIX;
    htmx.trigger(form, "submit");
});
document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    // Shift+Enter allows new line, plain Enter submits
    if (event.shiftKey) return;
    // Only submit if the message input (#msg) is focused
    const msgInput = document.getElementById("msg");
    if (!msgInput || document.activeElement !== msgInput) return;
    const form = document.getElementById("form");
    if (!form) return;
    event.preventDefault();
    form.requestSubmit();
});
(function initScrollDebug() {
    const debug = [];
    const maxEntries = 300;
    const getScrollTop = () => {
        const el = document.scrollingElement || document.documentElement;
        return el ? el.scrollTop : 0;
    };
    const getActive = () => {
        const el = document.activeElement;
        if (!el) return null;
        return { tag: el.tagName, id: el.id || "", cls: el.className || "" };
    };
    const push = (type, data) => {
        debug.push({
            t: Date.now(),
            type,
            scrollTop: getScrollTop(),
            active: getActive(),
            ...data,
        });
        if (debug.length > maxEntries) debug.shift();
    };
    window.__scrollDebug = debug;
    window.__dumpScrollDebug = () => JSON.stringify(debug, null, 2);

    let lastScrollTop = getScrollTop();
    let scrollTimer = null;
    document.addEventListener(
        "scroll",
        () => {
            if (scrollTimer) return;
            scrollTimer = requestAnimationFrame(() => {
                scrollTimer = null;
                const current = getScrollTop();
                if (current !== lastScrollTop) {
                    lastScrollTop = current;
                    push("scroll", {});
                }
            });
        },
        { passive: true },
    );

    const logSwap = (label, event) => {
        const target = event && event.detail && event.detail.target;
        push(label, {
            targetId: target ? target.id || "" : "",
            targetTag: target ? target.tagName : "",
        });
    };
    document.body.addEventListener("htmx:beforeSwap", (e) =>
        logSwap("beforeSwap", e),
    );
    document.body.addEventListener("htmx:afterSwap", (e) =>
        logSwap("afterSwap", e),
    );
    document.body.addEventListener("htmx:wsBeforeMessage", (e) =>
        logSwap("wsBeforeMessage", e),
    );
    document.body.addEventListener("htmx:wsAfterMessage", (e) =>
        logSwap("wsAfterMessage", e),
    );
    document.body.addEventListener("focusin", () => push("focusin", {}));
})();
