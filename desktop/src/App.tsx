import { Fragment, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open, save } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { BatchMain, BatchPlan } from "./BatchMain";
import { categoryOf, groupFindings, groupText } from "./categories";
import {
  DataTypeInfo,
  DocFormat,
  engineCall,
  EngineVersion,
  extOf,
  formatOf,
  FormatsInfo,
  MaskResult,
  PdfFinding,
  Rules,
  ScanResult,
} from "./engine";
import { PagePreview, Rect } from "./PagePreview";
import { Profile, profileRules, SettingsData, Terms, VaultStatus } from "./settings";
import { SettingsPage } from "./SettingsPage";
import { SonucNotu } from "./Hakkinda";
import { GuncellemeSeridi, useGuncelleme } from "./guncelleme";
import { t, useT } from "./i18n";
import { SheetPreview } from "./SheetPreview";
import { SlidePreview } from "./SlidePreview";
import { PasteScreen } from "./PasteScreen";
import { canLearn, ReviewExtras, UNCERTAIN } from "./ReviewExtras";
import { TextPreview } from "./TextPreview";
import { Icon, Logo, PathChanged } from "./ui";
import { ThemeSwitch } from "./theme";
import { UnlockDialog } from "./Vault";
import { WordPreview } from "./WordPreview";
import {
  LayoutMode,
  MethodPreset,
  readLayoutMode,
  resolveMethodForType,
  SharedLayoutProps,
  StudioWorkspace,
  WizardWorkspace,
} from "./DesignLayouts";
import "./App.css";

/*
 * Ana ekran akışı (tasarım: "kategori kartları", docs/kararlar/2026-11-05-sade-arayuz.md)
 *
 *   Başlangıç ──belge bırak──▶ (otomatik tarama) ──▶ Sonuç ──Maskele ve kaydet──▶ Kaydedildi
 *   Başlangıç ──klasör bırak──▶ Klasör (toplu işlem)
 *
 * Sonuç ekranı: üstte bulunan bilgilerin kartları (İsimler, Kimlik numaraları…), altında belgenin
 * kendisi. Girişte hiçbir şey sorulmaz.
 *
 * Birden çok belge bırakılırsa üstte belge sırası çıkar; her belge ayrı gözden geçirilir ve
 * kaydedilir, seçimler belge değiştirince kaybolmaz. Başlangıçtaki "Metin yapıştır" sekmesi
 * dosyasız, yapıştırılan metin içindir (PasteScreen).
 *
 * Doğrulanamayan bulgular ("dusuk") kartlara girmez; "Emin olamadıklarımız" bölümünde açık kalacak
 * şekilde gelir. Tanınabilirlik uyarısı ve "bir daha maskeleme" önerisi: ReviewExtras.
 *
 * Tarama her zaman bütün bilgi türlerini arar. Ayarlar'daki kural takımı yalnızca neyin
 * varsayılan olarak maskeleneceğini ve nasıl maskeleneceğini belirler: takımda kapalı olan bir tür
 * yine bulunur, kartı "açık kalacak" diye gelir. Böylece görünmeyen bir ayar, belgede bir
 * bilgi olduğunu kullanıcıdan saklamaz.
 */

type EngineState =
  | { kind: "loading" }
  | { kind: "ready"; version: EngineVersion }
  | { kind: "error"; message: string };

type View = "orijinal" | "maskeli" | "kaydedilen";

export interface RecentTypeSummary {
  type: string;
  label: string;
  method?: string;
  methodLabel?: string;
  count: number;
}

export interface Recent {
  path: string;
  target: string;
  count: number;
  at: number;
  profileName?: string;
  droppedPages?: number;
  encrypted?: boolean;
  byType?: RecentTypeSummary[];
  folderName?: string;
  folderRoot?: string;
  /** Ajan komutuyla yapılan işlemde ajanın adı (Son yapılanlar'da "Ajan" etiketi). */
  agent?: string;
}

const RECENT_KEY = "bulutbelge.son-yapilanlar";

/**
 * Elle seçilen alan: PDF ve görselde sayfadaki dikdörtgen (`rect`), Excel'de bir satırın ya da sütunun
 * tamamı (`sheet`, `axis`, `index`; satır 1'den, sütun 0'dan).
 */
interface ManualArea {
  id: string;
  page: number;
  rect?: Rect;
  sheet?: string;
  axis?: "row" | "col";
  index?: number;
  /** Excel satır/sütununda yöntem: karartma, etiket, son4, bas_harf, takma_ad. */
  method?: string;
}

function manualRequest(areas: ManualArea[], excluded: Set<string>) {
  const on = areas.filter((a) => !excluded.has(a.id));
  return {
    manual_areas: on.filter((a) => a.rect).map((a) => ({ page: a.page, rect: a.rect })),
    manual_cells: on
      .filter((a) => a.sheet !== undefined)
      .map((a) => ({ sheet: a.sheet, axis: a.axis, index: a.index, method: a.method })),
  };
}

/** Sıradaki bir belgenin, başka belgeye geçince saklanan durumu. */
interface DocState {
  /** Taramanın kurallarının imzası; kurallar değişmişse saklanan tarama kullanılmaz. */
  rulesKey: string;
  scan: ScanResult;
  excluded: Set<string>;
  areas: ManualArea[];
  dropped: Set<number>;
  target: string | null;
  done: MaskResult | null;
  appliedProfileId: string;
  appliedMethodPreset: MethodPreset;
}

function loadRecent(): Recent[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as Recent[];
  } catch {
    return [];
  }
}

function saveRecent(list: Recent[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 10)));
  } catch {
    // tarayıcı deposu kapalıysa son yapılanlar yalnızca bu oturumda kalır
  }
}

function sourceFilters(f: FormatsInfo | null) {
  if (!f) return [{ name: "PDF", extensions: ["pdf"] }];
  return [
    { name: t("Desteklenen belgeler"), extensions: f.all },
    { name: "PDF", extensions: f.pdf },
    { name: "Word", extensions: f.word },
    { name: "Excel", extensions: f.tablo },
    { name: "PowerPoint", extensions: f.sunum },
    { name: t("Görseller"), extensions: f.gorsel },
    { name: "XML, TXT, CSV", extensions: f.metin },
    ...(f.eposta ? [{ name: t("E-posta"), extensions: f.eposta }] : []),
    ...(f.arsiv?.length ? [{ name: "ZIP", extensions: f.arsiv }] : []),
  ];
}

function splitPath(path: string): { name: string; dir: string } {
  const i = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return { name: path.slice(i + 1), dir: path.slice(0, i) };
}

function badgeKind(ext: string): string {
  if (ext === "pdf") return "pdf";
  if (ext === "docx") return "word";
  if (ext === "pptx") return "sunum";
  if (ext === "xlsx") return "tablo";
  if (["xml", "txt", "csv", "eml", "udf"].includes(ext)) return "metin";
  return "gorsel";
}

/** Çevrilmiş cümledeki {ad} yer tutucularını verilen düğümlerle (kalın, bağlantı vb.) değiştirir. */
function rich(text: string, nodes: Record<string, ReactNode>): ReactNode {
  return text.split(/(\{\w+\})/).map((part, i) => {
    const m = /^\{(\w+)\}$/.exec(part);
    return m && m[1] in nodes ? <Fragment key={i}>{nodes[m[1]]}</Fragment> : part;
  });
}

function Badge({ path }: { path: string }) {
  const ext = extOf(path);
  return <span className={`ext-badge ext-${badgeKind(ext)}`}>{ext.slice(0, 4).toUpperCase()}</span>;
}

