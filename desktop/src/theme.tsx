import { useEffect, useState } from "react";
import { useT } from "./i18n";
import { Icon, IconName } from "./ui";

/** "system": bilgisayarın ayarına uyar; "light"/"dark": kullanıcının seçimi. */
export type Theme = "system" | "light" | "dark";

const KEY = "bulutbelge.theme";
const EVENT = "bulutbelge-theme";

function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    // depolama kapalıysa sistem teması
  }
  return "system";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

// Uygulama açılırken kayıtlı tema hemen uygulansın (ilk çizimde yanıp sönmesin).
applyTheme(readTheme());

function systemIsDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Tema durumu; üst çubuk ve Ayarlar aynı ayarı paylaşır (biri değişince öbürü de güncellenir). */
export function useTheme(): [Theme, (t: Theme) => void, "light" | "dark"] {
  const [theme, setThemeState] = useState<Theme>(readTheme);
  const [sysDark, setSysDark] = useState(systemIsDark);

  useEffect(() => {
    const onChange = () => setThemeState(readTheme());
    window.addEventListener(EVENT, onChange);
    const mq = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    const onSys = () => setSysDark(systemIsDark());
    mq?.addEventListener("change", onSys);
    return () => {
      window.removeEventListener(EVENT, onChange);
      mq?.removeEventListener("change", onSys);
    };
  }, []);

  function setTheme(t: Theme) {
    try {
      localStorage.setItem(KEY, t);
    } catch {
      // yok say
    }
    applyTheme(t);
    setThemeState(t);
    window.dispatchEvent(new Event(EVENT));
  }

  const resolved = theme === "system" ? (sysDark ? "dark" : "light") : theme;
  return [theme, setTheme, resolved];
}

/** Üst çubuktaki "Açık | Koyu" anahtarı. */
export function ThemeSwitch() {
  const t = useT();
  const [, setTheme, resolved] = useTheme();
  const opts: { key: "light" | "dark"; label: string; icon: IconName }[] = [
    { key: "light", label: "Açık", icon: "sun" },
    { key: "dark", label: "Koyu", icon: "moon" },
  ];
  return (
    <div className="theme-switch" role="radiogroup" aria-label={t("Görünüm")}>
      {opts.map((o) => (
        <button key={o.key} role="radio" aria-checked={resolved === o.key} className={resolved === o.key ? "on" : undefined} onClick={() => setTheme(o.key)}>
          <Icon name={o.icon} size={15} /> {t(o.label)}
        </button>
      ))}
    </div>
  );
}

/** Ayarlar'daki tema seçimi: Açık, Koyu, Sistem. */
export function ThemeChoice() {
  const t = useT();
  const [theme, setTheme] = useTheme();
  const opts: { key: Theme; label: string; icon: IconName; hint: string }[] = [
    { key: "light", label: "Açık", icon: "sun", hint: "Beyaz zemin" },
    { key: "dark", label: "Koyu", icon: "moon", hint: "Gece görünümü" },
    { key: "system", label: "Sistem", icon: "monitor", hint: "Cihaz ayarına uyar" },
  ];
  return (
    <div className="theme-choice" role="radiogroup" aria-label={t("Görünüm")}>
      {opts.map((o) => (
        <button key={o.key} role="radio" aria-checked={theme === o.key} className={theme === o.key ? "on" : undefined} onClick={() => setTheme(o.key)}>
          <Icon name={o.icon} size={18} />
          <b>{t(o.label)}</b>
          <small>{t(o.hint)}</small>
        </button>
      ))}
    </div>
  );
}
