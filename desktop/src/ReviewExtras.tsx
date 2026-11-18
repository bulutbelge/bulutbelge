import { useState } from "react";
import { engineCall, PdfFinding } from "./engine";
import { t, useT } from "./i18n";
import { Icon } from "./ui";

/** Motorda doğrulanamayan bulguların güven değeri (detect.LOW). */
export const UNCERTAIN = "dusuk";

/**
 * Dolaylı tanımlayıcılar. KVKK'nın anonimleştirme rehberine göre ad ve TC gibi doğrudan bilgiler
 * maskelense de, bunların birkaçı birlikte açık kalırsa kişi yeniden tanınabilir.
 */
const QUASI: Record<string, string> = {
  dogum_tarihi: "doğum tarihi",
  adres: "adres",
  plaka: "araç plakası",
  ip: "IP adresi",
};

/**
 * Kısmi gösterim: değerin bir parçası kopyada kalır. KVKK rehberine göre kısmi maskeleme, parçalar
 * birleşince kişiyi yeniden tanıtabilir. Kaba genelleştirmeler (yalnızca il, on yıllık aralık,
 * yaş aralığı) ve banka/kart son 4 hanesi tek başına kişiyi daraltmadığı için sayılmaz.
 */
const PARTIAL: Record<string, string> = {
  son4: "son 4 hanesi",
  il_ilce: "il ve ilçesi",
  mahalle: "mahallesi",
  yil: "doğum yılı",
  alan_adi: "e-posta alan adı",
  plaka_il: "plaka il kodu",
  bas_harf: "baş harfleri",
};
const PARTIAL_IGNORED_TYPES = new Set(["iban", "kredi_karti", "tutar"]);
const SHORT_NAME: Record<string, string> = {
  tc_kimlik: "TC'nin",
  vkn: "vergi numarasının",
  telefon: "telefonun",
  pasaport: "pasaportun",
  ehliyet: "ehliyetin",
  sgk: "SGK numarasının",
  musteri_no: "müşteri numarasının",
  kisi_adi: "adın",
  adres: "adresin",
  eposta: "",
  plaka: "",
  dogum_tarihi: "",
};

/** Bulgunun kopyada kısmen görünen parçasının adı ("TC'nin son 4 hanesi"); kısmi değilse null. */
function partialClue(f: PdfFinding, method: string): string | null {
  const part = PARTIAL[method];
  if (!part || PARTIAL_IGNORED_TYPES.has(f.type)) return null;
  const owner = SHORT_NAME[f.type];
  if (method === "son4" || method === "bas_harf") return `${owner ? t(owner) : t(f.type_label)} ${t(part)}`.trim();
  return t(part);
}

const MAX_LEARN = 20;

/** Yalnızca kuruma ait olabilecek değerler için "bir daha maskeleme" önerilir; kimlik ve kart numarası, doğum tarihi için asla. */
const NEVER_LEARN = new Set(["tc_kimlik", "kredi_karti", "pasaport", "ehliyet", "sgk", "dogum_tarihi"]);

export function canLearn(f: PdfFinding): boolean {
  return f.kind === "metin" && !!f.value && !NEVER_LEARN.has(f.type);
}

/**
 * Sonuç ekranında kartların altı: emin olamadıklarımız, tanınabilirlik uyarısı ve
 * "bunlar bir daha hiç maskelenmesin mi?" önerisi. Üçü de yalnızca gerektiğinde görünür.
 */
export function ReviewExtras({
  unsure,
  sure,
  excluded,
  onToggle,
  onSetMany,
  lastOff,
  onClearLastOff,
  onError,
  methodOf,
  onBlackout,
  unsureOpen,
  onToggleUnsureOpen,
}: {
  unsure: PdfFinding[];
  sure: PdfFinding[];
  excluded: Set<string>;
  onToggle: (id: string) => void;
  onSetMany: (items: PdfFinding[], hide: boolean) => void;
  lastOff: PdfFinding[];
  onClearLastOff: () => void;
  onError: (message: string) => void;
  methodOf: (type: string) => string;
  /** Kısmen gösterilen türleri bu belgede tamamen karart (verilmezse yalnızca uyarılır). */
  onBlackout?: (types: string[]) => void;
  unsureOpen?: boolean;
  onToggleUnsureOpen?: () => void;
}) {
  return (
    <>
      {unsure.length > 0 && (
        <Unsure
          items={unsure}
          excluded={excluded}
          onToggle={onToggle}
          onSetMany={onSetMany}
          isOpen={unsureOpen}
          onToggleOpen={onToggleUnsureOpen}
        />
      )}
      <RiskNote sure={sure} excluded={excluded} onSetMany={onSetMany} methodOf={methodOf} onBlackout={onBlackout} />
      <LearnBar items={lastOff} onDone={onClearLastOff} onError={onError} />
    </>
  );
}