function App() {
  const t = useT();
  const [engine, setEngine] = useState<EngineState>({ kind: "loading" });
  const [dataTypes, setDataTypes] = useState<DataTypeInfo[]>([]);
  const [formats, setFormats] = useState<FormatsInfo | null>(null);
  // Sürükle-bırak dinleyicisi bir kez kurulur; güncel biçim listesini referanstan okur.
  const formatsRef = useRef<FormatsInfo | null>(null);
  formatsRef.current = formats;

  const [showSettings, setShowSettings] = useState(false);
  // Açılışta yeni sürüm denetimi (ağ yoksa sessizce geçer; Ayarlar'dan kapatılır).
  const [yeniSurum, surumuGormezdenGel] = useGuncelleme();
  const [settings, setSettings] = useState<SettingsData | null>(null);
  // Kasa açıkken özel ifadeler; yalnızca bellekte.
  const [terms, setTerms] = useState<Terms | null>(null);
  const [unlockOpen, setUnlockOpen] = useState(false);

  const [source, setSource] = useState<string | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  // Önizlemede elle çizilen alanlar (sayfa koordinatı, pt).
  const [areas, setAreas] = useState<ManualArea[]>([]);

  const [folder, setFolder] = useState<string | null>(null);
  const [recursive, setRecursive] = useState(true);
  const [targetDir, setTargetDir] = useState<string | null>(null);
  const [plan, setPlan] = useState<BatchPlan | null>(null);
  const [batchRunning, setBatchRunning] = useState(false);
  /** Toplu işlem bitişinde bağlanabilirlik uyarısı (TAKIP 1.71); bilgi verir, engellemez. */
  const [linkability, setLinkability] = useState<{ duzey: string; uyari: string[] } | null>(null);

  const [scan, setScan] = useState<ScanResult | null>(null);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"scan" | "mask" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<MaskResult | null>(null);
  const [view, setView] = useState<View>("maskeli");
  const [dragging, setDragging] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  const [recent, setRecent] = useState<Recent[]>(loadRecent);
  const [inspectedRecentTarget, setInspectedRecentTarget] = useState<string | null>(null);
  const [homeTab, setHomeTab] = useState<"belge" | "metin">("belge");
  const [layoutMode] = useState<LayoutMode>(() => readLayoutMode("studio"));
  const [docText, setDocText] = useState<string | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [methodPreset, setMethodPreset] = useState<MethodPreset>("profil");
  const [appliedProfileId, setAppliedProfileId] = useState<string>("");
  const [appliedMethodPreset, setAppliedMethodPreset] = useState<MethodPreset>("profil");
  const [rulesApplied, setRulesApplied] = useState(false);
  // Birden çok belge bırakıldıysa sıra; tek belgede boş.
  const [queue, setQueue] = useState<string[]>([]);
  const sourceRef = useRef<string | null>(null);
  const queueRef = useRef<string[]>([]);
  useEffect(() => {
    sourceRef.current = source;
  }, [source]);
  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);
  const [saved, setSaved] = useState<Record<string, MaskResult>>({});
  const docCache = useRef<Map<string, DocState>>(new Map());
  const [cacheTick, setCacheTick] = useState(0);
  // Klasör seçildiğinde alt klasör yapısını ve hedef yollarını saklar.
  const [plannedFiles, setPlannedFiles] = useState<Record<string, { target: string; relative: string }>>({});
  const [folderRoot, setFolderRoot] = useState<string | null>(null);
  const [folderTargetDir, setFolderTargetDir] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number; mode: "scan" | "mask" } | null>(null);
  const [confirmGoHome, setConfirmGoHome] = useState(false);
  // Bir belgede kategori/tür ya da belirli bir isim/değer maskelenip açıldığında tüm klasördeki belgelere yansıtılır.
  const queueOverridesRef = useRef<{ types: Record<string, boolean>; values: Record<string, boolean> }>({
    types: {},
    values: {},
  });
  // PDF: paylaşılacak kopyadan çıkarılacak sayfalar.
  const [dropped, setDropped] = useState<Set<number>>(new Set());
  // Klasör/oturum genelinde "Ara ve maskele" sözcükleri ve tamamen karartılacak türler:
  // Bir belgede eklenen sözcük seçili tüm belgelerde aranır ve maskelenir.
  const [queueExtra, setQueueExtra] = useState<DocExtra>(NO_EXTRA);
  // Kopyanın parolası (yalnızca PDF); yalnızca bellekte, belge değişince silinir.
  const [protect, setProtect] = useState(false);
  const [password, setPassword] = useState("");
  // Düzleştir modu (TAKIP 1.63): yalnızca tek belge akışında, PDF için.
  const [flatten, setFlatten] = useState(false);
  // Aynı belge yeniden taranırken seçimler korunsun diye son taranan belge.
  const scannedPath = useRef<string | null>(null);
  // En son açık bırakılan değerler: "bunlar bir daha hiç maskelenmesin mi?" önerisi için.
  const [lastOff, setLastOff] = useState<PdfFinding[]>([]);
  // Her taramaya bir numara: yalnızca en son başlatılan taramanın sonucu ekrana gelir.
  const scanTicket = useRef(0);

  useEffect(() => {
    engineCall<EngineVersion>("version")
      .then((version) => setEngine({ kind: "ready", version }))
      .catch((e) => setEngine({ kind: "error", message: String(e) }));
    engineCall<DataTypeInfo[]>("rules.types")
      .then(setDataTypes)
      .catch((e) => setError(String(e)));
    engineCall<FormatsInfo>("doc.formats")
      .then(setFormats)
      .catch((e) => setError(String(e)));
    engineCall<SettingsData>("settings.get")
      .then((s) => {
        setSettings(s);
        setSelectedProfileId(s.active);
        setAppliedProfileId(s.active);
      })
      .catch((e) => setError(String(e)));
    const legacy = loadRecent();
    const historyPromise =
      legacy.length > 0
        ? engineCall<Recent[]>("history.add", { entries: legacy }).then((dbList) => {
            try {
              localStorage.removeItem(RECENT_KEY);
            } catch {
              // yok say
            }
            return dbList;
          })
        : engineCall<Recent[]>("history.list");
    historyPromise
      .then((dbList) => {
        if (Array.isArray(dbList)) setRecent(dbList);
      })
      .catch(() => {
        // Motor henüz hazır değilse mevcut bellekteki liste korunur
      });
  }, []);

  function setVault(vault: VaultStatus, tr: Terms | null) {
    setSettings((s) => (s ? { ...s, vault } : s));
    setTerms(tr);
  }

  // Pencereye belge ya da klasör sürükleyip bırakma.
  useEffect(() => {
    const unlisten = getCurrentWebview().onDragDropEvent((event) => {
      const p = event.payload;
      if (p.type === "enter" || p.type === "over") setDragging(true);
      else if (p.type === "leave") setDragging(false);
      else if (p.type === "drop") {
        setDragging(false);
        const docs = p.paths.filter((x) => formatOf(x, formatsRef.current) !== null);
        if (docs.length > 0) {
          if (sourceRef.current || queueRef.current.length > 0) {
            const existing = queueRef.current.length > 0 ? queueRef.current : sourceRef.current ? [sourceRef.current] : [];
            const newPaths = docs.filter((d) => !existing.includes(d));
            if (newPaths.length > 0) {
              const nextQueue = [...existing, ...newPaths];
              setQueue(nextQueue);
              switchDoc(newPaths[0]);
            } else if (docs[0] && docs[0] !== sourceRef.current) {
              switchDoc(docs[0]);
            }
          } else {
            if (docs.length > 1) chooseMany(docs);
            else chooseSource(docs[0]);
          }
        } else if (p.paths[0] && !extOf(p.paths[0])) {
          void chooseFolder(p.paths[0]);
        } else if (p.paths[0]) {
          setError(t("Bu dosya türü desteklenmiyor: .{ext}", { ext: extOf(p.paths[0]) }));
        }
      }
    });
    return () => {
      unlisten.then((f) => f());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedProfile: Profile | null =
    settings?.profiles.find((p) => p.id === selectedProfileId) ??
    settings?.profiles.find((p) => p.id === settings.active) ??
    settings?.profiles[0] ??
    null;
  const profile: Profile | null =
    settings?.profiles.find((p) => p.id === appliedProfileId) ??
    selectedProfile;
  const rules: Rules | null = useMemo(() => (profile ? profileRules(profile, terms) : null), [profile, terms]);
  const extra: DocExtra = queueExtra;
  const extraKey = JSON.stringify(extra);

  function normValueKey(val: string): string {
    return val.trim().replace(/\s+/g, " ").toLocaleLowerCase("tr");
  }

  function computeExcludedForScan(
    result: ScanResult,
    activeProf: Profile | null,
    keep?: { ids: Set<string>; excluded: Set<string> },
  ): Set<string> {
    const defaultOff = (f: PdfFinding) => activeProf?.types[f.type]?.enabled === false || f.confidence === UNCERTAIN;
    const out = new Set<string>();
    for (const f of result.findings) {
      const vKey = f.value.trim().length >= 2 ? normValueKey(f.value) : "";
      if (vKey && queueOverridesRef.current.values[vKey] !== undefined) {
        if (!queueOverridesRef.current.values[vKey]) out.add(f.id);
        continue;
      }
      if (queueOverridesRef.current.types[f.type] !== undefined) {
        if (!queueOverridesRef.current.types[f.type]) out.add(f.id);
        continue;
      }
      const isOff = keep?.ids.has(f.id) ? keep.excluded.has(f.id) : defaultOff(f);
      if (isOff) out.add(f.id);
    }
    return out;
  }

  function buildScanRules(prof: Profile | null, preset: MethodPreset, docEx: DocExtra): Rules | null {
    if (!prof) return null;
    const base = profileRules(prof, terms);
    return {
      ...base,
      terms: [...base.terms, ...docEx.terms],
      types: Object.fromEntries(
        Object.entries(base.types).map(([k, v]) => [
          k,
          {
            ...v,
            enabled: true,
            method: docEx.blackout.includes(k)
              ? "karartma"
              : resolveMethodForType(k, preset, v.method, dataTypes),
          },
        ]),
      ),
    };
  }

  // Tek belgede tarama bütün türleri arar; takımda kapalı türler varsayılan olarak "açık kalacak" gelir.
  // Belgeye özel aranan sözcükler özel ifade olarak eklenir; seçilen maskeleme metodu uygulanır.
  const scanRules: Rules | null = useMemo(
    () => buildScanRules(profile, appliedMethodPreset, extra),
    // extra, extraKey ile izlenir
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [profile, appliedMethodPreset, terms, extraKey, dataTypes],
  );
  const scanKey = scanRules ? JSON.stringify(scanRules) : "";
  const offByRule = (type: string) => profile?.types[type]?.enabled === false;
  // Özel ifade ve kalıbın yöntemi profilde ayrıca seçilmez; seçilen maskeleme metoduna göre belirlenir.
  const methodOf = (type: string) => {
    if (extra.blackout.includes(type)) return "karartma";
    const base = profile?.types[type]?.method ?? "karartma";
    return resolveMethodForType(type, appliedMethodPreset, base, dataTypes);
  };

  function updateExtra(patch: Partial<DocExtra>) {
    if (!source) return;
    setQueueExtra((prev) => ({ ...prev, ...patch }));
  }
  const format: DocFormat | null = source ? formatOf(source, formats) : null;

  // Taramadan önce metin ve arşiv belgelerinin (XML, TXT, CSV, ZIP) önizlemesi için içeriği oku.
  useEffect(() => {
    setDocText(null);
    const fmt = source ? formatOf(source, formats) : null;
    if (!source || (fmt !== "metin" && fmt !== "arsiv")) return;
    let alive = true;
    engineCall<{ text: string }>("doc.text", { path: source })
      .then((r) => alive && setDocText(r.text))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [source, formats]);

  // Belge seçilince önce önizleme açılır; daha önce bu oturumda "Uygula" denmişse önceki tarama geri gelir,
  // aksi hâlde kullanıcı kural/metod seçip "Uygula" diyene kadar beklenir.
  useEffect(() => {
    setPreviewPage(1);
    setView("maskeli");
    const cached = source ? docCache.current.get(source) : undefined;
    if (cached) {
      scanTicket.current++;
      setScan(cached.scan);
      setExcluded(cached.excluded);
      setAreas(cached.areas);
      setDropped(cached.dropped);
      setTarget(cached.target);
      setDone(cached.done);
      setAppliedProfileId(cached.appliedProfileId);
      setAppliedMethodPreset(cached.appliedMethodPreset);
      setSelectedProfileId(cached.appliedProfileId);
      setMethodPreset(cached.appliedMethodPreset);
      setRulesApplied(true);
      scannedPath.current = source;
      setBusy(null);
      return;
    }
    scanTicket.current++;
    scannedPath.current = null;
    setScan(null);
    setExcluded(new Set());
    setDropped(new Set());
    setDone(null);
    setBusy(null);
    setAppliedProfileId("");
  }, [source]);

  // Belge zaten taranmışken "Ara ve maskele" veya "Tamamen karart" değişirse açık belgeyi ve sıradaki tüm belgeleri yeniden tara.
  useEffect(() => {
    if (!source || !scan || scannedPath.current !== source || !scanRules) return;
    void applyRulesAndScan(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extraKey]);

  // Parola belgeye ait değildir: belge değişince silinir.
  useEffect(() => {
    setProtect(false);
    setPassword("");
    setFlatten(false);
  }, [source]);

  // Elle seçilen alanlar belgeye aittir; kurallar değişince kalır, belge değişince silinir.
  useEffect(() => {
    if (!source || !docCache.current.has(source)) setAreas([]);
  }, [source]);

  // Klasör: klasör, alt klasör seçeneği ya da hedef değişince planı yeniden çıkar.
  useEffect(() => {
    if (!folder) {
      setPlan(null);
      return;
    }
    engineCall<BatchPlan>("batch.plan", { source_dir: folder, target_dir: targetDir, recursive })
      .then((p) => {
        setPlan(p);
        setError(null);
      })
      .catch((e) => {
        setPlan(null);
        setError(String(e));
      });
  }, [folder, targetDir, recursive]);

  const manualFindings: PdfFinding[] = useMemo(
    () =>
      areas.map((a) => ({
        id: a.id,
        page: a.page,
        type: "elle",
        type_label: "Elle seçilen alan",
        source: "",
        value: "",
        replacement: methodOf("elle") === "etiket" ? "[GIZLI]" : "",
        confidence: "yuksek",
        locatable: true,
        kind: "alan",
        preview: null,
        rects: a.rect ? [a.rect] : [],
      })),
    // methodOf profile'a bağlı
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [areas, profile],
  );
  const allFindings = scan ? [...scan.findings, ...manualFindings] : [];
  // Çıkarılan sayfadaki bulgular maskelenmeye gerek kalmadan kopyadan gider; sayıya katılmaz.
  const onKeptPage = (f: PdfFinding) => format !== "pdf" || !dropped.has(f.page);
  const included = allFindings.filter((f) => !excluded.has(f.id) && onKeptPage(f));
  const unlocated = included.filter((f) => !f.locatable).length;
  const sure = allFindings.filter((f) => f.confidence !== UNCERTAIN);
  const unsure = allFindings.filter((f) => f.confidence === UNCERTAIN);
  const groups = groupFindings(sure, excluded);

  function addArea(page: number, rect: Rect) {
    setAreas((a) => [...a, { id: `alan:${Date.now()}:${a.length}`, page, rect }]);
    setDone(null);
  }

  /** Excel: satır ya da sütun başlığına tıklanınca o satırın/sütunun tamamı maskelenir; ikinci tıklama kaldırır. */
  function toggleSheetLine(sheet: string, axis: "row" | "col", index: number) {
    const id = `alan:xl:${sheet}:${axis}:${index}`;
    const method = methodOf("elle") === "etiket" ? "etiket" : "karartma";
    setAreas((a) => (a.some((x) => x.id === id) ? a.filter((x) => x.id !== id) : [...a, { id, page: 1, sheet, axis, index, method }]));
    setDone(null);
  }

  function setLineMethod(id: string, method: string) {
    setAreas((a) => a.map((x) => (x.id === id ? { ...x, method } : x)));
    setDone(null);
  }

  function removeArea(id: string) {
    setAreas((a) => a.filter((x) => x.id !== id));
    setDone(null);
  }

  /** `offer`: tek tek açık bırakılan değerler için "bir daha maskeleme" önerisi gösterilsin mi. */
  function updateExcluded(next: Set<string>, offer = false) {
    setLastOff(offer ? allFindings.filter((f) => next.has(f.id) && !excluded.has(f.id) && canLearn(f)) : []);
    setExcluded(next);
    setDone(null);
  }

  /** Seçilen tür veya değer tercihini sıradaki diğer tüm taranmış belgelere de uygular. */
  function syncAcrossQueue(typesToSync: Set<string>, valuesToSync: Set<string>, shouldHide: boolean) {
    for (const ty of typesToSync) {
      queueOverridesRef.current.types[ty] = shouldHide;
    }
    for (const v of valuesToSync) {
      queueOverridesRef.current.values[v] = shouldHide;
    }
    for (const [docPath, st] of docCache.current.entries()) {
      if (docPath === source) continue;
      const nextEx = new Set(st.excluded);
      let changed = false;
      for (const cf of st.scan.findings) {
        const vKey = cf.value.trim().length >= 2 ? normValueKey(cf.value) : "";
        const matchVal = vKey !== "" && valuesToSync.has(vKey);
        const matchType = typesToSync.has(cf.type);
        if (matchVal || matchType) {
          if (shouldHide && nextEx.has(cf.id)) {
            nextEx.delete(cf.id);
            changed = true;
          } else if (!shouldHide && !nextEx.has(cf.id)) {
            nextEx.add(cf.id);
            changed = true;
          }
        }
      }
      if (changed) {
        docCache.current.set(docPath, { ...st, excluded: nextEx, done: null });
      }
    }
    setCacheTick((c) => c + 1);
  }

  function setMany(items: PdfFinding[], hide: boolean) {
    const next = new Set(excluded);
    const typesToSync = new Set<string>();
    const valuesToSync = new Set<string>();
    for (const f of items) {
      if (hide) next.delete(f.id);
      else next.add(f.id);
      if (f.type !== "elle") typesToSync.add(f.type);
      if (f.value.trim().length >= 2) valuesToSync.add(normValueKey(f.value));
    }
    updateExcluded(next);
    syncAcrossQueue(typesToSync, valuesToSync, hide);
  }

  function toggleDrop(page: number) {
    const next = new Set(dropped);
    if (next.has(page)) next.delete(page);
    else next.add(page);
    setDropped(next);
    setDone(null);
  }

  /** Şu anki belgenin durumunu saklar (sırada başka belgeye geçerken). */
  function stash() {
    if (source && scan && scanRules) {
      docCache.current.set(source, {
        rulesKey: scanKey,
        scan,
        excluded,
        areas,
        dropped,
        target,
        done,
        appliedProfileId: profile?.id ?? selectedProfile?.id ?? "",
        appliedMethodPreset,
      });
    }
  }

  function toggleFinding(id: string) {
    const shouldHide = excluded.has(id);
    const targetFinding = allFindings.find((f) => f.id === id);
    const vKey = targetFinding && targetFinding.value.trim().length >= 2 ? normValueKey(targetFinding.value) : "";
    const next = new Set(excluded);
    if (shouldHide) next.delete(id);
    else next.add(id);
    // Aynı belgede ve klasördeki diğer belgelerde aynı değer (örn. aynı kişi adı) varsa onları da eşitle.
    if (vKey) {
      for (const f of allFindings) {
        if (f.value.trim().length >= 2 && normValueKey(f.value) === vKey) {
          if (shouldHide) next.delete(f.id);
          else next.add(f.id);
        }
      }
    }
    updateExcluded(next, true);
    if (vKey) {
      syncAcrossQueue(new Set(), new Set([vKey]), shouldHide);
    }
  }

  /** Kart: grubun hepsi maskeleniyorsa hepsini açık bırak, değilse hepsini maskele (klasördeki tüm belgelere de uygular). */
  function toggleGroup(items: PdfFinding[]) {
    const allOn = items.every((f) => !excluded.has(f.id));
    const shouldHide = !allOn;
    const next = new Set(excluded);
    const typesToSync = new Set<string>();
    for (const f of items) {
      if (allOn) next.add(f.id);
      else next.delete(f.id);
      if (f.type !== "elle") typesToSync.add(f.type);
      if (f.value.trim().length >= 2) {
        delete queueOverridesRef.current.values[normValueKey(f.value)];
      }
    }
    updateExcluded(next);
    syncAcrossQueue(typesToSync, new Set(), shouldHide);
  }

  function resetQueueContext() {
    docCache.current.clear();
    queueOverridesRef.current = { types: {}, values: {} };
    setQueueExtra(NO_EXTRA);
    setPlannedFiles({});
    setFolderRoot(null);
    setFolderTargetDir(null);
    setBatchProgress(null);
    setAppliedProfileId("");
    setRulesApplied(false);
    setCacheTick((c) => c + 1);
  }

  function chooseSource(path: string) {
    resetQueueContext();
    setQueue([]);
    setSaved({});
    openDoc(path);
  }

  function chooseMany(
    paths: string[],
    folderMeta?: {
      root: string;
      targetDir: string;
      planned: Record<string, { target: string; relative: string }>;
    },
  ) {
    resetQueueContext();
    setQueue(paths);
    setSaved({});
    setPlannedFiles(folderMeta?.planned ?? {});
    setFolderRoot(folderMeta?.root ?? null);
    setFolderTargetDir(folderMeta?.targetDir ?? null);
    openDoc(paths[0], folderMeta?.planned[paths[0]]?.target ?? null);
  }

  /** Sıradaki belgeye geçer; o anki belgenin seçimleri saklanır. */
  function switchDoc(path: string) {
    if (path === source || busy === "mask") return;
    stash();
    openDoc(path, plannedFiles[path]?.target ?? null);
  }

  function openDoc(path: string, defaultTargetOverride: string | null = null) {
    setLastOff([]);
    setFolder(null);
    setSource(path);
    setTarget(defaultTargetOverride ?? plannedFiles[path]?.target ?? null);
    setError(null);
    setShowSettings(false);
  }

  /** Klasör seçildiğinde alt klasörler dahil tüm desteklenen belgeleri Stüdyo sırasına yükler. */
  async function chooseFolder(path: string) {
    setError(null);
    setShowSettings(false);
    try {
      const p = await engineCall<BatchPlan>("batch.plan", { source_dir: path, recursive: true });
      const paths = p.files.map((f) => f.source);
      if (paths.length === 0) {
        setError(t("Seçilen klasörde (ve alt klasörlerinde) işlenebilecek desteklenen bir belge bulunamadı."));
        return;
      }
      const planned: Record<string, { target: string; relative: string }> = {};
      for (const f of p.files) {
        planned[f.source] = { target: f.target, relative: f.relative };
      }
      if (paths.length > 1) {
        chooseMany(paths, { root: path, targetDir: p.target_dir, planned });
      } else {
        chooseMany(paths, { root: path, targetDir: p.target_dir, planned });
      }
    } catch (e) {
      setError(String(e));
    }
  }

  function goHome() {
    if (batchRunning) return;
    resetQueueContext();
    setQueue([]);
    setSaved({});
    setSource(null);
    setFolder(null);
    setError(null);
    setShowSettings(false);
    setInspectedRecentTarget(null);
    setConfirmGoHome(false);
    setAppliedProfileId("");
    setRulesApplied(false);
  }

  function handleHomeClick() {
    if (batchRunning) return;
    // Eğer kural takımı uygulanmış ve henüz işlem tamamlanmamışsa onay iste.
    // Kullanıcı kural takımını henüz "Uygula" ile uygulamadıysa doğrudan ana sayfaya dön.
    const hasAnyScan = Boolean(scan) || Array.from(docCache.current.values()).some((c) => Boolean(c.scan));
    const isApplied = rulesApplied || hasAnyScan;
    const isAllDone = queue.length > 1 ? queue.every((q) => Boolean(saved[q])) : Boolean(done);
    if (isApplied && !isAllDone) {
      setConfirmGoHome(true);
    } else {
      goHome();
    }
  }

  async function pickSource() {
    const picked = await open({ multiple: true, directory: false, filters: sourceFilters(formats) });
    const paths = Array.isArray(picked) ? picked : typeof picked === "string" ? [picked] : [];
    if (paths.length === 0) return;
    if (source || queue.length > 0) {
      // Zaten açık belge(ler) var, listeyi sıfırlamak yerine yeni belgeleri ekle
      const existing = queue.length > 0 ? queue : source ? [source] : [];
      const newPaths = paths.filter((p) => !existing.includes(p));
      if (newPaths.length > 0) {
        const nextQueue = [...existing, ...newPaths];
        setQueue(nextQueue);
        switchDoc(newPaths[0]);
      } else if (paths[0] && paths[0] !== source) {
        switchDoc(paths[0]);
      }
    } else {
      if (paths.length > 1) chooseMany(paths);
      else if (paths.length === 1) chooseSource(paths[0]);
    }
  }

  function updateFolderTargetDir(newFullDir: string) {
    const cleanFullDir = newFullDir.trim().replace(/[/\\]+$/, "");
    if (!cleanFullDir) return;
    setFolderTargetDir(cleanFullDir);
    const isWin = cleanFullDir.includes("\\");
    const sep = isWin ? "\\" : "/";
    const updatedPlanned: Record<string, { target: string; relative: string }> = {};
    for (const [docPath, info] of Object.entries(plannedFiles)) {
      const cleanRel = info.relative.replace(/^[/\\]+/, "").replace(/[/\\]+/g, sep);
      const newDocTarget = `${cleanFullDir}${sep}${cleanRel}`;
      updatedPlanned[docPath] = { relative: info.relative, target: newDocTarget };
      const cached = docCache.current.get(docPath);
      if (cached) {
        docCache.current.set(docPath, { ...cached, target: newDocTarget });
      }
    }
    setPlannedFiles(updatedPlanned);
    if (source && updatedPlanned[source]) {
      setTarget(updatedPlanned[source].target);
    }
  }

  async function pickFolder() {
    const path = await open({ multiple: false, directory: true });
    if (typeof path === "string") void chooseFolder(path);
  }

  async function pickTargetDir() {
    const path = await open({ multiple: false, directory: true, defaultPath: plan?.target_dir });
    if (typeof path === "string") setTargetDir(path);
  }

  async function pickTarget() {
    const ext = source ? extOf(source) : "pdf";
    const path = await save({ filters: [{ name: ext.toUpperCase(), extensions: [ext] }], defaultPath: target ?? undefined });
    if (path) {
      setTarget(path);
      setDone(null);
    }
  }

  /** `keep`: aynı belgenin önceki taramasındaki seçimler; hâlâ bulunan bulgularda korunur. */
  async function runScan(path: string, r: Rules, keep?: { ids: Set<string>; excluded: Set<string> }, prof?: Profile | null, flat: boolean = flatten) {
    const ticket = ++scanTicket.current;
    setBusy("scan");
    setError(null);
    try {
      const result = await engineCall<ScanResult>("doc.scan", { path, rules: r, flatten: flat });
      // Bu sırada başka belge seçildiyse eski sonuç gösterilmez.
      if (ticket !== scanTicket.current) return;
      const activeProf = prof ?? profile;
      const nextEx = computeExcludedForScan(result, activeProf, keep);
      const nextTarget = plannedFiles[path]?.target ?? result.suggested_target ?? result.default_target;
      setScan(result);
      scannedPath.current = path;
      setExcluded(nextEx);
      setTarget((cur) => cur ?? nextTarget);
      docCache.current.set(path, {
        rulesKey: JSON.stringify(r),
        scan: result,
        excluded: nextEx,
        areas: path === source ? areas : [],
        dropped: path === source ? dropped : new Set(),
        target: nextTarget,
        done: null,
        appliedProfileId: activeProf?.id ?? "",
        appliedMethodPreset: methodPreset,
      });
      setCacheTick((c) => c + 1);
    } catch (e) {
      if (ticket === scanTicket.current) setError(String(e));
    } finally {
      if (ticket === scanTicket.current) setBusy(null);
    }
  }

  /** Düzleştir anahtarı: bulgular görüntüden OCR ile okunduğu için belge yeniden taranır. */
  async function toggleFlatten(on: boolean) {
    setFlatten(on);
    setDone(null);
    if (!source) return;
    const nextRules = buildScanRules(selectedProfile, methodPreset, extra);
    if (!nextRules) return;
    const keep = scan ? { ids: new Set(scan.findings.map((f) => f.id)), excluded } : undefined;
    await runScan(source, nextRules, keep, selectedProfile, on);
  }

  /** Kullanıcı sol alttan veya sağ panelden bir Kural Takımı seçtiğinde çalışır. */
  function handleSelectProfileId(nextProfId: string) {
    setSelectedProfileId(nextProfId);
    if (!scan) {
      setAppliedProfileId(nextProfId);
    }
    if (settings && settings.active !== nextProfId) {
      const nextSettings: SettingsData = { ...settings, active: nextProfId };
      setSettings(nextSettings);
      void engineCall("settings.save", { active: nextProfId, profiles: settings.profiles });
    }
  }

  /**
   * Kullanıcı sağ panelden maskeleme kuralı seçip "Uygula" dediğinde çalışır:
   * Yalnızca tek belgeyi değil, klasördeki/sıradaki TÜM belgeleri seçilen kuralla tarar.
   */
  async function applyRulesAndScan(preserveOverrides = false) {
    if (!source || !selectedProfile) return;
    setRulesApplied(true);
    const nextProfId = selectedProfile.id;
    if (!preserveOverrides && nextProfId !== appliedProfileId) {
      queueOverridesRef.current = { types: {}, values: {} };
    }
    setAppliedProfileId(nextProfId);
    setAppliedMethodPreset(methodPreset);
    setDone(null);
    setView("maskeli");
    if (settings && settings.active !== nextProfId) {
      const nextSettings: SettingsData = { ...settings, active: nextProfId };
      setSettings(nextSettings);
      void engineCall("settings.save", { active: nextProfId, profiles: settings.profiles });
    }
    const nextRules = buildScanRules(selectedProfile, methodPreset, extra);
    if (!nextRules) return;
    const rKey = JSON.stringify(nextRules);
    const allDocs = queue.length > 1 ? queue : [source];
    if (allDocs.length > 1) {
      setBatchProgress({ done: 0, total: allDocs.length, mode: "scan" });
    }
    const keep = scan ? { ids: new Set(scan.findings.map((f) => f.id)), excluded } : undefined;
    await runScan(source, nextRules, keep, selectedProfile);

    if (allDocs.length > 1) {
      let completed = 1;
      setBatchProgress({ done: completed, total: allDocs.length, mode: "scan" });
      for (const docPath of allDocs) {
        if (docPath === source) continue;
        try {
          const prevCached = docCache.current.get(docPath);
          const prevKeep = prevCached
            ? { ids: new Set(prevCached.scan.findings.map((f) => f.id)), excluded: prevCached.excluded }
            : undefined;
          const res = await engineCall<ScanResult>("doc.scan", { path: docPath, rules: nextRules });
          const nextEx = computeExcludedForScan(res, selectedProfile, prevKeep);
          const nextTarget = plannedFiles[docPath]?.target ?? prevCached?.target ?? res.default_target;
          docCache.current.set(docPath, {
            rulesKey: rKey,
            scan: res,
            excluded: nextEx,
            areas: prevCached?.areas ?? [],
            dropped: prevCached?.dropped ?? new Set(),
            target: nextTarget,
            done: null,
            appliedProfileId: nextProfId,
            appliedMethodPreset: methodPreset,
          });
        } catch {
          // Tekil okunamayan belge diğerlerini durdurmasın
        }
        completed++;
        setBatchProgress({ done: completed, total: allDocs.length, mode: "scan" });
        setCacheTick((c) => c + 1);
      }
      setBatchProgress(null);
    }
  }

  function buildRecentByType(findingsList: PdfFinding[], ex: Set<string>, manualCount = 0): RecentTypeSummary[] {
    const map = new Map<string, RecentTypeSummary>();
    for (const f of findingsList) {
      if (ex.has(f.id)) continue;
      const mKey = methodOf(f.type);
      const dt = dataTypes.find((d) => d.key === f.type);
      const mLabel = dt?.methods.find((m) => m.key === mKey)?.label ?? mKey;
      const existing = map.get(f.type);
      if (existing) {
        existing.count += 1;
      } else {
        map.set(f.type, {
          type: f.type,
          label: dt?.label ?? f.type_label ?? f.type,
          method: mKey,
          methodLabel: mLabel,
          count: 1,
        });
      }
    }
    if (manualCount > 0 && !map.has("elle")) {
      const mKey = methodOf("elle");
      const dt = dataTypes.find((d) => d.key === "elle");
      const mLabel = dt?.methods.find((m) => m.key === mKey)?.label ?? "Karartma";
      map.set("elle", {
        type: "elle",
        label: "Elle seçilen alan",
        method: mKey,
        methodLabel: mLabel,
        count: manualCount,
      });
    }
    return [...map.values()];
  }

  async function runMask() {
    if (!source || !target || !scan || !scanRules) return;
    setBusy("mask");
    setError(null);
    try {
      const { manual_areas, manual_cells } = manualRequest(areas, excluded);
      const result = await engineCall<MaskResult>("doc.mask", {
        source,
        target,
        rules: scanRules,
        excluded_ids: [...excluded].filter((id) => !id.startsWith("alan:")),
        manual_areas,
        manual_cells,
        drop_pages: format === "pdf" ? [...dropped].sort((a, b) => a - b) : [],
        password: format === "pdf" && protect ? password : undefined,
        flatten: format === "pdf" && flatten,
        fixed_box: profile?.fixed_box === true,
        make_dirs: true,
      });
      setDone(result);
      setSaved((s) => ({ ...s, [source]: result }));
      // Sayfa çıkarıldıysa kaydedilen kopyada sayfa numaraları değişir; baştan gösterilir.
      if (result.dropped) setPreviewPage(1);
      const entry: Recent = {
        path: source,
        target: result.target,
        count: result.masked,
        at: Date.now(),
        profileName: (profile ?? selectedProfile)?.name,
        droppedPages: result.dropped,
        encrypted: result.encrypted,
        byType: buildRecentByType(allFindings, excluded, manual_areas.length + manual_cells.length),
      };
      const next = [entry, ...recent.filter((x) => x.target !== result.target)];
      setRecent(next);
      void engineCall<Recent[]>("history.add", { entry })
        .then((dbList) => {
          if (Array.isArray(dbList)) setRecent(dbList);
        })
        .catch(() => saveRecent(next));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  /** Klasördeki / sıradaki TÜM belgeleri tek seferde maskeler ve klasör yapısını koruyarak kaydeder. */
  async function runMaskAll() {
    if (!scanRules || !selectedProfile) return;
    const allDocs = queue.length > 1 ? queue : source ? [source] : [];
    if (allDocs.length === 0) return;
    stash();
    setBusy("mask");
    setError(null);

    // Eğer bu oturumda klasör daha önce maskelenmişse, üzerine yazmamak için yeni ardışık hedef klasörü (örn. _maskeli_2) al
    if (folderRoot && Object.keys(saved).length > 0) {
      try {
        const nextPlan = await engineCall<BatchPlan>("batch.plan", { source_dir: folderRoot, recursive: true });
        if (nextPlan.target_dir && nextPlan.target_dir !== folderTargetDir) {
          updateFolderTargetDir(nextPlan.target_dir);
        }
      } catch {
        // Hata durumunda mevcut plannedFiles ile devam et
      }
    }

    setBatchProgress({ done: 0, total: allDocs.length, mode: "mask" });
    setLinkability(null);
    const rKey = JSON.stringify(scanRules);
    let updatedRecent = [...recent];
    const addedEntries: Recent[] = [];
    try {
      for (let i = 0; i < allDocs.length; i++) {
        const docPath = allDocs[i];
        let st = docCache.current.get(docPath);
        if (!st) {
          const res = await engineCall<ScanResult>("doc.scan", { path: docPath, rules: scanRules });
          const nextEx = computeExcludedForScan(res, profile ?? selectedProfile);
          const nextTarget = plannedFiles[docPath]?.target ?? res.default_target;
          st = {
            rulesKey: rKey,
            scan: res,
            excluded: nextEx,
            areas: [],
            dropped: new Set(),
            target: nextTarget,
            done: null,
            appliedProfileId: (profile ?? selectedProfile).id,
            appliedMethodPreset: methodPreset,
          };
          docCache.current.set(docPath, st);
        }
        const docTarget = plannedFiles[docPath]?.target ?? st.target ?? st.scan.default_target;
        const docFmt = formatOf(docPath, formats);
        const { manual_areas, manual_cells } = manualRequest(st.areas, st.excluded);
        const result = await engineCall<MaskResult>("doc.mask", {
          source: docPath,
          target: docTarget,
          rules: scanRules,
          excluded_ids: [...st.excluded].filter((id) => !id.startsWith("alan:")),
          manual_areas,
          manual_cells,
          drop_pages: docFmt === "pdf" ? [...st.dropped].sort((a, b) => a - b) : [],
          password: docFmt === "pdf" && protect ? password : undefined,
          flatten: docFmt === "pdf" && docPath === source && flatten,
          fixed_box: profile?.fixed_box === true,
          make_dirs: true,
        });
        const updatedState: DocState = { ...st, target: docTarget, done: result };
        docCache.current.set(docPath, updatedState);
        setSaved((s) => ({ ...s, [docPath]: result }));
          if (docPath === source) {
          setDone(result);
          if (result.dropped) setPreviewPage(1);
        }
        const folderRootName = folderRoot ? splitPath(folderRoot).name : null;
        const targetFolderName = folderTargetDir ? splitPath(folderTargetDir).name : null;
        const effectiveFolderName = targetFolderName || (folderRootName ? `${folderRootName}_maskeli` : undefined);
        const entry: Recent = {
          path: docPath,
          target: result.target,
          count: result.masked,
          at: Date.now(),
          profileName: (profile ?? selectedProfile)?.name,
          droppedPages: result.dropped,
          encrypted: result.encrypted,
          byType: buildRecentByType(st.scan.findings, st.excluded, manual_areas.length + manual_cells.length),
          folderName: effectiveFolderName,
          folderRoot: folderTargetDir ?? (folderRoot ? `${folderRoot}_maskeli` : undefined),
        };
        addedEntries.push(entry);
        updatedRecent = [entry, ...updatedRecent.filter((x) => x.target !== result.target)];
        setBatchProgress({ done: i + 1, total: allDocs.length, mode: "mask" });
        setCacheTick((c) => c + 1);
      }
      setRecent(updatedRecent);
      if (addedEntries.length > 1) {
        try {
          const lk = await engineCall<{ duzey: string; uyari: string[] }>("batch.linkability", {
            paths: addedEntries.map((e) => e.target),
          });
          if (lk.duzey !== "Yok" && lk.uyari.length > 0) setLinkability(lk);
        } catch {
          // Uyarı yalnızca bilgidir; alınamazsa işlem sonucu etkilenmez.
        }
      }
      if (addedEntries.length > 0) {
        void engineCall<Recent[]>("history.add", { entries: addedEntries })
          .then((dbList) => {
            if (Array.isArray(dbList)) setRecent(dbList);
          })
          .catch(() => saveRecent(updatedRecent));
      }

      // Klasör maskelemesi tamamlandı; sonraki maskelemenin (örn. _maskeli_2) yeni bir klasöre yazılması için hedefi güncelle
      if (folderRoot) {
        void engineCall<BatchPlan>("batch.plan", { source_dir: folderRoot, recursive: true })
          .then((nextPlan) => {
            if (nextPlan.target_dir && nextPlan.target_dir !== folderTargetDir) {
              updateFolderTargetDir(nextPlan.target_dir);
            }
          })
          .catch(() => {});
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBatchProgress(null);
      setBusy(null);
    }
  }

  const onBatchRunning = useCallback((r: boolean) => setBatchRunning(r), []);

  const linkabilityBanner = linkability && (
    <div className="banner warn" role="status">
      <Icon name="alert" size={18} />
      <span>
        {t("Birlikte paylaşılırsa kişi tanınabilir (bağlanabilirlik: {duzey}). Takma ad anonimleştirme değildir.", { duzey: t(linkability.duzey) })}
        {linkability.uyari.map((u, i) => (
          <span key={i} style={{ display: "block" }}>{t(u)}</span>
        ))}
      </span>
      <button className="icon-btn" aria-label={t("Kapat")} onClick={() => setLinkability(null)}>
        <Icon name="x" size={14} />
      </button>
    </div>
  );

  const errorOnlyBanner = error && (
    <div className="banner err" role="alert">
      <Icon name="alert" size={18} />
      <span>{t(error)}</span>
      {/kasa/i.test(error) && settings?.vault.exists && !settings.vault.unlocked && (
        <button className="btn small" onClick={() => setUnlockOpen(true)}>
          <Icon name="unlock" size={14} /> {t("Kilidi aç")}
        </button>
      )}
      <button className="icon-btn" aria-label={t("Kapat")} onClick={() => setError(null)}>
        <Icon name="x" size={14} />
      </button>
    </div>
  );

  const errorBanner = (error || linkability) && (
    <>
      {errorOnlyBanner}
      {linkabilityBanner}
    </>
  );

  const pagesOut = format === "pdf" ? dropped.size : 0;
  const saveLabel =
    busy === "mask"
      ? t("Kaydediliyor…")
      : included.length === 0 && pagesOut > 0
      ? t("Sayfayı çıkar ve kaydet")
      : t("{n} bilgiyi maskele ve kaydet", { n: included.length });
  const passwordOk = !(format === "pdf" && protect) || password.length >= MIN_PASSWORD;
  const canSave = busy === null && unlocated === 0 && passwordOk && (included.length > 0 || pagesOut > 0);

  function preview(v: View) {
    if (!source || !format) return null;
    const effectiveView: View = !scan ? "orijinal" : v;
    const plain = !scan;
    const common = {
      source,
      target: done?.target ?? null,
      findings: allFindings,
      excluded,
      methodOf,
      hovered,
      onHover: setHovered,
      onToggle: toggleFinding,
      view: effectiveView,
      plain,
    };
    if (format === "sunum") return <SlidePreview {...common} page={previewPage} onPage={setPreviewPage} />;
    if (format === "tablo")
      return (
        <SheetPreview
          {...common}
          lines={areas
            .filter((a) => a.sheet !== undefined && !excluded.has(a.id))
            .map((a) => ({ id: a.id, sheet: a.sheet!, axis: a.axis!, index: a.index!, method: a.method ?? "karartma" }))}
          onToggleLine={scan && !done ? toggleSheetLine : undefined}
          onLineMethod={scan && !done ? setLineMethod : undefined}
        />
      );
    if (format === "word") return <WordPreview {...common} />;
    if (format === "metin" || format === "arsiv") return <TextPreview {...common} text={scan?.text ?? docText ?? ""} isXml={extOf(source) === "xml"} />;
    return (
      <PagePreview
        {...common}
        pages={scan?.pages}
        onAddArea={addArea}
        onRemoveArea={removeArea}
        page={previewPage}
        onPage={setPreviewPage}
        dropped={format === "pdf" && effectiveView !== "kaydedilen" ? dropped : undefined}
        onToggleDrop={format === "pdf" && effectiveView !== "kaydedilen" && !done && !!scan ? toggleDrop : undefined}
        readOnly={!!done || !scan}
      />
    );
  }

  function renderFilePreview(filePath: string, page: number, onPage: (p: number) => void): ReactNode {
    const fmt = formatOf(filePath, formats);
    const noop = () => {};
    const common = {
      source: filePath,
      target: null,
      findings: [] as PdfFinding[],
      excluded: new Set<string>(),
      methodOf: () => "karartma",
      hovered: null,
      onHover: noop,
      onToggle: noop,
      view: "orijinal" as const,
      plain: true,
    };
    if (fmt === "sunum") return <SlidePreview {...common} page={page} onPage={onPage} />;
    if (fmt === "tablo") return <SheetPreview {...common} />;
    if (fmt === "word") return <WordPreview {...common} />;
    if (fmt === "metin" || fmt === "arsiv") return <ReadOnlyTextFilePreview path={filePath} />;
    return (
      <PagePreview
        {...common}
        onAddArea={noop}
        onRemoveArea={noop}
        page={page}
        onPage={onPage}
        readOnly
      />
    );
  }

  const nextInQueue = queue.find((p) => p !== source && !saved[p]);
  const queueBar = queue.length > 1 && (
    <nav className="queue" aria-label={t("Belgeler")}>
      <span className="queue-count">
        {t("{done}/{total} kaydedildi", { done: queue.filter((p) => saved[p]).length, total: queue.length })}
      </span>
      <div className="queue-list">
        {queue.map((p, i) => (
          <button
            key={p}
            className={["queue-item", p === source ? "on" : "", saved[p] ? "done" : ""].join(" ")}
            aria-current={p === source}
            disabled={busy === "mask"}
            title={p}
            onClick={() => switchDoc(p)}
          >
            <span className="queue-num">{saved[p] ? <Icon name="check" size={12} /> : i + 1}</span>
            <span className="queue-name">{splitPath(p).name}</span>
          </button>
        ))}
      </div>
    </nav>
  );

  // ---------------------------------------------------------------- ekranlar

  const docSummaries = useMemo(() => {
    void cacheTick;
    const out: Record<string, { scanned: boolean; included: number; total: number }> = {};
    const allDocs = queue.length > 0 ? queue : source ? [source] : [];
    for (const p of allDocs) {
      if (p === source && scan) {
        out[p] = { scanned: true, included: included.length, total: allFindings.length };
      } else {
        const st = docCache.current.get(p);
        if (st) {
          const tot = st.scan.findings.length + st.areas.length;
          const inc = st.scan.findings.filter((f) => !st.excluded.has(f.id)).length + st.areas.filter((a) => !st.excluded.has(a.id)).length;
          out[p] = { scanned: true, included: inc, total: tot };
        } else {
          out[p] = { scanned: false, included: 0, total: 0 };
        }
      }
    }
    return out;
  }, [cacheTick, queue, source, scan, included.length, allFindings.length]);

  const sharedLayoutProps: SharedLayoutProps = {
    source,
    target,
    format,
    scan,
    done,
    busy,
    view,
    setView,
    previewPage,
    setPreviewPage,
    queue,
    saved,
    nextInQueue,
    switchDoc,
    pickSource,
    pickFolder,
    pickTarget,
    goHome: handleHomeClick,
    runMask,
    runMaskAll: () => void runMaskAll(),
    plannedFiles,
    folderRoot,
    folderTargetDir,
    updateFolderTargetDir,
    inspectedRecentTarget,
    setInspectedRecentTarget,
    batchProgress,
    docSummaries,
    setDone,
    openSettings: (profId?: string) => {
      if (profId) setSelectedProfileId(profId);
      setShowSettings(true);
    },
    openUnlock: () => setUnlockOpen(true),
    vaultLocked: Boolean(settings?.vault.exists && !settings.vault.unlocked),
    profile,
    profiles: settings?.profiles ?? [],
    selectedProfileId: selectedProfile?.id ?? "",
    onSelectProfileId: handleSelectProfileId,
    methodPreset,
    onSelectMethodPreset: setMethodPreset,
    appliedProfileId: profile?.id ?? "",
    appliedMethodPreset,
    onApplyRules: () => void applyRulesAndScan(),
    dataTypes,
    allFindings,
    included,
    sure,
    unsure,
    groups,
    excluded,
    dropped,
    unlocated,
    canSave,
    saveLabel,
    methodOf,
    offByRule,
    scanRules,
    hovered,
    setHovered,
    toggleFinding,
    toggleGroup,
    setMany,
    toggleDrop,
    clearDropped: () => setDropped(new Set()),
    lastOff,
    clearLastOff: () => setLastOff([]),
    setError,
    blackoutTypes: extra.blackout,
    addBlackout: (types) => updateExtra({ blackout: [...new Set([...extra.blackout, ...types])] }),
    clearBlackout: () => updateExtra({ blackout: [] }),
    homeTab,
    setHomeTab,
    recent,
    removeRecent: (tg: string | string[]) => {
      const targets = Array.isArray(tg) ? tg : [tg];
      const targetSet = new Set(targets);
      setRecent((prev) => prev.filter((x) => !targetSet.has(x.target)));
      void engineCall<Recent[]>("history.delete", { targets })
        .then((dbList) => {
          if (Array.isArray(dbList)) setRecent(dbList);
        })
        .catch(() => {
          // yok say
        });
    },
    clearRecent: () => {
      setRecent([]);
      try {
        localStorage.removeItem(RECENT_KEY);
      } catch {
        // yok say
      }
      void engineCall<Recent[]>("history.clear").catch(() => {
        // yok say
      });
    },
    revealInDir: (p) => void revealItemInDir(p),
    renderFilePreview,
    openRecentDoc: (p) => chooseSource(p),
    errorBanner,
    previewNode: preview,
    searchHideNode: (
      <SearchHide
        terms={extra.terms}
        findings={allFindings}
        busy={busy === "scan"}
        onAdd={(w) => updateExtra({ terms: [...extra.terms, w] })}
        onRemove={(w) => updateExtra({ terms: extra.terms.filter((x) => x !== w) })}
      />
    ),
    // Parolalı kopya (TAKIP 1.81, karar: 2026-11-07-parolali-kopya-kalacak.md); yalnızca PDF.
    passwordNode:
      format === "pdf" ? (
        <>
        <FlattenLine on={flatten} onToggle={toggleFlatten} />
        <PasswordLine
          on={protect}
          value={password}
          onToggle={(v) => {
            setProtect(v);
            setDone(null);
          }}
          onChange={setPassword}
        />
        </>
      ) : null,
    saveLineNode: <SaveLine source={source} target={target} onChange={pickTarget} />,
    leftOpenNode: <LeftOpen findings={allFindings.filter((f) => excluded.has(f.id) && onKeptPage(f))} />,
  };

  let screen: ReactNode;
  if (showSettings && settings) {
    screen = (
      <SettingsPage
        dataTypes={dataTypes}
        saved={settings}
        terms={terms}
        initialProfileId={selectedProfileId}
        onSaved={(s, tr) => {
          setSettings(s);
          setTerms(tr);
          setSelectedProfileId(s.active);
          setAppliedProfileId(s.active);
        }}
        onVault={setVault}
        onBack={() => setShowSettings(false)}
      />
    );
  } else if (folder) {
    screen = (
      <main className="v2-main folder-screen">
        {errorBanner}
        <div className="folder-bar">
          <span className="file-icon">
            <Icon name="folder" size={18} />
          </span>
          <span className="file-text" title={folder}>
            <b>{splitPath(folder).name}</b>
            <small>{splitPath(folder).dir}</small>
          </span>
          <label className="check-row">
            <input type="checkbox" checked={recursive} disabled={batchRunning} onChange={(e) => setRecursive(e.target.checked)} />
            {t("Alt klasörler dahil")}
          </label>
        </div>
        {plan && (
          <p className="hint save-line">
            {rich(t("Güvenli kopyalar şuraya kaydedilir: {dir}"), { dir: <b>{plan.target_dir}</b> })}{" "}
            <button className="link-btn" disabled={batchRunning} onClick={pickTargetDir}>
              {t("Değiştir")}
            </button>
          </p>
        )}
        <BatchMain plan={plan} rules={rules} onRunningChange={onBatchRunning} />
      </main>
    );
  } else if (layoutMode === "studio") {
    screen = <StudioWorkspace {...sharedLayoutProps} />;
  } else if (layoutMode === "wizard") {
    screen = <WizardWorkspace {...sharedLayoutProps} />;
  } else if (!source && homeTab === "metin") {
    screen = (
      <main className="v2-main home paste">
        <HomeTabs value={homeTab} onChange={setHomeTab} />
        <PasteScreen rules={scanRules} offByRule={offByRule} methodOf={methodOf} />
      </main>
    );
  } else if (!source) {
    screen = (
      <main className="v2-main home">
        {errorBanner}
        <HomeTabs value={homeTab} onChange={setHomeTab} />
        <button className="home-drop" onClick={pickSource}>
          <span className="home-drop-icon">
            <Icon name="upload" size={34} />
          </span>
          <b>{t("Belgeleri buraya bırakın")}</b>
          <span>{t("İsim, TC kimlik, telefon, adres gibi kişisel bilgileri bulup gizliyoruz. Ne maskeleneceğini sonra siz seçersiniz.")}</span>
          <span className="home-pick">{t("Bilgisayardan seç")}</span>
          <span className="home-formats">{t("PDF · Word · Excel · PowerPoint · fotoğraf · XML, TXT, CSV, ZIP · birden çok dosya olabilir")}</span>
        </button>
        <p className="home-alt">
          {t("Bir klasördeki bütün belgeler mi?")}{" "}
          <button className="link-btn" onClick={pickFolder}>
            {t("Klasör seçin")}
          </button>
        </p>
        {recent.length > 0 && (
          <section className="recent">
            <div className="recent-head">
              <h2>{t("Son yapılanlar")}</h2>
              <button
                className="link-btn subtle"
                onClick={() => {
                  setRecent([]);
                  saveRecent([]);
                }}
              >
                {t("Listeyi temizle")}
              </button>
            </div>
            <ul>
              {recent.map((r) => (
                <li key={r.target}>
                  <Badge path={r.path} />
                  <span className="recent-name" title={r.target}>
                    {splitPath(r.path).name}
                  </span>
                  <span className="recent-meta">{t("{n} bilgi maskelendi", { n: r.count })}{r.agent ? ` · ${t("Ajan")} (${r.agent})` : ""}</span>
                  <button className="link-btn" onClick={() => revealItemInDir(r.target)}>
                    {t("Klasörde göster")}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        <p className="home-promise">
          <Icon name="shield" size={14} /> {t("Belge bilgisayarınızdan çıkmaz · Orijinal dosyaya dokunulmaz")}
        </p>
      </main>
    );
  } else if (!scan) {
    screen = (
      <main className="v2-main center">
        {queueBar}
        {errorBanner}
        {busy === "scan" ? (
          <div className="loading-card">
            <span className="spinner" aria-hidden />
            <b>{t("Kişisel bilgiler aranıyor…")}</b>
            <span>{splitPath(source).name}</span>
            {(format === "gorsel" || format === "pdf") && <small>{t("Fotoğraf ve taranmış sayfalarda biraz sürebilir.")}</small>}
          </div>
        ) : (
          <div className="loading-card">
            <b>{t("Belge okunamadı")}</b>
            <button className="btn" onClick={goHome}>
              {t("Başka belge seç")}
            </button>
          </div>
        )}
      </main>
    );
  } else if (done) {
    screen = (
      <main className={queue.length > 1 ? "v2-split with-queue" : "v2-split"}>
        {queueBar}
        <section className="v2-doc">
          {done.encrypted && (
            <p className="hint enc-note">
              <Icon name="lock" size={14} /> {t("Kopya parolalı olduğu için burada kaydedilmeden önceki görünüm gösteriliyor.")}
            </p>
          )}
          {preview(done.encrypted ? "maskeli" : "kaydedilen")}
        </section>
        <aside className="v2-side">
          <span className="done-icon">
            <Icon name="check" size={28} />
          </span>
          <div>
            <h1 className="side-title">{t("Güvenli kopya hazır")}</h1>
            <p className="side-sub">
              {done.warnings.some((w) => w.includes("imza izleri")) ? t("{n} kişisel bilgi belgeden silindi, ama imza bölgesinde izler kalmış olabilir. Kopyayı açıp imzayı gözle kontrol edin.", { n: done.masked }) : t("{n} kişisel bilgi belgeden gerçekten silindi. Dosya yeniden okunarak kontrol edildi; iz kalmadı.", { n: done.masked })}
            </p>
            <SonucNotu />
          </div>
          <ul className="done-list">
            <li>
              <Icon name="check" size={14} /> {t("Yazar, yorum, konum gibi gizli bilgiler temizlendi")}
            </li>
            {!!done.dropped && (
              <li>
                <Icon name="check" size={14} /> {t("{n} sayfa kopyadan çıkarıldı", { n: done.dropped })}
              </li>
            )}
            {done.encrypted && (
              <li>
                <Icon name="lock" size={14} /> {t("Parolayla korundu; parolayı alıcıya ayrı bir yoldan iletin")}
              </li>
            )}
            <li>
              <Icon name="check" size={14} /> {t("Orijinal dosyaya dokunulmadı")}
            </li>
            <li>
              <Icon name="check" size={14} /> {t("Hiçbir yere gönderilmedi")}
            </li>
            {done.warnings.map((w) => (
              <li key={w} className="done-warning">
                <Icon name="alert" size={14} /> {t(w)}
              </li>
            ))}
          </ul>
          <LeftOpen findings={allFindings.filter((f) => excluded.has(f.id) && onKeptPage(f))} />
          <PathChanged reason={done.changed} />
          <code className="path-line">{done.target}</code>
          <div className="side-spacer" />
          <div className="side-actions">
            {nextInQueue ? (
              <>
                <button className="btn primary big" onClick={() => switchDoc(nextInQueue)}>
                  {t("Sıradaki belge")} <Icon name="arrowRight" />
                </button>
                <p className="hint center next-name">{splitPath(nextInQueue).name}</p>
                <button className="btn big" onClick={() => revealItemInDir(done.target)}>
                  <Icon name="folder" /> {t("Klasörde göster")}
                </button>
              </>
            ) : (
              <>
                <button className="btn primary big" onClick={() => revealItemInDir(done.target)}>
                  <Icon name="folder" /> {t("Klasörde göster")}
                </button>
                <button className="btn big" onClick={goHome}>
                  {queue.length > 1 ? t("Bitti, başa dön") : t("Yeni belge")}
                </button>
              </>
            )}
            <button className="link-btn center" onClick={() => setDone(null)}>
              {t("Seçimleri değiştirip yeniden kaydet")}
            </button>
          </div>
        </aside>
      </main>
    );
  } else {
    // Sonuç: üstte bulunanlar gruplar hâlinde kart kart (dokununca açılıp kapanır), altında belge.
    screen = (
      <main className="v2-main result">
        {queueBar}
        {errorBanner}
        <header className="result-head">
          <span className="file-chip">
            <Badge path={source} /> {splitPath(source).name}
          </span>
          <h1>{allFindings.length ? t("Bu belgede {n} kişisel bilgi bulduk", { n: allFindings.length }) : t("Kişisel bilgi bulamadık")}</h1>
          <p>
            {sure.length
              ? t("Maskelenecekler işaretli. Açık kalmasını istediğinize dokunun.")
              : allFindings.length
              ? t("Kesin bir bilgi bulamadık; aşağıda emin olamadıklarımız var.")
              : t("Gözden kaçan bir şey olduğunu düşünüyorsanız belgede kendiniz işaretleyebilirsiniz.")}
          </p>
        </header>

        {groups.length > 0 && (
          <div className="cat-grid">
            {groups.map((g) => {
              const allOn = g.on === g.items.length;
              const state = allOn ? "on" : g.on ? "part" : "off";
              return (
                <button key={g.category.key} className={`cat-card ${state}`} aria-pressed={allOn} onClick={() => toggleGroup(g.items)}>
                  <span className="cat-check" aria-hidden>
                    {state !== "off" && <Icon name={state === "on" ? "check" : "minus"} size={14} />}
                  </span>
                  <Icon name={g.category.icon} size={26} />
                  <b>{t(g.category.label)}</b>
                  <span>{groupText(g, dataTypes, methodOf)}</span>
                </button>
              );
            })}
          </div>
        )}

        <ReviewExtras
          unsure={unsure}
          sure={sure}
          excluded={excluded}
          onToggle={toggleFinding}
          onSetMany={setMany}
          lastOff={lastOff}
          onClearLastOff={() => setLastOff([])}
          onError={setError}
          methodOf={methodOf}
          onBlackout={(types) => updateExtra({ blackout: [...new Set([...extra.blackout, ...types])] })}
        />

        <SearchHide
          terms={extra.terms}
          findings={allFindings}
          busy={busy === "scan"}
          onAdd={(w) => updateExtra({ terms: [...extra.terms, w] })}
          onRemove={(w) => updateExtra({ terms: extra.terms.filter((x) => x !== w) })}
        />

        <div className="result-actions">
          <button className="btn primary big" disabled={!canSave} onClick={runMask}>
            {allFindings.length === 0 && pagesOut === 0 ? t("Maskelenecek bilgi yok") : saveLabel}
          </button>
        </div>
        {unlocated > 0 && (
          <p className="warn-text center">
            {t("{n} bilginin belgedeki yeri bulunamadı. Aşağıda belgede işaretine tıklayıp kaldırın.", { n: unlocated })}
          </p>
        )}
        {allFindings.length > 0 && included.length === 0 && dropped.size === 0 && (
          <p className="hint center">{t("Hiçbir şey maskelenmeyecek; en az bir kartı işaretleyin.")}</p>
        )}
        {format === "pdf" && dropped.size > 0 && (
          <p className="hint center">
            {t("{pages}. sayfa kopyadan çıkarılacak.", { pages: [...dropped].sort((a, b) => a - b).join(", ") })}{" "}
            <button className="link-btn" onClick={() => setDropped(new Set())}>
              {t("Geri al")}
            </button>
          </p>
        )}
        <SaveLine source={source} target={target} onChange={pickTarget} />
        {format === "pdf" && <FlattenLine on={flatten} onToggle={toggleFlatten} />}
        {format === "pdf" && (
          <PasswordLine
            on={protect}
            value={password}
            onToggle={(v) => {
              setProtect(v);
              setDone(null);
            }}
            onChange={setPassword}
          />
        )}
        {extra.blackout.length > 0 && (
          <p className="hint center">
            {t("Bu belgede kısmi gösterim yerine tamamen karartılıyor: {list}.", {
              list: extra.blackout.map((k) => t(dataTypes.find((d) => d.key === k)?.label ?? k)).join(", "),
            })}{" "}
            <button className="link-btn" onClick={() => updateExtra({ blackout: [] })}>
              {t("Geri al")}
            </button>
          </p>
        )}
        {profile && (
          <p className="hint rules-line">
            {rich(t("Maskeleme kuralları: {ad}"), { ad: <b>{profile.name}</b> })}{" "}
            <button className="link-btn" onClick={() => setShowSettings(true)}>
              {t("Ayarlar'da değiştir")}
            </button>
          </p>
        )}

        {(scan.warnings.length > 0 || (settings?.vault.exists && !settings.vault.unlocked)) && (
          <details className="notes">
            <summary>
              <Icon name="alert" size={14} /> {t("Bilmeniz gerekenler")}
            </summary>
            <ul>
              {settings?.vault.exists && !settings.vault.unlocked && (
                <li>
                  {t("Özel ifadeleriniz kilitli olduğu için aranmadı.")}{" "}
                  <button className="link-btn" onClick={() => setUnlockOpen(true)}>
                    {t("Kilidi aç")}
                  </button>
                </li>
              )}
              {scan.warnings.map((w) => (
                <li key={w}>{t(w)}</li>
              ))}
            </ul>
          </details>
        )}

        <section className="result-doc" aria-label={t("Belge")}>
          <div className="result-doc-head">
            <h2>{t("Belge")}</h2>
            <ViewToggle value={view === "orijinal" ? "orijinal" : "maskeli"} onChange={setView} labels={[t("Orijinal"), t("Maskelenmiş hâli")]} />
          </div>
          <p className="hint">
            {t("İşaretli yerlere tıklayarak tek tek açıp kapatabilirsiniz.")}
            {(format === "pdf" || format === "gorsel") && (
              <>
                {" "}
                {rich(t("Gözden kaçan bir yer varsa {alan} ile fareyle işaretleyin."), { alan: <b>{t("Alan seç")}</b> })}
              </>
            )}
            {format === "pdf" && scan.pages > 1 && <> {t("Kimlik fotokopisi gibi bir sayfanın tamamını kopyadan çıkarabilirsiniz.")}</>}
          </p>
          {preview(view === "kaydedilen" ? "maskeli" : view)}
        </section>
      </main>
    );
  }

  return (
    <div className="app v2">
      <header className="v2-top">
        <button className="logo-btn" onClick={handleHomeClick} title={t("Ana Sayfa")} disabled={batchRunning}>
          <Logo />
        </button>
        <div className="top-end">
          {(source || folder || queue.length > 0 || showSettings || inspectedRecentTarget) && (
            <button
              type="button"
              className="btn top-home-btn"
              onClick={() => (showSettings ? setShowSettings(false) : handleHomeClick())}
              disabled={busy !== null || batchRunning}
              title={showSettings ? t("Çalışma alanına dön") : t("Ana sayfaya dön")}
            >
              <Icon name="arrowLeft" size={16} />
              <span>{showSettings ? t("Geri Dön") : t("Ana Sayfa")}</span>
            </button>
          )}
          <EngineDot state={engine} />
          <ThemeSwitch />
          <button
            className={showSettings ? "btn settings-btn on" : "btn settings-btn"}
            disabled={batchRunning}
            onClick={() => setShowSettings(!showSettings)}
          >
            <Icon name="settings" size={17} /> {t("Ayarlar")}
          </button>
        </div>
      </header>

      {yeniSurum && <GuncellemeSeridi yeni={yeniSurum} onKapat={surumuGormezdenGel} />}

      {screen}

      {confirmGoHome && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => e.target === e.currentTarget && setConfirmGoHome(false)}
        >
          <div className="modal studio-confirm-modal" role="dialog" aria-modal="true">
            <div className="modal-head">
              <span className="file-icon danger">
                <Icon name="alert" size={18} />
              </span>
              <div>
                <h2>{t("Ana Sayfaya dönülsün mü?")}</h2>
                <p className="hint">
                  {t("Taranan kişisel bilgiler ve yaptığınız seçimler temizlenecektir. Devam eden işlemi sonlandırıp Ana Sayfa'ya dönmek istediğinize emin misiniz?")}
                </p>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label={t("Kapat")}
                onClick={() => setConfirmGoHome(false)}
              >
                <Icon name="x" size={14} />
              </button>
            </div>
            <div className="studio-confirm-actions">
              <button
                type="button"
                className="btn"
                onClick={() => setConfirmGoHome(false)}
              >
                {t("Vazgeç")}
              </button>
              <button
                type="button"
                className="btn danger"
                onClick={() => {
                  setConfirmGoHome(false);
                  goHome();
                }}
              >
                <Icon name="arrowLeft" size={14} /> {t("Evet, Ana Sayfaya Dön")}
              </button>
            </div>
          </div>
        </div>
      )}

      {unlockOpen && (
        <UnlockDialog
          onUnlocked={(tr) => {
            setVault({ exists: true, unlocked: true }, tr);
            setUnlockOpen(false);
          }}
          onClose={() => setUnlockOpen(false)}
        />
      )}

      {dragging && !showSettings && (
        <div className="drop-overlay">
          <div>
            <Icon name="upload" size={36} />
            <p>{t("Belgeyi ya da klasörü bırakın")}</p>
          </div>
        </div>
      )}
    </div>
  );
}

interface DocExtra {
  terms: string[];
  blackout: string[];
}

const NO_EXTRA: DocExtra = { terms: [], blackout: [] };
const MIN_PASSWORD = 6;

/** "Ara ve maskele": belgeye özel sözcük ya da ifade; geçtiği her yer maskelenecekler arasına eklenir. */
function SearchHide({
  terms,
  findings,
  busy,
  onAdd,
  onRemove,
}: {
  terms: string[];
  findings: PdfFinding[];
  busy: boolean;
  onAdd: (term: string) => void;
  onRemove: (term: string) => void;
}) {
  const t = useT();
  const [text, setText] = useState("");
  const value = text.trim();
  const fold = (s: string) => s.toLocaleLowerCase("tr");
  const count = (term: string) => findings.filter((f) => f.type === "ozel_ifade" && fold(f.source) === fold(term)).length;
  function submit() {
    if (value.length < 2 || terms.some((x) => fold(x) === fold(value))) return;
    onAdd(value);
    setText("");
  }
  return (
    <section className="search-hide" aria-label={t("Ara ve maskele")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Icon name="search" size={17} />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("Ara ve maskele: ör. proje adı, karşı taraf şirketi")}
          aria-label={t("Belgede aranacak sözcük")}
        />
        <button className="btn small" type="submit" disabled={value.length < 2 || busy}>
          {t("Bul ve maskele")}
        </button>
      </form>
      {terms.length > 0 && (
        <ul>
          {terms.map((term) => {
            const n = count(term);
            return (
              <li key={term} className={n === 0 && !busy ? "none" : undefined}>
                <b>“{term}”</b>
                <span>{busy ? t("aranıyor…") : n === 0 ? t("bulunamadı") : t("{n} yerde · Özel ifadeler kartında", { n })}</span>
                <button className="icon-btn" aria-label={t("“{term}” aramasını kaldır", { term })} onClick={() => onRemove(term)}>
                  <Icon name="x" size={12} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** PDF kopyasını parolayla koruma. Parola yalnızca bellekte; motora kaydetme anında gider. */
function FlattenLine({ on, onToggle }: { on: boolean; onToggle: (on: boolean) => void }) {
  const t = useT();
  return (
    <div className={on ? "password-line on" : "password-line"}>
      <label className="check-row">
        <input type="checkbox" checked={on} onChange={(e) => onToggle(e.target.checked)} />
        <Icon name="shield" size={14} /> {t("Düzleştir (yüksek riskli belge)")}
      </label>
      {on && (
        <span className="hint">
          {t("Sayfalar görüntüye çevrilip yeniden OCR ile okunur; metin katmanı, gizli metin, ek ve meta veri kopyaya geçmez. E-imza kopyada kalmaz.")}
        </span>
      )}
    </div>
  );
}

function PasswordLine({
  on,
  value,
  onToggle,
  onChange,
}: {
  on: boolean;
  value: string;
  onToggle: (on: boolean) => void;
  onChange: (v: string) => void;
}) {
  const t = useT();
  const [show, setShow] = useState(false);
  return (
    <div className={on ? "password-line on" : "password-line"}>
      <label className="check-row">
        <input type="checkbox" checked={on} onChange={(e) => onToggle(e.target.checked)} />
        <Icon name="lock" size={14} /> {t("Kopyayı parolayla koru")}
      </label>
      {on && (
        <>
          <span className="password-field">
            <input
              type={show ? "text" : "password"}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={t("En az {n} karakter", { n: MIN_PASSWORD })}
              autoComplete="new-password"
              aria-label={t("Kopyanın parolası")}
            />
            <button className="icon-btn" type="button" aria-label={show ? t("Parolayı gizle") : t("Parolayı göster")} onClick={() => setShow(!show)}>
              <Icon name={show ? "eyeOff" : "eye"} size={15} />
            </button>
          </span>
          <small>
            {value.length > 0 && value.length < MIN_PASSWORD
              ? t("Parola en az {n} karakter olmalı.", { n: MIN_PASSWORD })
              : t("Parolayı alıcıya ayrı bir yoldan (telefon, mesaj) iletin. Uygulama parolayı saklamaz.")}
          </small>
        </>
      )}
    </div>
  );
}

/** Son kontrol: kopyada bilerek açık bırakılanlar (değer gösterilmez, yalnızca tür ve sayı). */
function LeftOpen({ findings }: { findings: PdfFinding[] }) {
  const t = useT();
  if (findings.length === 0) {
    return (
      <div className="left-open ok">
        <Icon name="shield" size={16} />
        <span>{t("Bulunan kişisel bilgilerin hepsi kopyada gizli.")}</span>
      </div>
    );
  }
  const counts = new Map<string, number>();
  for (const f of findings) {
    const label = f.confidence === UNCERTAIN ? t("{label} (emin olunamayan)", { label: t(f.type_label) }) : t(categoryOf(f.type).label);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return (
    <div className="left-open">
      <b>
        <Icon name="eye" size={15} /> {t("Kopyada açık kalanlar")}
      </b>
      <ul>
        {[...counts].map(([label, n]) => (
          <li key={label}>
            <span>{label}</span>
            <span>{n}</span>
          </li>
        ))}
      </ul>
      <small>{t("Bunları bilerek açık bıraktınız. Değiştirmek için “Seçimleri değiştirip yeniden kaydet”.")}</small>
    </div>
  );
}

function HomeTabs({ value, onChange }: { value: "belge" | "metin"; onChange: (v: "belge" | "metin") => void }) {
  const t = useT();
  return (
    <div className="home-tabs" role="tablist" aria-label={t("Ne temizlenecek?")}>
      <button role="tab" aria-selected={value === "belge"} className={value === "belge" ? "on" : undefined} onClick={() => onChange("belge")}>
        <Icon name="files" size={17} /> {t("Belge")}
      </button>
      <button role="tab" aria-selected={value === "metin"} className={value === "metin" ? "on" : undefined} onClick={() => onChange("metin")}>
        <Icon name="text" size={17} /> {t("Metin yapıştır")}
      </button>
    </div>
  );
}

function ViewToggle({
  value,
  onChange,
  labels,
}: {
  value: "orijinal" | "maskeli";
  onChange: (v: View) => void;
  labels: [string, string];
}) {
  const t = useT();
  return (
    <div className="segmented view-toggle" role="tablist" aria-label={t("Görünüm")}>
      {(["orijinal", "maskeli"] as const).map((v, i) => (
        <button key={v} role="tab" aria-selected={value === v} className={value === v ? "on" : undefined} onClick={() => onChange(v)}>
          {labels[i]}
        </button>
      ))}
    </div>
  );
}

function SaveLine({ source, target, onChange }: { source: string | null; target: string | null; onChange: () => void }) {
  const t = useT();
  if (!target) return null;
  const { name, dir } = splitPath(target);
  // Hedef değiştirildiyse etiket seçilen klasörü söyler (TAKIP 1.75).
  const yaninda = !source || splitPath(source).dir.toLowerCase() === dir.toLowerCase();
  const klasor = splitPath(dir).name || dir;
  return (
    <p className="hint save-line">
      {yaninda
        ? rich(t("Kopya orijinalin yanına {ad} adıyla kaydedilir."), { ad: <b title={target}>{name}</b> })
        : rich(t("Kopya {klasor} klasörüne {ad} adıyla kaydedilir."), {
            klasor: <b title={dir}>{klasor}</b>,
            ad: <b title={target}>{name}</b>,
          })}{" "}
      <button className="link-btn" onClick={onChange}>
        {t("Değiştir")}
      </button>
    </p>
  );
}

function ReadOnlyTextFilePreview({ path }: { path: string }) {
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const t = useT();

  useEffect(() => {
    let alive = true;
    setText(null);
    setErr(null);
    engineCall<{ text: string }>("doc.text", { path })
      .then((r) => alive && setText(r.text))
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, [path]);

  if (err) return <p className="field-error">{t(err)}</p>;
  if (text === null) return <div className="sheet loading" style={{ aspectRatio: "16 / 9" }} />;
  return (
    <TextPreview
      text={text}
      isXml={extOf(path) === "xml"}
      findings={[]}
      excluded={new Set()}
      methodOf={() => "karartma"}
      hovered={null}
      onHover={() => {}}
      onToggle={() => {}}
      plain
      view="orijinal"
    />
  );
}

function EngineDot({ state }: { state: EngineState }) {
  const t = useT();
  const cls = state.kind === "ready" ? "ok" : state.kind === "error" ? "err" : "";
  const text =
    state.kind === "ready"
      ? t("Motor hazır ({surum})", { surum: state.version.engine })
      : state.kind === "error"
      ? t("Motor çalışmıyor: {mesaj}", { mesaj: state.message })
      : t("Motor başlatılıyor");
  return (
    <span className={`engine-dot ${cls}`} title={text} aria-label={text} role="img">
      {state.kind === "error" && t("Motor çalışmıyor")}
    </span>
  );
}

export default App;
