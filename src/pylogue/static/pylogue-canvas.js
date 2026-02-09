const STOP_PREFIX = '__PYLOGUE_STOP__:';
const IMPORT_PREFIX = '__PYLOGUE_IMPORT__:';

const state = {
  cards: new Map(),
  processedBlocks: new Set(),
  cardSeq: 1,
  contentSeq: 1,
  zSeq: 5,
  debug: [],
};

const canvasRoot = document.getElementById('pylogue-canvas-root');
const form = document.getElementById('form');
const messageInput = document.getElementById('msg');
const canvasStateInput = document.getElementById('canvas-state');
const addCardBtn = document.getElementById('canvas-add-card-btn');

const enc = new TextEncoder();
const dec = new TextDecoder();

function encodeUtf8Base64(text) {
  const bytes = enc.encode(text || '');
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}

function decodeUtf8Base64(value) {
  if (!value) return '';
  try {
    const binary = atob(value);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return dec.decode(bytes);
  } catch {
    return '';
  }
}

function safeNumber(value, fallback) {
  const n = Number(value);
  if (Number.isFinite(n)) return n;
  return fallback;
}

function pushDebug(type, data = {}) {
  state.debug.push({ t: Date.now(), type, ...data });
  if (state.debug.length > 200) state.debug.shift();
}

function normalizeCard(raw) {
  const id = String(raw.id || `card-${state.cardSeq++}`);
  const card = {
    id,
    title: typeof raw.title === 'string' && raw.title.trim() ? raw.title.trim() : id,
    x: safeNumber(raw.x, 40),
    y: safeNumber(raw.y, 40),
    w: Math.max(180, safeNumber(raw.w, 320)),
    h: Math.max(140, safeNumber(raw.h, 240)),
    z: Math.max(1, safeNumber(raw.z, ++state.zSeq)),
    content: Array.isArray(raw.content) ? raw.content.map(normalizeContent) : [],
  };
  return card;
}

function normalizeContent(raw) {
  return {
    id: String(raw.id || `content-${state.contentSeq++}`),
    type: raw.type === 'html' ? 'html' : 'text',
    text: typeof raw.text === 'string' ? raw.text : '',
    html: typeof raw.html === 'string' ? raw.html : '',
    align: ['left', 'center', 'right'].includes(raw.align) ? raw.align : 'left',
  };
}

function exportSnapshot() {
  return {
    cards: Array.from(state.cards.values())
      .sort((a, b) => a.z - b.z)
      .map((card) => ({
        id: card.id,
        title: card.title,
        x: card.x,
        y: card.y,
        w: card.w,
        h: card.h,
        content: card.content.map((item) => ({
          id: item.id,
          type: item.type,
          text: item.text,
          html: item.html,
          align: item.align,
        })),
      })),
  };
}

function persistState() {
  if (canvasStateInput) {
    canvasStateInput.value = JSON.stringify(exportSnapshot());
  }
}

function createCardNode(card) {
  const cardEl = document.createElement('article');
  cardEl.className = 'canvas-card';
  cardEl.dataset.cardId = card.id;

  const header = document.createElement('header');
  header.className = 'canvas-card-header';

  const title = document.createElement('h3');
  title.className = 'canvas-card-title';
  title.textContent = card.title;

  const meta = document.createElement('span');
  meta.className = 'canvas-card-meta';
  meta.textContent = `@(${Math.round(card.x)}, ${Math.round(card.y)}) ${Math.round(card.w)} x ${Math.round(card.h)}`;

  header.append(title, meta);

  const body = document.createElement('div');
  body.className = 'canvas-card-body';

  for (const item of card.content) {
    const itemNode = document.createElement('div');
    itemNode.className = 'canvas-card-item';
    itemNode.dataset.contentId = item.id;
    itemNode.dataset.align = item.align;
    if (item.type === 'html') {
      itemNode.innerHTML = item.html;
    } else {
      itemNode.textContent = item.text;
    }
    body.appendChild(itemNode);
  }

  const resize = document.createElement('div');
  resize.className = 'canvas-card-resize';
  resize.title = 'Resize card';

  cardEl.append(header, body, resize);
  bindCardInteractions(cardEl, card.id);
  applyCardStyle(cardEl, card);
  return cardEl;
}

function applyCardStyle(cardEl, card) {
  cardEl.style.left = `${card.x}px`;
  cardEl.style.top = `${card.y}px`;
  cardEl.style.width = `${card.w}px`;
  cardEl.style.height = `${card.h}px`;
  cardEl.style.zIndex = String(card.z);

  const meta = cardEl.querySelector('.canvas-card-meta');
  if (meta) {
    meta.textContent = `@(${Math.round(card.x)}, ${Math.round(card.y)}) ${Math.round(card.w)} x ${Math.round(card.h)}`;
  }

  const title = cardEl.querySelector('.canvas-card-title');
  if (title) title.textContent = card.title;
}

