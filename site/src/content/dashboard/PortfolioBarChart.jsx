import React from "react";
import {
  Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { DataComponent } from "../../data-app-public.jsx";
import "./portfolio-chart.css";

const includeZero = [(minimum) => Math.min(minimum, 0), (maximum) => Math.max(maximum, 0)];
const axisStyle = { fill: "var(--secondary)", fontSize: 11 };

export function PortfolioBarChart({ id, title, queryId, rows, sourceRows, scopeFilters, spec, height, children }) {
  const horizontal = spec.type === "horizontalBar";
  const measures = spec.fields ?? [spec.y];
  const formatting = spec.currency ? { style: "currency", currency: spec.currency } : {};
  const compact = new Intl.NumberFormat("en-GB", { ...formatting, notation: "compact", maximumFractionDigits: 1 });
  const exact = new Intl.NumberFormat("en-GB", {
    ...formatting, minimumFractionDigits: spec.valueDecimals, maximumFractionDigits: spec.valueDecimals,
  });
  const category = { type: "category", dataKey: spec.x, tick: axisStyle, tickLine: false, axisLine: false };
  const value = {
    type: "number", domain: includeZero, tickFormatter: n => compact.format(n),
    tick: axisStyle, tickLine: false, axisLine: false, tickCount: 5,
  };
  const color = key => spec.colors?.[key] ?? "var(--chart-1)";
  return <DataComponent id={id} queryId={queryId} kind="custom" variant="card" title={title}
    sourceRows={sourceRows} displayRows={rows} scopeFilters={scopeFilters}>
    <div className="portfolio-bar-plot" data-reviewed-rows>
      {measures.length > 1 && <ul className="portfolio-bar-key" aria-label="Series">
        {measures.map(key => <li key={key}><i aria-hidden="true" style={{background:color(key)}} />{key}</li>)}
      </ul>}
      <ResponsiveContainer width="100%" height={height} minWidth={0}>
        <BarChart data={rows} layout={horizontal ? "vertical" : "horizontal"} accessibilityLayer
          title={title} margin={{ top: 10, right: 14, bottom: 8, left: 2 }} barGap={1} maxBarSize={45}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 4" horizontal={!horizontal} vertical={horizontal} />
          {horizontal
            ? <><XAxis {...value}/><YAxis {...category} width={102} interval={0}/></>
            : <><XAxis {...category} minTickGap={12} height={32}/><YAxis {...value} width={60}/></>}
          {horizontal
            ? <ReferenceLine x={0} stroke="var(--secondary)"/>
            : <ReferenceLine y={0} stroke="var(--secondary)"/>}
          <Tooltip formatter={(n, label) => [exact.format(n), label]}
            cursor={{ fill: "var(--muted)", fillOpacity: 0.7 }} isAnimationActive={false}
            contentStyle={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:8,color:"var(--text)",fontSize:12}}
            itemStyle={{color:"var(--text)"}}/>
          {measures.map(key => <Bar key={key} dataKey={key} fill={color(key)} isAnimationActive={false}/>)}
        </BarChart>
      </ResponsiveContainer>
      {children}
      <details className="portfolio-chart-values"><summary>Exact chart values</summary>
        <div><table><caption>{title}</caption>
          <thead><tr><th scope="col">{spec.x === "month" ? "Source month" : spec.x === "country" ? "Country" : "Pickup hour"}</th>
            {measures.map(key => <th scope="col" key={key}>{key}</th>)}</tr></thead>
          <tbody>{rows.map(row => <tr key={row[spec.x]}><th scope="row">{row[spec.x]}</th>
            {measures.map(key => <td key={key}>{exact.format(row[key])}</td>)}</tr>)}</tbody>
        </table></div>
      </details>
    </div>
  </DataComponent>;
}
