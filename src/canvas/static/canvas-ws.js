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
    if (event.data === "canvas_refresh") {
      if (window.htmx) {
        console.log("[canvas-ws] triggering htmx canvas_refresh");
        window.htmx.trigger(document.body, "canvas_refresh");
        return;
      }
      console.warn("[canvas-ws] htmx not found; canvas refresh not triggered");
      return;
    }
    if (typeof event.data === "string" && event.data.startsWith("canvas_navigate:")) {
      try {
        const payload = JSON.parse(event.data.slice("canvas_navigate:".length));
        const panelHref = payload?.panel_href;
        const pageHref = payload?.page_href;
        if (!panelHref || !pageHref) return;
        console.log("[canvas-ws] navigating", { panelHref, pageHref });
        fetch(panelHref, { headers: { "HX-Request": "true" } })
          .then((res) => (res.ok ? res.text() : Promise.reject(new Error(`HTTP ${res.status}`))))
          .then((html) => {
            const host = document.createElement("div");
            host.innerHTML = html.trim();
            const nextPanel = host.firstElementChild;
            const currentPanel = document.getElementById("canvas-panel");
            if (!nextPanel || !currentPanel) throw new Error("canvas-panel missing");
            currentPanel.outerHTML = nextPanel.outerHTML;
            window.history.pushState({}, "", pageHref);
            window.dispatchEvent(new CustomEvent("pylogue:canvas-changed"));
            const inserted = document.getElementById("canvas-panel");
            if (inserted && window.htmx) window.htmx.process(inserted);
          })
          .catch((err) => {
            console.error("[canvas-ws] navigation failed; falling back", err);
            window.location.assign(pageHref);
          });
      } catch (err) {
        console.error("[canvas-ws] bad canvas_navigate payload", err);
      }
      return;
    }
    if (window.htmx && event.data) {
      console.log("[canvas-ws] triggering htmx canvas_refresh");
      window.htmx.trigger(document.body, String(event.data));
      return;
    }
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
