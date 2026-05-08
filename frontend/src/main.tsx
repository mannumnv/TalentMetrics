import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Shield, Upload, Users } from "lucide-react";
import "./styles.css";

type Page = "dashboard" | "upload" | "admin";
type PipelineItem = { status: string; key: string; count: number; percentage: number };
type EngineerItem = { engineer_id: number; category: string };
type UploadResult = { validation_run_id: number; total_records: number; inserted_records: number; updated_records: number; unchanged_records: number; error_records: number };
type AuthUser = { user_id: number; email: string; role: string; dob: string; location: string };
type AdminUser = AuthUser & { created_at: string };
type AuthResponse = { token: string; user: AuthUser };

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const colors = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#64748b"];
const queryClient = new QueryClient();

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

async function fetchJson<T>(url: string, token?: string): Promise<T> {
  const response = await fetch(url, token ? { headers: authHeaders(token) } : undefined);
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const body = await response.json();
      message = body?.detail?.details || body?.detail?.message || body?.detail || message;
    } catch {
      // Keep the status fallback when the backend does not return JSON.
    }
    throw new Error(String(message));
  }
  return response.json();
}

function currentMonthValue() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function minimumDobValue() {
  const now = new Date();
  return `${now.getFullYear() - 20}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [token, setToken] = useState(() => localStorage.getItem("talentmetrics_token") || "");
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = localStorage.getItem("talentmetrics_user");
    return stored ? JSON.parse(stored) : null;
  });

  function handleAuth(auth: AuthResponse) {
    localStorage.setItem("talentmetrics_token", auth.token);
    localStorage.setItem("talentmetrics_user", JSON.stringify(auth.user));
    setToken(auth.token);
    setUser(auth.user);
  }

  function logout() {
    localStorage.removeItem("talentmetrics_token");
    localStorage.removeItem("talentmetrics_user");
    setToken("");
    setUser(null);
    setPage("dashboard");
    queryClient.clear();
  }

  if (!token || !user) return <AuthPage onAuth={handleAuth} />;

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>HR Analytics</h1>
        <p>{user.email}</p>
        <button className={page === "dashboard" ? "active" : ""} onClick={() => setPage("dashboard")}><Users size={18} />Dashboard</button>
        <button className={page === "upload" ? "active" : ""} onClick={() => setPage("upload")}><Upload size={18} />Upload</button>
        <button className={page === "admin" ? "active" : ""} onClick={() => setPage("admin")}><Shield size={18} />Admin</button>
        <button onClick={logout}>Logout</button>
      </aside>
      <main className="main">
        {page === "dashboard" && <Dashboard token={token} />}
        {page === "upload" && <UploadPage token={token} />}
        {page === "admin" && <AdminPage token={token} currentUser={user} />}
      </main>
    </div>
  );
}

function AuthPage({ onAuth }: { onAuth: (auth: AuthResponse) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    if (mode === "signup" && String(payload.dob || "") > minimumDobValue()) {
      setMessage("DOB must be at least 20 years ago");
      return;
    }
    setMessage("Please wait...");
    const response = await fetch(`${API_URL}/api/v1/auth/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const json = await response.json();
    if (!response.ok) {
      setMessage(json?.detail || "Authentication failed");
      return;
    }
    onAuth(json);
  }

  return (
    <main className="auth-page">
      <Panel title={mode === "login" ? "Login" : "Signup"}>
        <form onSubmit={submit} className="auth-form">
          <input name="email" type={mode === "login" ? "text" : "email"} placeholder={mode === "login" ? "Email ID / Admin ID" : "Email ID"} required />
          <input name="password" type="password" placeholder="Password" required minLength={6} />
          {mode === "signup" && (
            <>
              <input name="dob" type="date" required max={minimumDobValue()} />
              <input name="location" placeholder="Location" required />
              <select name="role" defaultValue="user">
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
            </>
          )}
          <button>{mode === "login" ? "Login" : "Signup"}</button>
        </form>
        <button onClick={() => { setMode(mode === "login" ? "signup" : "login"); setMessage(""); }}>
          {mode === "login" ? "Create account" : "Back to login"}
        </button>
        {message && <p>{message}</p>}
      </Panel>
    </main>
  );
}

