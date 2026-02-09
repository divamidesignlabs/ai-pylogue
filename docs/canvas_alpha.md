# Canvas Alpha (Canvas + Core)

## Goal
Provide a blank 2D canvas host UI (cards with x/y/w/h) while keeping Pylogue core chat streaming.

Assistant controls the canvas using typed action blocks.

## Run
```bash
python -m scripts.examples.canvas.main
```

Open: `http://localhost:5012`

## What Alpha Supports
- Draggable cards (drag the card header)
- Resizable cards (drag the bottom-right corner)
- Card model: `id`, `title`, `x`, `y`, `w`, `h`, `content[]`
- Content model: `id`, `type` (`text|html`), `text`, `html`, `align` (`left|center|right`)
- Assistant-driven CRUD for cards and content via `pylogue-canvas` fenced blocks

## Assistant Action Contract
Preferred path: assistant calls tool `canvas_actions(actions=[...])`.

Fallback path: assistant emits a fenced block:

```text
```pylogue-canvas
{"actions":[ ... ]}
```
```

Supported operations:

### `create_card`
```json
{"op":"create_card","card":{"id":"card-2","title":"Revenue","x":140,"y":100,"w":360,"h":240,"content":[]}}
```

### `update_card`
```json
{"op":"update_card","id":"card-2","patch":{"title":"Weekly Revenue","w":420,"h":280}}
```

### `delete_card`
```json
{"op":"delete_card","id":"card-2"}
```

### `create_content`
```json
{"op":"create_content","card_id":"card-2","content":{"id":"content-7","type":"text","text":"Top SKUs","align":"center"}}
```

### `update_content`
```json
{"op":"update_content","card_id":"card-2","content_id":"content-7","patch":{"text":"Top SKUs (7d)","align":"left"}}
```

### `delete_content`
```json
{"op":"delete_content","card_id":"card-2","content_id":"content-7"}
```

## LLM Read Context (Alpha)
Before each prompt is sent, the frontend appends a compact canvas snapshot in a hidden fenced block:
- fence type: `pylogue-canvas-state`
- payload: JSON with current cards and content

This gives the model current canvas state for update/delete decisions.

## Notes / Limits
- Frontend action execution currently ignores malformed JSON blocks silently.
- `html` content is inserted directly in card body for flexibility; avoid untrusted HTML in production.
- No server persistence for canvas cards yet (memory in browser session).
- No authorization/allowlist layer yet for action permissions.
- Tool channel is supported through hidden `tool-canvas-actions` payloads in chat stream.
