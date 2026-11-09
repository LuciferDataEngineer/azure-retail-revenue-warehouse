import React from "react";
import { BarFamilyRenderer as SharedBarFamilyRenderer } from "@openai/data-charts";
import { useDashboardAsk } from "../components/DashboardAsk.jsx";
export { ProgressTooltip, BarTooltip } from "@openai/data-charts";
export function BarFamilyRenderer(props) {
  const interactions = useDashboardAsk();
  return <SharedBarFamilyRenderer {...props} interactions={interactions} />;
}
