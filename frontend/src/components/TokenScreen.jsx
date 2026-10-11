import { useEffect, useState } from "react";
import { api } from "../api";
import { DiskLogo } from "./icons";

export default function TokenScreen({ onConnected }) {
  const [token, setToken] = useState("");
  const [oauthUrl, setOauthUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .oauthUrl()
      .then((d) => setOauthUrl(d.url))
      .catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.saveToken(token);
      onConnected();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="token-screen">
      <div className="token-card">
        <div className="token-logo">
          <DiskLogo size={52} />
          <h1>Выгрузка из Яндекс Диска</h1>
        </div>
        <p className="muted">
          Массовое асинхронное скачивание файлов и папок на локальный диск с сохранением
          структуры вложенных каталогов.
        </p>
        {oauthUrl && (
          <p className="hint">
            1. Откройте ссылку авторизации:{" "}
            <a href={oauthUrl} target="_blank" rel="noreferrer">
              получить токен
            </a>
            <br />
            2. Скопируйте токен из адресной строки и вставьте его ниже.
          </p>
        )}
        <form onSubmit={submit}>
          <textarea
            className="token-input"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Вставьте токен (y0_Ag…)"
            rows={4}
          />
          {error && <div className="alert error">{error}</div>}
          <button className="btn btn-primary btn-block" disabled={busy || !token.trim()}>
            {busy ? "Подключаем…" : "Подключить диск"}
          </button>
        </form>
      </div>
    </div>
  );
}
