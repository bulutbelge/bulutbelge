import { FormEvent, useEffect, useState } from "react";
import { engineCall } from "./engine";
import { useT } from "./i18n";
import { SavedPassword } from "./settings";
import { Icon } from "./ui";

/** Çekirdekteki PDF parola sınırıyla aynı (bulutbelge_core.pdf.MIN_PASSWORD). */
const MIN_COPY_PASSWORD = 6;
const CLEAR_CLIP_MS = 30_000;

/** Pano hâlâ bizim kopyaladığımız parolayı taşıyorsa boşaltır; kullanıcı başka şey kopyaladıysa dokunmaz. */
async function clearClipboardIf(copied: string) {
  try {
    if ((await navigator.clipboard.readText()) !== copied) return;
  } catch {
    // Okuma izni yoksa yine de boşaltmayı dene.
  }
  try {
    await navigator.clipboard.writeText("");
  } catch {
    // Yazma izni de yoksa yapılacak bir şey yok.
  }
}

/**
 * Ayarlar › Kopya parolaları (karar 2026-11-25-kayitli-kopya-parolalari).
 * Adlandırılmış PDF parolaları kasada durur. Listede yalnızca ad görünür; değer yalnızca kullanıcı
 * "Göster" ya da "Kopyala" deyince motordan istenir ve işlem günlüğüne (değersiz) yazılır.
 * Ajan komutu ve MCP bu parolaları kullanamaz.
 */
export function CopyPasswords() {
  const t = useT();
  const [items, setItems] = useState<SavedPassword[]>([]);
  const [shown, setShown] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    engineCall<{ passwords: SavedPassword[] }>("vault.passwords")
      .then((r) => setItems(r.passwords))
      .catch((e) => setError(String(e)));
  }, []);

  async function run(fn: () => Promise<{ passwords: SavedPassword[] }>, done?: string) {
    setError(null);
    setNote(null);
    try {
      const r = await fn();
      setItems(r.passwords);
      if (done) setNote(done);
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    }
  }

  async function reveal(id: string): Promise<string | null> {
    try {
      return (await engineCall<{ value: string }>("vault.password_reveal", { id })).value;
    } catch (e) {
      setError(String(e));
      return null;
    }
  }

  async function toggleShow(id: string) {
    if (shown[id] !== undefined) {
      const { [id]: _gone, ...rest } = shown;
      setShown(rest);
      return;
    }
    const value = await reveal(id);
    if (value !== null) setShown({ ...shown, [id]: value });
  }

  async function copy(id: string) {
    const value = await reveal(id);
    if (value === null) return;
    try {
      await navigator.clipboard.writeText(value);
      setNote(t("Parola panoya kopyalandı; 30 saniye sonra panodan silinir."));
      window.setTimeout(() => void clearClipboardIf(value), CLEAR_CLIP_MS);
    } catch {
      setError(t("Panoya kopyalanamadı."));
    }
  }

  async function remove(item: SavedPassword) {
    if (!window.confirm(t("\"{ad}\" parolası silinsin mi? Bu işlem geri alınamaz.", { ad: item.name }))) return;
    const { [item.id]: _gone, ...rest } = shown;
    setShown(rest);
    await run(() => engineCall("vault.password_delete", { id: item.id }), t("Parola silindi."));
  }

  return (
    <div className="copy-passwords">
      {items.length === 0 && !adding && (
        <p className="hint">{t("Henüz kayıtlı kopya parolası yok.")}</p>
      )}
      {items.length > 0 && (
        <ul className="copy-password-list">
          {items.map((p) =>
            editing === p.id ? (
              <li key={p.id}>
                <PasswordEditor
                  initialName={p.name}
                  requireValue={false}
                  onCancel={() => setEditing(null)}
                  onSubmit={async (name, value) => {
                    const ok = await run(
                      () =>
                        engineCall("vault.password_update", {
                          id: p.id,
                          name: name !== p.name ? name : undefined,
                          value: value || undefined,
                        }),
                      t("Parola güncellendi."),
                    );
                    if (ok) {
                      setEditing(null);
                      const { [p.id]: _gone, ...rest } = shown;
                      setShown(rest);
                    }
                  }}
                />
              </li>
            ) : (
              <li key={p.id} className="copy-password-row">
                <span className="copy-password-name">
                  <Icon name="lock" size={13} /> {p.name}
                </span>
                {shown[p.id] !== undefined && <code className="copy-password-value">{shown[p.id]}</code>}
                <span className="copy-password-actions">
                  <button type="button" className="link-btn" onClick={() => void toggleShow(p.id)}>
                    <Icon name={shown[p.id] !== undefined ? "eyeOff" : "eye"} size={13} />{" "}
                    {shown[p.id] !== undefined ? t("Gizle") : t("Göster")}
                  </button>
                  <button type="button" className="link-btn" onClick={() => void copy(p.id)}>
                    {t("Kopyala")}
                  </button>
                  <button type="button" className="link-btn" onClick={() => setEditing(p.id)}>
                    {t("Değiştir")}
                  </button>
                  <button type="button" className="link-btn danger" onClick={() => void remove(p)}>
                    {t("Sil")}
                  </button>
                </span>
              </li>
            ),
          )}
        </ul>
      )}
      {adding ? (
        <PasswordEditor
          initialName=""
          requireValue
          onCancel={() => setAdding(false)}
          onSubmit={async (name, value) => {
            const ok = await run(() => engineCall("vault.password_add", { name, value }), t("Parola kaydedildi."));
            if (ok) setAdding(false);
          }}
        />
      ) : (
        <button type="button" className="link-btn" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> {t("Parola ekle")}
        </button>
      )}
      {note && <p className="hint">{note}</p>}
      {error && <p className="field-error">{t(error)}</p>}
    </div>
  );
}

