import { FormEvent, useEffect, useState } from "react";
import { engineCall } from "./engine";
import { useT } from "./i18n";
import { Terms, VaultStatus } from "./settings";
import { Icon } from "./ui";

const MIN_PASSWORD = 8;

/** Kasa parolasıyla kilidi açar. Parola yalnızca motora gider, saklanmaz. */
export function UnlockForm({
  onUnlocked,
  onForgot,
  compact,
}: {
  onUnlocked: (terms: Terms) => void;
  onForgot?: () => void;
  compact?: boolean;
}) {
  const t = useT();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { terms } = await engineCall<{ terms: Terms }>("vault.unlock", { password });
      setPassword("");
      onUnlocked(terms);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={compact ? "vault-form compact" : "vault-form"} onSubmit={submit}>
      <div className="vault-row">
        <input
          type="password"
          autoFocus
          placeholder={t("Kasa parolası")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button className="btn primary" disabled={!password || busy}>
          <Icon name="unlock" /> {busy ? t("Açılıyor…") : t("Kilidi aç")}
        </button>
      </div>
      {error && <p className="field-error">{t(error)}</p>}
      {onForgot && (
        <button type="button" className="link-btn subtle" onClick={onForgot}>
          {t("Parolamı unuttum")}
        </button>
      )}
    </form>
  );
}

/** İlk kez parola belirleme ya da parola değiştirme. */
export function PasswordForm({
  mode,
  onDone,
  onCancel,
}: {
  mode: "create" | "change";
  onDone: (terms?: Terms) => void;
  onCancel?: () => void;
}) {
  const t = useT();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = confirm.length > 0 && confirm !== password;
  const valid = password.length >= MIN_PASSWORD && confirm === password;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") {
        const { terms } = await engineCall<{ terms: Terms }>("vault.create", { password });
        onDone(terms);
      } else {
        await engineCall("vault.change_password", { password });
        onDone();
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="vault-form" onSubmit={submit}>
      <div className="vault-grid">
        <input
          type="password"
          placeholder={mode === "create" ? t("Parola (en az 8 karakter)") : t("Yeni parola")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
        />
        <input
          type="password"
          placeholder={t("Parola tekrar")}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
        />
      </div>
      {(tooShort || mismatch || error) && (
        <p className="field-error">
          {error ? t(error) : tooShort ? t("Parola en az {n} karakter olmalı.", { n: MIN_PASSWORD }) : t("Parolalar aynı değil.")}
        </p>
      )}
      <div className="vault-row end">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            {t("Vazgeç")}
          </button>
        )}
        <button className="btn primary" disabled={!valid || busy}>
          <Icon name="lock" /> {mode === "create" ? t("Kasayı oluştur") : t("Parolayı değiştir")}
        </button>
      </div>
    </form>
  );
}

/** Kasa silme onayı: parola unutulduysa tek çıkış yolu. */
export function DeleteVault({ onDeleted, onCancel }: { onDeleted: (s: VaultStatus) => void; onCancel: () => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  return (
    <div className="danger-box">
      <p>
        <b>{t("Parola kurtarılamaz.")}</b>{" "}
        {t("Kasayı silerseniz tüm profillerdeki özel ifadeler kalıcı olarak silinir; ardından yeni bir parolayla baştan oluşturabilirsiniz.")}
      </p>
      <div className="vault-row end">
        <button className="btn" onClick={onCancel}>
          {t("Vazgeç")}
        </button>
        <button
          className="btn danger"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            onDeleted(await engineCall<VaultStatus>("vault.delete"));
          }}
        >
          <Icon name="trash" /> {t("Kasayı sil")}
        </button>
      </div>
    </div>
  );
}

/** Ana ekrandan açılan kilit açma penceresi. */
export function UnlockDialog({ onUnlocked, onClose }: { onUnlocked: (terms: Terms) => void; onClose: () => void }) {
  const t = useT();
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="unlock-title">
        <div className="modal-head">
          <span className="file-icon">
            <Icon name="lock" size={18} />
          </span>
          <div>
            <h2 id="unlock-title">{t("Özel ifadelerin kilidini açın")}</h2>
            <p className="hint">{t("Kişi, müşteri ve proje adları bu bilgisayarda parolayla şifreli saklanır.")}</p>
          </div>
          <button className="icon-btn" aria-label={t("Kapat")} onClick={onClose}>
            <Icon name="x" size={14} />
          </button>
        </div>
        <UnlockForm onUnlocked={onUnlocked} />
      </div>
    </div>
  );
}

