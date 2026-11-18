import { useEffect, useRef, useState } from "react";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { engineCall, MaskResult, Rules } from "./engine";
import { useT } from "./i18n";
import { Icon } from "./ui";

export interface BatchPlan {
  target_dir: string;
  files: { source: string; target: string; relative: string; size: number }[];
}

type FileState =
  | { kind: "bekliyor" }
  | { kind: "isleniyor" }
  | { kind: "tamam"; masked: number; target: string; warnings: string[] }
  | { kind: "hata"; message: string };

/**
 * Klasörle toplu işlem. Dosyalar sırayla, aynı profille maskelenir; her dosya
 * motorda ayrı bir istek olduğu için işlem istenince durdurulabilir. Bulgular tek
 * tek gözden geçirilmez: yeri bulunamayan bulgusu olan dosya atlanır (şüphede reddet).
 */
export function BatchMain({ plan, rules, onRunningChange }: { plan: BatchPlan | null; rules: Rules | null; onRunningChange: (running: boolean) => void }) {
  const t = useT();
  const [states, setStates] = useState<FileState[]>([]);
  const [running, setRunning] = useState(false);
  const stopRef = useRef(false);

  // Plan ya da kurallar değişince sonuçlar geçersiz.
  useEffect(() => {
    setStates(plan ? plan.files.map(() => ({ kind: "bekliyor" })) : []);
  }, [plan, rules]);

  useEffect(() => onRunningChange(running), [running, onRunningChange]);

  async function run() {
    if (!plan || !rules) return;
    stopRef.current = false;
    setRunning(true);
    const next: FileState[] = plan.files.map(() => ({ kind: "bekliyor" }));
    setStates([...next]);
    for (let i = 0; i < plan.files.length; i++) {
      if (stopRef.current) break;
      const f = plan.files[i];
      next[i] = { kind: "isleniyor" };
      setStates([...next]);
      try {
        const r = await engineCall<MaskResult>("doc.mask", { source: f.source, target: f.target, rules, make_dirs: true });
        next[i] = { kind: "tamam", masked: r.masked, target: r.target, warnings: r.warnings };
      } catch (e) {
        next[i] = { kind: "hata", message: String(e) };
      }
      setStates([...next]);
    }
    setRunning(false);
  }

  if (!plan) {
    return (
      <div className="empty">
        <div className="ready-doc">
          <Icon name="folder" size={36} />
          <b>{t("Klasör seçin")}</b>
          <span>{t("Klasördeki tüm belgeler (PDF, Word, Excel, PowerPoint, görsel, XML, TXT, CSV) aynı profille maskelenir; klasör yapısı hedefte korunur.")}</span>
        </div>
      </div>
    );
  }

  const done = states.filter((s) => s.kind === "tamam") as Extract<FileState, { kind: "tamam" }>[];
  const failed = states.filter((s) => s.kind === "hata").length;
  const processed = done.length + failed;
  const total = plan.files.length;
  const findings = done.reduce((n, s) => n + s.masked, 0);
  const finished = !running && processed > 0;

  return (
    <>
      <div className="main-scroll">
        <div className="banner info">
          <Icon name="alert" size={18} />
          <span>
            {t("Klasördeki her belgede, seçtiğiniz “Kime gidecek?” kurallarıyla bulunan bilgilerin hepsi maskelenir; tek tek sorulmaz.")}{" "}
            {t("Açılamayan ya da yeri bulunamayan bilgi içeren belge")} <b>{t("atlanır")}</b>{" "}
            {t("ve listede gösterilir. Emin olmadığınız belgeleri tek tek işleyin.")}
          </span>
        </div>

        <div className="stats four">
          <Stat label="Dosya" value={total} />
          <Stat label="İşlenen" value={processed} />
          <Stat label="Silinen bulgu" value={findings} accent />
          <Stat label="Atlanan" value={failed} warn={failed > 0} />
        </div>

        {(running || finished) && (
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={processed}>
            <span style={{ width: `${(processed / Math.max(total, 1)) * 100}%` }} />
          </div>
        )}

        {finished && (
          <div className={failed ? "success partial" : "success"}>
            <span className="success-icon">
              <Icon name={failed ? "alert" : "check"} size={22} />
            </span>
            <div>
              <h2>{failed ? t("{n} dosya maskelendi, {m} dosya atlandı", { n: done.length, m: failed }) : t("{n} dosya maskelendi", { n: done.length })}</h2>
              <p>{t("Maskeli kopyalar klasör yapısı korunarak yazıldı; orijinallere dokunulmadı.")}</p>
              <code className="path-line">{plan.target_dir}</code>
            </div>
            <button className="btn" onClick={() => revealItemInDir(plan.target_dir)}>
              <Icon name="folder" /> {t("Klasörde göster")}
            </button>
          </div>
        )}

        {total === 0 ? (
          <div className="empty-inline">
            <Icon name="file" size={28} />
            <p>{t("Bu klasörde desteklenen belge yok.")}</p>
          </div>
        ) : (
          <table className="findings files">
            <thead>
              <tr>
                <th>{t("Dosya")}</th>
                <th className="col-size">{t("Boyut")}</th>
                <th className="col-status">{t("Durum")}</th>
              </tr>
            </thead>
            <tbody>
              {plan.files.map((f, i) => {
                const s = states[i] ?? { kind: "bekliyor" };
                return (
                  <tr key={f.source} className={s.kind === "isleniyor" ? "hover" : undefined}>
                    <td>
                      <span className="type-name">
                        <Icon name="file" size={14} />
                        <span className="mono">{f.relative}</span>
                      </span>
                    </td>
                    <td className="col-size">{formatSize(f.size)}</td>
                    <td className="col-status">
                      <FileStatus state={s} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <footer className="actionbar">
        <span className="status">
          {running
            ? t("İşleniyor: {n} / {total}", { n: processed + 1, total })
            : finished
              ? t("Tamamlandı.")
              : t("{total} belge maskelenecek → {dir}", { total, dir: plan.target_dir })}
        </span>
        {running ? (
          <button className="btn" onClick={() => (stopRef.current = true)}>
            <Icon name="stop" /> {t("Durdur")}
          </button>
        ) : (
          <button className="btn primary" disabled={!rules || total === 0} onClick={run}>
            <Icon name="shield" /> {finished ? t("Yeniden çalıştır") : t("Tümünü maskele")}
          </button>
        )}
      </footer>
    </>
  );
}

function FileStatus({ state }: { state: FileState }) {
  const t = useT();
  switch (state.kind) {
    case "bekliyor":
      return <span className="muted">{t("Bekliyor")}</span>;
    case "isleniyor":
      return <span className="pill conf-orta">{t("İşleniyor…")}</span>;
    case "tamam":
      return (
        <span className="pill conf-yuksek" title={state.warnings.map((w) => t(w)).join("\n") || state.target}>
          <Icon name="check" size={12} /> {state.warnings.length ? t("{n} bulgu · uyarı", { n: state.masked }) : t("{n} bulgu", { n: state.masked })}
        </span>
      );
    case "hata":
      return (
        <span className="file-error">
          <span className="pill warn">
            <Icon name="alert" size={12} /> {t("Atlandı")}
          </span>
          <small>{t(state.message)}</small>
        </span>
      );
  }
}

function Stat({ label, value, accent, warn }: { label: string; value: number; accent?: boolean; warn?: boolean }) {
  const t = useT();
  return (
    <div className={accent ? "stat accent" : warn ? "stat warn" : "stat"}>
      <span>{t(label)}</span>
      <b>{value}</b>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
