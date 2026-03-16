import React, { useState, useEffect } from "react";

const API_URL = process.env.REACT_APP_API_URL;

const COLUMNS = ["todo", "in_progress", "done"];

const COLUMN_LABELS = {
  todo: "To Do",
  in_progress: "In Progress",
  done: "Done",
};

function App() {
  const [tasks, setTasks] = useState([]);
  const [newTitle, setNewTitle] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTasks();
  }, []);

  async function fetchTasks() {
    try {
      const response = await fetch(`${API_URL}/api/tasks`);
      const data = await response.json();
      setTasks(data);
    } catch (err) {
      console.error("Failed to load tasks:", err);
    } finally {
      setLoading(false);
    }
  }

  async function createTask(e) {
    e.preventDefault();
    if (!newTitle.trim()) return;

    try {
      const response = await fetch(`${API_URL}/api/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle }),
      });
      const task = await response.json();
      setTasks([task, ...tasks]);
      setNewTitle("");
    } catch (err) {
      console.error("Failed to create task:", err);
    }
  }

  async function moveTask(id, newStatus) {
    try {
      await fetch(`${API_URL}/api/tasks/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      setTasks(
        tasks.map((t) => (t.id === id ? { ...t, status: newStatus } : t))
      );
    } catch (err) {
      console.error("Failed to move task:", err);
    }
  }

  async function deleteTask(id) {
    try {
      await fetch(`${API_URL}/api/tasks/${id}`, { method: "DELETE" });
      setTasks(tasks.filter((t) => t.id !== id));
    } catch (err) {
      console.error("Failed to delete task:", err);
    }
  }

  if (loading) return <p>Loading...</p>;

  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
      <h1>TaskBoard</h1>

      <form onSubmit={createTask} style={{ marginBottom: "2rem" }}>
        <input
          type="text"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="New task title..."
          style={{ padding: "0.5rem", marginRight: "0.5rem", width: "300px" }}
        />
        <button type="submit" style={{ padding: "0.5rem 1rem" }}>
          Add Task
        </button>
      </form>

      <div style={{ display: "flex", gap: "2rem" }}>
        {COLUMNS.map((status) => (
          <div
            key={status}
            style={{
              flex: 1,
              background: "#f4f4f4",
              borderRadius: "8px",
              padding: "1rem",
              minHeight: "300px",
            }}
          >
            <h2>{COLUMN_LABELS[status]}</h2>
            {tasks
              .filter((t) => t.status === status)
              .map((task) => (
                <div
                  key={task.id}
                  style={{
                    background: "#fff",
                    borderRadius: "4px",
                    padding: "0.75rem",
                    marginBottom: "0.5rem",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
                  }}
                >
                  <strong>{task.title}</strong>
                  {task.description && (
                    <p style={{ margin: "0.25rem 0", color: "#666" }}>
                      {task.description}
                    </p>
                  )}
                  <div style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                    {COLUMNS.filter((s) => s !== status).map((s) => (
                      <button
                        key={s}
                        onClick={() => moveTask(task.id, s)}
                        style={{ marginRight: "0.5rem" }}
                      >
                        {COLUMN_LABELS[s]}
                      </button>
                    ))}
                    <button
                      onClick={() => deleteTask(task.id)}
                      style={{ color: "red" }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
