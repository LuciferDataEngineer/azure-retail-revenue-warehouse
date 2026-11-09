/** Shared, dependency-free status UI; the HTML bootstrap embeds this before CDN code. */
export const DATA_STATUS_CSS = `
[data-data-status]{box-sizing:border-box;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;min-height:inherit;padding:24px;border-radius:12px;background:color-mix(in srgb,currentColor 4%,transparent);color:inherit;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
[data-data-status][hidden]{display:none}
[data-data-status] p{margin:0;text-align:center}
[data-data-status] button{font:inherit;color:inherit;background:transparent;border:1px solid color-mix(in srgb,currentColor 25%,transparent);border-radius:8px;padding:6px 12px;cursor:pointer}
[data-data-status] button:focus-visible{outline:2px solid currentColor;outline-offset:3px}
[data-data-status] textarea{box-sizing:border-box;width:100%;max-width:640px;min-height:160px;resize:vertical;font:12px/1.5 monospace;color:inherit;background:transparent;border:1px solid currentColor;border-radius:6px;padding:8px}
`;

// Keep this function self-contained: it also runs in generated HTML when the CDN fails.
export function createDataStatus(root, { version = "unknown", surface = "chart" } = {}) {
  const doc = root.ownerDocument;
  const layer = root.querySelector("[data-data-status]") ?? doc.createElement("div");
  layer.setAttribute("data-data-status", "");
  if (!layer.parentNode) root.append(layer);
  const redact = value => String(value ?? "")
    .slice(0, 12_000)
    .replace(/https?:\/\/[^\s)]+/giu, url => "[url]" + (url.match(/(?::\d+){1,2}$/u)?.[0] ?? ""))
    .replace(/(?:file:\/\/)?\/(?:Users|home|root|private|tmp|var)\/[^\s):]+/gu, "[path]")
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/giu, "[email]")
    .replace(/\b(?:bearer\s+|(?:token|api[_-]?key|password|secret|authorization)\s*[:=]\s*)[^\s,;]+/giu, "[credential]")
    .replace(/(["'`])[^\n]*?\1/gu, "[quoted value]")
    .slice(0, 4000);
  return {
    ready() {
      layer.remove();
      root.removeAttribute("aria-busy");
    },
    fail(error, stage = "render") {
      if (!layer.parentNode) root.append(layer);
      root.removeAttribute("aria-busy");
      layer.hidden = false;
      layer.setAttribute("role", "alert");
      layer.setAttribute("data-data-status", "error");
      const title = doc.createElement("p");
      title.textContent = "An error occurred inside the visualization.";
      const button = doc.createElement("button");
      button.type = "button";
      button.textContent = "Copy error logs";
      const hint = doc.createElement("p");
      hint.setAttribute("role", "status");
      const logs = JSON.stringify({
        source: "data-plugin", version, surface, stage,
        timestamp: new Date().toISOString(),
        error: { name: redact(error?.name ?? "Error").slice(0, 128), message: redact(error?.message ?? error).slice(0, 1500),
          stack: redact(error?.stack).split("\n").slice(0, 9).join("\n") },
      }, null, 2);
      // Deliberately exclude chart configuration, reviewed rows, HTML and page URLs.
      const text = doc.createElement("textarea");
      text.readOnly = true;
      text.hidden = true;
      text.value = logs;
      text.setAttribute("aria-label", "Error logs");
      button.addEventListener("click", async () => {
        try {
          const clipboard = doc.defaultView?.navigator?.clipboard;
          if (!clipboard?.writeText) throw new Error("Clipboard unavailable");
          await clipboard.writeText(logs);
          hint.textContent = "Error logs copied.";
        } catch {
          text.hidden = false;
          hint.textContent = "Select and copy the error logs below.";
          text.focus();
          text.select();
        }
      });
      layer.replaceChildren(title, button, hint, text);
    },
  };
}
