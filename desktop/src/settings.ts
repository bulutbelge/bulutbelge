import { ColumnRule, CustomPattern, Rules, TypeRule } from "./engine";

export const DEFAULT_PROFILE_ID = "varsayilan";

/** Motorda settings.json'da saklanan profil. Özel ifadeler burada değil, şifreli kasadadır. */
export interface Profile {
  id: string;
  name: string;
  types: Record<string, TypeRule>;
  patterns: CustomPattern[];
  whitelist: string[];
  institutions?: string[];
  column_rules?: ColumnRule[];
  signature_labels: string[];
  pseudonym_scope?: "belge";
}

export interface VaultStatus {
  exists: boolean;
  unlocked: boolean;
}

/** Kasadaki kayıtlı kopya (PDF) parolası: arayüze yalnızca kimlik ve ad gelir, değer gelmez. */
export interface SavedPassword {
  id: string;
  name: string;
}

export interface SettingsData {
  profiles: Profile[];
  active: string;
  vault: VaultStatus;
}

/** Kasa açıkken profil kimliğine göre özel ifadeler; yalnızca bellekte. */
export type Terms = Record<string, string[]>;

export function profileRules(profile: Profile, terms: Terms | null): Rules {
  return {
    types: profile.types,
    terms: terms?.[profile.id] ?? [],
    patterns: profile.patterns.filter((p) => p.pattern.trim()),
    whitelist: profile.whitelist,
    institutions: profile.institutions ?? [],
    ...(profile.column_rules?.some((r) => r.header.trim() && (r.type || r.action)) ? { column_rules: profile.column_rules.filter((r) => r.header.trim() && (r.type || r.action)) } : {}),
    signature_labels: profile.signature_labels,
    ...(profile.pseudonym_scope === "belge" ? { pseudonym_scope: "belge" as const } : {}),
    profile_name: profile.name,
  };
}

export function newProfileId(name: string, taken: string[]): string {
  const base =
    name
      .toLocaleLowerCase("tr")
      .replace(/[çğıöşü]/g, (c) => ({ ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u" })[c] ?? c)
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "profil";
  let id = base;
  for (let n = 2; taken.includes(id); n++) id = `${base}-${n}`;
  return id;
}

export function enabledTypeCount(profile: Profile): number {
  // Elle seçilen alan her zaman açıktır; sayıya katılmaz.
  return Object.entries(profile.types).filter(([k, t]) => k !== "elle" && t.enabled).length;
}