function renderCard(card) {
  if (!canvasRoot) return;
  let node = canvasRoot.querySelector(`[data-card-id="${card.id}"]`);
  if (!node) {
    node = createCardNode(card);
    canvasRoot.appendChild(node);
  }

  const body = node.querySelector('.canvas-card-body');
  if (body) {
    body.replaceChildren();
    for (const item of card.content) {
      const itemNode = document.createElement('div');
      itemNode.className = 'canvas-card-item';
      itemNode.dataset.contentId = item.id;
      itemNode.dataset.align = item.align;
      if (item.type === 'html') {
        itemNode.innerHTML = item.html;
      } else {
        itemNode.textContent = item.text;
      }
      body.appendChild(itemNode);
    }
  }

  applyCardStyle(node, card);
  persistState();
}

function removeCard(id) {
  state.cards.delete(id);
  const node = canvasRoot?.querySelector(`[data-card-id="${id}"]`);
  if (node) node.remove();
  persistState();
}

function bringToFront(cardId) {
  const card = state.cards.get(cardId);
  if (!card) return;
  card.z = ++state.zSeq;
  const node = canvasRoot?.querySelector(`[data-card-id="${cardId}"]`);
  if (node) node.style.zIndex = String(card.z);
}

function clampCardPosition(card) {
  if (!canvasRoot) return;
  const maxX = Math.max(0, canvasRoot.clientWidth - 100);
  const maxY = Math.max(0, canvasRoot.clientHeight - 60);
  card.x = Math.max(0, Math.min(card.x, maxX));
  card.y = Math.max(0, Math.min(card.y, maxY));
}

function bindCardInteractions(cardEl, cardId) {
  const header = cardEl.querySelector('.canvas-card-header');
  const resize = cardEl.querySelector('.canvas-card-resize');

  header?.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    const card = state.cards.get(cardId);
    if (!card) return;
    bringToFront(cardId);

    const startX = event.clientX;
    const startY = event.clientY;
    const originX = card.x;
    const originY = card.y;

    function onMove(moveEvent) {
      card.x = originX + (moveEvent.clientX - startX);
      card.y = originY + (moveEvent.clientY - startY);
      clampCardPosition(card);
      applyCardStyle(cardEl, card);
    }

    function onEnd() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      persistState();
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd, { once: true });
  });

  resize?.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    const card = state.cards.get(cardId);
    if (!card) return;
    bringToFront(cardId);

    const startX = event.clientX;
    const startY = event.clientY;
    const startW = card.w;
    const startH = card.h;

    function onMove(moveEvent) {
      card.w = Math.max(180, startW + (moveEvent.clientX - startX));
      card.h = Math.max(140, startH + (moveEvent.clientY - startY));
      applyCardStyle(cardEl, card);
    }

    function onEnd() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      persistState();
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd, { once: true });
  });
}

function applyAction(action) {
  if (!action || typeof action !== 'object') return;
  const op = action.op;
  pushDebug('apply_action', { op, action });

  if (op === 'create_card') {
    const incoming = normalizeCard(action.card || {});
    const existing = state.cards.get(incoming.id);
    if (!existing) {
      state.cards.set(incoming.id, incoming);
      renderCard(incoming);
      return;
    }
    existing.title = incoming.title || existing.title;
    existing.x = incoming.x;
    existing.y = incoming.y;
    existing.w = incoming.w;
    existing.h = incoming.h;
    existing.z = Math.max(existing.z, ++state.zSeq);
    if (Array.isArray(incoming.content) && incoming.content.length > 0) {
      existing.content = incoming.content;
    }
    clampCardPosition(existing);
    renderCard(existing);
    return;
  }

  if (op === 'update_card') {
    const id = String(action.id || '');
    const card = state.cards.get(id);
    if (!card) return;
    const patch = action.patch && typeof action.patch === 'object' ? action.patch : {};
    if (typeof patch.title === 'string') card.title = patch.title;
    if (patch.x !== undefined) card.x = safeNumber(patch.x, card.x);
    if (patch.y !== undefined) card.y = safeNumber(patch.y, card.y);
    if (patch.w !== undefined) card.w = Math.max(180, safeNumber(patch.w, card.w));
    if (patch.h !== undefined) card.h = Math.max(140, safeNumber(patch.h, card.h));
    if (patch.z !== undefined) card.z = Math.max(1, safeNumber(patch.z, card.z));
    clampCardPosition(card);
    renderCard(card);
    return;
  }

  if (op === 'delete_card') {
    const id = String(action.id || '');
    if (!id) return;
    removeCard(id);
    return;
  }

  if (op === 'create_content') {
    const cardId = String(action.card_id || '');
    const card = state.cards.get(cardId);
    if (!card) return;
    const item = normalizeContent(action.content || {});
    const exists = card.content.find((entry) => entry.id === item.id);
    if (!exists) card.content.push(item);
    renderCard(card);
    return;
  }

  if (op === 'update_content') {
    const cardId = String(action.card_id || '');
    const contentId = String(action.content_id || '');
    const card = state.cards.get(cardId);
    if (!card) return;
    const target = card.content.find((entry) => entry.id === contentId);
    if (!target) return;
    const patch = action.patch && typeof action.patch === 'object' ? action.patch : {};
    if (patch.type === 'html' || patch.type === 'text') target.type = patch.type;
    if (typeof patch.text === 'string') target.text = patch.text;
    if (typeof patch.html === 'string') target.html = patch.html;
    if (['left', 'center', 'right'].includes(patch.align)) target.align = patch.align;
    renderCard(card);
    return;
  }

  if (op === 'delete_content') {
    const cardId = String(action.card_id || '');
    const contentId = String(action.content_id || '');
    const card = state.cards.get(cardId);
    if (!card) return;
    card.content = card.content.filter((entry) => entry.id !== contentId);
    renderCard(card);
    return;
  }
}

