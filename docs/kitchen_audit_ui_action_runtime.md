# Kitchen Audit: Design Learnings for Pylogue UI Action Runtime

## Purpose
Audit of `/Users/yeshwanth/Code/Personal/kitchen` to extract design patterns for Pylogue's goal:
- chat-driven read/create/update/delete over external UI elements
- dashboard/widget behavior as a specialization, not the architecture

## Executive Summary
Kitchen validates the core idea: an LLM can act as a UI control plane when it emits typed state changes and a host runtime executes them.

The most transferable pattern is **"agent plans diffs, runtime applies diffs"**. In Kitchen this is represented by `StateUpdate` + `StateManager.apply_update(...)`.

For Pylogue, we should generalize this from a single domain state (`cards`, `recipes`) to a **resource/action runtime** over multiple UI resource kinds (`panel`, `widget`, later others).

## What Kitchen Does Well

### 1. Typed diff contract between AI and UI executor
- `models.py` defines `StateUpdate` with explicit fields like `add_cards`, `remove_card_ids`, `update_cards`, `table_name`.
- `agent_config.py` sets `output_type=StateUpdate`, forcing structured outputs.
- This constrains model behavior and avoids free-form UI mutation.

Why it matters for Pylogue:
- Gives predictable execution path.
- Enables validation and safe failure handling before touching UI.

### 2. Single execution boundary for state mutation
- `state_manager.py` centralizes mutations in `apply_update()` and persistence in `save()`.
- Routes and tools do not directly mutate random UI state; they go through this boundary.

Why it matters for Pylogue:
- We need one bridge runtime for all chat-driven UI actions.
- Access control, idempotency, conflict policy, and auditing should live there.

### 3. Clear orchestration flow
- `main.py` route receives prompt -> agent returns typed update -> state manager applies update -> UI rerender.
- This is a clear control loop and easy to reason about.

### 4. Useful domain tools with constrained side effects
- Tools like `read_state`, `set_card_selection`, `clear_all_selections`, `save_recipe` are narrow and observable.
- This supports bounded capabilities without unrestricted DOM writes.

### 5. Frontend can consume structured streaming events
- `agui_parser.py` models AG-UI event types (run lifecycle, text/tool events, state snapshots/deltas).
- Conceptually strong for future real-time UI synchronization.

## Gaps / Risks Seen in Kitchen (Useful Warnings)

### 1. Domain-coupled update schema
- `StateUpdate` is tightly tied to inventory cards/recipes.
- Hard to reuse for arbitrary UI resource kinds.

Pylogue implication:
- Do not freeze the contract around `chart` or `widget` only.

### 2. No explicit resource identity model beyond local IDs
- IDs are scoped to specific domain entities, not a global UI namespace.

Pylogue implication:
- Need globally addressable `resource_ref` (kind + id + optional parent/scope).

### 3. Concurrency and conflict policy is implicit
- Multiple operations can race conceptually; conflict handling is not formalized.

Pylogue implication:
- Add version/etag or last-write policy in bridge runtime for deterministic behavior.

### 4. Persistence strategy is file-centric
- `state.json` is pragmatic for demo, weak for multi-user/live collaborative cases.

Pylogue implication:
- Alpha can stay in-memory, but bridge API should not assume file persistence model.

### 5. Event model appears partially inconsistent at usage sites
- `agui_parser.py` exposes names like `is_text_message_start`, while `ui.py` checks `is_text_start`.
- This suggests potential drift between parser contract and consumers.

Pylogue implication:
- Keep one canonical event contract and add integration tests for producer/consumer compatibility.

## Mapping Learnings to Pylogue

Current Pylogue strengths relevant to this direction:
- Existing streaming and tool event pipeline (`integrations/*.py` + `core.py`).
- Existing HTML embedding path (`dashboarding.py` + `embeds.py`) for charts.
- Existing custom frontend script surface (`static/pylogue-core.js`).

What is missing:
- Generic resource/action contract.
- Central action executor runtime.
- Bidirectional action result channel (`action_id`, `ok`, `data/error`).
- Resource registry that host UI owns.

## Recommended Target Architecture for Pylogue

### Control Plane vs Data Plane
- **Control plane (chat/agent):** emits structured UI intents.
- **Execution plane (host app runtime):** validates, authorizes, executes intents against registered resources.
- **Render/data plane (UI):** reflects current resource state and subscriptions.

### Minimal generic action envelope
```json
{
  "action_id": "act_123",
  "op": "create",
  "resource": {"kind": "widget", "id": "w-42", "parent": {"kind": "panel", "id": "right"}},
  "payload": {"type": "altair", "spec": {}, "query": "..."},
  "meta": {"source": "pylogue", "ts": "..."}
}
```

### Minimal operation set
- `read`
- `create`
- `update`
- `delete`
- (defer) `invoke`, `subscribe`

### Execution result envelope
```json
{
  "action_id": "act_123",
  "ok": true,
  "data": {"resource": {"kind": "widget", "id": "w-42"}},
  "error": null
}
```

## Alpha Scope (Recommended)

### Goal
Prove generic bridge viability, not full dashboard platform.

### Resource kinds for alpha
- `panel`
- `widget`

### Operations for alpha
- `read`, `create`, `update`, `delete`

### Demo scenario
1. Chat creates chart widget in right panel.
2. Chat updates chart config (e.g., aggregation/granularity).
3. Chat reads panel contents.
4. Chat deletes widget.

### Explicit non-goals
- No arbitrary raw DOM mutation from model output.
- No full subscription framework yet.
- No broad set of resource kinds yet.

## Guardrails to add from day 1
- Schema validation for action payloads.
- Allowlist of resource kinds/ops per context.
- Idempotency key / action_id dedupe.
- Bounded query limits/timeouts for data-backed widgets.
- Structured error responses surfaced back into chat.

## Suggested Pylogue Implementation Phases

### Phase 1: Contract + Runtime skeleton
- Add action models (Pydantic) for envelope + result.
- Add in-memory `UIResourceRegistry` + `UIActionExecutor`.
- Wire executor results back into chat as tool summaries.

### Phase 2: Widget specialization on top of generic contract
- Implement `widget` handlers for `altair` widgets using existing embed pipeline.
- Add host UI panel mounting via `pylogue-core.js` bridge events.

### Phase 3: Live update semantics
- Add optional `refresh_policy` in widget payload.
- Add scheduler/subscription manager per widget.
- Maintain last refresh status/error for `read` visibility.

## File References Reviewed (Kitchen)
- `/Users/yeshwanth/Code/Personal/kitchen/src/kitchen/main.py`
- `/Users/yeshwanth/Code/Personal/kitchen/src/kitchen/models.py`
- `/Users/yeshwanth/Code/Personal/kitchen/src/kitchen/state_manager.py`
- `/Users/yeshwanth/Code/Personal/kitchen/src/kitchen/agent_config.py`
- `/Users/yeshwanth/Code/Personal/kitchen/src/kitchen/agui_parser.py`
- `/Users/yeshwanth/Code/Personal/kitchen/src/kitchen/ui.py`
- `/Users/yeshwanth/Code/Personal/kitchen/src/kitchen/ARCHITECTURE.md`

## Bottom Line
Kitchen proves the pattern, but its contract is domain-specific. Pylogue should adopt the same core discipline (typed diffs + single executor) while moving to a generalized resource/action model where widgets are only one resource kind.
