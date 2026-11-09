# Typed data views

This is the optional `--component-kit` authoring path. Default HTML dashboard and report preparation uses the production JSX composition and public components.

Read this guide and the generated `src/content/view.ts` once; edit the preparer's returned `editableFile`. The components are bundled with the project, so authoring needs no package install or implementation read.

Reports retain the standard `ReportFrame`, numbered claim citations, Sources list and `report.css`; preserve those when customizing the body. Keep `ReportCitation` beside each supported finding, using the same ordered `sources` IDs as the frame. `--prepared-on`, `--author`, `--source` and `--chart` work with the kit. Add or modify charts and source IDs in the generated content.

The [worked report](examples/fulfillment-report.tsx) and [sample snapshot](examples/fulfillment-snapshot.json) show a pooled rate, claim citation and horizontal comparison sharing selected shipment records. Import `RowsOf<"queryId">` from `../view` for extracted helpers.

## One contract, one scope

`view.ts` declares query IDs, row fields, nullability and grain. Preparation infers field shape from all supplied rows; review it against the analysis. It does not infer units, metric definitions or aggregation. Keep dates and dimension columns in `breakdown` to retain history and detailed rows. A different aggregate grain needs its own explicit view contract. Add new fields/queries there when the analysis changes; do not weaken the contract to hide errors. Reviewed empty arrays are supported, but declare their fields and types before adding measures; preparation can retain filter field names, not infer missing types. Unavailable/deferred data must remain distinct from an empty result.

```tsx
// src/content/view.ts — initialize once, outside render
import { createDataView } from "./shared/DataView";
export const View = createDataView({
  sales: { columns: {date:"date", region:"string", revenue:"number", cost:"number"},
    breakdown: ["date", "region"] }
});
```

```tsx
// src/content/dashboard/DashboardBody.tsx (also works in ReportBody.tsx)
import React from "react";
import { View } from "../view";
import { Section } from "../../data-app-public.jsx";
export function DashboardContent() {
  return <View.Provider>
    <View.Filters />
    <Section>
    <View.Chart id="trend" query="sales" title="Revenue by day and region"
      spec={{type:"line", x:"date", y:"revenue", series:"region"}} />
    <View.Table id="detail" query="sales" title="Reviewed rows"
      columns={[{field:"date"},{field:"region"},{field:"revenue"}]} />
    <View.Block id="margin" query="sales" title="Contribution">
      {rows => <p>{rows.reduce((sum, row) => sum + row.revenue - row.cost, 0)}</p>}
    </View.Block>
    </Section>
  </View.Provider>;
}
```

Page filters/date ranges come from `src/data.json.filters` and the existing shell. All components above use the same scoped rows, source evidence and saved state. For multi-query views, set a filter's `queryIds` when it applies only to some queries; missing fields produce a diagnostic rather than a silently ignored filter. Unknown queries, fields and table columns fail typechecking; malformed refreshed values fail runtime validation. Charts retain the standard renderer, editor and menu. Top-level chart field bindings are checked against input or `select` output fields; specialized nested chart options also need the existing chart validation.

**Reports require an explicit visibility opt-in.** Beside `<View.Filters />` in a report, configure the intended page filters in `src/data.json`, for example:

```json
{
  "surface": "report",
  "report": { "visibleFilterIds": ["date", "region"] },
  "filters": [
    { "id": "date", "field": "date", "label": "Date range", "type": "date", "mode": "through", "queryIds": ["sales"] },
    { "id": "region", "field": "region", "label": "Region", "defaultValue": "all", "queryIds": ["sales"] }
  ]
}
```

