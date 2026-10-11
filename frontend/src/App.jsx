import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./format";
import Browser from "./components/Browser";
import TaskPanel from "./components/TaskPanel";
import TokenScreen from "./components/TokenScreen";
import { DiskLogo } from "./components/icons";

export default function App() {
  const [token, setToken] = useState(undefined); // undefined = загрузка
  const [tasks, setTasks] = useState([]);
  const [selected, setSelected] = useState({});

  const loadToken = useCallback(async () => {
    try {
      setToken(await api.tokenStatus());
    } catch {
      setToken(null);
    }
  }, []);

  useEffect(() => {
    loadToken();
  }, [loadToken]);

  const refreshTasks = useCallback(() => {
    api
      .tasks()
      .then((d) => setTasks(d.tasks))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshTasks();
    const t = setInterval(refreshTasks, 2000);
    return () => clearInterval(t);
  }, [refreshTasks]);

  if (token === undefined) {
    return <div className="loading">Загрузка…</div>;
  }

  if (!token || !token.connected) {
    return <TokenScreen onConnected={loadToken} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo">
          <DiskLogo size={26} />
          <span>Яндекс Диск</span>
        </span>
        <span className="sep" />
        <span className="subtitle">Выгрузка на диск</span>
        <span className="spacer" />
        <span className="account">
          {token.login || "Диск"} · занято {formatBytes(token.used_bytes)} из{" "}
          {formatBytes(token.total_bytes)} · {token.token_masked}
        </span>
        <button
          className="btn btn-ghost btn-small"
          onClick={async () => {
            await api.deleteToken();
            loadToken();
          }}
        >
          Отключить
        </button>
      </header>

      <div className="main">
        <Browser onSelectionChange={setSelected} />
        <TaskPanel
          tasks={tasks}
          selected={selected}
          onTaskCreated={() => setSelected({})}
          onRefresh={refreshTasks}
        />
      </div>
    </div>
  );
}
