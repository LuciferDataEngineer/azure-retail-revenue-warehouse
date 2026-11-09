import React from "react";
import {
  DataComponent, MetricCard, Section, SortableItem, SortableRegion,
  useDashboardTabs, useDataApp,
} from "../../data-app-public.jsx";
import { ProjectView } from "./ProjectViews.jsx";

const tabs = [
  { id: "overview", label: "Portfolio", filterIds: [] },
  { id: "retail", label: "Retail", filterIds: [] },
  { id: "mobility", label: "Mobility", filterIds: [] },
];

const actionLabels = { retail: "Explore retail", mobility: "Explore mobility" };

function DeliveryMetrics({ projects }) {
  const published = projects.filter(project => project.status === "published_local");
  const completedDeployments = projects.filter(project => project.cloud_status === "deployed");
  const metrics = [
    { id: "published-projects", title: "Published projects", value: `${published.length} / ${projects.length}`, rows: projects },
    { id: "local-test-count", title: "Local tests passed", value: published.reduce((total, project) => total + project.tests_passed, 0), rows: published },
    { id: "azure-deployments", title: "Azure deployments", value: completedDeployments.length, rows: projects },
  ];

  return <SortableRegion id="portfolio:delivery-metrics" variant="canvas"
    label="Portfolio delivery metrics" columns={12} spacing="standard"
    rows={[{ id: "portfolio:delivery-row", kind: "metrics", items: metrics.map(metric => metric.id) }]}>
    {metrics.map(({ id, title, value, rows }) =>
      <SortableItem key={id} id={id} label={title} kind="metric" span={4}>
        <MetricCard id={id} queryId="portfolio" title={title} value={value}
          displayRows={[{ measure: title, value }]} sourceRows={rows} />
      </SortableItem>
    )}
  </SortableRegion>;
}

function ProjectCard({ project }) {
  const { snapshot, exploreDashboard, reviewedRows } = useDataApp();
  const hasExplorer = Object.hasOwn(actionLabels, project.id);
  const queryId = project.id + "_totals";
  const totals = hasExplorer ? reviewedRows(queryId) : [];
  const coverage = hasExplorer ? snapshot.projectMetadata[project.id].period.label : project.coverage;
  const observed = hasExplorer ? [{
    label: "Dataset", value: totals[0]?.accepted_rows,
    unit: project.id === "retail" ? "accepted invoice lines" : "accepted taxi records",
  }] : project.metrics;
  const displayRows = observed.map(metric => ({
    project: project.title, coverage, ...metric,
    localTestsPassed: project.tests_passed, azureStatus: project.cloud_status,
  }));
  const evidence = hasExplorer ? {
    queryIds: ["portfolio", queryId],
    sourceRowsByQuery: {portfolio: [project], [queryId]: totals},
  } : {sourceRows: [project]};

  return <DataComponent id={project.id + "-project-card"} title={project.title}
    queryId="portfolio" kind="custom" variant="card" padding="spacious"
    displayRows={displayRows} {...evidence}>
    <div className="portfolio-project-body" data-reviewed-rows>
      <p className="portfolio-summary-line">{project.summary}</p>
      <dl className="portfolio-facts">
        <div><dt>Source coverage</dt><dd>{coverage}</dd></div>
        {observed.map(metric => <div key={metric.label}>
          <dt>{metric.label}</dt>
          <dd>{new Intl.NumberFormat("en-GB", {maximumSignificantDigits: 15}).format(metric.value)} {metric.unit}</dd>
        </div>)}
        <div><dt>Validation</dt><dd>{project.tests_passed} local tests passed</dd></div>
      </dl>
      <div className="portfolio-stack" aria-label="Implemented stack">
        {project.stack.map(tool => <span key={tool}>{tool}</span>)}
      </div>
      <div className="portfolio-links">
        {hasExplorer && <button type="button" className="portfolio-explore" onClick={() => exploreDashboard(project.id, {})}>
          {actionLabels[project.id]} <span aria-hidden="true">→</span>
        </button>}
        <a href={project.repo_url} aria-label={project.title + " GitHub repository"}>GitHub</a>
        <a href={project.evidence_url} aria-label={project.title + " validation evidence"}>Test results</a>
      </div>
    </div>
  </DataComponent>;
}

function Overview() {
  const { reviewedRows, queries } = useDataApp();
  const projects = reviewedRows("portfolio", ["id"]);
  const published = projects.filter(project => project.status === "published_local");
  const remaining = projects.filter(project => project.status === "in_progress" || project.status === "queued");
  return <article className="portfolio-page">
    <DeliveryMetrics projects={projects} />
    <Section id="portfolio-published" title="Published implementations" spacing="after-metrics">
      <div className="portfolio-project-grid">
        {published.map(project => <ProjectCard key={project.id} project={project} />)}
      </div>
      <p className="portfolio-scope">The charts use historical public data from the locally tested pipelines. Azure deployment, security and recovery checks are pending.</p>
    </Section>
    {remaining.length > 0 && <Section id="portfolio-planned" title="Project roadmap">
      <DataComponent id="portfolio-roadmap-list" title="Projects in development or queued" queryId="portfolio" kind="custom"
        variant="card" showHeading={false} sourceRows={remaining} displayRows={remaining}>
        <ul className="portfolio-roadmap" data-reviewed-rows>
          {remaining.map(project => <li key={project.id}>
            <div><h3>{project.title}</h3><p>{project.pattern}</p></div>
            <span className="portfolio-roadmap-status">{project.status === "in_progress" ? "In progress" : "Queued"}</span>
          </li>)}
        </ul>
      </DataComponent>
    </Section>}
    <footer className="portfolio-foot">
      <a href="https://github.com/LuciferDataEngineer">LuciferDataEngineer on GitHub</a>
      <span>Portfolio record · {queries.portfolio.source.period}</span>
    </footer>
  </article>;
}

export function DashboardContent() {
  const { activeTabId } = useDashboardTabs(tabs);
  if (activeTabId === "retail" || activeTabId === "mobility") {
    return <ProjectView key={activeTabId} domain={activeTabId} />;
  }
  return <Overview />;
}
