import { useEffect, useState } from "react";
import { engineCall } from "./engine";
import { localeCode, useT } from "./i18n";
import { Icon } from "./ui";

interface AllowItem {
  id: string;
  type: string;
  type_label: string;
  at: number | null;
}

/**
 * Ana ekranda "Bir daha maskeleme" denilen değerler. Değerlerin kendisi saklanmadığı için burada
 * yalnızca türü ve eklendiği gün görünür; tek tek ya da hepsi birden kaldırılabilir.
 */
export function AllowPanel() {
  const t = useT();
  const [items, setItems] = useState<AllowItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    engineCall<AllowItem[]>("allow.list").then(setItems).catch((e) => setError(String(e)));
  }, []);

  function remove(id: string) {
    engineCall<AllowItem[]>("allow.remove", { id }).then(setItems).catch((e) => setError(String(e)));
  }

  if (error) return <p className="field-error">{t(error)}</p>;
  if (!items) return null;
  if (items.length === 0) {
    return <p className="hint">{t("Henüz yok. Ana ekranda bir değerin işaretini kaldırınca “Bir daha maskeleme” önerisi çıkar.")}</p>;
  }
  return (
    <div className="allow-list">
      <ul>
        {items.map((x) => (
          <li key={x.id}>
            <Icon name="ban" size={14} />
            <span>{t(x.type_label)}</span>
            <small>{x.at ? new Date(x.at * 1000).toLocaleDateString(localeCode()) : ""}</small>
            <button className="link-btn subtle" onClick={() => remove(x.id)}>
              {t("Kaldır")}
            </button>
          </li>
        ))}
      </ul>
      <button className="btn small" onClick={() => remove("*")}>
        <Icon name="trash" size={14} /> {t("Hepsini kaldır")}
      </button>
    </div>
  );
}