function extractActionBlocks(text) {
  const blocks = [];
  const regex = /```(?:pylogue-canvas|json|javascript|js)?\s*([\s\S]*?)```/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const payload = match[1].trim();
    if (payload) blocks.push(payload);
  }
  return blocks;
}

function parseActionObject(payload) {
  if (!payload || typeof payload !== 'string') return null;
  const raw = payload.trim();
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return { actions: parsed };
    if (parsed && typeof parsed === 'object' && (Array.isArray(parsed.actions) || parsed.op)) {
      return Array.isArray(parsed.actions) ? parsed : { actions: [parsed] };
    }
  } catch {
    const first = raw.indexOf('{');
    const last = raw.lastIndexOf('}');
    if (first >= 0 && last > first) {
      const slice = raw.slice(first, last + 1);
      try {
        const parsed = JSON.parse(slice);
        if (Array.isArray(parsed)) return { actions: parsed };
        if (parsed && typeof parsed === 'object' && (Array.isArray(parsed.actions) || parsed.op)) {
          return Array.isArray(parsed.actions) ? parsed : { actions: [parsed] };
        }
      } catch {
        return null;
      }
    }
  }
  return null;
}

function runActionBlock(payload) {
  const parsed = parseActionObject(payload);
  if (!parsed) {
    pushDebug('parse_failed', { payload: String(payload || '').slice(0, 200) });
    return;
  }
  try {
    pushDebug('actions_parsed', { count: parsed.actions.length });
    for (const action of parsed.actions) applyAction(action);
  } catch {
    // Intentionally ignore malformed blocks in alpha.
    pushDebug('apply_failed');
  }
}

function extractToolActionPayloadsFromText(text) {
  if (!text) return [];
  const payloads = [];
  const regex = /<div[^>]*class=["'][^"']*tool-canvas-actions[^"']*["'][^>]*data-actions-b64=["']([^"']+)["'][^>]*>/gi;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const decoded = decodeUtf8Base64(match[1]);
    if (decoded && decoded.trim()) payloads.push(decoded.trim());
  }
  return payloads;
}

function processToolActionNodes() {
  const nodes = Array.from(document.querySelectorAll('#cards .tool-canvas-actions[data-actions-b64]'));
  pushDebug('tool_nodes_scan', { count: nodes.length });
  if (!nodes.length) return;
  nodes.forEach((node) => {
    const encoded = node.getAttribute('data-actions-b64');
    if (!encoded) return;
    const key = `tool:${encoded}`;
    if (state.processedBlocks.has(key)) return;
    const payload = decodeUtf8Base64(encoded);
    if (!payload) return;
    state.processedBlocks.add(key);
    pushDebug('tool_payload_found', { size: payload.length });
    runActionBlock(payload);
  });
}

function getAssistantRawText(node) {
  const encoded = node.getAttribute('data-raw-b64');
  const decoded = decodeUtf8Base64(encoded);
  if (decoded && decoded.trim()) return decoded;
  return (node.textContent || '').trim();
}

