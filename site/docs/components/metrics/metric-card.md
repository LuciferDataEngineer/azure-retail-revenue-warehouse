# Metric cards

Use the standard value, comparison and description slots. This complete example assumes `current` and `previous` are already computed for the selected periods and filters, and `sourceRows` contains their reviewed evidence. Replace `queryId` with that evidence query's ID. Identify the comparison period once in the surrounding controls.

Custom KPI layouts can keep their own hierarchy. Give enlarged values an explicit line height and space before the label; an inherited body line height can be smaller than the glyphs. Scope typography to the value slot, rather than every `b` or `strong` inside a page that also contains charts. For a value-first reading, for example:

```jsx
<div className="launch-reading">
  <b className="launch-reading-value">1 / 3</b>
  <span>devices ready</span>
</div>
```

```css
.launch-reading { display: grid; gap: 8px; min-width: 0; }
.launch-reading > .launch-reading-value {
  font-size: 38px; line-height: 1.15; overflow-wrap: anywhere;
}
```

Check the value/label gap with wrapped labels and large values at phone width. The standard `MetricCard` already supplies its own value line height and spacing.

```jsx
import React from "react";
import { MetricCard, periodComparison } from "../../data-app-public.jsx";

export function RevenueMetric({ current, previous, sourceRows, history, selectedPeriod, periodDescription }) {
  return <MetricCard id="revenue" queryId="account_days" title="Revenue"
    value={current == null ? "—" : new Intl.NumberFormat("en-US", {
      style: "currency", currency: "USD", maximumFractionDigits: 0,
    }).format(current)}
    {...periodComparison(current, previous, { includePeriod: false })}
    trendValues={history} trendLabel={`Revenue · ${periodDescription}`}
    periodLabel={selectedPeriod} periodDescription={periodDescription}
    description="Recognized revenue during the selected period."
    sourceRows={sourceRows} />;
}
```

Required props are `id`, `queryId`, `title` (strings) and `value` (text, number or JSX). `comparison` also accepts text or JSX; `description` is plain text shown by the info control. `periodComparison` returns `{ comparison?, negative? }`, so spread its result as above. For a lower-is-better metric, pass `lowerIsBetter: true`. `trendValues` is a numeric array with `null` gaps, `trendLabel` names its measure/grain, and `periodLabel` shows a short selected window beside the sparkline, or below the reading when no sparkline is shown. For example, pass `selectedPeriod="Jul 5–8"` and `periodDescription="Jul 5–8, 2026 · Daily"`; the full description appears on hover, focus or tap. Without a description, the label stays plain text. Supply these by default for dated metrics with comparable history. Derive them from the same date/category selection as the value; use selected boundaries even for empty scope. Include years in a cross-year label. Do not infer rolling windows from point counts or shorten a historical range to `Last 2 weeks`. Never parse formatted values into a history or sum distinct counts/ratios. Omit a trend when no comparable history exists; `trendValues={[]}` and an omitted/empty `periodLabel` remain deliberate opt-outs. Use `deltaTone="positive"`, `"negative"` or `"neutral"` for an explicitly computed semantic tone. The [complete props](../../../scripts/types/data-app-public.d.ts) are optional reference material.

`View.Metric` also accepts `trendValues(rows)`, `trendLabel(rows)`, `periodLabel(rows)` and `periodDescription(rows)` callbacks over the same filtered records as `value(rows)`. Static arrays and labels remain supported. See the [typed example](../component-kit.md#dated-metrics) for explicit bucketing; the wrapper never infers aggregation from the display value.

`MetricCard` uses `variant="card" padding="spacious"` by default, with a 112px minimum height. It accepts children for an integrated trend and omits its duplicate mini-sparkline. Supply the chart spec, display rows, and nonduplicated source evidence for consistent editing and inspection. See [comparison formatting](comparison-formatting.md) for deltas and trend labels.

Use `comparison` for the prior-value or change reading and `description` for the metric definition exposed by the shared info control. Children remain available for a useful integrated trend or custom detail; they are not needed to reproduce those standard slots. Keep adjacent headline values aligned when their supporting content differs, and verify both the compact and expanded layouts.

`MetricCardTabs` groups related selectable metrics with one associated chart/detail panel. Keep its selected ID controlled and use stable item IDs; retain separate charts when simultaneous comparison matters. See [comparison formatting](comparison-formatting.md) for item tones.

Import these components through the app's `data-app-public.jsx` entry. Their evidence actions and presentation state use the Data app providers; they are not a standalone inline React entry. For shared card styling and evidence scope, see [cards and layout](../layout/layout.md).
