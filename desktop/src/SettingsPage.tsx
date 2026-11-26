import { useMemo, useState } from "react";
import { DataTypeInfo, engineCall } from "./engine";
import { AgentPanel } from "./AgentPanel";
import { AllowPanel } from "./AllowPanel";
import { HistoryPanel } from "./HistoryPanel";
import { PatternEditor, TypeList } from "./RulesPanel";
import {
  DEFAULT_PROFILE_ID,
  enabledTypeCount,
  newProfileId,
  Profile,
  SettingsData,
  Terms,
  VaultStatus,
} from "./settings";
import { denetimAcik, denetimiAyarla } from "./guncelleme";
import { HakkindaBolumu } from "./Hakkinda";
import { SorunBildirBolumu } from "./SorunBildir";
import { LANGUAGES, useLang, useT } from "./i18n";
import { open, save as saveDialog } from "@tauri-apps/plugin-dialog";
import { ThemeChoice } from "./theme";
import { ChipInput, Icon } from "./ui";
import type { ColumnRule } from "./engine";

// Sütun kuralında kullanılamayan türler (çekirdekteki COLUMN_EXCLUDED ile aynı).
const COLUMN_EXCLUDED = ["yuz", "imza", "elle", "ozel_ifade", "ozel_kalip"];
import { DeleteVault, PasswordForm, PseudonymPanel, UnlockForm } from "./Vault";
import { CopyPasswords } from "./CopyPasswords";

/**
 * Ayarlar: Sade 2 sütunlu düzen.
 * - Sol: Görünüm teması (en üstte), kural takımları, dil ve güncelleme
 * - Sağ: Seçili kural takımının maskeleme kuralları (ve altta kapalı duran gelişmiş ayarlar)
 */
