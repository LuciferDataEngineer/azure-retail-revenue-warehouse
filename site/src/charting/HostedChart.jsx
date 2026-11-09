import React, { lazy, Suspense } from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as jsx from "react/jsx-runtime";
import * as jsxDev from "react/jsx-dev-runtime";
import * as Recharts from "recharts";
import pin from "@openai/data-chart-pin";

const peers = { react: React, "react-dom": ReactDOM, "react-dom/client": ReactDOMClient,
  "react/jsx-runtime": jsx, "react/jsx-dev-runtime": jsxDev, recharts: Recharts };

function loadAsset(name) {
  const url = new URL("library/" + name, pin.baseUrl).href;
  const node = document.createElement(name.endsWith(".css") ? "link" : "script");
  if (node.tagName === "LINK") {
    node.rel = "stylesheet";
    node.href = url;
  } else {
    node.src = url;
  }
  const hash = pin.library.assets[name].sha256;
  node.integrity = "sha256-" + btoa(String.fromCharCode(...hash.match(/../g).map(byte => parseInt(byte, 16))));
  node.crossOrigin = "anonymous";
  return new Promise((resolve, reject) => {
    node.onload = resolve;
    node.onerror = () => reject(new Error("Chart library unavailable"));
    document.head.append(node);
  });
}

let libraryPromise;
function loadLibrary() {
  return libraryPromise ??= Promise.all([loadAsset("library.js"), loadAsset("chart.css")]).then(() => {
    const factory = globalThis.DataChartLibraries?.[pin.library.buildId];
    if (factory?.apiVersion !== pin.library.apiVersion) throw new Error("Incompatible chart library");
    return factory.create(peers);
  });
}

function hostedComponent(name) {
  const Component = lazy(() => loadLibrary().then(
    library => ({ default: library[name] }),
    () => ({ default: () => <p role="status">Charts couldn’t load. Check your connection and reload.</p> }),
  ));
  return function HostedComponent(props) {
    return <Suspense fallback={<p role="status">Loading chart…</p>}><Component {...props} /></Suspense>;
  };
}

export const ChartRenderer = hostedComponent("ChartRenderer");
export const BarFamilyRenderer = hostedComponent("BarFamilyRenderer");
export const ChartMark = hostedComponent("ChartMark");
export const ProgressTooltip = hostedComponent("ProgressTooltip");
export const BarTooltip = hostedComponent("BarTooltip");
