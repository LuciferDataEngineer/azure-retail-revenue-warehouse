import React from "react";
import { ChartRenderer as SharedChartRenderer } from "@openai/data-charts";
import { hasReviewedBoxPlotSummary } from "./chart-transforms.js";
import { BarFamilyRenderer } from "./BarFamilyRenderer.jsx";
import { useDashboardAsk } from "../components/DashboardAsk.jsx";

/** Adapt the shared chart core to Data's existing editor, selection and presentation API. */
export function ChartRenderer({ spec, canonical = false, ...props }) {
  const interactions = useDashboardAsk();
  // Released HTML labels name physical axes; the shared horizontal renderer
  // labels category/value fields. Canonical configs already translate these.
  // Retained raw-observation charts default to minimum/maximum whiskers.
  // Reviewed summaries already supply their endpoints and cannot accept a rule.
  const compatible = canonical ? spec
    : ["horizontalBar", "horizontal-bar", "horizontalStackedBar", "horizontalStackedBar100"].includes(spec?.type)
      ? { ...spec, xLabel: spec.yLabel, yLabel: spec.xLabel }
    : spec?.type === "boxPlot" && spec.whiskers == null && !hasReviewedBoxPlotSummary(props.rows ?? [])
    ? { ...spec, whiskers: "minMax" }
    : spec?.type === "histogram" && !spec.bins
      ? { ...spec, yLabel: spec.showYAxisLabel === false ? "" : spec.yLabel ?? "Observations" } : spec;
  return <SharedChartRenderer {...props} spec={compatible} interactions={interactions}
    presentationRenderer={BarFamilyRenderer} />;
}
