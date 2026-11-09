import React from "react";
import { ChartMark as SharedChartMark } from "@openai/data-charts";
import { useDashboardAsk } from "../components/DashboardAsk.jsx";
export function ChartMark(props) {
  const interactions = useDashboardAsk();
  return <SharedChartMark {...props} interactions={interactions} />;
}
