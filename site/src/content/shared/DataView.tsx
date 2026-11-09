import React, { createContext, useContext } from "react";
import {
  DataComponent, DataTable, EvidenceChart, Filters, MetricCard, QueryDataBoundary,
  useDataApp, useSectionFilters, chartConfigEntries,
} from "../../data-app-public.jsx";
import type {
  ChartEvidenceProps, DataComponentProps, DataRow, DataTableProps, FilterDefinition, FilterValues,
  FiltersProps, MetricCardProps, ScopedFilter, SingleChart, TableColumn,
} from "../../data-app-public.jsx";
import { assertDataViewSchema, assertFilterFields, assertReviewedRows } from "./data-view-contract";
import type { CheckedSchema, DataViewSchema, ReviewedRow } from "./data-view-contract";
export type { DataViewSchema, ReviewedRow } from "./data-view-contract";

type Evidence = { sourceRows: readonly DataRow[]; scopeFilters: readonly ScopedFilter[] };
const EvidenceContext = createContext<((query: string) => Evidence) | null>(null);
/** Existing report citations can join the active scope without knowing its schema. */
export function useDataViewEvidence(query: string): Evidence | undefined {
  return useContext(EvidenceContext)?.(query);
}

const boundProps = ["queryId", "queryIds", "sourceRows", "displayRows", "scopeFilters", "sourceRowsByQuery", "sectionFilters"] as const;
type BoundProps = typeof boundProps[number];
function componentProps<Props extends object>(props: Props): Props {
  const conflict = boundProps.find(key => Object.hasOwn(props, key));
  if (conflict) throw new Error(`Data view: ${conflict} is supplied by the active query scope.`);
  return props;
}
type SectionDefinition<Filter extends FilterDefinition> = { id: string; filters: readonly Filter[]; initialValues?: FilterValues; label?: string };
type Field<Row> = Extract<keyof Row, string>;
type NumericField<Row> = Extract<keyof { [K in keyof Row as NonNullable<Row[K]> extends number ? K : never]: Row[K] }, string>;
// Reviewed five-number summaries label a box plot's quantity without storing a raw observation field.
type BoxSummary = Record<"minimum" | "lowerQuartile" | "median" | "upperQuartile" | "maximum", number>;
type MeasureField<Row, Spec> = Spec extends { type: "boxPlot" } ? Row extends BoxSummary ? string : NumericField<Row> : NumericField<Row>;
type FieldReference<Value, Name> = Value extends string ? Name
  : Value extends readonly string[] ? { [I in keyof Value]: Name } : Value;
type HorizontalBar = "horizontalBar" | "horizontalStackedBar" | "horizontalStackedBar100";
type MeasureAxis<Spec> = Spec extends { type: HorizontalBar } ? "x"
  : Spec extends { type: "heatmap" } ? never : Spec extends { type: "histogram" } ? "x" | "y" : "y";
type BoundChartSpec<Row, Spec = SingleChart["spec"]> = Spec extends unknown ? {
  [P in keyof Spec]: P extends "x" | "y" | "value" | "category" | "series" | "stages" | "rowId"
    ? Spec[P] extends { lower: string; upper: string; label: string }
      ? { lower: NumericField<Row>; upper: NumericField<Row>; label: Field<Row> }
      : FieldReference<Spec[P], P extends MeasureAxis<Spec> | "value"
        ? MeasureField<Row, Spec> : Field<Row>>
    : Spec[P];
} : never;

