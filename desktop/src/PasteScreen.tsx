import { useEffect, useMemo, useRef, useState } from "react";
import { engineCall, PdfFinding, Rules } from "./engine";
import { canLearn, ReviewExtras, UNCERTAIN } from "./ReviewExtras";
import { TextPreview } from "./TextPreview";
import { useT } from "./i18n";
import { Icon } from "./ui";

/**
 * Metin yapıştır: e-posta, not ya da yapay zekâya gönderilecek bir istem. Metin yalnızca
 * bellekte taranır (motorda text.scan); temizlenmiş metin burada kurulur ve panoya kopyalanır.
 * Hiçbir şey diske yazılmaz. Seçimler değere göre tutulur; metin düzenlenince kaybolmaz.
 */
const CLEAR_CLIP_KEY = "bb.panoyuTemizle";
const CLEAR_CLIP_MS = 60_000;

/** Pano hâlâ bizim yazdığımız metni taşıyorsa (ya da okunamıyorsa) boşaltır; kullanıcı başka şey kopyaladıysa dokunmaz. */
async function clearClipboardIf(copiedText: string) {
  try {
    const now = await navigator.clipboard.readText();
    if (now !== copiedText) return;
  } catch {
    // Okuma izni yok: yine de bizim yazdığımız metni boşaltmayı dene.
  }
  try {
    await navigator.clipboard.writeText("");
  } catch {
    // Pano yazma izni de yoksa yapılacak bir şey yok.
  }
}

