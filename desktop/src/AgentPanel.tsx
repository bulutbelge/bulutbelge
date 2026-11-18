import { open } from "@tauri-apps/plugin-dialog";
import { useEffect, useState } from "react";
import { engineCall } from "./engine";
import { Profile } from "./settings";
import { useT } from "./i18n";
import { Icon, Switch } from "./ui";

interface AgentSettings {
  folders: string[];
  allow_write: boolean;
  allow_without_terms: boolean;
  profile: string | null;
}

/**
 * Ajan erişimi (TAKIP 1.37): yapay zekâ ajanının komut satırıyla hangi klasörlerde çalışabileceği. Ajan okuma
 * sonucunu yalnızca maskeli görür; yazma ayrıca açılmadıkça yapılmaz ve her zaman yeni dosyaya yazar. Değişiklik
 * hemen kaydedilir (kural takımlarının Kaydet düğmesinden bağımsız).
 */
export function AgentPanel({ profiles, vaultExists }: { profiles: Profile[]; vaultExists: boolean }) {
  const t = useT();
  const [cfg, setCfg] = useState<AgentSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    engineCall<AgentSettings>("agent.get").then(setCfg).catch((e) => setError(String(e)));
  }, []);

  async function update(patch: Partial<AgentSettings>) {
    if (!cfg) return;
    try {
      setCfg(await engineCall<AgentSettings>("agent.save", { ...cfg, ...patch }));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  async function addFolder() {
    const path = await open({ multiple: false, directory: true });
    if (typeof path === "string" && cfg && !cfg.folders.includes(path)) update({ folders: [...cfg.folders, path] });
  }

  async function copyGuide() {
    try {
      const { prompt } = await engineCall<{ prompt: string }>("agent.guide");
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setError(null);
      setTimeout(() => setCopied(false), 3000);
    } catch (e) {
      setError(String(e));
    }
  }

  if (!cfg) return error ? <p className="field-error">{t(error)}</p> : null;
  return (
    <div className="agent-panel">
      {error && <p className="field-error">{t(error)}</p>}
      {cfg.folders.length === 0 ? (
        <p className="hint">{t("Henüz izinli klasör yok; ajan komutu hiçbir dosyayı okumaz.")}</p>
      ) : (
        <div className="allow-list">
          <ul>
            {cfg.folders.map((f) => (
              <li key={f}>
                <Icon name="folder" size={14} />
                <span className="mono">{f}</span>
                <span />
                <button className="link-btn subtle" onClick={() => update({ folders: cfg.folders.filter((x) => x !== f) })}>
                  {t("Kaldır")}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <button className="btn small" onClick={addFolder}>
        <Icon name="plus" size={14} /> {t("Klasör ekle")}
      </button>

      <div className="agent-row">
        <Switch checked={cfg.allow_write} onChange={(v) => update({ allow_write: v })} label={t("Ajan maskeli kopya yazabilsin")} />
        <span>
          <b>{t("Maskeli kopya yazabilsin")}</b>
          <small>{t("Her zaman yeni dosyaya yazılır; var olan dosyanın üzerine yazılmaz, kaynak belgeye dokunulmaz.")}</small>
        </span>
      </div>
      {vaultExists && (
        <div className="agent-row">
          <Switch
            checked={cfg.allow_without_terms}
            onChange={(v) => update({ allow_without_terms: v })}
            label={t("Özel ifadeler olmadan çalışabilsin")}
          />
          <span>
            <b>{t("Özel ifadeler olmadan çalışabilsin")}</b>
            <small>
              {t("Ajan komutu şifreli kasayı açamaz; kasadaki kişi, müşteri ve proje adları ajan çıktısında maskelenmez. Bu kapalıyken ajan hiç çalışmaz. Takma ad yöntemi kullanan kural takımı ajanla kullanılamaz.")}
            </small>
          </span>
        </div>
      )}
      <label className="agent-row">
        <span>
          <b>{t("Ajanın kural takımı")}</b>
          <small>{t("Ajan komutta başka bir takım seçmezse bu kullanılır.")}</small>
        </span>
        <select value={cfg.profile ?? ""} onChange={(e) => update({ profile: e.target.value || null })}>
          <option value="">{t("Şu an kullanılan")}</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {t(p.name)}
            </option>
          ))}
        </select>
      </label>
      <div className="agent-row">
        <button className="btn small" onClick={copyGuide}>
          <Icon name="copy" size={14} /> {t("Ajan yönergesini kopyala")}
        </button>
        <span>
          <small>
            {copied
              ? t("Kopyalandı. Ajanın talimat dosyasına (CLAUDE.md, AGENTS.md) yapıştırın.")
              : t("Ajana BulutBelge'yi nasıl kullanacağını anlatan hazır metni panoya alır.")}
          </small>
        </span>
      </div>
      <p className="hint">
        {t("Komut ve ajana verilecek hazır yönerge:")} <code>bulutbelge kilavuz</code> · <code>bulutbelge.com/ajan.html</code>.{" "}
        {t("Ajanın her çağrısı işlem günlüğüne “Ajan” olarak yazılır.")}
      </p>
    </div>
  );
}
