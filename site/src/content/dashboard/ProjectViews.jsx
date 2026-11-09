import React from "react";
import {
  DataComponent, DataTable, Filters, MetricCard, Section,
  useDataApp, useSectionFilters,
} from "../../data-app-public.jsx";
import { PortfolioBarChart } from "./PortfolioBarChart.jsx";
import { count, money, sum, sumMoney } from "./portfolio-metrics.js";

function ReviewedTable({ id, title, queryId, rows, columns, description, searchable = true }) {
  return (
    <DataComponent id={id} kind="table" title={title} queryId={queryId}
      displayRows={rows} sourceRows={rows} description={description}>
      <DataTable rows={rows} columns={columns} label={title} searchable={searchable}
        compactNumbers={false} />
    </DataComponent>
  );
}

const currencyCell = currency => value => money(Number(value), currency);
const periodText = month => new Intl.DateTimeFormat("en-GB", {
  month: "short", year: "numeric", timeZone: "UTC",
}).format(new Date(month + "-01T00:00:00Z"));

function MonthlySection({ domain }) {
  const retail = domain === "retail";
  const queryId = domain + "_monthly";
  const scope = useSectionFilters([
    { id: "month", field: "month", label: "Source month", queryIds: [queryId], defaultValue: "all" },
  ], {}, { id: domain + "-month-selection" });
  const binding = scope.componentProps(queryId, ["month"]);
  const rows = binding.sourceRows;
  const currency = retail ? "GBP" : "USD";
  const netKey = retail ? "net_revenue_gbp" : "signed_charges_usd";
  const adjustmentKey = retail ? "negative_adjustments_gbp" : "adjustment_charges_usd";
  const label = scope.values.month === "all" ? "All source months" : periodText(scope.values.month);
  const metrics = [
    { key: "accepted", title: retail ? "Accepted invoice lines" : "Accepted trip records",
      value: count(sum(rows, "accepted_rows")) },
    { key: "signed", title: retail ? "Net signed sales" : "Signed total charges",
      value: money(sumMoney(rows, netKey), currency) },
    { key: "adjustments", title: retail ? "Negative line amounts" : "Adjustment-record charges",
      value: money(sumMoney(rows, adjustmentKey), currency) },
  ];
  const chartRows = rows.map(row => ({
    month: periodText(row.month),
    [retail ? "Net signed sales" : "Signed total charges"]: Number(row[netKey]),
    [retail ? "Negative line amounts" : "Adjustment-record charges"]: Number(row[adjustmentKey]),
  }));
  const measures = Object.keys(chartRows[0] ?? {}).filter(field => field !== "month");
  return (
    <>
      <Section id={domain + "-monthly-heading"} title="Monthly results" kind="metrics" columns={3}
        spacing="content" filters={<Filters {...scope.filterProps} />}>
        {metrics.map(metric => (
          <MetricCard key={metric.key} id={domain + "-metric-" + metric.key} queryId={queryId}
            title={metric.title} value={rows.length ? metric.value : "—"} periodLabel={label}
            sourceRows={rows} displayRows={rows.length ? [{ measure: metric.title, value: metric.value, period: label }] : []}
            scopeFilters={binding.scopeFilters} />
        ))}
      </Section>
      <Section spacing="content">
        {rows.length > 0 ? (
          <PortfolioBarChart id={domain + "-monthly-amounts"} title={retail ? "Sales and adjustments by month" : "Charges and adjustments by source month"}
            queryId={queryId} rows={chartRows} sourceRows={rows} scopeFilters={binding.scopeFilters}
            spec={{ type: "bar", x: "month", y: measures[0], fields: measures, currency, valueDecimals: 2,
              stackable: false, colors: { [measures[0]]: "var(--chart-1)", [measures[1]]: "var(--chart-4)" } }}
            height={260}>
            <small>{retail
              ? "Net includes negative lines. Each signed quantity × unit price is rounded to pennies before summation."
              : "Total charges include adjustments. An adjustment record has a negative original fare or total."}
              {retail && rows.some(row => row.partial) ? " December 2011 ends on the ninth." : ""}
            </small>
          </PortfolioBarChart>
        ) : <p role="status">The selected period has no observations.</p>}
      </Section>
    </>
  );
}

