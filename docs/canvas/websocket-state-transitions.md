# Canvas WebSocket State Transitions

This doc explains how canvas/chat state moves through HTTP and WebSocket channels, why drift happened, and how the context-sync patch fixes it.

## 1) Runtime channels and ownership

```mermaid
flowchart LR
  U["User (Browser)"] -->|"HTTP/HTMX requests"| S["FastHTML Server"]
  U -->|"WS /ws (chat)"| CWS["Chat WS handler"]
  U -->|"WS /canvas/ws (canvas events)"| VWS["Canvas WS handler"]

  S -->|"session['canvas_current_id'] set on /canvas routes"| SES["HTTP Session Store"]
  CWS -->|"build responder context"| AG["LLM Agent Tools"]
  VWS -->|"canvas_refresh / canvas_navigate events"| U

  SES --> CWS
```

Key point: chat context (`ctx.deps.pylogue_canvas.current_canvas_id`) is resolved inside chat WS flow, not from the visible canvas DOM directly.

## 2) Pre-fix sequence (state drift bug)

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant H as HTTP Routes
  participant C as Chat WS (/ws)
  participant V as Canvas WS (/canvas/ws)
  participant A as Agent Tool get_current_canvas

  B->>H: GET /canvas/main
  H-->>B: HTML + chat form (ws_connect=/ws) + canvas panel
  B->>C: WS connect /ws
  C->>C: _build_responder_context() => canvas_current_id=main
  B->>V: WS connect /canvas/ws

  B->>H: HTMX GET /canvas/details/panel?from=main
  H->>H: session['canvas_current_id'] = details
  H-->>B: panel HTML (details)
  B->>V: receives canvas_navigate/canvas_refresh, updates panel DOM

  B->>C: user sends "where am i"
  C->>C: _build_responder_context() reads stale ws session view (main)
  C->>A: get_current_canvas(ctx.deps.pylogue_canvas.current_canvas_id)
  A-->>C: "main" (wrong for visible UI)
```

Why this happens: long-lived WS session state can be stale relative to later HTTP route updates unless explicitly synchronized.

## 3) Post-fix sequence (explicit WS context sync)

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant H as HTTP Routes
  participant C as Chat WS (/ws)
  participant JS as pylogue-core.js
  participant A as Agent Tool get_current_canvas

  B->>H: "HTMX/page navigation to /canvas/details"
  H->>H: "session['canvas_current_id'] = details"
  H-->>B: "updated panel/page"

  JS->>JS: "detect canvas change (afterSwap/popstate/custom event)"
  JS->>C: "send '__PYLOGUE_CONTEXT__:{canvas_current_id:'details'}'"
  C->>C: "parse control msg - set ws_canvas_current_id=details"
  C->>C: "refresh responder context + deps"

  B->>C: "user sends prompt"
  C->>A: "get_current_canvas(ctx.deps.pylogue_canvas.current_canvas_id)"
  A-->>C: "details (correct)"
```

## 4) Current invariants to rely on

1. Visible canvas changes must trigger a context-sync control message on chat WS before the next user prompt.
2. Chat WS context resolver should prefer `ws_canvas_current_id` over HTTP session fallback.
3. Agent tools should treat `ctx.deps.pylogue_canvas.current_canvas_id` as the authoritative active canvas for that chat turn.

## 5) Quick debugging checklist

1. In browser devtools, verify chat WS sends `__PYLOGUE_CONTEXT__:{...}` after canvas swap/navigation.
2. In server logs, verify chat WS receives the context prefix branch before the next prompt.
3. Print `ctx.deps` in a tool call and confirm `pylogue_canvas.current_canvas_id` matches breadcrumb canvas.
4. If mismatch appears, inspect whether a canvas change event fired without `sendCanvasContextIfNeeded()`.
