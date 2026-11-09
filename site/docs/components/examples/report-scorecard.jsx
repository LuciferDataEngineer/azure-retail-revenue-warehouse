import React from "react";
import { DataTable, ReportSection, RichNarrative } from "../../data-app-public.jsx";

// Copy beneath src/content/shared/. Pass calculated display rows and the
// original reviewed evidence separately; formatted strings preserve precision.
export function ReportScorecard({ queryId, sourceRows, rows }) {
  return <ReportSection id="kpi-scorecard" title="Weekly KPI scorecard" queryId={queryId} sourceRows={sourceRows}>
    <RichNarrative id="kpi-scorecard:intro" value="Completed-week comparisons against operating targets. **pp** means percentage points." />
    <DataTable rows={rows} searchable={false} caption="Weekly KPI scorecard"
      columns={[
        { field: "kpi", label: "KPI" },
        { field: "previous", label: "Sep 7–13" },
        { field: "latest", label: "Sep 14–20" },
        { field: "change", label: "Weekly change" },
        { field: "target", label: "Latest target" },
        { field: "status", label: "Gap / status" },
      ]} />
  </ReportSection>;
}