function RetailBreakdowns() {
  const { reviewedRows } = useDataApp();
  const countries = reviewedRows("retail_countries", ["country"]);
  const products = reviewedRows("retail_top_products", ["stock_code"]);
  const ranked = [...countries].sort((a, b) => Number(b.net_revenue_gbp) - Number(a.net_revenue_gbp)).slice(0, 8);
  return (
    <>
      <Section id="retail-markets-heading" title="Markets over the full retail period" columns={2}>
        <PortfolioBarChart id="retail-market-rank" queryId="retail_countries" title="Eight highest country totals"
          rows={ranked.map(row => ({ country: row.country, "Net signed sales": Number(row.net_revenue_gbp) }))}
          sourceRows={ranked} height={295} spec={{ type: "horizontalBar", x: "country", y: "Net signed sales",
            currency: "GBP", valueDecimals: 2 }}>
          <small>Country is the label recorded on the invoice line. Amounts cover December 2010 through 9 December 2011.</small>
        </PortfolioBarChart>
        <ReviewedTable id="retail-country-table" title="Country details" queryId="retail_countries" rows={countries}
          columns={[{field:"country", label:"Country"}, {field:"accepted_rows", label:"Lines"},
            {field:"net_revenue_gbp", label:"Net GBP", renderCell: currencyCell("GBP")}]}/>
      </Section>
      <Section id="retail-products-heading" title="Products and line quality" columns={2}>
        <ReviewedTable id="retail-products" title="Top 20 stock codes by signed amount" queryId="retail_top_products"
          rows={products} columns={[{field:"stock_code",label:"Stock code"},
            {field:"signed_units",label:"Signed units"},
            {field:"signed_revenue_gbp",label:"Signed amount",renderCell:currencyCell("GBP")}]}
          description="Full-period ranking includes administrative stock codes. Description changes remain traceable in the warehouse."/>
        <QualityTable domain="retail" />
      </Section>
    </>
  );
}

function MobilityBreakdowns() {
  const { reviewedRows } = useDataApp();
  const hours = reviewedRows("mobility_hourly", ["hour"]);
  const zones = reviewedRows("mobility_top_zones", ["zone"]);
  const monthly = reviewedRows("mobility_monthly", ["month"]);
  return (
    <>
      <Section id="mobility-ordinary-heading" title="Ordinary pickup records across January–March 2024" columns={2}>
        <PortfolioBarChart id="mobility-by-hour" title="Pickups by New York local hour" queryId="mobility_hourly"
          rows={hours.map(row => ({ hour: String(row.hour).padStart(2, "0") + ":00", Pickups: row.records }))}
          sourceRows={hours} height={285} spec={{ type:"bar", x:"hour", y:"Pickups", valueDecimals:0 }}>
          <small>Counts include accepted rows with a nonnegative original fare and total. The hour uses the recorded local pickup time.</small>
        </PortfolioBarChart>
        <ReviewedTable id="mobility-zone-rank" title="Ten busiest pickup zones" queryId="mobility_top_zones"
          rows={zones} columns={[{field:"zone",label:"Zone",presentation:"identity",secondaryField:"borough"},
            {field:"records",label:"Pickups"}, {field:"signed_charges_usd",label:"Charges USD",renderCell:currencyCell("USD")}]}
          description="Ranked by ordinary-record count across all three source months. Zone names use the project's published lookup snapshot." />
      </Section>
      <Section id="mobility-qc-heading" title="Ingestion and quarantine across the full period" columns={2}>
        <ReviewedTable id="mobility-conservation" title="Source rows accounted for" queryId="mobility_monthly" rows={monthly}
          searchable={false} columns={[{field:"month",label:"Month",renderCell:periodText},{field:"raw_rows",label:"Source rows"},
            {field:"accepted_rows",label:"Accepted"},{field:"quarantined_rows",label:"Quarantined"}]}/>
        <QualityTable domain="mobility" />
      </Section>
    </>
  );
}

function QualityTable({ domain }) {
  const { reviewedRows } = useDataApp();
  const queryId = domain + "_quality";
  const rows = reviewedRows(queryId, ["label"]);
  const retail = domain === "retail";
  return (
    <DataComponent id={domain + "-quality-table"} kind="table" queryId={queryId}
      title={retail ? "Retained line warnings" : "Quarantine reasons"} displayRows={rows} sourceRows={rows}>
      <DataTable rows={rows} searchable={false} compactNumbers={false} label={retail ? "Line warnings" : "Quarantine reasons"}
        columns={[{field:"label",label:retail ? "Warning" : "Reason"}, {field:"records",label:"Occurrences"}]}/>
      <small>{retail ? "A retained line can have more than one warning." : "A quarantined record can have more than one reason."}</small>
    </DataComponent>
  );
}

export function ProjectView({ domain }) {
  const { snapshot } = useDataApp();
  const project = snapshot.projectMetadata[domain];
  const source = project.sources[0];
  return (
    <article className="portfolio-project-view">
      <Section spacing="metrics" id={domain + "-title"} title={project.title}>
        <div className="project-context">
          <p>{project.period.label} · {source.title} · Historical source data</p>
          <p><a href={project.validation.repo_url}>Repository</a>{" · "}
            <a href={project.validation.evidence_url}>Validation results</a>{" · "}
            <a href={project.validation.azure_url}>Azure deployment plan</a></p>
        </div>
      </Section>
      <MonthlySection key={domain} domain={domain} />
      {domain === "retail" ? <RetailBreakdowns /> : <MobilityBreakdowns />}
      <footer className="project-source-note">
        <p>{source.citation} <a href={source.url}>Dataset</a>{" · "}
          <a href={source.license_url}>{source.license}</a></p>
        <p>Local validation passed {project.validation.tests_passed} tests. Azure deployment and cloud validation are pending.</p>
      </footer>
    </article>
  );
}