function processAssistantActions() {
  const assistantNodes = Array.from(document.querySelectorAll('#cards [id^="assistant-"]'));
  pushDebug('assistant_nodes_scan', { count: assistantNodes.length });
  if (!assistantNodes.length) return;
  assistantNodes.forEach((node) => {
    const answerText = getAssistantRawText(node);
    if (!answerText) return;

    const embeddedToolPayloads = extractToolActionPayloadsFromText(answerText);
    if (embeddedToolPayloads.length) {
      pushDebug('assistant_embedded_tool_payloads', { nodeId: node.id, count: embeddedToolPayloads.length });
    }
    embeddedToolPayloads.forEach((payload, index) => {
      const key = `${node.id}:tool-payload:${index}:${payload}`;
      if (state.processedBlocks.has(key)) return;
      state.processedBlocks.add(key);
      runActionBlock(payload);
    });

    const blocks = extractActionBlocks(answerText);
    if (blocks.length) {
      pushDebug('assistant_code_blocks', { nodeId: node.id, count: blocks.length });
    }
    if (!blocks.length) {
      blocks.push(answerText);
    }
    blocks.forEach((payload, index) => {
      const key = `${node.id}:${index}:${payload}`;
      if (state.processedBlocks.has(key)) return;
      state.processedBlocks.add(key);
      runActionBlock(payload);
    });
  });
}

function scrubUserStateContext() {
  const userNodes = Array.from(document.querySelectorAll('#cards .chat-row-user .marked'));
  for (const node of userNodes) {
    const raw = decodeUtf8Base64(node.getAttribute('data-raw-b64'));
    if (!raw.includes('```pylogue-canvas-state')) continue;
    const cleaned = raw.replace(/\n*```pylogue-canvas-state[\s\S]*?```\s*$/m, '').trim();
    node.textContent = cleaned;
    node.setAttribute('data-raw-b64', encodeUtf8Base64(cleaned));
  }
}

function ensureSeedCard() {
  if (state.cards.size > 0) return;
  applyAction({
    op: 'create_card',
    card: {
      id: 'card-1',
      title: 'Canvas Card',
      x: 40,
      y: 40,
      w: 360,
      h: 220,
      content: [
        {
          id: 'content-1',
          type: 'text',
          text: 'Ask chat to create/update/delete cards or content with a ```pylogue-canvas``` action block.',
          align: 'left',
        },
      ],
    },
  });
}

function injectCanvasStateIntoPrompt() {
  if (!form || !messageInput) return;

  document.body.addEventListener('htmx:wsBeforeSend', (event) => {
    const targetForm = event.detail && event.detail.elt;
    if (!targetForm || targetForm.id !== 'form') return;

    const msg = messageInput.value || '';
    if (!msg || msg.startsWith(STOP_PREFIX) || msg.startsWith(IMPORT_PREFIX)) {
      return;
    }

    const snapshot = exportSnapshot();
    const statePayload = JSON.stringify(snapshot);
    messageInput.value = `${msg}\n\n\`\`\`pylogue-canvas-state\n${statePayload}\n\`\`\``;
  });
}

function initEvents() {
  addCardBtn?.addEventListener('click', () => {
    applyAction({
      op: 'create_card',
      card: {
        title: `Card ${state.cardSeq}`,
        x: 60 + state.cards.size * 24,
        y: 60 + state.cards.size * 24,
        w: 300,
        h: 200,
        content: [
          {
            type: 'text',
            text: 'New card. Ask the assistant to update me.',
            align: 'center',
          },
        ],
      },
    });
  });

  document.body.addEventListener('htmx:afterSwap', (event) => {
    const target = event.detail && event.detail.target;
    if (!target) return;
    if (target.id === 'chat-export') {
      processToolActionNodes();
      processAssistantActions();
    }
    if (target.id === 'cards') {
      scrubUserStateContext();
      processToolActionNodes();
      processAssistantActions();
    }
  });
  document.body.addEventListener('htmx:wsAfterMessage', () => {
    pushDebug('ws_after_message');
    processToolActionNodes();
    processAssistantActions();
  });

  const cardsRoot = document.getElementById('cards');
  if (cardsRoot) {
    const observer = new MutationObserver(() => {
      processToolActionNodes();
      processAssistantActions();
    });
    observer.observe(cardsRoot, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['data-raw-b64'],
    });
  }

  // Fallback safety net: periodically scan for newly streamed assistant/tool payloads.
  window.setInterval(() => {
    processToolActionNodes();
    processAssistantActions();
  }, 600);
}

ensureSeedCard();
injectCanvasStateIntoPrompt();
initEvents();
processToolActionNodes();
processAssistantActions();
persistState();
window.__pylogueCanvasDebug = state.debug;
window.__dumpPylogueCanvasDebug = () => JSON.stringify(state.debug, null, 2);
