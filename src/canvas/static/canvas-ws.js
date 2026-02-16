const proto = window.location.protocol === "https:" ? "wss" : "ws";
const wsUrl = `${proto}://${window.location.host}/canvas/ws`;

const connect = () => {
  console.log("[canvas-ws] connecting", wsUrl);
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("[canvas-ws] connected");
  };

  ws.onmessage = (event) => {
    console.log("[canvas-ws] message", event.data);
    if (event.data !== "canvas_refresh") return;
    if (window.htmx) {
      console.log("[canvas-ws] triggering htmx canvas_refresh");
      window.htmx.trigger(document.body, "canvas_refresh");
      return;
    }
    console.warn("[canvas-ws] htmx not found; canvas refresh not triggered");
  };

  ws.onerror = (event) => {
    console.error("[canvas-ws] error", event);
  };

  ws.onclose = () => {
    console.log("[canvas-ws] closed; reconnecting in 1s");
    window.setTimeout(connect, 1000);
  };
};

connect();
