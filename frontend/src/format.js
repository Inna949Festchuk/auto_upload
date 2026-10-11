const UNITS = ["Б", "КБ", "МБ", "ГБ", "ТБ"];

export function formatBytes(n) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  if (n === 0) return "0 Б";
  let v = Number(n);
  let i = 0;
  while (v >= 1024 && i < UNITS.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${UNITS[i]}`;
}

export function formatSpeed(bps) {
  if (!bps || bps <= 0) return "";
  return `${formatBytes(bps)}/с`;
}

export function formatDate(s) {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d)) return s;
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
