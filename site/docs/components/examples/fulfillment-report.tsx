import React from "react";
import { View, type RowsOf } from "../view";
import { ReportFrame } from "../shared/ReportParts.jsx";
import { ReportCitation } from "../shared/ReportSources.jsx";
import "./report.css";

const sources = ["shipments"];

// The reviewed shipments query has date, carrier, shipped and onTime columns.
function byCarrier(rows: RowsOf<"shipments">) {
  const counts = new Map<string, number>();
  for (const row of rows) counts.set(row.carrier, (counts.get(row.carrier) ?? 0) + row.shipped);
  return Array.from(counts, ([carrier, shipped]) => ({ carrier, shipped }));
}

function onTimeRate(rows: RowsOf<"shipments">) {
  const shipped = rows.reduce((n, row) => n + row.shipped, 0);
  const onTime = rows.reduce((n, row) => n + row.onTime, 0);
  return shipped ? (onTime / shipped).toLocaleString("en-US", { style: "percent", maximumFractionDigits: 1 }) : "—";
}

export function ReportContent() {
  return <View.Provider><ReportFrame sources={sources} preparedOn="Oct 5, 2026">
    <View.Filters />
    <View.Block id="summary" query="shipments" title="Summary">
      {rows => <p>The on-time rate for the selected shipments is {onTimeRate(rows)}. <ReportCitation queryIds={sources} queryId="shipments" /></p>}
    </View.Block>
    <View.Metric id="on-time" title="On-time shipment rate" query="shipments" value={onTimeRate} />
    <View.Chart id="carriers" title="Shipments by carrier" query="shipments" select={byCarrier}
      spec={{ type: "horizontalBar", x: "shipped", y: "carrier", xLabel: "Shipments" }} />
    <View.Table id="shipment-detail" title="Daily shipment records" query="shipments" />
  </ReportFrame></View.Provider>;
}
