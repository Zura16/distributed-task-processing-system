import React, { useState, useEffect, useRef } from "react";
import { 
  Activity, Play, Clock, CheckCircle2, XCircle, RotateCcw, 
  Cpu, Terminal, PlusCircle, Server, Ban, RefreshCw
} from "lucide-react";

// API Base URL - adjusts dynamically if running in docker-compose or locally
const API_BASE_URL = window.location.hostname === "localhost" 
  ? "http://localhost:8000" 
  : `http://${window.location.hostname}:8000`;

function App() {
  // System metrics state
  const [metrics, setMetrics] = useState({
    queue_size: 0,
    delayed_size: 0,
    active_workers: 0,
    busy_workers: 0,
    statuses: { PENDING: 0, SCHEDULED: 0, RUNNING: 0, SUCCESS: 0, FAILED: 0, CANCELLED: 0, RETRYING: 0 },
    success_rate: 0
  });

  // Tasks and Workers lists
  const [tasks, setTasks] = useState([]);
  const [workers, setWorkers] = useState({});
  const [availableTasks, setAvailableTasks] = useState(["heavy_computation", "flaky_task", "add", "fetch_data_api"]);
  
  // Selected task logs state
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [logs, setLogs] = useState([]);
  
  // Form submission state
  const [form, setForm] = useState({
    name: "heavy_computation",
    args: "[5]",
    kwargs: "{}",
    delay_seconds: 0,
    max_retries: 3,
    retry_delay: 5
  });
  const [submissionError, setSubmissionError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Terminal scroll reference
  const terminalEndRef = useRef(null);

  // Initial fetch on mount
  useEffect(() => {
    fetchAvailableTasks();
    fetchSystemData();
    
    // Poll system metrics and task updates every 2 seconds
    const interval = setInterval(fetchSystemData, 2000);
    return () => clearInterval(interval);
  }, []);

  // Poll logs in real-time if a running task is selected
  useEffect(() => {
    if (!selectedTaskId) {
      setLogs([]);
      return;
    }

    // Fetch logs immediately
    fetchLogs(selectedTaskId);

    // Find the selected task's current status
    const selectedTask = tasks.find(t => t.id === selectedTaskId);
    const isTaskActive = selectedTask && ["PENDING", "RUNNING", "RETRYING", "SCHEDULED"].includes(selectedTask.status);

    if (isTaskActive) {
      // Poll logs every 1 second
      const logInterval = setInterval(() => {
        fetchLogs(selectedTaskId);
      }, 1000);
      return () => clearInterval(logInterval);
    }
  }, [selectedTaskId, tasks]);

  // Scroll to bottom of terminal whenever logs update
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const fetchAvailableTasks = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/tasks/available`);
      if (res.ok) {
        const data = await res.json();
        setAvailableTasks(data);
      }
    } catch (err) {
      console.error("Error fetching registered tasks:", err);
    }
  };

  const fetchSystemData = async () => {
    try {
      // Parallel fetches for responsiveness
      const [metricsRes, tasksRes, workersRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/metrics`),
        fetch(`${API_BASE_URL}/api/tasks?limit=30`),
        fetch(`${API_BASE_URL}/api/workers`)
      ]);

      if (metricsRes.ok) setMetrics(await metricsRes.json());
      if (tasksRes.ok) setTasks(await tasksRes.json());
      if (workersRes.ok) setWorkers(await workersRes.json());
    } catch (err) {
      console.error("Error querying backend API:", err);
    }
  };

  const fetchLogs = async (taskId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/logs`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data);
      }
    } catch (err) {
      console.error(`Error fetching logs for task ${taskId}:`, err);
    }
  };

  const handleSubmitTask = async (e) => {
    e.preventDefault();
    setSubmissionError("");
    setIsSubmitting(true);

    // Parse args and kwargs
    let parsedArgs = [];
    let parsedKwargs = {};

    try {
      parsedArgs = JSON.parse(form.args);
      if (!Array.isArray(parsedArgs)) {
        throw new Error("Arguments must be a valid JSON array (e.g., [1, 2] or ['value']).");
      }
    } catch (err) {
      setSubmissionError(`Arguments JSON error: ${err.message}`);
      setIsSubmitting(false);
      return;
    }

    try {
      parsedKwargs = JSON.parse(form.kwargs);
      if (typeof parsedKwargs !== "object" || parsedKwargs === null || Array.isArray(parsedKwargs)) {
        throw new Error("Keyword arguments must be a valid JSON object (e.g., {\"key\": \"value\"}).");
      }
    } catch (err) {
      setSubmissionError(`Keyword Arguments JSON error: ${err.message}`);
      setIsSubmitting(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          args: parsedArgs,
          kwargs: parsedKwargs,
          delay_seconds: parseInt(form.delay_seconds) || 0,
          max_retries: parseInt(form.max_retries) || 0,
          retry_delay: parseInt(form.retry_delay) || 5
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to submit task.");
      }

      const data = await res.json();
      setSelectedTaskId(data.task_id); // Auto-select the newly created task to view logs
      fetchSystemData();
      
      // Reset delay/retries form fields slightly
      setForm(prev => ({
        ...prev,
        delay_seconds: 0
      }));
    } catch (err) {
      setSubmissionError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelTask = async (taskId, e) => {
    e.stopPropagation(); // Avoid selecting the row
    try {
      const res = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/cancel`, { method: "POST" });
      if (res.ok) {
        fetchSystemData();
      } else {
        const err = await res.json();
        alert(err.detail);
      }
    } catch (err) {
      console.error("Error cancelling task:", err);
    }
  };

  const handleRetryTask = async (taskId, e) => {
    e.stopPropagation(); // Avoid selecting the row
    try {
      const res = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/retry`, { method: "POST" });
      if (res.ok) {
        setSelectedTaskId(taskId); // Focus on retried task
        fetchSystemData();
      } else {
        const err = await res.json();
        alert(err.detail);
      }
    } catch (err) {
      console.error("Error retrying task:", err);
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case "PENDING": return "badge badge-pending";
      case "SCHEDULED": return "badge badge-scheduled";
      case "RUNNING": return "badge badge-running";
      case "SUCCESS": return "badge badge-success";
      case "FAILED": return "badge badge-failed";
      case "RETRYING": return "badge badge-retrying";
      case "CANCELLED": return "badge badge-cancelled";
      default: return "badge";
    }
  };

  const formatTimestamp = (ts) => {
    if (!ts) return "-";
    const date = new Date(ts * 1000);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const formatDuration = (task) => {
    if (!task.started_at) return "-";
    const end = task.finished_at || (Date.now() / 1000);
    const duration = end - task.started_at;
    return `${duration.toFixed(1)}s`;
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-title">
          <Activity size={28} color="#6366f1" />
          <h1>Antigravity Flow</h1>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginLeft: "0.5rem" }}>
            v1.0.0 (Mini-Airflow + Celery)
          </span>
        </div>
        
        <div style={{ display: "flex", gap: "1rem" }}>
          <button onClick={fetchSystemData} className="btn btn-secondary btn-sm" title="Force Refresh">
            <RefreshCw size={14} />
          </button>
          <div className="system-status">
            <div className="status-dot"></div>
            <span>CLUSTER ONLINE</span>
          </div>
        </div>
      </header>

      {/* Metrics Panel */}
      <section className="dashboard-grid">
        <div className="metric-card">
          <div className="metric-header">
            <span>ACTIVE QUEUE</span>
            <div className="metric-icon"><Terminal size={18} color="#6366f1" /></div>
          </div>
          <div>
            <div className="metric-value">{metrics.queue_size}</div>
            <div className="metric-desc">Tasks waiting to be picked up</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-header">
            <span>SCHEDULED JOBS</span>
            <div className="metric-icon"><Clock size={18} color="#3b82f6" /></div>
          </div>
          <div>
            <div className="metric-value">{metrics.delayed_size}</div>
            <div className="metric-desc">Jobs waiting on scheduled timers</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-header">
            <span>WORKERS ACTIVE</span>
            <div className="metric-icon"><Cpu size={18} color="#10b981" /></div>
          </div>
          <div>
            <div className="metric-value">{metrics.active_workers}</div>
            <div className="metric-desc">{metrics.busy_workers} busy, {metrics.active_workers - metrics.busy_workers} idle</div>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-header">
            <span>SUCCESS RATE</span>
            <div className="metric-icon">
              {metrics.success_rate >= 80 ? (
                <CheckCircle2 size={18} color="#10b981" />
              ) : (
                <XCircle size={18} color="#ef4444" />
              )}
            </div>
          </div>
          <div>
            <div className="metric-value">{metrics.success_rate}%</div>
            <div className="metric-desc">Success rate of completed runs</div>
          </div>
        </div>
      </section>

      {/* Main Grid Layout */}
      <div className="main-layout">
        {/* Left Hand: Controls & Workers */}
        <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
          
          {/* Submit Task Form */}
          <div className="section-panel">
            <div className="section-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <PlusCircle size={18} color="var(--primary)" />
                <h2>Trigger Task</h2>
              </div>
            </div>
            
            <form onSubmit={handleSubmitTask}>
              <div className="form-group">
                <label>Task Type</label>
                <select 
                  className="form-control"
                  value={form.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    let defaultArgs = "[]";
                    if (name === "heavy_computation") defaultArgs = "[5]";
                    if (name === "flaky_task") defaultArgs = "[0.6]";
                    if (name === "add") defaultArgs = "[10, 20]";
                    if (name === "fetch_data_api") defaultArgs = "[\"https://api.github.com\"]";
                    setForm(prev => ({ ...prev, name, args: defaultArgs }));
                  }}
                >
                  {availableTasks.map(tname => (
                    <option key={tname} value={tname}>{tname}</option>
                  ))}
                </select>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Positional Args (JSON Array)</label>
                  <input 
                    type="text" 
                    className="form-control" 
                    value={form.args} 
                    onChange={e => setForm(prev => ({ ...prev, args: e.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label>Keyword Args (JSON Object)</label>
                  <input 
                    type="text" 
                    className="form-control" 
                    value={form.kwargs} 
                    onChange={e => setForm(prev => ({ ...prev, kwargs: e.target.value }))}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Delay Run (Seconds)</label>
                  <input 
                    type="number" 
                    className="form-control" 
                    value={form.delay_seconds} 
                    onChange={e => setForm(prev => ({ ...prev, delay_seconds: e.target.value }))}
                    min="0"
                  />
                </div>
                <div className="form-group">
                  <label>Max Retries on Error</label>
                  <input 
                    type="number" 
                    className="form-control" 
                    value={form.max_retries} 
                    onChange={e => setForm(prev => ({ ...prev, max_retries: e.target.value }))}
                    min="0"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Retry Delay (Seconds)</label>
                <input 
                  type="number" 
                  className="form-control" 
                  value={form.retry_delay} 
                  onChange={e => setForm(prev => ({ ...prev, retry_delay: e.target.value }))}
                  min="1"
                />
              </div>

              {submissionError && (
                <div style={{ color: "var(--danger)", fontSize: "0.85rem", marginBottom: "1rem", display: "flex", gap: "0.25rem", alignItems: "center" }}>
                  <XCircle size={14} />
                  <span>{submissionError}</span>
                </div>
              )}

              <button 
                type="submit" 
                className="btn btn-primary" 
                style={{ width: "100%" }}
                disabled={isSubmitting}
              >
                <Play size={16} />
                {isSubmitting ? "Queueing Task..." : "Queue Task"}
              </button>
            </form>
          </div>

          {/* Active Workers Panel */}
          <div className="section-panel">
            <div className="section-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Server size={18} color="var(--success)" />
                <h2>Workers Cluster ({Object.keys(workers).filter(k => workers[k].online).length} Active)</h2>
              </div>
            </div>

            <div className="workers-grid">
              {Object.keys(workers).length === 0 ? (
                <div style={{ color: "var(--text-muted)", fontSize: "0.9rem", textAlign: "center", padding: "1rem 0", width: "100%" }}>
                  No workers registered. Start worker containers.
                </div>
              ) : (
                Object.entries(workers).map(([name, data]) => (
                  <div key={name} className={`worker-card ${!data.online ? 'offline' : ''}`}>
                    <div className="worker-meta">
                      <span className="worker-title" title={name}>{name.split('@')[0]}</span>
                      <span className={`badge ${data.online ? (data.status === 'busy' ? 'badge-running' : 'badge-success') : 'badge-cancelled'}`}>
                        {data.online ? (data.status === 'busy' ? 'busy' : 'idle') : 'offline'}
                      </span>
                    </div>
                    
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                      <div>Completed: <strong>{data.tasks_completed}</strong></div>
                      {data.online && data.current_task_id && (
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          Running: <span 
                            style={{ color: "var(--primary)", cursor: "pointer", textDecoration: "underline" }}
                            onClick={() => setSelectedTaskId(data.current_task_id)}
                          >
                            {data.current_task_id.substring(0, 8)}...
                          </span>
                        </div>
                      )}
                      <div>Last seen: {new Date(data.last_seen * 1000).toLocaleTimeString()}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Hand: Monitor & Log Streams */}
        <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
          
          {/* Task Monitor */}
          <div className="section-panel" style={{ flexGrow: 1 }}>
            <div className="section-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Activity size={18} color="var(--primary)" />
                <h2>Monitor Tasks</h2>
              </div>
            </div>

            <div className="table-container">
              <table className="task-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Task Name</th>
                    <th>Runtime</th>
                    <th>Retries</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.length === 0 ? (
                    <tr>
                      <td colSpan="5" style={{ textCenter: "center", color: "var(--text-muted)", padding: "2rem", textAlign: "center" }}>
                        No tasks submitted yet. Submit a task using the form.
                      </td>
                    </tr>
                  ) : (
                    tasks.map(task => (
                      <tr 
                        key={task.id} 
                        className={`task-row ${selectedTaskId === task.id ? 'selected' : ''}`}
                        onClick={() => setSelectedTaskId(task.id)}
                      >
                        <td>
                          <span className={getStatusBadgeClass(task.status)}>{task.status}</span>
                        </td>
                        <td>
                          <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{task.name}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                            ID: {task.id.substring(0, 8)}...
                          </div>
                        </td>
                        <td>
                          <div>{formatDuration(task)}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            In: {formatTimestamp(task.created_at)}
                          </div>
                        </td>
                        <td>
                          {task.max_retries - task.retries_left} / {task.max_retries}
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            {["PENDING", "SCHEDULED"].includes(task.status) && (
                              <button 
                                onClick={(e) => handleCancelTask(task.id, e)} 
                                className="btn btn-danger btn-sm"
                                title="Cancel Task"
                                style={{ padding: "0.25rem 0.5rem" }}
                              >
                                <Ban size={12} />
                              </button>
                            )}
                            {["FAILED", "CANCELLED"].includes(task.status) && (
                              <button 
                                onClick={(e) => handleRetryTask(task.id, e)} 
                                className="btn btn-secondary btn-sm"
                                title="Manual Retry"
                                style={{ padding: "0.25rem 0.5rem" }}
                              >
                                <RotateCcw size={12} color="var(--warning)" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Execution Log Terminal */}
          <div className="section-panel">
            <div className="section-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Terminal size={18} color="var(--accent)" />
                <h2>
                  Execution Logs
                  {selectedTaskId && ` (Task ID: ${selectedTaskId.substring(0, 8)}...)`}
                </h2>
              </div>
              {selectedTaskId && (
                <span className={getStatusBadgeClass(tasks.find(t => t.id === selectedTaskId)?.status)}>
                  {tasks.find(t => t.id === selectedTaskId)?.status}
                </span>
              )}
            </div>

            <div className="terminal-window">
              <div className="terminal-header">
                <div className="terminal-dots">
                  <div className="terminal-dot red"></div>
                  <div className="terminal-dot yellow"></div>
                  <div className="terminal-dot green"></div>
                </div>
                <div className="terminal-title">bash - stdout_capture.log</div>
                <div style={{ width: "42px" }}></div>
              </div>
              
              <div className="terminal-body">
                {!selectedTaskId ? (
                  <div className="terminal-placeholder">
                    <Terminal size={32} color="var(--text-muted)" />
                    <span>Select a task from the list to view its output logs</span>
                  </div>
                ) : logs.length === 0 ? (
                  <div className="terminal-placeholder">
                    <div className="status-dot" style={{ backgroundColor: "var(--primary)" }}></div>
                    <span>Waiting for task logs to stream...</span>
                  </div>
                ) : (
                  <>
                    {logs.map((log, index) => (
                      <div key={index} style={{ wordBreak: "break-all" }}>{log}</div>
                    ))}
                    
                    {/* Error display if task failed */}
                    {tasks.find(t => t.id === selectedTaskId)?.error && (
                      <div style={{ color: "var(--danger)", marginTop: "0.5rem", borderTop: "1px dashed rgba(239, 68, 68, 0.3)", paddingTop: "0.5rem" }}>
                        [CRITICAL EXCEPTION DETAILS]
                        <pre style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem", whiteSpace: "pre-wrap", marginTop: "0.25rem" }}>
                          {tasks.find(t => t.id === selectedTaskId)?.error}
                        </pre>
                      </div>
                    )}

                    {/* Result display if task succeeded */}
                    {tasks.find(t => t.id === selectedTaskId)?.result && (
                      <div style={{ color: "var(--success)", marginTop: "0.5rem", borderTop: "1px dashed rgba(16, 185, 129, 0.3)", paddingTop: "0.5rem" }}>
                        [RUN SUCCESSFUL]
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem", marginTop: "0.25rem" }}>
                          Result: {tasks.find(t => t.id === selectedTaskId)?.result}
                        </div>
                      </div>
                    )}
                    <div ref={terminalEndRef} />
                  </>
                )}
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

export default App;
