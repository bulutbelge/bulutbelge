import { CustomPattern, DataTypeInfo, TypeRule } from "./engine";
import { useT } from "./i18n";
import { Icon, IconName, MethodSample, Switch } from "./ui";

/**
 * Ayarlar'da veri türlerinin gruplanması.
 */
export const TYPE_GROUPS: { key: string; label: string; hint: string; icon: IconName; types: string[] }[] = [
  {
    key: "kisi",
    label: "Kişisel bilgiler",
    hint: "Kişiyi doğrudan ya da dolaylı tanıtan bilgiler",
    icon: "user",
    types: ["kisi_adi", "tc_kimlik", "dogum_tarihi", "pasaport", "ehliyet", "mrz"],
  },
  {
    key: "iletisim",
    label: "İletişim ve adres",
    hint: "Kişiye ulaşmayı sağlayan bilgiler",
    icon: "phone",
    types: ["telefon", "eposta", "web_sitesi", "adres"],
  },
  {
    key: "finans",
    label: "Banka ve para",
    hint: "Hesap, kart ve tutarlar",
    icon: "card",
    types: ["iban", "banka_bilgisi", "kredi_karti", "tutar"],
  },
  {
    key: "sirket",
    label: "Şirket ve kurum bilgileri",
    hint: "Unvan, vergi, sicil ve müşteri numaraları",
    icon: "idcard",
    types: ["kurum_unvani", "vkn", "vergi_dairesi", "mersis", "ticaret_sicil", "sgk", "sicil_no", "musteri_no", "ettn"],
  },
  {
    key: "gorsel",
    label: "İmza, kaşe ve görseller",
    hint: "Belgedeki imza, kaşe, fotoğraftaki yüzler ve elle seçilen alanlar",
    icon: "pen",
    types: ["imza", "yuz", "barkod_qr", "elle"],
  },
  {
    key: "teknik",
    label: "Araç ve teknik bilgiler",
    hint: "Plaka, IP adresi, IMEI, MAC adresi, şase no, GPS konumu, kullanıcı adı, unvan + kurum",
    icon: "monitor",
    types: ["plaka", "ip", "imei", "mac", "sase_no", "gps", "kullanici_adi", "unvan_kurum", "gizli_anahtar"],
  },
];

/** Veri türleri: sade kategori grupları ve tek satırda temiz yöntem seçimi. */
export function TypeList({
  dataTypes,
  value,
  onChange,
}: {
  dataTypes: DataTypeInfo[];
  value: Record<string, TypeRule>;
  onChange: (next: Record<string, TypeRule>) => void;
}) {
  const t = useT();
  const known = new Set(TYPE_GROUPS.flatMap((g) => g.types));
  const rest = dataTypes.filter((d) => !known.has(d.key)).map((d) => d.key);
  const groups = rest.length
    ? [...TYPE_GROUPS, { key: "diger", label: "Diğer", hint: "", icon: "tag" as IconName, types: rest }]
    : TYPE_GROUPS;

  return (
    <div className="type-groups">
      {groups.map((g, gi) => {
        const items = g.types
          .map((k) => dataTypes.find((d) => d.key === k))
          .filter((d): d is DataTypeInfo => !!d && !!value[d.key]);
        if (!items.length) return null;

        const toggleable = items.filter((d) => !d.always_on);
        const on = toggleable.filter((d) => value[d.key].enabled).length;

        const setAllInGroup = (enabled: boolean) => {
          const next = { ...value };
          for (const d of toggleable) next[d.key] = { ...next[d.key], enabled };
          onChange(next);
        };

        return (
          <details key={g.key} className="type-group" open={gi === 0}>
            <summary>
              <span className="type-group-icon">
                <Icon name={g.icon} size={17} />
              </span>
              <span className="type-group-text">
                <b>{t(g.label)}</b>
                {g.hint && <small>{t(g.hint)}</small>}
              </span>
              <span className={on === 0 ? "type-group-count off" : "type-group-count"}>
                {toggleable.length ? t("{on}/{n} maskelenir", { on, n: toggleable.length }) : t("her zaman")}
              </span>
              {toggleable.length > 1 && (
                <button
                  type="button"
                  className="link-btn subtle"
                  onClick={(e) => {
                    e.preventDefault();
                    setAllInGroup(on < toggleable.length);
                  }}
                >
                  {on < toggleable.length ? t("Hepsini aç") : t("Hepsini kapat")}
                </button>
              )}
              <Icon name="chevron" size={14} />
            </summary>

            <ul className="type-list">
              {items.map((d) => {
                const rule = value[d.key];
                return (
                  <li key={d.key} className={rule.enabled ? "type-row" : "type-row off"}>
                    {d.always_on ? (
                      <span className="switch-placeholder" title={t("Her zaman açık")} />
                    ) : (
                      <Switch
                        label={t(d.label)}
                        checked={rule.enabled}
                        onChange={(enabled) => onChange({ ...value, [d.key]: { ...rule, enabled } })}
                      />
                    )}
                    <span className="type-name">
                      <i className={`dot t-${d.key}`} />
                      <b>{t(d.label)}</b>
                    </span>
                    <div className="method-picker" role="radiogroup" aria-label={t("{ad} yöntemi", { ad: t(d.label) })}>
                      {d.methods.map((m) => {
                        const selected = rule.method === m.key;
                        return (
                          <button
                            key={m.key}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            disabled={!rule.enabled}
                            className={selected ? "on" : ""}
                            onClick={() => onChange({ ...value, [d.key]: { ...rule, method: m.key } })}
                          >
                            <MethodSample method={m.key} text={m.sample ?? (m.key === "etiket" ? d.tag : undefined)} />
                            <small>{t(m.label)}</small>
                          </button>
                        );
                      })}
                    </div>
                  </li>
                );
              })}
            </ul>
          </details>
        );
      })}
    </div>
  );
}

export function PatternEditor({
  value,
  onChange,
}: {
  value: CustomPattern[];
  onChange: (next: CustomPattern[]) => void;
}) {
  const t = useT();
  function set(i: number, patch: Partial<CustomPattern>) {
    onChange(value.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  }

  return (
    <div className="patterns">
      {value.map((p, i) => (
        <div className="pattern-row" key={i}>
          <input placeholder={t("Ad (ör. Proje kodu)")} value={p.name} onChange={(e) => set(i, { name: e.target.value })} />
          <input
            className="mono"
            placeholder="PRJ-\d{4}"
            value={p.pattern}
            spellCheck={false}
            onChange={(e) => set(i, { pattern: e.target.value })}
          />
          <button
            type="button"
            className="icon-btn"
            aria-label={t("Kalıbı sil")}
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            <Icon name="trash" size={15} />
          </button>
        </div>
      ))}
      <button type="button" className="link-btn" onClick={() => onChange([...value, { name: "", pattern: "" }])}>
        <Icon name="plus" size={14} /> {t("Kalıp ekle")}
      </button>
    </div>
  );
}
