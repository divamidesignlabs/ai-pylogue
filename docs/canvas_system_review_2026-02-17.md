# Canvas System Review (2026-02-17)

## Scope and method
This review covers the canvas implementation and integration surface in:
- `src/canvas/main.py`
- `src/canvas/agent_pack.py`
- `src/canvas/crud.py`
- `src/canvas/state.py`
- `src/canvas/components.py`
- `src/canvas/static/canvas-ws.js`
- `src/pylogue/core.py` (canvas context handoff)
- `src/pylogue/integrations/pydantic_ai.py` (tool-call event handling)

The lens is: operational efficiency, LLM tool ergonomics, infrastructure resilience, and architectural elegance.

## Executive summary
The current canvas stack is a strong MVP with clear seams (`main`/`state`/`crud`/`agent_pack`) and pragmatic HTMX+WS synchronization.  
The biggest drag on agent performance is tool I/O shape: CSV strings and forced multi-call discovery workflows introduce avoidable tokens, parsing ambiguity, and extra round trips.  
The most brittle areas are in-memory/global runtime state, non-transactional persistence, and ad hoc client-side WS+DOM orchestration that can silently diverge under failures.  
Despite that, there is real elegance in how canvas context is threaded into agent deps, how tool functions are narrowly scoped, and how server-rendered HTML keeps the UI simple.

## What is elegant
1. Clean module boundaries for an MVP:
   - UI routing/layout in `src/canvas/main.py`.
   - data mutation/read API in `src/canvas/crud.py`.
   - cross-session signaling and persistence in `src/canvas/state.py`.
   - model-facing tool contract in `src/canvas/agent_pack.py`.
2. Minimal implicit context handoff from web session to model deps:
   - `canvas_current_id` captured in session context in `src/pylogue/core.py:125-136`.
   - merged into model deps in `src/pylogue/integrations/pydantic_ai.py:59-90`.
3. Deterministic tool granularity:
   - `link_canvas_item`, `move_canvas_item`, and `navigate_to_canvas` encode higher-level intents into explicit operations (`src/canvas/agent_pack.py:145-247`), reducing hallucinated low-level orchestration.
4. Straightforward reactive refresh path:
   - on mutation, `CanvasItemCRUD` emits change (`src/canvas/crud.py:110-113`), which persists + publishes refresh (`src/canvas/state.py:93-95`), and UI panel re-fetches via HTMX trigger (`src/canvas/main.py:88-90`).
5. Progressive enhancement approach:
   - WS handles both generic refresh and targeted navigation events (`src/canvas/static/canvas-ws.js:14-55`) while preserving fallback to full page navigation (`src/canvas/static/canvas-ws.js:43-46`).

## Inefficiencies (especially LLM <-> tools)
1. CSV as tool transport is expensive and fragile for LLMs:
   - `list_canvas_items`, `get_canvas_item`, `list_canvases` return CSV or comma-separated strings (`src/canvas/agent_pack.py:87-119` + `src/canvas/crud.py:28-39,47-55`).
   - This increases parse burden, adds quoting/escaping edge cases, and forces additional schema-recovery calls.
2. Prompt-enforced multi-call choreography adds latency and token burn:
   - instruction contract requires `get_current_canvas` + `list_canvases` + `list_canvas_items` + optional `get_canvas_item` before action (`src/canvas/agent_pack.py:21-45`).
   - For common operations, this is operationally safe but inefficient, especially when context already has current canvas.
3. Tool response payloads are inconsistent:
   - Some tools return full objects (`create_canvas_item`), some booleans wrapped in dict (`delete_canvas_item`), some CSV strings, and some nullable strings (`get_canvas_item`).
   - Inconsistent output contracts make robust model planning harder and inflate defensive prompting.
4. Redundant deep copies in hot paths:
   - `list_items`, `_get_item_raw`, and several operations repeatedly `deepcopy` (`src/canvas/crud.py:18-19,41-45,74-99`).
   - Safe but potentially expensive if card count/payload size grows.
