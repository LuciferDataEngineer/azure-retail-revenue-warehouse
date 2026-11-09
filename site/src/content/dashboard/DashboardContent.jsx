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
  const queryId = project.id + "_totals";
  const totals = reviewedRows(queryId);
  const source = snapshot.projectMetadata[project.id];
  const accepted = totals[0]?.accepted_rows;
  const recordLabel = project.id === "retail" ? "accepted invoice lines" : "accepted taxi records";
  const displayed = [{
    project: project.title, sourcePeriod: source.period.label, accepted,
    localTestsPassed: project.tests_passed, azureStatus: project.cloud_status,
  }];

  return <DataComponent id={project.id + "-project-card"} title={project.title}
    queryId="portfolio" queryIds={["portfolio", queryId]} kind="custom" variant="card" padding="spacious"
    displayRows={displayed} sourceRowsByQuery={{ portfolio: [project], [queryId]: totals }}>
    <div className="portfolio-project-body" data-reviewed-rows>
      <p className="portfolio-summary-line">{project.summary}</p>
      <dl className="portfolio-facts">
        <div><dt>Historical coverage</dt><dd>{source.period.label}</dd></div>
        <div><dt>Dataset</dt><dd>{Number.isSafeInteger(accepted) ? new Intl.NumberFormat("en-GB").format(accepted) + " " + recordLabel : "Source count unavailable"}</dd></div>
        <div><dt>Validation</dt><dd>{project.tests_passed} local tests passed</dd></div>
      </dl>
      <div className="portfolio-stack" aria-label="Implemented stack">
        {project.stack.map(tool => <span key={tool}>{tool}</span>)}
      </div>
      <div className="portfolio-links">
        <button type="button" className="portfolio-explore" onClick={() => exploreDashboard(project.id, {})}>
          {actionLabels[project.id]} <span aria-hidden="true">→</span>
        </button>
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
  const queued = projects.filter(project => project.status === "queued");
  return <article className="portfolio-page">
    <DeliveryMetrics projects={projects} />
    <Section id="portfolio-published" title="Published implementations" spacing="after-metrics">
      <div className="portfolio-project-grid">
        {published.map(project => <ProjectCard key={project.id} project={project} />)}
      </div>
      <p className="portfolio-scope">The charts use historical public data from the locally tested pipelines. Azure deployment, security and recovery checks are pending.</p>
    </Section>
    <Section id="portfolio-planned" title="Project roadmap">
      <DataComponent id="portfolio-roadmap-list" title="Queued projects" queryId="portfolio" kind="custom"
        variant="card" showHeading={false} sourceRows={queued} displayRows={queued}>
        <ul className="portfolio-roadmap" data-reviewed-rows>
          {queued.map(project => <li key={project.id}>
            <div><h3>{project.title}</h3><p>{project.pattern}</p></div>
            <span className="portfolio-roadmap-status">Queued</span>
          </li>)}
        </ul>
      </DataComponent>
    </Section>
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