export function PasteScreen({
  rules,
  offByRule,
  methodOf,
}: {
  rules: Rules | null;
  offByRule: (type: string) => boolean;
  methodOf: (type: string) => string;
}) {
  const t = useT();
  const [text, setText] = useState("");
  const [findings, setFindings] = useState<PdfFinding[]>([]);
  // KVKK m.6 ipucu satırları (motor yalnızca kategori ve sayı yazar, eşleşen sözcüğü değil).
  const [special, setSpecial] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Kullanıcının değere göre yaptığı seçimler (varsayılanın tersine çevrilenler).
  const [userOn, setUserOn] = useState<Set<string>>(new Set());
  const [userOff, setUserOff] = useState<Set<string>>(new Set());
  const [lastOff, setLastOff] = useState<PdfFinding[]>([]);
  const [copied, setCopied] = useState(false);
  // Pano hijyeni (1.73): temizlenmiş metin panoda kalmasın isteyen için 60 sn sonra panoyu boşaltır (isteğe bağlı, varsayılan kapalı).
  const [clearClip, setClearClip] = useState(() => {
    try {
      return localStorage.getItem(CLEAR_CLIP_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [hovered, setHovered] = useState<string | null>(null);
  const ticket = useRef(0);

  // Hızlı yol (1.48): panodaki metni tek tıkla ya da Ctrl/Cmd+Shift+V ile alır. Onay, kullanıcının kendi tıklaması ya da
  // tuşudur: uygulama panoyu kendiliğinden okumaz, sistem geneli kısayol yoktur.
  async function pasteFromClipboard() {
    try {
      const clip = await navigator.clipboard.readText();
      if (!clip.trim()) {
        setError(t("Pano boş. Önce metni kopyalayın."));
        return;
      }
      setError(null);
      setText(clip);
      setCopied(false);
      setUserOn(new Set());
      setUserOff(new Set());
      setLastOff([]);
    } catch {
      setError(t("Panoya erişilemedi. Metni sol alana Ctrl+V ile yapıştırın."));
    }
  }
  const pasteRef = useRef(pasteFromClipboard);
  pasteRef.current = pasteFromClipboard;
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "v") {
        e.preventDefault();
        void pasteRef.current();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!rules) return;
    const id = ++ticket.current;
    if (!text.trim()) {
      setFindings([]);
      setSpecial([]);
      return;
    }
    const timer = window.setTimeout(() => {
      setBusy(true);
      engineCall<{ findings: PdfFinding[]; warnings?: string[] }>("text.scan", { text, rules })
        .then((r) => {
          if (id !== ticket.current) return;
          setFindings(r.findings);
          setSpecial(r.warnings ?? []);
          setError(null);
        })
        .catch((e) => id === ticket.current && setError(String(e)))
        .finally(() => id === ticket.current && setBusy(false));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [text, rules]);

  const defaultOff = (f: PdfFinding) => offByRule(f.type) || f.confidence === UNCERTAIN;
  const excluded = useMemo(
    () =>
      new Set(
        findings
          .filter((f) => userOff.has(f.value) || (defaultOff(f) && !userOn.has(f.value)))
          .map((f) => f.id),
      ),
    // defaultOff kural takımına bağlı; findings kurallar değişince zaten yenilenir
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [findings, userOn, userOff],
  );

  function setHidden(items: PdfFinding[], hide: boolean) {
    const on = new Set(userOn);
    const off = new Set(userOff);
    const newlyOff: PdfFinding[] = [];
    for (const f of items) {
      on.delete(f.value);
      off.delete(f.value);
      if (hide && defaultOff(f)) on.add(f.value);
      if (!hide && !defaultOff(f)) off.add(f.value);
      if (!hide && !excluded.has(f.id) && items.length === 1 && canLearn(f)) newlyOff.push(f);
    }
    setUserOn(on);
    setUserOff(off);
    setLastOff(newlyOff);
    setCopied(false);
  }

  const toggle = (id: string) => {
    const f = findings.find((x) => x.id === id);
    if (f) setHidden([f], excluded.has(id));
  };

  const cleaned = useMemo(() => {
    let out = "";
    let pos = 0;
    for (const f of [...findings].sort((a, b) => a.span![0] - b.span![0])) {
      if (excluded.has(f.id) || !f.span) continue;
      out += text.slice(pos, f.span[0]) + f.replacement;
      pos = f.span[1];
    }
    return out + text.slice(pos);
  }, [findings, excluded, text]);

  const hiddenCount = findings.filter((f) => !excluded.has(f.id)).length;
  const sure = findings.filter((f) => f.confidence !== UNCERTAIN);
  const unsure = findings.filter((f) => f.confidence === UNCERTAIN);

  async function copy() {
    try {
      await navigator.clipboard.writeText(cleaned);
    } catch {
      // Pano izni yoksa eski yol: görünmez alanı seçip kopyala.
      const area = document.createElement("textarea");
      area.value = cleaned;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2500);
    if (clearClip) window.setTimeout(() => void clearClipboardIf(cleaned), CLEAR_CLIP_MS);
  }

  return (
    <div className="paste-screen">
      <header className="paste-head">
        <h1>{t("Metni temizleyip kopyalayın")}</h1>
        <p>{t("Yapay zekâya, e-postaya ya da mesaja yapıştırmadan önce. Metin hiçbir yere kaydedilmez ve gönderilmez.")}</p>
      </header>

      {error && (
        <div className="banner err" role="alert">
          <Icon name="alert" size={18} />
          <span>{t(error)}</span>
        </div>
      )}

      {special.length > 0 && (
        <div className="banner warn" role="note">
          <Icon name="alert" size={18} />
          <span>{special.map((x) => t(x)).join(" ")}</span>
        </div>
      )}

      <div className="paste-grid">
        <section className="paste-pane">
          <div className="paste-pane-head">
            <b>{t("1. Metninizi yapıştırın")}</b>
            <button className="link-btn subtle" onClick={() => void pasteFromClipboard()} title="Ctrl/Cmd+Shift+V">
              {t("Panodan yapıştır")}
            </button>
            {text && (
              <button
                className="link-btn subtle"
                onClick={() => {
                  setText("");
                  setUserOn(new Set());
                  setUserOff(new Set());
                  setLastOff([]);
                }}
              >
                {t("Temizle")}
              </button>
            )}
          </div>
          <textarea
            className="paste-input"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setCopied(false);
            }}
            placeholder={t("Örnek: Merhaba, ben Ayşe Yılmaz. TC kimlik numaram 12345678950, telefonum 0532 000 12 34…")}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            autoFocus
          />
        </section>

        <section className="paste-pane">
          <div className="paste-pane-head">
            <b>{t("2. Temizlenmiş hâli")}</b>
            <span className="hint">
              {busy ? t("Taranıyor…") : findings.length ? t("{n} bilgi maskelendi · işarete tıklayıp açabilirsiniz", { n: hiddenCount }) : text ? t("Kişisel bilgi bulunamadı") : ""}
            </span>
          </div>
          {text ? (
            <TextPreview
              text={text}
              isXml={false}
              findings={findings}
              excluded={excluded}
              methodOf={methodOf}
              hovered={hovered}
              onHover={setHovered}
              onToggle={toggle}
              view="maskeli"
            />
          ) : (
            <div className="paste-empty">
              <Icon name="shield" size={28} />
              <span>{t("Soldaki alana yapıştırdığınız metin, kişisel bilgileri maskelenmiş olarak burada görünür.")}</span>
            </div>
          )}
          <button className="btn primary big paste-copy" disabled={!text || busy} onClick={copy}>
            <Icon name={copied ? "check" : "copy"} /> {copied ? t("Kopyalandı") : t("Temizlenmiş metni kopyala")}
          </button>
          <label className="paste-clear-clip">
            <input
              type="checkbox"
              checked={clearClip}
              onChange={(e) => {
                setClearClip(e.target.checked);
                try {
                  localStorage.setItem(CLEAR_CLIP_KEY, e.target.checked ? "1" : "0");
                } catch {
                  // Tercih kaydedilemezse bu oturumda geçerli kalır.
                }
              }}
            />{" "}
            {t("Kopyaladıktan 60 saniye sonra panoyu temizle")}
          </label>
        </section>
      </div>

      <ReviewExtras
        unsure={unsure}
        sure={sure}
        excluded={excluded}
        onToggle={toggle}
        onSetMany={setHidden}
        lastOff={lastOff}
        onClearLastOff={() => setLastOff([])}
        onError={setError}
        methodOf={methodOf}
      />
    </div>
  );
}