export function SettingsPage({
  dataTypes,
  saved,
  terms,
  initialProfileId,
  onSaved,
  onVault,
}: {
  dataTypes: DataTypeInfo[];
  saved: SettingsData;
  terms: Terms | null;
  initialProfileId?: string;
  onSaved: (s: SettingsData, terms: Terms | null) => void;
  onVault: (status: VaultStatus, terms: Terms | null) => void;
  onBack?: () => void;
}) {
  const [profiles, setProfiles] = useState<Profile[]>(saved.profiles);
  const [active, setActive] = useState(saved.active);
  const [draftTerms, setDraftTerms] = useState<Terms | null>(terms);
  const [selected, setSelected] = useState(initialProfileId || saved.active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [kaydedildi, setKaydedildi] = useState(false);
  const [vaultMode, setVaultMode] = useState<"idle" | "change" | "forgot">("idle");
  const t = useT();
  const [lang, setLang] = useLang();
  const [guncellemeDenetle, setGuncellemeDenetle] = useState(denetimAcik);

  const vault = saved.vault;
  const profile = profiles.find((p) => p.id === selected) ?? profiles[0];
  const dirty =
    JSON.stringify([profiles, active]) !== JSON.stringify([saved.profiles, saved.active]) ||
    JSON.stringify(draftTerms) !== JSON.stringify(terms);
  const typeLabels = useMemo(() => Object.fromEntries(dataTypes.map((d) => [d.key, d.label])), [dataTypes]);

  function update(patch: Partial<Profile>) {
    setProfiles(profiles.map((p) => (p.id === profile.id ? { ...p, ...patch } : p)));
  }

  function updateColumnRule(i: number, patch: Partial<ColumnRule>) {
    update({ column_rules: (profile.column_rules ?? []).map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  }

  function addProfile(from?: Profile) {
    const name = from ? t("{ad} (kopya)", { ad: from.name }) : t("Yeni kural takımı");
    const id = newProfileId(name, profiles.map((p) => p.id));
    const base = from ?? profiles.find((p) => p.id === DEFAULT_PROFILE_ID)!;
    setProfiles([...profiles, { ...structuredClone(base), id, name }]);
    if (draftTerms && from) setDraftTerms({ ...draftTerms, [id]: [...(draftTerms[from.id] ?? [])] });
    setSelected(id);
  }

  function removeProfile(id: string) {
    setProfiles(profiles.filter((p) => p.id !== id));
    if (draftTerms) {
      const { [id]: _, ...rest } = draftTerms;
      setDraftTerms(rest);
    }
    if (active === id) setActive(DEFAULT_PROFILE_ID);
    setSelected(DEFAULT_PROFILE_ID);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const s = await engineCall<{ profiles: Profile[]; active: string }>("settings.save", { profiles, active });
      let savedTerms = terms;
      if (draftTerms && vault.unlocked) {
        savedTerms = (await engineCall<{ terms: Terms }>("vault.save", { terms: draftTerms })).terms;
        setDraftTerms(savedTerms);
      }
      setProfiles(s.profiles);
      onSaved({ ...s, vault }, savedTerms);
      setFlash(t("Kaydedildi"));
      setKaydedildi(true);
      setTimeout(() => setKaydedildi(false), 1800);
      setTimeout(() => setFlash(null), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function exportProfiles() {
    setError(null);
    try {
      const path = await saveDialog({ filters: [{ name: "JSON", extensions: ["json"] }], defaultPath: "kural-takimlari.json" });
      if (!path) return;
      const r = await engineCall<{ target: string; count: number }>("profiles.export", { target: path });
      setFlash(t("{n} kural takımı dışa aktarıldı", { n: r.count }));
      setTimeout(() => setFlash(null), 3000);
    } catch (e) {
      setError(String(e));
    }
  }

  async function importProfiles() {
    setError(null);
    if (dirty) {
      setError("İçe aktarmadan önce değişiklikleri kaydedin.");
      return;
    }
    try {
      const path = await open({ multiple: false, directory: false, filters: [{ name: "JSON", extensions: ["json"] }] });
      if (typeof path !== "string") return;
      const r = await engineCall<{ profiles: Profile[]; active: string; imported: string[] }>("profiles.import", { source: path });
      setProfiles(r.profiles);
      onSaved({ profiles: r.profiles, active: r.active, vault }, terms);
      if (r.imported[0]) setSelected(r.imported[0]);
      setFlash(t("{n} kural takımı içe aktarıldı", { n: r.imported.length }));
      setTimeout(() => setFlash(null), 3000);
    } catch (e) {
      setError(String(e));
    }
  }

  function revert() {
    setProfiles(saved.profiles);
    setActive(saved.active);
    setDraftTerms(terms);
    setError(null);
    if (!saved.profiles.some((p) => p.id === selected)) setSelected(saved.active);
  }

  return (
    <div className="settings-page-clean">
      <aside className="profile-list">
        <div className="settings-side-section settings-theme-section">
          <h2>{t("Görünüm")}</h2>
          <ThemeChoice />
        </div>

        <div className="settings-side-section">
          <h2>{t("Kural Takımları")}</h2>
          <p className="hint">
            {t("Belgede hangi bilgilerin maskeleneceğini ve nasıl yazılacağını belirler.")}
          </p>
          <ul>
            {profiles.map((p) => {
              const isCurrent = p.id === profile.id;
              const isActive = p.id === active;
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    className={isCurrent ? "profile-item on" : "profile-item"}
                    onClick={() => setSelected(p.id)}
                  >
                    <div className="profile-item-top">
                      <b>{t(p.name)}</b>
                      {isActive && <span className="profile-active-dot">{t("Aktif")}</span>}
                    </div>
                    <small>{t("{n} bilgi türü maskelenir", { n: enabledTypeCount(p) })}</small>
                  </button>
                </li>
              );
            })}
          </ul>
          <button type="button" className="btn small full" onClick={() => addProfile()}>
            <Icon name="plus" size={13} /> {t("Yeni kural takımı")}
          </button>
          <button type="button" className="btn small full" onClick={() => void importProfiles()}>
            {t("İçe aktar")}
          </button>
          <button type="button" className="btn small full" onClick={() => void exportProfiles()}>
            {t("Dışa aktar")}
          </button>
        </div>

        <div className="settings-side-section">
          <h2>{t("Dil")}</h2>
          <select
            className="lang-select"
            aria-label={t("Dil")}
            value={lang}
            onChange={(e) => setLang(e.target.value as typeof lang)}
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
          </select>
        </div>

        <div className="settings-side-section">
          <h2>{t("Güncellemeler")}</h2>
          <label className="check-row">
            <input
              type="checkbox"
              checked={guncellemeDenetle}
              onChange={(e) => {
                denetimiAyarla(e.target.checked);
                setGuncellemeDenetle(e.target.checked);
              }}
            />
            {t("Açılışta yeni sürümü denetle")}
          </label>
          <p className="hint">
            {t("Varsayılan olarak kapalıdır. Açarsanız, internet varsa bulutbelge.com'daki sürüm bilgisine bakılır. Belge, kural ya da kişisel veri gönderilmez.")}
          </p>
        </div>

        <HakkindaBolumu />
        <SorunBildirBolumu />
      </aside>

      <div className="settings-main">
        <div className="settings-scroll-clean">
          {error && (
            <div className="banner err" role="alert">
              <Icon name="alert" size={18} />
              <span>{t(error)}</span>
            </div>
          )}

          <div className="profile-head-clean">
            <input
              className="profile-name"
              aria-label={t("Kural takımının adı")}
              value={profile.name}
              onChange={(e) => update({ name: e.target.value })}
            />
            <div className="profile-actions">
              {profile.id !== active ? (
                <button type="button" className="btn primary small" onClick={() => setActive(profile.id)}>
                  <Icon name="check" size={13} /> {t("Bunu kullan")}
                </button>
              ) : (
                <span className="pill conf-yuksek">
                  <Icon name="check" size={12} /> {t("Şu an kullanılıyor")}
                </span>
              )}
              <button
                type="button"
                className="icon-btn"
                title={t("Kopyasını oluştur")}
                aria-label={t("Kural takımının kopyasını oluştur")}
                onClick={() => addProfile(profile)}
              >
                <Icon name="copy" />
              </button>
              {profile.id !== DEFAULT_PROFILE_ID && (
                <button
                  type="button"
                  className="icon-btn"
                  title={t("Sil")}
                  aria-label={t("Kural takımını sil")}
                  onClick={() => removeProfile(profile.id)}
                >
                  <Icon name="trash" />
                </button>
              )}
            </div>
          </div>

          <section className="card">
            <h3>{t("Hangi bilgiler maskelensin, nasıl?")}</h3>
            <p className="hint">
              {t("Açık olanlar ana ekranda maskelenecek olarak gelir. Kapalı olanlar yine bulunur ama “açık kalacak” diye gelir. Her satırda belgeye ne yazılacağını seçin.")}
            </p>
              <TypeList dataTypes={dataTypes} value={profile.types} onChange={(types) => update({ types })} />
          </section>

          <details className="settings-advanced-box">
            <summary>
              <Icon name="settings" size={15} />
              <span>{t("Gelişmiş Ayarlar (Beyaz Liste, Özel İfadeler, İmza ve İstisnalar)")}</span>
              <Icon name="chevron" size={14} />
            </summary>
            <div className="settings-advanced-body">
              <section className="card">
                <h3>{t("Beyaz liste")}</h3>
                <p className="hint">{t("Bulunsa da maskelenmeyecek değerler: kurum adı, genel telefon, kurum e-postası.")}</p>
                  <ChipInput
                    values={profile.whitelist}
                    onChange={(whitelist) => update({ whitelist })}
                    placeholder={t("ör. info@kurum.com.tr")}
                  />
              </section>

              <section className="card">
                <h3>{t("Kurum sözlüğü")}</h3>
                <p className="hint">{t("Kurum adları ve genel unvanlar (ör. Sağlık Bakanlığı). Kişi adı veya adres diye bulunsa bile bu ifadelerin içindeyse maskelenmez.")}</p>
                  <ChipInput
                    values={profile.institutions ?? []}
                    onChange={(institutions) => update({ institutions })}
                    placeholder={t("ör. Örnek Belediyesi")}
                  />
              </section>

              <section className="card">
                <h3>{t("Sütun kuralları")}</h3>
                <p className="hint">{t("Excel ve CSV'de başlığı eşleşen sütun, içeriğe bakılmadan seçilen türden maskelenir (ör. başlık: TC → T.C. kimlik no).")}</p>
                {(profile.column_rules ?? []).map((r, i) =>
                  r.action ? null : (
                    <div className="pattern-row" key={i}>
                      <input
                        placeholder={t("Sütun başlığı (ör. TC)")}
                        value={r.header}
                        onChange={(e) => updateColumnRule(i, { header: e.target.value })}
                      />
                      <select value={r.type ?? ""} onChange={(e) => updateColumnRule(i, { type: e.target.value })}>
                        <option value="">{t("Tür seçin")}</option>
                        {dataTypes.filter((d) => !COLUMN_EXCLUDED.includes(d.key)).map((d) => (
                          <option key={d.key} value={d.key}>{d.label}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label={t("Kuralı sil")}
                        onClick={() => update({ column_rules: (profile.column_rules ?? []).filter((_, j) => j !== i) })}
                      >
                        <Icon name="trash" size={15} />
                      </button>
                    </div>
                  ),
                )}
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => update({ column_rules: [...(profile.column_rules ?? []), { header: "", type: "" }] })}
                >
                  <Icon name="plus" size={14} /> {t("Kural ekle")}
                </button>
              </section>

              <section className="card">
                <h3>
                  <Icon name="lock" size={16} /> {t("Özel ifadeler")}
                </h3>
                <p className="hint">
                  {t("Kişi, müşteri ve proje adları. Bu bilgisayarda parolayla şifreli (AES-256) saklanır.")}
                </p>
                {!vault.exists ? (
                  <PasswordForm
                    mode="create"
                    onDone={(tm) => {
                      setDraftTerms(tm ?? {});
                      onVault({ exists: true, unlocked: true }, tm ?? {});
                    }}
                  />
                ) : !vault.unlocked || !draftTerms ? (
                  vaultMode === "forgot" ? (
                    <DeleteVault
                      onDeleted={(s) => {
                        setVaultMode("idle");
                        onVault(s, null);
                      }}
                      onCancel={() => setVaultMode("idle")}
                    />
                  ) : (
                    <UnlockForm
                      onUnlocked={(tm) => {
                        setDraftTerms(tm);
                        onVault({ exists: true, unlocked: true }, tm);
                      }}
                      onForgot={() => setVaultMode("forgot")}
                    />
                  )
                ) : (
                  <>
                    <ChipInput
                      values={draftTerms[profile.id] ?? []}
                      onChange={(v) => setDraftTerms({ ...draftTerms, [profile.id]: v })}
                      placeholder={t("ör. Mavi Kartal")}
                    />
                    {vaultMode === "change" ? (
                      <PasswordForm
                        mode="change"
                        onDone={() => setVaultMode("idle")}
                        onCancel={() => setVaultMode("idle")}
                      />
                    ) : (
                      <div className="vault-row">
                        <span className="pill conf-yuksek">
                          <Icon name="unlock" size={12} /> {t("Kasa açık")}
                        </span>
                        <button type="button" className="link-btn" onClick={() => setVaultMode("change")}>
                          {t("Parolayı değiştir")}
                        </button>
                        <button
                          type="button"
                          className="link-btn"
                          disabled={dirty}
                          onClick={async () => {
                            const s = await engineCall<VaultStatus>("vault.lock");
                            setDraftTerms(null);
                            onVault(s, null);
                          }}
                        >
                          {t("Kilitle")}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </section>

              <section className="card">
                <h3>
                  <Icon name="pen" size={16} /> {t("İmza ve kaşe etiketleri")}
                </h3>
                <p className="hint">{t("Bu etiketlerin yanındaki ya da altındaki görsel ve el çizimi imza sayılır.")}</p>
                  <ChipInput
                    values={profile.signature_labels}
                    onChange={(signature_labels) => update({ signature_labels })}
                    placeholder={t("ör. Yetkili")}
                  />
              </section>

              <section className="card">
                <h3>{t("Özel kalıplar")}</h3>
                <p className="hint">{t("Düzenli ifadeyle kurum içi numaralar: proje kodu, sözleşme no, personel sicili.")}</p>
                  <PatternEditor value={profile.patterns} onChange={(patterns) => update({ patterns })} />
              </section>

              <section className="card">
                <h3>
                  <Icon name="key" size={16} /> {t("Takma adlar ve Hiç maskelenmeyenler")}
                </h3>
                {vault.unlocked ? (
                  <PseudonymPanel />
                ) : (
                  <p className="hint">{t("Takma adları görmek için yukarıdan kasanın kilidini açın.")}</p>
                )}
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={profile.pseudonym_scope === "belge"}
                    onChange={(e) => update({ pseudonym_scope: e.target.checked ? "belge" : undefined })}
                  />
                  {t("Her belgede farklı takma ad ver")}
                </label>
                <p className="hint">
                  {t("Kapalıyken aynı kişi tüm belgelerde aynı takma adı alır; bu, belgelerin birbiriyle eşleştirilmesini kolaylaştırır. Takma ad anonimleştirme değildir.")}
                </p>
                <AllowPanel />
              </section>

              <section className="card">
                <h3>
                  <Icon name="lock" size={16} /> {t("Kopya parolaları")}
                </h3>
                <p className="hint">
                  {t("PDF kopyayı korumak için sık kullandığınız parolalar; kaydederken listeden seçilir. Kasada şifreli durur, yalnızca bu uygulamanın arayüzünden kullanılır (ajan komutu ve MCP kullanamaz).")}
                </p>
                {vault.unlocked ? (
                  <CopyPasswords />
                ) : (
                  <p className="hint">{t("Kopya parolalarını görmek için yukarıdan kasanın kilidini açın.")}</p>
                )}
              </section>
            </div>
          </details>

          <details className="settings-advanced-box">
            <summary>
              <Icon name="folder" size={15} />
              <span>{t("Ajan erişimi (komut satırı)")}</span>
              <Icon name="chevron" size={14} />
            </summary>
            <div className="settings-advanced-body">
              <section className="card">
                <p className="hint">
                  {t("Yapay zekâ ajanı BulutBelge'yi komut satırından yalnızca burada izin verdiğiniz klasörlerde kullanabilir. Ajan belgeleri yalnızca maskeli okur; orijinal değerleri görmez. Bu bölüm hemen kaydedilir.")}
                </p>
                <AgentPanel profiles={saved.profiles} vaultExists={vault.exists} />
              </section>
            </div>
          </details>

          <details className="settings-advanced-box">
            <summary>
              <Icon name="shield" size={15} />
              <span>{t("İşlem günlüğü")}</span>
              <Icon name="chevron" size={14} />
            </summary>
            <div className="settings-advanced-body">
              <section className="card">
                <p className="hint">
                  {t("Önizlenen, taranan, maskelenen ve dışa aktarılan her belge ile her maske kaldırma; uygulamadan ya da ajandan. Günlükte bulunan değerler ve belge içeriği yoktur, yalnızca tür bazında sayılar. Kayıtlar birbirine zincirlidir: sonradan değiştirilen ya da silinen kayıt denetimde görünür.")}
                </p>
                <HistoryPanel typeLabels={typeLabels} />
              </section>
            </div>
          </details>
        </div>

        <footer className="actionbar">
          <span className="status" key={flash ?? (dirty ? "k" : "t")}>
            {flash ?? (dirty ? t("Kaydedilmemiş değişiklikler var.") : t("Tüm değişiklikler kaydedildi."))}
          </span>
          <button type="button" className="btn" onClick={revert} disabled={!dirty || busy}>
            {t("Geri al")}
          </button>
          <button type="button" className={"btn primary" + (busy ? " is-busy" : "") + (kaydedildi && !dirty ? " kaydedildi" : "")} onClick={save} disabled={!dirty || busy}>
            <Icon name="check" /> {busy ? t("Kaydediliyor…") : kaydedildi && !dirty ? t("Kaydedildi") : t("Kaydet")}
          </button>
        </footer>
      </div>
    </div>
  );
}
