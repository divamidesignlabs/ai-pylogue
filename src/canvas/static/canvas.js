const css = `
.canvas-shell { display: grid; grid-template-columns: 3fr 1fr; min-height: 100vh; }
.canvas-left { background: #f8fafc; border-right: 1px solid #e2e8f0; padding: 1rem; }
.canvas-right { background: #ffffff; padding: 1rem; }
.canvas-empty { height: calc(100vh - 2rem); border: 2px dashed #cbd5e1; border-radius: 0.75rem; }
.chat-panel { max-height: calc(100vh - 9rem); overflow: auto; }
@media (max-width: 960px) {
  .canvas-shell { grid-template-columns: 1fr; }
  .canvas-left { min-height: 30vh; border-right: 0; border-bottom: 1px solid #e2e8f0; }
  .chat-panel { max-height: 50vh; }
}
`;

const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);
