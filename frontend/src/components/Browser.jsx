import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { formatBytes, formatDate } from "../format";
import { FileIcon, FolderIcon } from "./icons";

export default function Browser({ onSelectionChange }) {
  const [path, setPath] = useState("/");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState({});

  const load = useCallback(async (p) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.browse(p);
      setPath(data.path || p);
      setItems(data.items);
    } catch (e) {
      setError(e.message);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load("/");
  }, [load]);

  const update = (next) => {
    setSelected(next);
    onSelectionChange(next);
  };

  const isSel = (p) => Boolean(selected[p]);

  const toggle = (item) => {
    const next = { ...selected };
    if (next[item.path]) {
      delete next[item.path];
    } else {
      next[item.path] = { path: item.path, type: item.type };
    }
    update(next);
  };

  const allSelected = items.length > 0 && items.every((i) => isSel(i.path));
  const toggleAll = () => {
    if (allSelected) {
      update({});
    } else {
      const next = { ...selected };
      items.forEach((i) => {
        next[i.path] = { path: i.path, type: i.type };
      });
      update(next);
    }
  };

  const crumbs = path.split("/").filter(Boolean);
  const go = (p) => load(p);
  const count = Object.keys(selected).length;

  return (
    <div className="browser">
      <div className="breadcrumbs">
        <button className="crumb" onClick={() => go("/")}>
          Диск
        </button>
        {crumbs.map((c, i) => (
          <span className="crumb-sep" key={i}>
            <span className="crumb-sep-mark">/</span>
            <button className="crumb" onClick={() => go("/" + crumbs.slice(0, i + 1).join("/"))}>
              {c}
            </button>
          </span>
        ))}
        <span className="spacer" />
        <button className="btn btn-ghost btn-small" onClick={() => load(path)} title="Обновить">
          ⟳ Обновить
        </button>
      </div>

      {error && <div className="alert error browse-alert">{error}</div>}

      {loading ? (
        <div className="loading">Загрузка…</div>
      ) : (
        <div className="table-wrap">
          <table className="file-table">
            <thead>
              <tr>
                <th className="col-check">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                </th>
                <th>Имя</th>
                <th className="col-size">Размер</th>
                <th className="col-date">Изменён</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && (
                <tr>
                  <td colSpan={4} className="empty">
                    Папка пуста
                  </td>
                </tr>
              )}
              {items.map((item) => (
                <tr
                  key={item.path}
                  className={isSel(item.path) ? "selected" : ""}
                  onDoubleClick={item.type === "folder" ? () => go(item.path) : undefined}
                >
                  <td className="col-check">
                    <input
                      type="checkbox"
                      checked={isSel(item.path)}
                      onChange={() => toggle(item)}
                    />
                  </td>
                  <td>
                    <span
                      className={"file-name" + (item.type === "folder" ? " clickable" : "")}
                      onClick={item.type === "folder" ? () => go(item.path) : undefined}
                    >
                      {item.type === "folder" ? <FolderIcon /> : <FileIcon />}
                      {item.name}
                    </span>
                  </td>
                  <td className="col-size">
                    {item.type === "file" ? formatBytes(item.size) : "—"}
                  </td>
                  <td className="col-date">{formatDate(item.modified)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {count > 0 && (
        <div className="selection-bar">
          <span>
            Выбрано: <b>{count}</b>
          </span>
          <button className="btn btn-ghost btn-small" onClick={() => update({})}>
            Сбросить
          </button>
        </div>
      )}
    </div>
  );
}
