import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Shield, Upload, Users } from "lucide-react";
import "./styles.css";

type Page = "dashboard" | "upload" | "admin";
type PipelineItem = { status: string; key: string; count: number; percentage: number };
type UploadResult = { validation_run_id: number; total_records: number; inserted_records: number; updated_records: number; unchanged_records: number; error_records: number };

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const colors = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#64748b"];
const queryClient = new QueryClient();

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  return (
    <div className="app">
      <aside className="sidebar">
        <h1>HR Analytics</h1>
        <button className={page === "dashboard" ? "active" : ""} onClick={() => setPage("dashboard")}><Users size={18} />Dashboard</button>
        <button className={page === "upload" ? "active" : ""} onClick={() => setPage("upload")}><Upload size={18} />Upload</button>
        <button className={page === "admin" ? "active" : ""} onClick={() => setPage("admin")}><Shield size={18} />Admin</button>
      </aside>
      <main className="main">
        {page === "dashboard" && <Dashboard />}
        {page === "upload" && <UploadPage />}
        {page === "admin" && <AdminPage />}
      </main>
    </div>
  );
}

function Dashboard() {
  const [drillDown, setDrillDown] = useState<string | null>(null);
  const [month, setMonth] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");

  const queryParams = new URLSearchParams();
  if (month) queryParams.set("as_of_month", month);
  if (category !== "all") queryParams.set("category", category);
  const queryString = queryParams.toString();
  const analyticsUrl = `${API_URL}/api/v1/analytics/pipeline-summary${queryString ? `?${queryString}` : ""}`;

  const { data = [], isLoading, error, refetch } = useQuery({
    queryKey: ["pipeline-summary", month, category],
    queryFn: () => fetchJson<PipelineItem[]>(analyticsUrl),
    refetchOnWindowFocus: true
  });

  const visibleData = status === "all" ? data : data.filter((item) => item.status === status);
  const total = visibleData.reduce((sum, item) => sum + item.count, 0);
  const countByKey = Object.fromEntries(visibleData.map((item) => [item.key, item.count]));
  const trendData = [{
    month: "Current",
    Training: countByKey.training || 0,
    ProjectJoined: countByKey.project_joined || 0
  }];

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p>Current pipeline, category mix, and monthly movement.</p>
        </div>
      </header>

      <div className="filters">
        <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="all">All Categories</option>
          <option value="Fresher">Fresher</option>
          <option value="Experienced">Experienced</option>
        </select>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="all">All Statuses</option>
          {data.map((item) => <option key={item.key} value={item.status}>{item.status}</option>)}
        </select>
        <button onClick={() => refetch()}>Apply</button>
      </div>

      {isLoading && <Panel title="Loading"><p>Loading analytics...</p></Panel>}
      {error && <Panel title="Error"><p>Unable to load analytics from backend.</p></Panel>}

      <div className="kpis">
        <Card title="Total Engineers" value={total} note="Live database count" />
        {visibleData.map((item) => <Card key={item.key} title={item.status} value={item.count} note={`${item.percentage}% of total`} />)}
      </div>

      <div className="grid two">
        <Panel title="Status Distribution">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={visibleData} dataKey="count" nameKey="status" outerRadius={90} labelLine={false} label={(entry) => `${entry.count} (${entry.percentage}%)`} onClick={(entry) => setDrillDown(entry.status)}>
                {visibleData.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Status Bar Chart">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={visibleData} onClick={(state) => setDrillDown(state?.activeLabel || null)}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="status" tick={{ fontSize: 12 }} interval={0} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <Panel title="Monthly Trend">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trendData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="Training" stroke="#2563eb" />
            <Line type="monotone" dataKey="ProjectJoined" stroke="#16a34a" />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      {drillDown && <div className="drawer"><button onClick={() => setDrillDown(null)}>Close</button><h3>{drillDown} Engineers</h3><EngineerTable status={drillDown} category={category} month={month} /></div>}
    </section>
  );
}

