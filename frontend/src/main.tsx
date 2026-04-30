import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Shield, Upload, Users } from "lucide-react";
import "./styles.css";

type Page = "dashboard" | "upload" | "admin";
type PipelineItem = { status: string; count: number; percentage: number };

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const colors = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#64748b"];

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
  const [data, setData] = useState<PipelineItem[]>([]);
  const [drillDown, setDrillDown] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/analytics/pipeline-summary`)
      .then((res) => res.json())
      .then(setData)
      .catch(() => setData([]));
  }, []);

  const total = data.reduce((sum, item) => sum + item.count, 0);
  const trendData = [
    { month: "Jan", Training: 12, Bench: 18, Joined: 44 },
    { month: "Feb", Training: 18, Bench: 21, Joined: 51 },
    { month: "Mar", Training: 15, Bench: 19, Joined: 62 },
    { month: "Apr", Training: data[0]?.count || 0, Bench: data[1]?.count || 0, Joined: data[3]?.count || 0 }
  ];

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p>Current pipeline, category mix, and monthly movement.</p>
        </div>
      </header>

      <div className="filters">
        <input type="date" />
        <select><option>All Categories</option><option>Fresher</option><option>Experienced</option></select>
        <select><option>All Statuses</option>{data.map((item) => <option key={item.status}>{item.status}</option>)}</select>
        <button>Apply</button>
      </div>

      <div className="kpis">
        <Card title="Total Engineers" value={total} note="Live database count" />
        {data.map((item) => <Card key={item.status} title={item.status} value={item.count} note={`${item.percentage}% of total`} />)}
      </div>

      <div className="grid two">
        <Panel title="Status Distribution">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={data} dataKey="count" nameKey="status" outerRadius={95} label={(entry) => `${entry.status}: ${entry.count} (${entry.percentage}%)`} onClick={(entry) => setDrillDown(entry.status)}>
                {data.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Status Bar Chart">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data} onClick={(state) => setDrillDown(state?.activeLabel || null)}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="status" />
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
            <Line type="monotone" dataKey="Bench" stroke="#16a34a" />
            <Line type="monotone" dataKey="Joined" stroke="#dc2626" />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      {drillDown && <div className="drawer"><button onClick={() => setDrillDown(null)}>Close</button><h3>{drillDown} Engineers</h3><EngineerTable status={drillDown} /></div>}
    </section>
  );
}

function UploadPage() {
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = new FormData(form);
    setMessage("Uploading...");
    const res = await fetch(`${API_URL}/api/v1/uploads/engineers`, { method: "POST", body: file });
    const json = await res.json();
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
        {message && <pre>{message}</pre>}
      </Panel>
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

function EngineerTable({ status }: { status: string }) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    fetch(`${API_URL}/api/v1/engineers?status=${encodeURIComponent(status)}`).then((res) => res.json()).then(setRows).catch(() => setRows([]));
  }, [status]);
  return <table><thead><tr><th>ITE</th><th>Name</th><th>Category</th><th>Status</th></tr></thead><tbody>{rows.map((row) => <tr key={row.engineer_id}><td>{row.ite_number}</td><td>{row.full_name}</td><td>{row.category}</td><td>{row.current_status}</td></tr>)}</tbody></table>;
}

function Card({ title, value, note }: { title: string; value: number; note: string }) {
  return <div className="card"><span>{title}</span><strong>{value}</strong><small>{note}</small></div>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="panel"><h3>{title}</h3>{children}</section>;
}

createRoot(document.getElementById("root")!).render(<App />);

