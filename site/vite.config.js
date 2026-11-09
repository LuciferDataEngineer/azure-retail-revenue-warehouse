import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const localThreadId = [process.env.CODEX_SESSION_ID, process.env.CODEX_THREAD_ID].find((value) =>
  /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/iu.test(value ?? ""),
);

const projectRoot = new URL(existsSync(new URL("./src", import.meta.url)) ? "./" : "../", import.meta.url);
const source = path => fileURLToPath(new URL("src/" + path, projectRoot));

const snapshotIntegrityPlugin = {
  name: "data-app-snapshot-integrity",
  async transformIndexHtml(_html, context) {
    const root = fileURLToPath(projectRoot);
    let snapshotBytes = readFileSync(source("data.json"));
    if (context?.filename && /^examples\/(?:compositions\/)?[\w-]+\/index\.html$/u.test(relative(root, context.filename).replaceAll("\\", "/"))) {
      const entry = join(dirname(context.filename), "data.js");
      if (!existsSync(entry)) throw new Error(`Gallery example needs an explicit snapshot entry: ${entry}`);
      const { snapshot } = context.server ? await context.server.ssrLoadModule(entry) : await import(pathToFileURL(entry).href);
      snapshotBytes = JSON.stringify(snapshot, null, 2) + "\n";
    }
    return [
      {
        tag: "meta",
        attrs: {
          name: "data-app-snapshot-sha256",
          content: createHash("sha256")
            .update(snapshotBytes)
            .digest("hex"),
        },
        injectTo: "head",
      },
      ...(context?.server && context.filename ? [{
        tag: "meta",
        attrs: { name: "data-app-local-reference", content: JSON.stringify({ root, htmlPath: context.filename }) },
        injectTo: "head",
      }] : []),
    ];
  },
};

export default defineConfig(({ command, isSsrBuild }) => ({
  // Gallery launchers and prepared apps consume the same authored reference modules.
  resolve: {
    alias: {
      "@openai/data-ui": source("ui/"),
      "@openai/data-app-runtime": source(""),
      "../../../templates/data-app-public.jsx": source("data-app-public.jsx"),
      "@openai/data-charts/chart.css": source("charting/hosted-chart.css"),
      "@openai/data-charts": source("charting/HostedChart.jsx"),
      "@openai/data-chart-pin": existsSync(source("charting/cdn.json")) ? source("charting/cdn.json") : fileURLToPath(new URL("../visualize-data/assets/cdn.json", projectRoot)),
    },
    // Canonical examples and UI sources live outside this package; resolve their
    // peers from this app's installed runtime as well as keeping React shared.
    dedupe: ["react", "react-dom", "recharts", "@radix-ui/react-dialog", "@radix-ui/react-dropdown-menu", "figma-squircle"],
  },
  plugins: isSsrBuild
    ? []
    : [
        viteSingleFile(),
        snapshotIntegrityPlugin,
        {
          name: "data-app-local-task",
          // Development gallery only. Prepared apps retain their own root entry.
          configureServer(server) {
            if (!existsSync(join(server.config.root, "examples/product-tracker/main.jsx"))) return;
            server.middlewares.use((request, response, next) => {
              if (request.method !== "GET" || request.url?.split("?")[0] !== "/") return next();
              response.writeHead(302, { Location: `/examples/product-tracker/${request.url.slice(1)}` });
              response.end();
            });
          },
          transformIndexHtml: () =>
            localThreadId
              ? [
                  {
                    tag: "meta",
                    attrs: {
                      name: "data-app-local-thread",
                      content: localThreadId,
                    },
                    injectTo: "head",
                  },
                ]
              : [],
        },
      ],
  server: {
    allowedHosts: ["terminal.local"],
    ...(process.env.CODEX_SANDBOX === "seatbelt" ? { watch: { useFsEvents: false, usePolling: true } } : {}),
  },
  define: {
    __DATA_APP_PROJECT_ROOT__: JSON.stringify(command === "serve" ? process.cwd() : ""),
  },
  build: isSsrBuild ? { rollupOptions: { output: { entryFileNames: "index.js" } } } : {},
}));
