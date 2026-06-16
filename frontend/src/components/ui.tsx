import { useId, useRef, useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "../lib/apiClient";

type BadgeVariant = "success" | "warning" | "danger" | "primary" | "neutral";

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  ready: "success",
  active: "success",
  processing: "warning",
  uploaded: "warning",
  failed: "danger",
  quarantined: "danger",
  deleted: "danger",
  archived: "neutral",
};

export function Badge({
  variant = "neutral",
  dot = false,
  children,
}: {
  variant?: BadgeVariant;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`badge ${variant}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="badge neutral">—</span>;
  const variant = STATUS_VARIANT[status] ?? "neutral";
  return (
    <span className={`badge ${variant}`}>
      <span className="dot" />
      {status}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={`card${className ? ` ${className}` : ""}`}>{children}</div>;
}

export function CardInner({
  children,
  role,
  id,
  "aria-labelledby": ariaLabelledby,
}: {
  children: ReactNode;
  role?: string;
  id?: string;
  "aria-labelledby"?: string;
}) {
  return (
    <div className="card-inner" role={role} id={id} aria-labelledby={ariaLabelledby}>
      {children}
    </div>
  );
}

export function SectionHead({
  title,
  hint,
  actions,
}: {
  title: string;
  hint?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {hint && <div className="hint">{hint}</div>}
      </div>
      {actions}
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  note,
  actions,
}: {
  eyebrow?: string;
  title: string;
  note?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {note && <div className="page-note">{note}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function KpiCard({
  icon,
  value,
  label,
  badge,
}: {
  icon: ReactNode;
  value: ReactNode;
  label: string;
  badge?: ReactNode;
}) {
  return (
    <article className="kpi">
      <div className="kpi-top">
        <div className="kpi-icon">{icon}</div>
        {badge}
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </article>
  );
}

/**
 * Tab-Leiste. Damit Tabs und Tabpanels barrierefrei verknuepft sind, sollte ein
 * stabiler `idBase` uebergeben werden: Tab-Buttons erhalten `id={`${idBase}-tab-${id}`}`
 * und `aria-controls={`${idBase}-panel-${id}`}`. Konsumenten rendern den zugehoerigen
 * Panel-Container dann mit `role="tabpanel"`, `id={`${idBase}-panel-${id}`}` und
 * `aria-labelledby={`${idBase}-tab-${id}`}`. Die Helfer `tabPanelId`/`tabId` erzeugen
 * dieselben Konventions-IDs. Ohne `idBase` wird eine interne (instabile) ID genutzt.
 */
export function tabId(base: string, id: string) {
  return `${base}-tab-${id}`;
}

export function tabPanelId(base: string, id: string) {
  return `${base}-panel-${id}`;
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  idBase,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
  idBase?: string;
}) {
  const uid = useId();
  const base = idBase ?? uid;
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          id={tabId(base, t.id)}
          role="tab"
          aria-selected={t.id === value}
          aria-controls={tabPanelId(base, t.id)}
          className={`tab${t.id === value ? " active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function ProgressBar({ percent }: { percent: number }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="progress">
      <div style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function UploadZone({
  onFile,
  accept,
  hint = "Datei hier ablegen oder klicken zum Auswaehlen",
  disabled = false,
}: {
  onFile: (file: File) => void;
  accept?: string;
  hint?: string;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  return (
    <div
      className={`upload-zone${drag ? " drag" : ""}`}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Datei hochladen"
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (!disabled) inputRef.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (disabled) return;
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <div>
        <div className="upload-icon" aria-hidden="true">
          {"⇧"}
        </div>
        <strong>Dateien hochladen</strong>
        <div className="hint">{hint}</div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Unbekannter Fehler";
  return <div className="banner error">{message}</div>;
}

export function SuccessBanner({ children }: { children: ReactNode }) {
  return <div className="banner success">{children}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Loading() {
  return <div className="empty">Lade …</div>;
}