function Dashboard({ token }: { token: string }) {
  const [drillDown, setDrillDown] = useState<string | null>(null);
  const [month, setMonth] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [appliedMonth, setAppliedMonth] = useState("");
  const [appliedCategory, setAppliedCategory] = useState("all");
  const [appliedStatus, setAppliedStatus] = useState("all");
  const [filterError, setFilterError] = useState("");

  const queryParams = new URLSearchParams();
  if (appliedMonth) queryParams.set("as_of_month", appliedMonth);
  if (appliedCategory !== "all") queryParams.set("category", appliedCategory);
  const queryString = queryParams.toString();
  const analyticsUrl = `${API_URL}/api/v1/analytics/pipeline-summary${queryString ? `?${queryString}` : ""}`;
  const engineerParams = new URLSearchParams();
  if (appliedMonth) engineerParams.set("as_of_month", appliedMonth);
  if (appliedCategory !== "all") engineerParams.set("category", appliedCategory);
  if (appliedStatus !== "all") engineerParams.set("status", appliedStatus);
  const engineerQueryString = engineerParams.toString();
  const engineersUrl = `${API_URL}/api/v1/engineers${engineerQueryString ? `?${engineerQueryString}` : ""}`;

  const { data = [], isLoading, error, refetch } = useQuery({
    queryKey: ["pipeline-summary", appliedMonth, appliedCategory],
    queryFn: () => fetchJson<PipelineItem[]>(analyticsUrl, token),
    refetchOnWindowFocus: true
  });
  const { data: filteredEngineers = [], refetch: refetchEngineers } = useQuery({
    queryKey: ["engineers-summary", appliedMonth, appliedCategory, appliedStatus],
    queryFn: () => fetchJson<EngineerItem[]>(engineersUrl, token),
    refetchOnWindowFocus: true
  });

  const visibleData = appliedStatus === "all" ? data : data.filter((item) => item.status === appliedStatus);
  const total = filteredEngineers.length;
  const countByKey = Object.fromEntries(visibleData.map((item) => [item.key, item.count]));
  const categoryCounts = filteredEngineers.reduce<Record<string, number>>((counts, engineer) => {
    counts[engineer.category] = (counts[engineer.category] || 0) + 1;
    return counts;
  }, {});
  const categoryData = ["Fresher", "Experienced"]
    .map((label) => ({ label, count: categoryCounts[label] || 0 }))
    .filter((item) => appliedCategory === "all" || item.label === appliedCategory);
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
        <button onClick={() => {
          if (month && month > currentMonthValue()) {
            setFilterError("正しい月を入力してください。");
            return;
          }
          setFilterError("");
          setAppliedMonth(month);
          setAppliedCategory(category);
          setAppliedStatus(status);
          setDrillDown(null);
          if (month === appliedMonth && category === appliedCategory && status === appliedStatus) {
            refetch();
            refetchEngineers();
          }
        }}>Apply</button>
      </div>

      {isLoading && <Panel title="Loading"><p>Loading analytics...</p></Panel>}
      {(filterError || error) && <Panel title="Error"><p>{filterError || (error instanceof Error ? error.message : "Unable to load analytics from backend.")}</p></Panel>}

      <div className="kpis">
        <Card title="Total Engineers" value={total} note="Live database count" />
        {categoryData.map((item) => <Card key={item.label} title={item.label} value={item.count} note="Category total" />)}
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

      {drillDown && <div className="drawer"><button onClick={() => setDrillDown(null)}>Close</button><h3>{drillDown} Engineers</h3><EngineerTable status={drillDown} category={appliedCategory} month={appliedMonth} token={token} /></div>}
    </section>
  );
}

function UploadPage({ token }: { token: string }) {
  const [message, setMessage] = useState("");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadedRows, setUploadedRows] = useState<any[]>([]);
  const queryClient = useQueryClient();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = new FormData(form);
    setMessage("Uploading...");
    const res = await fetch(`${API_URL}/api/v1/uploads/engineers`, { method: "POST", body: file, headers: authHeaders(token) });
    const json = await res.json();
    if (!res.ok) {
      setUploadResult(null);
      setMessage(JSON.stringify(json, null, 2));
      return;
    }
    setUploadResult(json);
    await queryClient.invalidateQueries({ queryKey: ["pipeline-summary"] });
    const rows = await fetchJson<any[]>(`${API_URL}/api/v1/engineers`, token);
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

