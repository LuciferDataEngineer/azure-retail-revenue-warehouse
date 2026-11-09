import { chartDataInputKeys } from "./chart-data-shape.js";
import { toRendererSpec } from "./shared/adapters/inline/physical-axes.js";

const wideVerticalTypes = new Set(["area", "stackedArea", "line", "sparkline", "bar", "stackedBar", "stackedBar100"]);

/** Saved settings are complete snapshots. Reviewed inputs stay current with the rows. */
export function resolveChartSpec(authored, saved, dataInputs) {
  let effective = saved ?? authored;
  // Leave malformed inputs for the renderer's per-chart error state.
  if (saved == null && wideVerticalTypes.has(authored?.type) && Array.isArray(authored.y)
    && authored.y.length && authored.y.every(key => typeof key === "string" && key.trim())
    && !Object.hasOwn(authored, "fields") && !Object.hasOwn(authored, "series")) {
    effective = toRendererSpec(authored);
  }
  if (saved == null && dataInputs == null) return effective;
  const chart = { ...effective };
  // Older apps put these data inputs in spec. Preserve that API without merging settings.
  for (const inputs of [authored, dataInputs]) {
    for (const key of chartDataInputKeys) {
      if (Object.hasOwn(inputs ?? {}, key)) chart[key] = inputs[key];
    }
  }
  return chart;
}
