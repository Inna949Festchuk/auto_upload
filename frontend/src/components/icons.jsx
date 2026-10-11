export function DiskLogo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="15" fill="#FFCC00" />
      <circle cx="16" cy="16" r="5.5" fill="#FFFFFF" />
    </svg>
  );
}

export function FolderIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 6a2 2 0 0 1 2-2h4.2l2 2H19a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6z"
        fill="#FFCC00"
        stroke="#DFAE00"
        strokeWidth="1"
      />
    </svg>
  );
}

export function FileIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"
        fill="#F2F2F2"
        stroke="#C9C9C9"
        strokeWidth="1"
      />
      <path d="M14 2v6h6" stroke="#C9C9C9" strokeWidth="1" fill="none" />
    </svg>
  );
}