5. Mutation verification is done via separate tool read:
   - prompt requires post-mutation verification read (`src/canvas/agent_pack.py:39`), but mutation tools could return normalized post-state directly.

## Brittle and hacky infrastructure
1. Process-local global state limits correctness under scale:
   - subscribers, event loop, stores are module globals (`src/canvas/state.py:10-13`).
   - multi-worker/process deployments will desynchronize state and WS events.
2. Persistence is not transactional and can race:
   - all updates rewrite one JSON file (`src/canvas/state.py:84-90`), with no locks/versioning/atomic temp+rename strategy.
   - concurrent writes risk lost updates or partial corruption.
3. Cross-canvas move is not atomic:
   - `move_canvas_item` creates in target then deletes source (`src/canvas/agent_pack.py:212-217`).
   - rollback is best-effort only; failure windows can duplicate or drop items.
4. WS delivery is fire-and-forget:
   - `run_coroutine_threadsafe` results are not observed (`src/canvas/state.py:53-66`).
   - dead subscribers or send exceptions are not pruned/retried deterministically.
5. Navigation path in client JS bypasses a single rendering authority:
   - manual `fetch` + `outerHTML` replacement + `htmx.process` in `src/canvas/static/canvas-ws.js:30-42`.
   - this works, but is easy to drift from HTMX lifecycle expectations and harder to reason about than a unified server-driven swap protocol.
6. UI delete control currently mutates DOM only:
   - remove button calls `tile.remove()` client-side (`src/canvas/components.py:40-45`) without tool/backend mutation.
   - refresh events can resurrect removed cards, causing user-visible inconsistency.
7. Weak domain validation in CRUD:
   - `update_item` merges arbitrary patch keys (`src/canvas/crud.py:90-99`) and does not constrain spans/types.
   - data model can drift into invalid states, then rendering code must absorb errors.
8. Observability is mostly console logging:
   - WS client logs verbosely (`src/canvas/static/canvas-ws.js:5-65`) but no metric counters/tracing for refresh latency, dropped messages, or mutation failures.

## Priority hardening plan
1. **Fix tool contracts first (highest leverage for LLM quality):**
   - Add JSON-returning v2 tools (`list_canvas_items_v2`, `get_canvas_item_v2`, `list_canvases_v2`) with stable typed schemas.
   - Keep legacy CSV tools for compatibility, then deprecate.
2. **Collapse discovery + mutate round trips:**
   - Introduce composite tools like `find_canvas_item(query=...)` and `update_canvas_item_and_verify(...)`.
   - Return canonical post-mutation state in the same response.
3. **Make state storage durable and concurrent-safe:**
   - Move from process globals + JSON file to SQLite/Postgres with optimistic versioning per canvas.
   - Emit WS events from persisted commits, not in-memory mutation side effects.
4. **Unify real-time transport semantics:**
   - Replace custom `canvas_navigate:` string protocol with structured event envelopes (`type`, `payload`, `version`).
   - Handle ack/failure, and prune broken subscribers.
5. **Enforce domain validation at write boundary:**
   - Validate `type`, `col_span`, `row_span`, `variant`, and known fields before mutating.
   - Reject unknown/unsafe patch keys by default.
6. **Resolve UI/backend delete divergence:**
   - Wire card close to `delete_canvas_item` (or equivalent endpoint) and optimistic UI with rollback on failure.

## Architecture scorecard (current)
- LLM ergonomics: **5/10** (workable, but verbose and parsing-heavy)
- Runtime resilience: **4/10** (good for single-process MVP, brittle for scale/concurrency)
- Change velocity: **8/10** (simple code paths, easy iteration)
- Conceptual clarity: **8/10** (clear separations and intent)
- Production readiness: **4/10** (needs storage/event hardening and stronger contracts)

## Bottom line
The codebase is elegantly pragmatic for an MVP: small, understandable, and easy to modify.  
The main bottleneck is not algorithmic complexity but contract design: once tool I/O is made typed/compact and state transitions are made transactional, the same architecture can scale much further with less prompt engineering overhead.