function UploadPage() {
  const [message, setMessage] = useState("");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadedRows, setUploadedRows] = useState<any[]>([]);
  const queryClient = useQueryClient();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = new FormData(form);
    setMessage("Uploading...");
    const res = await fetch(`${API_URL}/api/v1/uploads/engineers`, { method: "POST", body: file });
    const json = await res.json();
    if (!res.ok) {
      setUploadResult(null);
      setMessage(JSON.stringify(json, null, 2));
      return;
    }
    setUploadResult(json);
    await queryClient.invalidateQueries({ queryKey: ["pipeline-summary"] });
    const rows = await fetchJson<any[]>(`${API_URL}/api/v1/engineers`);
    setUploadedRows(rows);
    setMessage(JSON.stringify(json, null, 2));
  }

  return (
    <section className="page">
      <h2>Upload</h2>
      <Panel title="Upload Engineer Excel or CSV">
        <form onSubmit={submit} className="upload-form">
          <input name="file" type="file" accept=".xlsx,.xls,.csv" required />
          <button>Validate and Import</button>
        </form>
        {uploadResult && (
          <div className="kpis">
            <Card title="Total Records" value={uploadResult.total_records} note="Rows read from uploaded file" />
            <Card title="Inserted" value={uploadResult.inserted_records} note="New engineers added" />
            <Card title="Updated" value={uploadResult.updated_records} note="Existing engineers changed" />
            <Card title="Unchanged" value={uploadResult.unchanged_records} note="Already up to date" />
            <Card title="Errors" value={uploadResult.error_records} note="Rows skipped with validation errors" />
          </div>
        )}
        {message && <pre>{message}</pre>}
      </Panel>
      {uploadedRows.length > 0 && (
        <Panel title="Uploaded Data">
          <table>
            <thead><tr><th>ITE</th><th>Name</th><th>Category</th><th>Status</th><th>Join Date</th></tr></thead>
            <tbody>{uploadedRows.map((row) => <tr key={row.engineer_id}><td>{row.ite_number}</td><td>{row.full_name}</td><td>{row.category}</td><td>{row.current_status}</td><td>{row.date_of_joining || "-"}</td></tr>)}</tbody>
          </table>
        </Panel>
      )}
    </section>
  );
}

function AdminPage() {
  const [logs, setLogs] = useState<any[]>([]);
  useEffect(() => {
    fetch(`${API_URL}/api/v1/admin/audit-logs`).then((res) => res.json()).then(setLogs).catch(() => setLogs([]));
  }, []);
  return (
    <section className="page">
      <h2>Admin</h2>
      <Panel title="Audit Logs">
        <table>
          <thead><tr><th>Date</th><th>Table</th><th>Action</th><th>Changed By</th></tr></thead>
          <tbody>{logs.map((log) => <tr key={log.audit_log_id}><td>{new Date(log.changed_at).toLocaleString()}</td><td>{log.table_name}</td><td>{log.action}</td><td>{log.changed_by}</td></tr>)}</tbody>
        </table>
      </Panel>
    </section>
  );
}

function EngineerTable({ status, category, month }: { status: string; category: string; month: string }) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    const params = new URLSearchParams({ status });
    if (category !== "all") params.set("category", category);
    if (month) params.set("as_of_month", month);
    fetch(`${API_URL}/api/v1/engineers?${params.toString()}`).then((res) => res.json()).then(setRows).catch(() => setRows([]));
  }, [status, category, month]);
  return <table><thead><tr><th>ITE</th><th>Name</th><th>Category</th><th>Status</th></tr></thead><tbody>{rows.map((row) => <tr key={row.engineer_id}><td>{row.ite_number}</td><td>{row.full_name}</td><td>{row.category}</td><td>{row.current_status}</td></tr>)}</tbody></table>;
}

function Card({ title, value, note }: { title: string; value: number; note: string }) {
  return <div className="card"><span>{title}</span><strong>{value}</strong><small>{note}</small></div>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="panel"><h3>{title}</h3>{children}</section>;
}

createRoot(document.getElementById("root")!).render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>);