function PasswordEditor({
  initialName,
  requireValue,
  onSubmit,
  onCancel,
}: {
  initialName: string;
  /** Yeni kayıtta parola zorunlu; düzenlemede boş bırakılırsa parola değişmez. */
  requireValue: boolean;
  onSubmit: (name: string, value: string) => Promise<void>;
  onCancel: () => void;
}) {
  const t = useT();
  const [name, setName] = useState(initialName);
  const [value, setValue] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const tooShort = value.length > 0 && value.length < MIN_COPY_PASSWORD;
  const ok = name.trim().length > 0 && !tooShort && (!requireValue || value.length >= MIN_COPY_PASSWORD);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    try {
      await onSubmit(name.trim(), value);
    } finally {
      setBusy(false);
      setValue("");
    }
  }

  return (
    <form className="vault-form copy-password-editor" onSubmit={submit}>
      <div className="vault-row">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("Ad (ör. Muhasebe)")}
          aria-label={t("Parolanın adı")}
          maxLength={60}
        />
        <span className="password-field">
          <input
            type={show ? "text" : "password"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={requireValue ? t("En az {n} karakter", { n: MIN_COPY_PASSWORD }) : t("Değişmeyecekse boş bırakın")}
            autoComplete="new-password"
            aria-label={t("Kopyanın parolası")}
          />
          <button
            className="icon-btn"
            type="button"
            aria-label={show ? t("Parolayı gizle") : t("Parolayı göster")}
            onClick={() => setShow(!show)}
          >
            <Icon name={show ? "eyeOff" : "eye"} size={15} />
          </button>
        </span>
      </div>
      {tooShort && <p className="field-error">{t("Parola en az {n} karakter olmalı.", { n: MIN_COPY_PASSWORD })}</p>}
      <div className="vault-row">
        <button className="btn primary" disabled={!ok || busy}>
          {busy ? t("Kaydediliyor…") : t("Kaydet")}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          {t("Vazgeç")}
        </button>
      </div>
    </form>
  );
}
