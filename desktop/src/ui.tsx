import { KeyboardEvent, ReactNode, useState } from "react";
import { useT } from "./i18n";

// Küçük, satır içi SVG simgeler (uygulama çevrimdışı çalışır, simge kütüphanesi yok).
const paths = {
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Zm0 0v5h5",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z",
  shield: "M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6l-7-3Zm-3 9 2 2 4-4",
  scan: "M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M4 12h16",
  check: "m5 12 5 5L20 7",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  eyeOff: "M3 3l18 18M10.6 5.1A10.6 10.6 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.1 4M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a10 10 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2",
  plus: "M12 5v14M5 12h14",
  x: "M6 6l12 12M18 6 6 18",
  alert: "M12 9v4m0 4h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  sun: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7 1.4-1.4M4.9 19.1l1.4-1.4m0-11.4L4.9 4.9m14.2 14.2-1.4-1.4M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z",
  moon: "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z",
  monitor: "M3 5h18v11H3zM8 20h8m-4-4v4",
  upload: "M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3",
  chevron: "m9 6 6 6-6 6",
  trash: "M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3",
  lock: "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3",
  unlock: "M6 11h12v9H6zM8 11V8a4 4 0 0 1 7.5-2",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.3l2-1.6-2-3.4-2.4 1a7.3 7.3 0 0 0-2.2-1.3L14.3 3h-4l-.4 2.4a7.3 7.3 0 0 0-2.2 1.3l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.6l-2 1.6 2 3.4 2.4-1a7.3 7.3 0 0 0 2.2 1.3l.4 2.4h4l.4-2.4a7.3 7.3 0 0 0 2.2-1.3l2.4 1 2-3.4-2-1.6c.1-.4.1-.9.1-1.3Z",
  pen: "M3 17c3-1 4-6 6-6s1 5 3 5 3-4 5-4 2 2 4 2M3 21h18",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  arrowLeft: "M19 12H5m6-6-6 6 6 6",
  home: "m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  crop: "M6 2v14a2 2 0 0 0 2 2h14M18 22V8a2 2 0 0 0-2-2H2",
  stop: "M7 7h10v10H7z",
  minus: "M5 12h14",
  slides: "M3 5h18v12H3zM8 21h8M12 17v4M7 9h6M7 12h10",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21a8 8 0 0 1 16 0",
  idcard: "M3 5h18v14H3zM9 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM14 10h4M14 14h4",
  phone: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2",
  pin: "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Zm0-8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  card: "M3 6h18v12H3zM3 10h18M7 15h3",
  calendar: "M4 5h16v16H4zM8 3v4M16 3v4M4 10h16",
  tag: "M3 12V4h8l10 10-8 8L3 12Zm5-4h.01",
  grid: "M4 4h16v16H4zM4 9h16M4 14h16M9 4v16M15 4v16",
  key: "M15 7a4 4 0 1 1-3.9 4.9L4 19v2h3v-2h2v-2h2l1.1-1.1A4 4 0 0 1 15 7Zm1 3h.01",
  doc: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Zm0 0v5h5M8 12h8M8 15.5h8M8 19h5",
  expand: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  shrink: "M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 2-2 5 5M15.5 9.5a1.5 1.5 0 1 0 0-.01",
  code: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Zm0 0v5h5M10 12l-2 2 2 2m4-4 2 2-2 2",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 5 5",
  undo: "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  question: "M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z",
  text: "M4 6h16M4 10h16M4 14h10M4 18h7",
  files: "M15 2H8a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7l-5-5ZM15 2v5h5M3 7v13a2 2 0 0 0 2 2h10",
  arrowRight: "M5 12h14m-6-6 6 6-6 6",
  refresh: "M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16m0 4v-4h-4",
  menu: "M4 6h16M4 12h16M4 18h16",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  download: "M12 3v12m-5-5 5 5 5-5M5 21h14",
  ban: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM5 5l14 14",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Zm7 12 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z",
} as const;

export type IconName = keyof typeof paths;

export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="logo">
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M7 18a4 4 0 0 1-.6-8 6 6 0 0 1 11.5 1.5A3.3 3.3 0 0 1 17.5 18H7Z"
          fill="var(--accent-soft)"
          stroke="var(--accent)"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <rect x="8.5" y="12.3" width="7" height="2.4" rx="1" fill="var(--mask)" />
      </svg>
      Bulut<span>Belge</span>
    </span>
  );
}

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={checked ? "switch on" : "switch"}
      onClick={() => onChange(!checked)}
    >
      <span />
    </button>
  );
}

/** Enter, virgül ya da yapıştırmayla etiket ekleyen giriş alanı. */
export function ChipInput({
  values,
  onChange,
  placeholder,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
}) {
  const t = useT();
  const [draft, setDraft] = useState("");

  function add(raw: string) {
    const items = raw
      .split(/[\n,;]/)
      .map((s) => s.trim())
      .filter((s) => s && !values.includes(s));
    if (items.length) onChange([...values, ...new Set(items)]);
    setDraft("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div className="chips">
      {values.map((v) => (
        <span className="chip" key={v}>
          {v}
          <button type="button" aria-label={t("{v} kaldır", { v })} onClick={() => onChange(values.filter((x) => x !== v))}>
            <Icon name="x" size={12} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        placeholder={values.length ? "" : placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => draft.trim() && add(draft)}
        onPaste={(e) => {
          const text = e.clipboardData.getData("text");
          if (/[\n,;]/.test(text)) {
            e.preventDefault();
            add(text);
          }
        }}
      />
    </div>
  );
}

export function Section({
  title,
  hint,
  children,
  defaultOpen = true,
  badge,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  defaultOpen?: boolean;
  badge?: ReactNode;
}) {
  return (
    <details className="section" open={defaultOpen}>
      <summary>
        <Icon name="chevron" size={14} />
        <span className="section-title">{title}</span>
        {badge}
      </summary>
      {hint && <p className="hint">{hint}</p>}
      {children}
    </details>
  );
}

/** Belgedeki karartmanın küçük önizlemesi (sitedeki .mask ile aynı görünüm). */
export function MaskBar({ width = 64 }: { width?: number }) {
  const t = useT();
  return <span className="mask" style={{ width }} aria-label={t("siyah kutu")} />;
}

const SAMPLE_TEXT: Record<string, string> = { etiket: "[TC NO]", son4: "**** 1234" };

/** Bir yöntemin belgede nasıl görüneceği: tabloda gerçek metinle, ayarlarda örnekle. */
export function MethodSample({ method, text }: { method: string; text?: string }) {
  const t = useT();
  if (method === "bulanik") return <span className="blur-chip" aria-label={t("bulanık dolgu")} />;
  const shown = text ?? SAMPLE_TEXT[method];
  if (shown) return <code className="replacement">{shown}</code>;
  return <MaskBar />;
}

/** Kopya, kullanıcının seçtiği yoldan farklı bir yere ya da adla kaydedildiyse nedenini gösterir. */
export function PathChanged({ reason }: { reason?: string | null }) {
  const t = useT();
  if (!reason) return null;
  return (
    <p className="path-changed" role="status">
      <Icon name="alert" size={15} />
      <span>{t(reason)}</span>
    </p>
  );
}
