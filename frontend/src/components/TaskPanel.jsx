import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatBytes, formatSpeed } from "../format";

const STATUS = {
  pending: { label: "В очереди", cls: "st-pending" },
  running: { label: "Выгрузка…", cls: "st-running" },
  done: { label: "Завершено", cls: "st-done" },
  error: { label: "Ошибка", cls: "st-error" },
  cancelled: { label: "Отменено", cls: "st-cancelled" },
};

function TaskCard({ task, onRefresh }) {
  const [showErrors, setShowErrors] = useState(false);
  const prev = useRef({ bytes: 0, at: Date.now() });
  const [speed, setSpeed] = useState(0);

  useEffect(() => {
    if (task.status !== "running") {
      setSpeed(0);
      prev.current = { bytes: 0, at: Date.now() };
      return;
    }
    const now = Date.now();
    const dt = (now - prev.current.at) / 1000;
    if (dt > 0.5) {
      setSpeed(Math.max(0, (task.done_bytes - prev.current.bytes) / dt));
      prev.current = { bytes: task.done_bytes, at: now };
    }
  }, [task.done_bytes, task.status]);

  const st = STATUS[task.status] || STATUS.pending;
  const pct = task.total_files ? Math.min(100, (task.done_files / task.total_files) * 100) : 0;
  const active = task.status === "running" || task.status === "pending";
  const label =
    task.failed_files > 0 && (task.status === "done" || task.status === "error")
      ? `С ошибками: ${task.failed_files}`
      : st.label;

  return (
    <div className={`task-card task-${task.status}`}>
      <div className="task-head">
        <span className="task-title" title={task.dest}>
          {task.dest}
        </span>
        <span className={`chip ${st.cls}`}>{label}</span>
      </div>

      {task.total_files > 0 || active ? (
        <>
          <div className="progress">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="task-meta">
            <span>
              {task.done_files} / {task.total_files || "…"} файлов
            </span>
            <span>
              {formatBytes(task.done_bytes)} из {formatBytes(task.total_bytes)}
            </span>
            {task.status === "running" && speed > 0 && <span>{formatSpeed(speed)}</span>}
          </div>
        </>
      ) : null}

      {task.error && <div className="task-error">{task.error}</div>}

      {task.errors && task.errors.length > 0 && (
        <>
          <button className="link-btn" onClick={() => setShowErrors(!showErrors)}>
            {showErrors ? "Скрыть ошибки" : `Ошибки (${task.errors.length})`}
          </button>
          {showErrors && (
            <ul className="task-errors">
              {task.errors.map((e, i) => (
                <li key={i}>
                  <code>{e.path}</code> — {e.error}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <div className="task-actions">
        {active && (
          <button
            className="btn btn-small btn-ghost"
            onClick={async () => {
              await api.cancelTask(task.id).catch(() => {});
              onRefresh();
            }}
          >
            Отменить
          </button>
        )}
        {!active && (
          <>
            {task.failed_files > 0 && task.errors.length > 0 && (
              <button
                className="btn btn-small btn-primary"
                title="Создаст новую задачу с файлами, которые не скачались (копии на CDN Яндекса могут восстановиться)"
                onClick={async () => {
                  const items = task.errors.map((e) => ({ path: e.path, type: "file" }));
                  await api.createTask(task.dest, items).catch(() => {});
                  onRefresh();
                }}
              >
                Повторить неудавшиеся ({task.errors.length})
              </button>
            )}
            <button
              className="btn btn-small btn-ghost"
              onClick={async () => {
                await api.deleteTask(task.id).catch(() => {});
                onRefresh();
              }}
            >
              Убрать
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function TaskPanel({ tasks, selected, onTaskCreated, onRefresh }) {
  const [dest, setDest] = useState("/data/");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [msgError, setMsgError] = useState(null);
  const count = Object.keys(selected).length;

  const start = async () => {
    setBusy(true);
    setMsg(null);
    setMsgError(null);
    try {
      const items = Object.values(selected);
      await api.createTask(dest, items);
      onTaskCreated();
      setMsg("Выгрузка запущена");
    } catch (e) {
      setMsgError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="task-panel">
      <h2>Выгрузка</h2>

      <label className="field-label" htmlFor="dest">
        Папка на сервере (внутри контейнера)
      </label>
      <input
        id="dest"
        className="text-input"
        value={dest}
        onChange={(e) => setDest(e.target.value)}
        placeholder="/data/..."
        spellCheck={false}
      />
      <p className="hint small">
        Доступна только смонтированная в контейнер область DOWNLOAD_ROOT (по умолчанию /data).
      </p>

      <button className="btn btn-primary btn-block" disabled={busy || count === 0} onClick={start}>
        {busy ? "Запускаем…" : `Скачать выбранное (${count})`}
      </button>

      {msg && <div className="alert ok">{msg}</div>}
      {msgError && <div className="alert error">{msgError}</div>}

      <div className="tasks-list">
        {tasks.length === 0 && <p className="muted">Задач пока нет</p>}
        {tasks.map((t) => (
          <TaskCard key={t.id} task={t} onRefresh={onRefresh} />
        ))}
      </div>
    </aside>
  );
}
