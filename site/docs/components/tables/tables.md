# Tables

Use `DataTable` (also exported as `Table`) for reviewed tabular data, with a `DataComponent` evidence wrapper where source/actions menus are needed. Keep scoped original evidence in `sourceRows`; `displayRows` may contain the derived values shown in the table. Multiple-source bindings are described in [layout](../layout/layout.md#evidence-wrappers).

## Report scorecard

`RichNarrative` supports prose Markdown, not pipe tables. Keep the narrative and a real `DataTable` side by side inside `ReportSection` (or `DataComponent`). The wrapper supplies Sources; the table supplies semantic headers, cells, sorting and horizontal scrolling on phones.

Copy the complete [ReportScorecard example](../examples/report-scorecard.jsx) beneath `src/content/shared/`, then call it from `ReportContent.jsx`:

```jsx
import { ReportScorecard } from "../shared/report-scorecard.jsx";
import { useDataApp } from "../../data-app-public.jsx";

export function ReportContent() {
  const { reviewedRows } = useDataApp();
  const sourceRows = reviewedRows("weekly");
  // Illustrative calculated display rows; replace with the reviewed analysis.
  const rows = [
    { kpi: "Weekly active accounts", previous: "820", latest: "900",
      change: "+80 / +9.76%", target: "≥950", status: "50 below; missed" },
    { kpi: "New-account activation", previous: "40.0%", latest: "44.0%",
      change: "+4.0 pp / +10.0%", target: "≥45.0%", status: "1.0 pp below; missed" },
  ];
  return <article className="report-content">
    <ReportScorecard queryId="weekly" sourceRows={sourceRows} rows={rows} />
  </article>;
}
```

Ordinary prebuilt `build` and offline `check` reject detectable pipe tables passed to `RichNarrative`, with `DATA_NARRATIVE_TABLE` and this repair path. The check follows static strings, concatenations/templates, imported constants, object/tuple members and literal-array `.map` bindings without running authored code. Fenced/indented code examples, inline code and ordinary pipes remain valid prose. Dynamic helpers, runtime data, prop spreads and saved narrative edits cannot be fully proven offline; `DATA_NARRATIVE_DYNAMIC` warns about unresolved authored values. Inspect representative rendered values and assert actual table headers, rows and cells at desktop and phone widths. The explicit `--source` build does not run this prebuilt validation.

## Columns and formatting

Column definitions support shared `identity` (with `secondaryField`), `sparkline`, `bar`, `status`, and `percent` cell presentations, including theme-aware visuals and accessible tooltips. They require no example-specific CSS. Keep unusual row density and chosen columns in authored content.

For specialized evidence cells, a column may supply `renderCell(value, row)`. It changes presentation only: search, sorting, source/export values, and first-column row actions still use the underlying evidence. Keep callbacks in authored code, not persisted specs.

Per-column `deltaTone` accepts `positive`, `negative`, `neutral`, or a function. Tone is an interpretation separate from numeric sign; omitting it preserves existing signed-delta behavior. See [comparison formatting](../metrics/comparison-formatting.md) for a signed percentage-point formatter and objective-based tones. Whole-percent presentation may round away small rates; use enough displayed precision while retaining raw numeric source rows.

## Search, local controls, and pagination

Use `toolbarControls` for controls affecting only table rows. Search and local filters share one toolbar; counts accompany pagination below. See [filtering](../controls/filtering.md) when a selection affects other blocks too.

Use `searchable={false}` for short fixed summaries, such as a two-period comparison, and keep search for record exploration. Pagination uses the shared eight-row page size; there is no `pageSize` prop.

## Accessible row actions

Supply an accessible `caption` or `label`. `DataTable` also accepts `rowKey`, `selectedRowKey`, `onRowSelect(row)`, and `rowActionLabel(row)`. Action rows accept pointer clicks and expose a first-cell keyboard action; embedded controls and text selection do not navigate.