const PSEUDONYM_TYPES: Record<string, string> = {
  kisi_adi: "Kişi",
  eposta: "E-posta",
  telefon: "Telefon",
  tc_kimlik: "TC kimlik",
  vkn: "VKN",
  iban: "IBAN",
  pasaport: "Pasaport",
  musteri_no: "Müşteri no",
};

/**
 * Kasadaki takma ad tablosu: türlere göre sayılar, tek bir takma adı geri çevirme
 * (maske kaldırma; kullanıcının açık isteğiyle, tek tek) ve tabloyu silme.
 */
export function PseudonymPanel() {
  const t = useT();
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [label, setLabel] = useState("");
  const [result, setResult] = useState<{ type: string; value: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [pasted, setPasted] = useState("");
  const [restored, setRestored] = useState<{ text: string; count: number } | null>(null);

  useEffect(() => {
    engineCall<{ counts: Record<string, number> }>("vault.pseudonyms")
      .then((r) => setCounts(r.counts))
      .catch((e) => setError(String(e)));
  }, []);

  const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="pseudo">
      <div className="pseudo-counts">
        {counts === null ? (
          <span className="iskelet-grup" role="status" aria-label={t("Yükleniyor…")}><i className="iskelet" /><i className="iskelet" /><i className="iskelet" /></span>
        ) : total === 0 ? (
          <span className="hint">{t("Henüz takma ad yok. Ayarlar'da bir türün yöntemini “Takma ad” yapıp maskeleyin.")}</span>
        ) : (
          Object.entries(counts).map(([k, n]) => (
            <span key={k} className="pill">
              {t(PSEUDONYM_TYPES[k] ?? k)} <b>{n}</b>
            </span>
          ))
        )}
      </div>
      <form
        className="vault-row"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          setResult(null);
          try {
            setResult(await engineCall<{ type: string; value: string }>("vault.pseudonym_lookup", { label }));
          } catch (err) {
            setError(String(err));
          }
        }}
      >
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={t("ör. Kişi-3")} aria-label={t("Takma ad")} />
        <button className="btn" disabled={!label.trim()}>
          <Icon name="unlock" size={14} /> {t("Gerçek değeri göster")}
        </button>
      </form>
      {result && (
        <p className="pseudo-result">
          <b>{label.trim()}</b> → <span className="mono">{result.value}</span>{" "}
          <button className="link-btn" onClick={() => setResult(null)}>
            {t("Maskele")}
          </button>
        </p>
      )}
      <form
        className="vault-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          setRestored(null);
          try {
            setRestored(await engineCall<{ text: string; count: number }>("vault.pseudonym_restore_text", { text: pasted }));
          } catch (err) {
            setError(String(err));
          }
        }}
      >
        <textarea
          value={pasted}
          rows={4}
          onChange={(e) => setPasted(e.target.value)}
          placeholder={t("Takma adlı metni yapıştırın (ör. yapay zekâ yanıtı)")}
          aria-label={t("Takma adlı metin")}
        />
        <button className="btn" disabled={!pasted.trim()}>
          <Icon name="unlock" size={14} /> {t("Metni geri çevir")}
        </button>
      </form>
      {restored && (
        <div className="pseudo-result">
          <p className="hint">
            {t("{n} takma ad çevrildi. Sonuç yalnızca burada görünür, kaydedilmez.", { n: restored.count })}{" "}
            <button
              className="link-btn"
              onClick={() => {
                setRestored(null);
                setPasted("");
              }}
            >
              {t("Maskele")}
            </button>
          </p>
          <pre className="mono">{restored.text}</pre>
        </div>
      )}
      {error && <p className="field-error">{t(error)}</p>}
      {total > 0 &&
        (confirmClear ? (
          <div className="danger-box">
            <p>{t("Tablo silinirse daha önce maskelenen belgelerdeki takma adlar bir daha geri çevrilemez ve yeni belgelerde numaralar baştan başlar.")}</p>
            <div className="vault-row end">
              <button className="btn" onClick={() => setConfirmClear(false)}>
                {t("Vazgeç")}
              </button>
              <button
                className="btn danger"
                onClick={async () => {
                  const r = await engineCall<{ counts: Record<string, number> }>("vault.pseudonym_clear");
                  setCounts(r.counts);
                  setConfirmClear(false);
                  setResult(null);
                }}
              >
                {t("Tabloyu sil")}
              </button>
            </div>
          </div>
        ) : (
          <button className="link-btn subtle" onClick={() => setConfirmClear(true)}>
            {t("Takma ad tablosunu sil")}
          </button>
        ))}
    </div>
  );
}