Merge these fields with the snapshot's existing queries and metadata. Setting `visible: true` on each intended filter is another supported opt-in. Hidden definitions stay inactive for report rows and Sources; listing only a subset keeps the others hidden. A mounted page `<View.Filters />` with configured filters but no visibility declarations raises an actionable error when all controls would disappear. An explicitly empty visibility list or explicit hidden definitions remain supported. For a static report, omit the filter bar. A date-range control uses `type: "date", mode: "through"`; `mode: "exact"` selects one value and `mode: "date-range"` is unsupported. Section-local definitions belong on `View.Section` and do not need page visibility opt-ins.

## Component map

| Need | Use / read only if needed |
| --- | --- |
| Standard chart | `View.Chart` uses the [public chart spec](../../../../skills/visualize-data/docs/react/app-charts.md). Bind physical axes. A horizontal bar puts the number on `x` and category on `y`. Use `select={rows => ...}` for derived plot rows. Sources retain scoped input rows. |
| KPI | `View.Metric` with typed `value(rows)`, compact `periodLabel` and full `periodDescription`. Add `trendValues(rows)` and `trendLabel` when a trend helps the decision; see [dated metrics](#dated-metrics) and [MetricCard props](metrics/metric-card.md). Handle empty/null/zero denominators explicitly. |
| Detail table | `View.Table`; typed columns and `table` options from [DataTable](tables/tables.md). |
| Custom sourced component | `View.Block` with typed `children(rows)`; it supplies the standard heading, actions and source details. |
| Reusable custom composition | `View.useQuery("sales")` inside the provider; returns `rows`, `sourceRows`, `displayRows`, `queryId`, `scopeFilters`. Wrap output in the existing `DataComponent` and forward the evidence binding. |
| Filters / dates | `View.Filters`; edit definitions in the snapshot, not separate component state. [Filter options](controls/filtering.md). |
| Scoped section | `View.Section` with stable `id`, `filters`, optional `initialValues`/`label`; put `View.Filters` and affected components inside. It intersects with page filters and reuses saved section state. |
| Layout / tabs / typography | Existing [layout](layout/layout.md), [sortable regions](layout/sortable-layout.md), [report narrative](narrative/reports.md), [primitives](primitives/primitives.md). The kit adds no layout engine. |
| Scenario inputs | Existing [numeric scenario helper](controls/numeric-scenarios.md) and [controls](controls/controls.md). Scenarios stay explicit and separate from reviewed actuals. |

## Dated metrics

Keep the selected period visible for dated metrics. Add a compact sparkline when at least two comparable observations provide useful context; omit it for a single observation or when the same pattern is already clear in an adjacent chart. The callbacks receive the same scoped facts as `value`; they do not choose a metric, aggregate automatically, or parse its formatted text. This daily sales example uses the `sales` contract above and the date filter below it:

```tsx
import React from "react";
import { View } from "../view";
import { Section, useDataApp } from "../../data-app-public.jsx";

function Headline() {
  const app = useDataApp();
  const dates = (app.queries.sales.rows ?? []).map(row => String(row.date)).sort();
  const selected = String(app.filters.date ?? "all");
  const [start, end = start] = selected === "all"
    ? [dates[0], dates.at(-1)] : selected.includes("..")
      ? selected.split("..") : [dates[0], selected];
  const days = start && end ? Array.from({
    length: Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 86400000) + 1),
  }, (_, i) => new Date(Date.parse(start) + i * 86400000).toISOString().slice(0, 10)) : [];
  const formatPeriod = (full: boolean) => {
    if (!start || !end) return "No dated coverage";
    const format = new Intl.DateTimeFormat("en-US", {
      month: "short", day: "numeric", timeZone: "UTC",
      ...(full || start.slice(0, 4) !== end.slice(0, 4) ? { year: "numeric" as const } : {}),
    });
    return format.formatRange(new Date(`${start}T00:00:00Z`), new Date(`${end}T00:00:00Z`));
  };
  const period = formatPeriod(false);
  const periodDescription = start && end ? `${formatPeriod(true)} · Daily` : period;
  return <>
    <Section id="headline" title="Performance" kind="metrics" columns={2}>
      <View.Metric id="revenue" query="sales" title="Revenue · USD"
        value={rows => rows.length ? rows.reduce((sum, row) => sum + row.revenue, 0) : "Unavailable"}
        trendValues={rows => days.map(date => {
          const day = rows.filter(row => row.date === date);
          return day.length ? day.reduce((sum, row) => sum + row.revenue, 0) : null;
        })}
        trendLabel={`Revenue · USD · ${periodDescription}`}
        periodLabel={period} periodDescription={periodDescription} />
    </Section>
    <Section spacing="after-metrics">
      <View.Table id="evidence" query="sales" title="Selected sales" />
    </Section>
  </>;
}
export function DashboardContent() {
  return <View.Provider><View.Filters /><Headline /></View.Provider>;
}
```

Keep selected boundaries visible even when category filters produce no rows. For nullable measures, preserve missing buckets and qualify sums of known values as observed/incomplete. Recompute daily distinct counts and ratios from each day's facts; the headline's period distinct count is not a sum of daily counts. Event histories use their metric's event date (for example, openings use `opened_date`). An undated or incomparable snapshot has no meaningful sparkline. Explicit `trendValues={[]}`, omitted/empty `periodLabel`, and custom integrated children remain supported.

`Section` owns the space before its content: use `kind="metrics"` for the KPI grid and `spacing="after-metrics"` on the following section, including a single readout card. Preserve deliberate `spacing="none"` and custom layouts. The shared card owns its internal padding.

## Modify or extend

Change a component's props, formula or layout in authored content. Extract repeated custom components into `src/content/shared/` and consume `View.useQuery` or `View.Block`; they then follow the current page/section scope automatically. For a derived chart, return records from `select`; the chart's field bindings refer to those records. For multi-query joins or calculations, retain the relevant original reviewed inputs alongside the explicit joined/derived query in the snapshot and view contract. On `View.Chart`, `View.Metric`, `View.Table` or `View.Block`, name those additional inputs with `evidenceQueries={['sales', 'traffic']}`. Each named query is resolved through the current page and section scope; `query` still supplies the displayed rows and values. Sources offers only the primary and explicitly named queries. Do not pass raw `queryIds`, `sourceRowsByQuery` or other binding overrides. Keep the original grain in each input's `breakdown`; do not substitute aggregate or invented rows for missing evidence. Record the actual inputs and calculation using the [supported source metadata fields](sources/sources.md). The kit never silently chooses a join, sums a ratio or changes the query grain.

For a section, use `<View.Section id="region-detail" filters={[{id:"detail-region",field:"region",label:"Detail region"}]}><View.Filters />…</View.Section>`. Section “All” stays within the page selection. One level of sections is supported. Reports with hidden filter definitions plus section scopes are rejected; remove unused hidden definitions first. These diagnostics prevent ambiguous scope. Existing dashboards/reports remain supported through the original public API.

Each project has a pinned editable copy of the library. Prefer authored custom components; change the copied library only for behavior they cannot express. Shared changes belong in the plugin's canonical library and behavioral tests and apply to newly prepared projects.

## Validate once, then inspect the behavior

For an unfamiliar component or query, run `node <plugin>/output_formats/html/scripts/data-app.mjs describe --project-dir <app> --component Chart --query <queryId>` for its props and field types. Omit both selectors for a short index. The lookup is optional when the starter already shows what you need.

Run `data-app.mjs check` and the build/finish flow. For filter-dependent calculations, use the verifier's `selectFilter`, `selectDateRange` and `withSource` callbacks in a short `--checks` file, following the [shared interaction recipe](controls/filtering.md#validate-filtered-values). These helpers handle desktop/touch controls and bounded waits. Assert the expected KPI, chart and source rows from the reviewed input, then reset. Check empty and zero cases, saved-view restoration and narrow/mobile layout when relevant. Compiler success does not establish metric correctness or layout quality.