function AdminPage({ token, currentUser }: { token: string; currentUser: AuthUser }) {
  const [logs, setLogs] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [dobEdits, setDobEdits] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("");

  function loadAdminData() {
    fetchJson<any[]>(`${API_URL}/api/v1/admin/audit-logs`, token).then(setLogs).catch(() => setLogs([]));
    fetchJson<any[]>(`${API_URL}/api/v1/admin/user-activity`, token).then(setActivity).catch(() => setActivity([]));
    fetchJson<AdminUser[]>(`${API_URL}/api/v1/admin/users`, token).then((items) => {
      setUsers(items);
      setDobEdits(Object.fromEntries(items.map((item) => [item.user_id, item.dob])));
    }).catch(() => setUsers([]));
  }

  useEffect(() => {
    loadAdminData();
  }, [token]);

  async function removeUser(user: AdminUser) {
    if (!window.confirm(`Remove user ${user.email}?`)) return;
    setMessage("Removing user...");
    const response = await fetch(`${API_URL}/api/v1/admin/users/${user.user_id}`, {
      method: "DELETE",
      headers: authHeaders(token)
    });
    const json = await response.json();
    if (!response.ok) {
      setMessage(json?.detail || "Unable to remove user");
      return;
    }
    setMessage(`Removed ${json.removed_user}`);
    loadAdminData();
  }

  async function updateDob(user: AdminUser, dob: string) {
    if (!dob || dob === user.dob) return;
    setMessage("Updating DOB...");
    const response = await fetch(`${API_URL}/api/v1/admin/users/${user.user_id}/dob`, {
      method: "PATCH",
      headers: { ...authHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({ dob })
    });
    const json = await response.json();
    if (!response.ok) {
      setMessage(json?.detail || "Unable to update DOB");
      return;
    }
    setMessage(`Updated DOB for ${json.email}`);
    loadAdminData();
  }

  return (
    <section className="page">
      <h2>Admin</h2>
      <Panel title="Users">
        {message && <p>{message}</p>}
        <table>
          <thead><tr><th>Email</th><th>Role</th><th>DOB</th><th>Location</th><th>Created</th><th>Action</th></tr></thead>
          <tbody>{users.map((user) => <tr key={user.user_id}><td>{user.email}</td><td>{user.role}</td><td>{currentUser.role === "admin" ? <div className="inline-edit"><input type="date" value={dobEdits[user.user_id] || user.dob} onChange={(event) => setDobEdits((items) => ({ ...items, [user.user_id]: event.target.value }))} /><button onClick={() => updateDob(user, dobEdits[user.user_id] || user.dob)} disabled={(dobEdits[user.user_id] || user.dob) === user.dob}>Update</button></div> : user.dob}</td><td>{user.location}</td><td>{new Date(user.created_at).toLocaleString()}</td><td>{currentUser.role === "admin" && user.user_id !== currentUser.user_id ? <button onClick={() => removeUser(user)}>Remove</button> : "-"}</td></tr>)}</tbody>
        </table>
      </Panel>
      <Panel title="User Activity">
        <table>
          <thead><tr><th>User Email</th><th>Role</th><th>Login Time</th><th>Action Performed</th><th>Timestamp</th></tr></thead>
          <tbody>{activity.map((log) => <tr key={log.activity_log_id}><td>{log.user_email || "-"}</td><td>{log.role || "-"}</td><td>{log.login_time ? new Date(log.login_time).toLocaleString() : "-"}</td><td>{log.action_performed}</td><td>{new Date(log.timestamp).toLocaleString()}</td></tr>)}</tbody>
        </table>
      </Panel>
      <Panel title="Audit Logs">
        <table>
          <thead><tr><th>Date</th><th>Table</th><th>Action</th><th>Changed By</th></tr></thead>
          <tbody>{logs.map((log) => <tr key={log.audit_log_id}><td>{new Date(log.changed_at).toLocaleString()}</td><td>{log.table_name}</td><td>{log.action}</td><td>{log.changed_by}</td></tr>)}</tbody>
        </table>
      </Panel>
    </section>
  );
}

function EngineerTable({ status, category, month, token }: { status: string; category: string; month: string; token: string }) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    const params = new URLSearchParams({ status });
    if (category !== "all") params.set("category", category);
    if (month) params.set("as_of_month", month);
    fetchJson<any[]>(`${API_URL}/api/v1/engineers?${params.toString()}`, token).then(setRows).catch(() => setRows([]));
  }, [status, category, month, token]);
  return <table><thead><tr><th>ITE</th><th>Name</th><th>Category</th><th>Status</th></tr></thead><tbody>{rows.map((row) => <tr key={row.engineer_id}><td>{row.ite_number}</td><td>{row.full_name}</td><td>{row.category}</td><td>{row.current_status}</td></tr>)}</tbody></table>;
}

function Card({ title, value, note }: { title: string; value: number; note: string }) {
  return <div className="card"><span>{title}</span><strong>{value}</strong><small>{note}</small></div>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="panel"><h3>{title}</h3>{children}</section>;
}

createRoot(document.getElementById("root")!).render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>);