/** Initialize once at module scope. The shell remains the sole owner of view state. */
export function createDataView<const Schema extends DataViewSchema>(schema: Schema & CheckedSchema<Schema>) {
  assertDataViewSchema(schema);
  type Key = Extract<keyof Schema, string>;
  type Row<K extends Key> = ReviewedRow<Schema[K]>;
  type LocalFilter = Omit<FilterDefinition, "field" | "queryIds"> & {
    field: { [K in Key]: Field<Row<K>> }[Key]; queryIds?: readonly Key[];
  };
  type Binding<K extends Key> = {
    queryId: K; rows: readonly Row<K>[]; sourceRows: readonly Row<K>[];
    displayRows: readonly Row<K>[]; scopeFilters: ScopedFilter[];
  };
  type Resolve = <K extends Key>(query: K) => Binding<K>;
  const Context = createContext<{ resolve: Resolve; filters: React.ComponentProps<typeof Filters>; section: boolean; hiddenReportFilters: boolean } | null>(null);
  // Query updates replace row arrays. Share validation across components/scopes,
  // but never reuse it for a refreshed array or another query contract.
  const checked = new Map<string, WeakSet<object>>();
  const ids = Object.keys(schema);

  function useView() {
    const view = useContext(Context);
    if (!view) throw new Error("Data view components must be inside View.Provider.");
    return view;
  }
  function useQuery<K extends Key>(query: K): Binding<K> { return useView().resolve(query); }
  type EvidenceQueries = { evidenceQueries?: readonly Key[] };
  function useEvidence<K extends Key>(query: K, evidenceQueries: readonly Key[] = []) {
    const { resolve } = useView();
    if (!Array.isArray(evidenceQueries)) throw new Error("Data view: evidenceQueries must be an array of reviewed query names.");
    const primary = resolve(query);
    const queryIds = [...new Set([query, ...evidenceQueries])];
    if (queryIds.length === 1) return primary;
    const bindings = queryIds.map(id => resolve(id));
    const filters = new Map<string, ScopedFilter>();
    for (const binding of bindings) {
      for (const filter of binding.scopeFilters) {
        const key = JSON.stringify([filter.field, filter.label, filter.value]);
        const previous = filters.get(key);
        filters.set(key, { ...filter, queryIds: [...(previous?.queryIds ?? []), binding.queryId] });
      }
    }
    return { ...primary, queryIds, scopeFilters: [...filters.values()],
      sourceRowsByQuery: Object.fromEntries(bindings.map(binding => [binding.queryId, binding.sourceRows])) };
  }

  function Scope({ children, section }: { children?: React.ReactNode; section?: SectionDefinition<LocalFilter> }) {
    const app = useDataApp();
    const parent = useContext(Context);
    if (section && (!parent || parent.section)) throw new Error("View.Section belongs directly within a View.Provider scope; nested section scopes are not supported.");
    const local = useSectionFilters(section?.filters ?? [], section?.initialValues ?? {}, section ? { id: section.id, label: section.label } : undefined);
    const visibleFilterIds = app.snapshot.report?.visibleFilterIds ?? app.snapshot.visibleReportFilters;
    const definitions = (app.snapshot.filters ?? []).filter(filter => app.snapshot.surface !== "report"
      || filter.visible === true || filter.reportVisible === true || filter.surface === "report"
      || filter.surfaces?.includes("report") || (Array.isArray(visibleFilterIds) && visibleFilterIds.includes(filter.id)));
    const explicitVisibility = Array.isArray(visibleFilterIds) || (app.snapshot.filters ?? []).every(filter =>
      filter.visible !== undefined || filter.reportVisible !== undefined || filter.surface !== undefined || filter.surfaces !== undefined);
    if (section && app.snapshot.surface === "report" && definitions.length !== (app.snapshot.filters ?? []).length)
      throw new Error("Data view: remove hidden report filter definitions before adding a section scope.");
    assertFilterFields(schema, [...definitions, ...(section?.filters ?? [])]);
    const resolved = new Map<string, Binding<Key>>();
    const resolve: Resolve = <K extends Key,>(query: K): Binding<K> => {
      if (!Object.hasOwn(schema, query)) throw new Error(`Data view: unknown query ${query}.`);
      const cached = resolved.get(query);
      if (cached) return cached as Binding<K>;
      const contract = schema[query];
      const original = app.queries[query]?.rows;
      const seen = checked.get(query) ?? new WeakSet<object>();
      if (!original || !seen.has(original)) {
        assertReviewedRows(query, contract, original);
        seen.add(original); checked.set(query, seen);
      }
      // Keep the declared grain/history in every consumer. Authors decide their
      // aggregation explicitly; chart and metric selection do not change scope.
      const breakdown = contract.breakdown ?? Object.keys(contract.columns);
      const pageRows = section ? undefined : app.reviewedRows(query, breakdown);
      // The shell adds page filters to Sources/export metadata. Only local
      // filters belong in scopeFilters, otherwise page labels appear twice.
      const selected = section ? local.componentProps(query, breakdown) : {
        displayRows: pageRows!, sourceRows: pageRows!, scopeFilters: [],
      };
      const result = { ...selected, queryId: query, rows: selected.displayRows } as Binding<K>;
      resolved.set(query, result); return result;
    };
    return <EvidenceContext.Provider value={query => resolve(query as Key)}><Context.Provider value={{ resolve, section: Boolean(section),
      hiddenReportFilters: !section && app.snapshot.surface === "report" && !explicitVisibility && Boolean(app.snapshot.filters?.length) && !definitions.length,
      filters: section ? local.filterProps : {
      filters: definitions, queries: app.queries, values: app.filters, onChange: app.setFilter,
    } }}>{children}</Context.Provider></EvidenceContext.Provider>;
  }
  function Provider({ children }: { children?: React.ReactNode }) {
    return <QueryDataBoundary queryIds={ids}><Scope>{children}</Scope></QueryDataBoundary>;
  }
  function Section({ children, ...section }: SectionDefinition<LocalFilter> & { children?: React.ReactNode }) {
    return <Scope section={section}>{children}</Scope>;
  }
  function ViewFilters({ sticky = false, ariaLabel, clearLabel, showClear, trailingControls, children }: Pick<FiltersProps,
    "sticky" | "ariaLabel" | "clearLabel" | "showClear" | "trailingControls" | "children">) {
    const view = useView();
    if (view.hiddenReportFilters)
      throw new Error("Data view: View.Filters has no visible report filters. Set report.visibleFilterIds in src/data.json to the intended filter IDs (or set visible: true on those definitions). Remove View.Filters if this report should have no filter controls.");
    return <Filters {...view.filters} sticky={!view.section && sticky} ariaLabel={ariaLabel ?? view.filters.ariaLabel}
      clearLabel={clearLabel} showClear={showClear ?? view.filters.showClear} trailingControls={trailingControls}>{children}</Filters>;
  }
  type ChartProps = Omit<ChartEvidenceProps, BoundProps> & Pick<SingleChart, "id" | "title" | "summary" | "description" | "height"> & EvidenceQueries;
  function Chart<K extends Key, R extends DataRow>(props: ChartProps & {
    query: K; select: (rows: readonly Row<K>[]) => readonly R[]; spec: BoundChartSpec<NoInfer<R>>;
  }): React.ReactElement;
  function Chart<K extends Key>(props: ChartProps & {
    query: K; select?: never; spec: BoundChartSpec<Row<NoInfer<K>>>;
  }): React.ReactElement;
  function Chart<K extends Key>({ query, evidenceQueries, select, spec, id, title, summary, description, height, ...props }: ChartProps & {
    query: K; select?: (rows: readonly Row<K>[]) => readonly DataRow[]; spec: SingleChart["spec"];
  }) {
    const { rows, ...evidence } = useEvidence(query, evidenceQueries);
    let chart;
    try {
      [chart] = chartConfigEntries({ schemaVersion: 1, id, title, summary, description, height: height ?? undefined,
        spec, rows: [...(select ? select(rows) : rows)] });
    } catch (error) {
      return <div role="alert" data-chart-config-error="true">{error instanceof Error ? error.message : String(error)}</div>;
    }
    const chartOptions = { ...props.chartOptions, canonical: true, accessibleLabel: summary ?? title };
    return <EvidenceChart {...componentProps(props)} {...evidence}
      id={chart.id} title={chart.title} description={chart.description ?? undefined} height={chart.height}
      spec={chart.spec} rows={chart.rows} chartOptions={chartOptions} />;
  }
  type MetricReading<K extends Key, P extends "trendValues" | "trendLabel" | "periodLabel" | "periodDescription"> =
    MetricCardProps[P] | ((rows: readonly Row<K>[]) => MetricCardProps[P]);
  function Metric<K extends Key>({ query, evidenceQueries, value, trendValues, trendLabel, periodLabel, periodDescription, ...props }: Omit<MetricCardProps, BoundProps | "value" | "trendValues" | "trendLabel" | "periodLabel" | "periodDescription"> & EvidenceQueries & {
    query: K; value: (rows: readonly Row<K>[]) => React.ReactNode;
    trendValues?: MetricReading<K, "trendValues">; trendLabel?: MetricReading<K, "trendLabel">;
    periodLabel?: MetricReading<K, "periodLabel">;
    periodDescription?: MetricReading<K, "periodDescription">;
  }) {
    const { rows, ...evidence } = useEvidence(query, evidenceQueries);
    return <MetricCard {...componentProps(props)} {...evidence} value={value(rows)}
      trendValues={typeof trendValues === "function" ? trendValues(rows) : trendValues}
      trendLabel={typeof trendLabel === "function" ? trendLabel(rows) : trendLabel}
      periodLabel={typeof periodLabel === "function" ? periodLabel(rows) : periodLabel}
      periodDescription={typeof periodDescription === "function" ? periodDescription(rows) : periodDescription} />;
  }
  type Column<K extends Key> = Omit<TableColumn<Row<K>>, "field" | "key" | "secondaryField">
    & ({ field: Field<Row<K>>; key?: Field<Row<K>> } | { field?: Field<Row<K>>; key: Field<Row<K>> }) & { secondaryField?: Field<Row<K>> };
  type TableOptions<K extends Key> = Omit<DataTableProps<Row<K>>, "rows" | "columns" | "rowKey" | "compactColumns"> & {
    rowKey?: Field<Row<K>>; compactColumns?: readonly Field<Row<K>>[];
  };
  function Table<K extends Key>({ query, evidenceQueries, columns, table, ...props }: Omit<DataComponentProps, BoundProps | "children" | "kind"> & EvidenceQueries & {
    query: K; columns?: readonly Column<K>[]; table?: TableOptions<K>;
  }) {
    const { rows, ...evidence } = useEvidence(query, evidenceQueries);
    return <DataComponent {...componentProps(props)} {...evidence} kind="table"><DataTable {...table} rows={rows}
      columns={columns ?? Object.keys(schema[query].columns).map(field => ({ field }))} /></DataComponent>;
  }
  function Block<K extends Key>({ query, evidenceQueries, children, ...props }: Omit<DataComponentProps, BoundProps | "children"> & EvidenceQueries & {
    query: K; children: (rows: readonly Row<K>[]) => React.ReactNode;
  }) {
    const { rows, ...evidence } = useEvidence(query, evidenceQueries);
    return <DataComponent kind="custom" {...componentProps(props)} {...evidence}>{children(rows)}</DataComponent>;
  }
  return { Provider, Section, Filters: ViewFilters, Chart, Metric, Table, Block, useQuery };
}