function Unsure({
  items,
  excluded,
  onToggle,
  onSetMany,
  isOpen,
  onToggleOpen,
}: {
  items: PdfFinding[];
  excluded: Set<string>;
  onToggle: (id: string) => void;
  onSetMany: (items: PdfFinding[], hide: boolean) => void;
  isOpen?: boolean;
  onToggleOpen?: () => void;
}) {
  const t = useT();
  const [localOpen, setLocalOpen] = useState(false);
  const open = isOpen !== undefined ? isOpen : localOpen;
  const toggle = onToggleOpen ?? (() => setLocalOpen((v) => !v));
  const hidden = items.filter((f) => !excluded.has(f.id)).length;

  return (
    <div className={["unsure", open ? "open" : "collapsed"].join(" ")} role="region" aria-label={t("Emin olamadıklarımız")}>
      <div
        className="unsure-head"
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggle();
          }
        }}
        aria-expanded={open}
        title={open ? t("Detayları kapat") : t("Emin olamadıklarımızı incele")}
      >
        <span className="unsure-icon">
          <Icon name="question" size={14} />
        </span>
        <div className="unsure-title-box">
          <b>{t("Emin olamadıklarımız ({n})", { n: items.length })}</b>
          <small>
            {hidden > 0 ? t("{n} maskelenecek · {m} açık", { n: hidden, m: items.length - hidden }) : t("Doğrulanamayan veri adayları")}
          </small>
        </div>
        <span className="unsure-toggle-trigger">
          {open ? t("Kapat") : t("İncele")} <Icon name="chevron" size={13} />
        </span>
      </div>

      {open && (
        <div className="unsure-body">
          <div className="unsure-subbar">
            <span>{t("Kişisel bilgiye benziyor ancak otomatik doğrulanamadı. İnceleyip maskeleyebilirsiniz.")}</span>
            {items.length > 1 && (
              <button
                type="button"
                className="link-btn unsure-bulk-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onSetMany(items, hidden < items.length);
                }}
              >
                {hidden < items.length ? t("Tümünü maskele") : t("Hiçbirini maskeleme")}
              </button>
            )}
          </div>
          <ul>
            {items.map((f) => {
              const on = !excluded.has(f.id);
              return (
                <li key={f.id} className={on ? "on" : undefined}>
                  <div className="unsure-item-left">
                    <code title={f.value}>{f.value}</code>
                    <span className="unsure-why">
                      {t(f.type_label)}
                      {f.source && ` · ${t(f.source)}`}
                    </span>
                  </div>
                  <button
                    type="button"
                    className={on ? "btn small primary unsure-item-btn" : "btn small unsure-item-btn"}
                    aria-pressed={on}
                    onClick={() => onToggle(f.id)}
                  >
                    {on ? (
                      <>
                        <Icon name="check" size={12} /> {t("Maskelenecek")}
                      </>
                    ) : (
                      t("Maskele")
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function RiskNote({
  sure,
  excluded,
  onSetMany,
  methodOf,
  onBlackout,
}: {
  sure: PdfFinding[];
  excluded: Set<string>;
  onSetMany: (items: PdfFinding[], hide: boolean) => void;
  methodOf: (type: string) => string;
  onBlackout?: (types: string[]) => void;
}) {
  const t = useT();
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  // Açık kalan dolaylı tanımlayıcılar
  const open = sure.filter((f) => f.type in QUASI && excluded.has(f.id));
  const openTypes = [...new Set(open.map((f) => f.type))].sort();
  // Maskelenen ama bir parçası kopyada kalan bilgiler
  const partial = new Map<string, string>();
  for (const f of sure) {
    if (excluded.has(f.id)) continue;
    const clue = partialClue(f, methodOf(f.type));
    if (clue) partial.set(f.type, clue);
  }
  const partialTypes = [...partial.keys()].sort();
  const clues = [...openTypes.map((ty) => t(QUASI[ty])), ...partialTypes.map((ty) => partial.get(ty)!)];
  const show = openTypes.length >= 2 || (partialTypes.length > 0 && clues.length >= 3);
  const key = [...openTypes, "|", ...partialTypes].join(",");
  if (!show || dismissed === key) return null;

  const list =
    clues.length === 2
      ? t("{a} ve {b}", { a: clues[0], b: clues[1] })
      : t("{list} ve {last}", { list: clues.slice(0, -1).join(", "), last: clues[clues.length - 1] });
  const canFix = open.length > 0 || (partialTypes.length > 0 && !!onBlackout);
  return (
    <div className={["risk-note", isOpen ? "open" : "collapsed"].join(" ")} role="status">
      <div
        className="risk-head"
        onClick={() => setIsOpen((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setIsOpen((v) => !v);
          }
        }}
        aria-expanded={isOpen}
        title={isOpen ? t("Uyarı detaylarını kapat") : t("Uyarı detaylarını aç")}
      >
        <span className="risk-icon">
          <Icon name="alert" size={16} />
        </span>
        <div className="risk-title-box">
          <b>{t("Kişi yine tanınabilir")}</b>
          {!isOpen && <small>{t("KVKK dolaylı veri uyarısı")}</small>}
        </div>
        <span className="risk-toggle-trigger">
          {isOpen ? t("Kapat") : t("Uyarıyı Aç")} <Icon name="chevron" size={13} />
        </span>
      </div>

      {isOpen && (
        <div className="risk-body">
          <span className="risk-desc">
            {partialTypes.length > 0
              ? t("Kopyada açık ya da kısmen görünen {list} birleşince, adı maskelense de kişi tanınabilir. KVKK'ya göre kısmi maskeleme tek başına yetmeyebilir.", { list })
              : t("Açık kalan {list} bir araya gelince, adı maskelense de kişi tanınabilir. KVKK'ya göre dolaylı bilgiler de birlikte değerlendirilmelidir.", { list })}
            {partialTypes.length > 0 && !onBlackout && t(" Maskeleme biçimini Ayarlar'dan değiştirebilirsiniz.")}
          </span>
          <div className="risk-actions">
            {canFix && (
              <button
                type="button"
                className="btn small primary"
                onClick={() => {
                  if (open.length) onSetMany(open, true);
                  if (partialTypes.length && onBlackout) onBlackout(partialTypes);
                }}
              >
                {partialTypes.length && onBlackout ? t("Bunları tamamen maskele") : t("Bunları da maskele")}
              </button>
            )}
            <button type="button" className="link-btn subtle" onClick={() => setDismissed(key)}>
              {t("Böyle kalsın")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function LearnBar({ items, onDone, onError }: { items: PdfFinding[]; onDone: () => void; onError: (m: string) => void }) {
  const t = useT();
  const [state, setState] = useState<"ask" | "saving" | "saved">("ask");
  const [savedCount, setSavedCount] = useState(0);
  const values = [...new Set(items.map((f) => f.value.trim()).filter(Boolean))];

  if (state === "saved") {
    return (
      <div className="learn-bar ok" role="status">
        <Icon name="check" size={16} />
        <span>
          {t("Tamam, {n} değer sonraki belgelerde artık bulunmayacak. Geri almak için: Ayarlar › Hiç maskelenmeyenler.", { n: savedCount })}
        </span>
        <button
          className="icon-btn"
          aria-label={t("Kapat")}
          onClick={() => {
            setState("ask");
            onDone();
          }}
        >
          <Icon name="x" size={14} />
        </button>
      </div>
    );
  }
  if (values.length === 0 || values.length > MAX_LEARN) return null;

  async function remember() {
    setState("saving");
    try {
      const byType = new Map<string, string[]>();
      for (const f of items) byType.set(f.type, [...(byType.get(f.type) ?? []), f.value]);
      for (const [type, vals] of byType) await engineCall("allow.add", { values: vals, type });
      setSavedCount(values.length);
      setState("saved");
    } catch (e) {
      setState("ask");
      onError(String(e));
    }
  }

  const sample = values.length === 1 ? `“${values[0]}”` : t("{n} değer", { n: values.length });
  return (
    <div className="learn-bar" role="status">
      <Icon name="ban" size={16} />
      <span>
        {values.length === 1
          ? t("{sample} açık kalacak. Bu değer başka belgelerde de hiç maskelenmesin mi?", { sample })
          : t("{sample} açık kalacak. Bu değerler başka belgelerde de hiç maskelenmesin mi?", { sample })}
        <small>{t(" Örneğin şirketin genel telefonu ya da kurum adı.")}</small>
      </span>
      <button className="btn small" disabled={state === "saving"} onClick={remember}>
        {t("Bir daha maskeleme")}
      </button>
      <button className="icon-btn" aria-label={t("Yalnızca bu belgede")} title={t("Yalnızca bu belgede")} onClick={onDone}>
        <Icon name="x" size={14} />
      </button>
    </div>
  );
}
