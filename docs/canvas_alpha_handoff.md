# Canvas Alpha Handoff (Progress Summary)

Date: 2026-02-09

## Goal Being Built
A **canvas + core** alpha where:
- Pylogue chat is the control plane.
- 2D canvas cards are the host UI.
- LLM can CRUD both cards and card content.
- Widgets/cards are not a one-off feature; this is a generic UI action direction.

## What Is Implemented

### 1. New canvas app surface
- Added: `/Users/yeshwanth/Code/Personal/pylogue/src/pylogue/canvas.py`
- This app:
  - Uses `pylogue.core` ws/chat runtime.
  - Renders custom shell: left canvas + right chat panel.
  - Does **not** depend on default history shell UI.

### 2. Canvas frontend runtime (drag/resize/CRUD)
- Added: `/Users/yeshwanth/Code/Personal/pylogue/src/pylogue/static/pylogue-canvas.js`
- Added: `/Users/yeshwanth/Code/Personal/pylogue/src/pylogue/static/pylogue-canvas.css`
- Supports:
  - Card model: `id,title,x,y,w,h,content[]`
  - Content model: `id,type(text|html),text,html,align`
  - Drag card by header
  - Resize card by corner handle
  - CRUD ops:
    - `create_card`, `update_card`, `delete_card`
    - `create_content`, `update_content`, `delete_content`

### 3. LLM action channels
Two paths are now supported:

#### Preferred: tool call channel
- Added tool-result extraction for canvas actions in integrations:
  - `/Users/yeshwanth/Code/Personal/pylogue/src/pylogue/integrations/common.py`
  - `/Users/yeshwanth/Code/Personal/pylogue/src/pylogue/integrations/pydantic_ai.py`
  - `/Users/yeshwanth/Code/Personal/pylogue/src/pylogue/integrations/agno.py`
- New hidden payload wrapper: `.tool-canvas-actions` with base64 JSON actions.
- Frontend executes these payloads directly (no reliance on prose parsing).

#### Fallback: fenced block parsing
- Still supports ` ```pylogue-canvas ... ``` ` JSON blocks from assistant text.
- Parser made tolerant for noisy output and mixed prose.

### 4. Agent tool added for reliable execution
- Updated: `/Users/yeshwanth/Code/Personal/pylogue/scripts/agents/haiku.py`
- Added `canvas_actions(actions=[...])` tool returning:
  - `{ "_pylogue_canvas_actions": [...], "purpose": ... }`
- This avoids brittle “haiku + parse text” behavior.

### 5. Example runner added
- Added: `/Users/yeshwanth/Code/Personal/pylogue/scripts/examples/canvas/main.py`
- Run:
  - `python -m scripts.examples.canvas.main`
  - Open `http://localhost:5012`

### 6. Docs added
- `/Users/yeshwanth/Code/Personal/pylogue/docs/canvas_alpha.md`
- `/Users/yeshwanth/Code/Personal/pylogue/docs/kitchen_audit_ui_action_runtime.md`

## Issues Encountered and Fixes

### Issue A: assistant returned actions but canvas did not update
Observed:
- Tool call succeeded in Logfire.
- UI sometimes showed completed tool status but no card change.

Fixes made:
- Added tool-call execution path in integrations + frontend.
- Added multiple trigger points for processing:
  - `htmx:afterSwap`
  - `htmx:wsAfterMessage`
  - `MutationObserver`
  - periodic fallback scan interval.
- Added robust extraction from raw assistant payload (`data-raw-b64`).

### Issue B: `create_card` with reused id could appear ignored
Fix:
- `create_card` behavior changed to upsert-like handling for existing IDs.

### Issue C: heading HTML inserted but looked like plain text size
Observed:
- `<h1>` content rendered but typography looked flat.

Fix:
- Added explicit heading styles for `.canvas-card-item h1..h6` in canvas CSS.

## Current UX State
- Card creation via assistant/tool works.
- Card origin is visible in header meta as `@(x, y)` plus size.
- Drag/resize works.
- H1 inside card HTML now has heading styling.

## Debugging Hooks Available
Browser console:
- `window.__dumpPylogueCanvasDebug()`
  - Returns event log for scans, parse attempts, and action application.
- `window.__pylogueCanvasDebug`
  - Raw in-memory debug array.

## Known Limitations (Still Alpha)
- No server-side persistence of canvas state yet (browser session only).
- No auth/permission model for action ops.
- No explicit action error feedback UI yet (mostly silent on malformed payloads).
- Periodic scan fallback is pragmatic; can be optimized later.
- Highlight.js warns for `pylogue-*` code fences (cosmetic).

## Suggested Next Steps (Tomorrow)
1. Add explicit action execution status panel in UI
- show last action id/op/result/error visibly, not only console debug.

2. Persist canvas state
- simple start: localStorage snapshot restore on load.
- next: server persistence endpoint + chat/session linkage.

3. Formalize action schema
- validate ops/payload fields before apply.
- return structured reject reasons into chat/tool result.

4. Move from interval fallback to deterministic event flow
- keep observer + ws events, remove polling when stable.

5. Add guardrails for HTML content
- sanitize or whitelist tags/attrs for `type=html` content.

6. Add tests
- frontend unit tests for parser/executor (if test harness available).
- integration test for tool result -> canvas mutation path.

## Quick Run Checklist
1. Start app: `python -m scripts.examples.canvas.main`
2. Hard refresh browser.
3. Prompt example:
   - "create a new card id banner-1 at x 0 y 0 width 1200 height 120 with centered H1 Welcome to my canvas"
4. Verify:
   - new card appears,
   - header shows origin/size,
   - H1 style appears as heading.
