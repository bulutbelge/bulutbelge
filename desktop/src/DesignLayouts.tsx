import { CSSProperties, Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { CategoryGroup, groupText } from "./categories";
import { DataTypeInfo, DocFormat, engineCall, extOf, MaskResult, PdfFinding, Rules, ScanResult } from "./engine";
import { PasteScreen } from "./PasteScreen";
import { ReviewExtras } from "./ReviewExtras";
import { localeCode, t, useT } from "./i18n";
import { enabledTypeCount, Profile } from "./settings";
import { SonucNotu } from "./Hakkinda";
import { sonucAciklamasi, sonucBasligi } from "./KacakKayit";
import { Icon, IconName, PathChanged } from "./ui";

export type LayoutMode = "studio" | "wizard" | "classic";
export type MethodPreset = "profil" | "karartma" | "etiket" | "kismi" | "bulanik";

export interface MethodPresetOption {
  key: MethodPreset;
  label: string;
  sample: string;
  desc: string;
}

export const METHOD_PRESETS: MethodPresetOption[] = [
  {
    key: "profil",
    get label() {
      return t("Kural Takımı Varsayılanı");
    },
    get sample() {
      return t("Kurala göre");
    },
    get desc() {
      return t("Her bilgi türü için kural takımında tanımlı yöntem uygulanır.");
    },
  },
  {
    key: "karartma",
    get label() {
      return t("Tam Karartma");
    },
    sample: "████████",
    get desc() {
      return t("Bulunan tüm kişisel bilgiler siyah kutu ile kapatılır.");
    },
  },
  {
    key: "etiket",
    get label() {
      return t("Etiketleme");
    },
    get sample() {
      return t("[TC NO]");
    },
    get desc() {
      return t("Bilginin yerine veri türünün etiketi ([AD SOYAD], [IBAN] vb.) yazılır.");
    },
  },
  {
    key: "kismi",
    get label() {
      return t("Kısmi Gösterim (Son 4 / Baş Harf)");
    },
    sample: "**** 1234",
    get desc() {
      return t("Numaralarda son 4 hane, isimde baş harf, adreste il/ilçe açık bırakılır.");
    },
  },
  {
    key: "bulanik",
    get label() {
      return t("Bulanıklaştırma");
    },
    sample: "░░░░░░░░",
    get desc() {
      return t("Bilgi silinir ve yerine buzlu cam görünümü yerleştirilir.");
    },
  },
];

const PARTIAL_PREFERENCE = ["son4", "bas_harf", "alan_adi", "il_ilce", "yil", "plaka_il", "genel"];

export function resolveMethodForType(
  typeKey: string,
  preset: MethodPreset,
  baseMethod: string,
  dataTypes: DataTypeInfo[],
): string {
  if (preset === "profil") return baseMethod;
  const dt = dataTypes.find((d) => d.key === typeKey);
  const allowed = dt ? dt.methods.map((m) => m.key) : null;
  if (preset === "karartma") return !allowed || allowed.includes("karartma") ? "karartma" : baseMethod;
  if (preset === "etiket") return !allowed || allowed.includes("etiket") ? "etiket" : baseMethod;
  if (preset === "bulanik") return !allowed || allowed.includes("bulanik") ? "bulanik" : baseMethod;
  if (preset === "kismi") {
    if (allowed) {
      for (const candidate of PARTIAL_PREFERENCE) {
        if (allowed.includes(candidate)) return candidate;
      }
      return baseMethod;
    }
    return baseMethod;
  }
  return baseMethod;
}

const LAYOUT_KEY = "bulutbelge.layout-mode";

export function readLayoutMode(_defaultMode: LayoutMode): LayoutMode {
  return "studio";
}

export function saveLayoutMode(mode: LayoutMode) {
  try {
    localStorage.setItem(LAYOUT_KEY, mode);
  } catch {
    // yok say
  }
}

export interface PurposeOption {
  id: string;
  label: string;
  short: string;
  desc: string;
  icon: IconName;
}

export const PURPOSES: PurposeOption[] = [
  {
    id: "musteri",
    get label() {
      return t("Müşteriye / Dış Alıcıya");
    },
    get short() {
      return t("Dış paylaşım");
    },
    get desc() {
      return t("Kişisel kimlik, iletişim ve banka bilgileri maskelenir.");
    },
    icon: "files",
  },
  {
    id: "denetim",
    get label() {
      return t("Resmi Kurum / Denetim");
    },
    get short() {
      return t("Denetim kopyası");
    },
    get desc() {
      return t("Üçüncü kişilere ait veriler maskelenir, denetim izi korunur.");
    },
    icon: "shield",
  },
  {
    id: "yapay_zeka",
    get label() {
      return t("Yapay Zekâ (AI) Aracı");
    },
    get short() {
      return t("AI / LLM sorgusu");
    },
    get desc() {
      return t("Belge dış modele gönderilmeden önce tüm özel bilgiler temizlenir.");
    },
    icon: "sparkle",
  },
  {
    id: "ic_rapor",
    get label() {
      return t("İç Rapor / Test Verisi");
    },
    get short() {
      return t("Kurum içi");
    },
    get desc() {
      return t("Doğrudan tanımlayıcılar maskelenir, belge yapısı korunur.");
    },
    icon: "grid",
  },
];

/** Üst çubuktaki tasarım düzeni seçici: Stüdyo (3 Panel) | Sihirbaz (Adım Adım) | Klasik */
export function LayoutSwitch({
  value,
  onChange,
}: {
  value: LayoutMode;
  onChange: (mode: LayoutMode) => void;
}) {
  const t = useT();
  const opts: { key: LayoutMode; label: string; icon: IconName; title: string }[] = [
    { key: "studio", label: t("3. Stüdyo"), icon: "grid", title: t("Tasarım 3: Üç Panelli Çalışma Alanı (Pro Masaüstü Stüdyosu)") },
    { key: "wizard", label: t("4. Sihirbaz"), icon: "sparkle", title: t("Tasarım 4: Adım Adım Sihirbaz (Rehberli Akış)") },
    { key: "classic", label: t("Klasik"), icon: "doc", title: t("Mevcut tek sütunlu kart görünümü") },
  ];
  return (
    <div className="layout-switch" role="radiogroup" aria-label={t("Tasarım düzeni")}>
      {opts.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={value === o.key}
          title={o.title}
          className={value === o.key ? "on" : undefined}
          onClick={() => onChange(o.key)}
        >
          <Icon name={o.icon} size={14} />
          <span>{o.label}</span>
        </button>
      ))}
    </div>
  );
}

/** Çevrilmiş cümledeki {ad} yer tutucularını düğümlerle (kalın metin gibi) doldurur. */
function rich(text: string, parts: Record<string, ReactNode>): ReactNode {
  return text.split(/(\{\w+\})/g).map((seg, i) => {
    const m = /^\{(\w+)\}$/.exec(seg);
    return m && m[1] in parts ? <Fragment key={i}>{parts[m[1]]}</Fragment> : seg;
  });
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

function ExtBadge({ path }: { path: string }) {
  const ext = extOf(path);
  return <span className={`ext-badge ext-${badgeKind(ext)}`}>{ext.slice(0, 4).toUpperCase()}</span>;
}

export interface SharedLayoutProps {
  source: string | null;
  target: string | null;
  format: DocFormat | null;
  scan: ScanResult | null;
  done: MaskResult | null;
  busy: "scan" | "mask" | null;
  view: "orijinal" | "maskeli" | "kaydedilen";
  setView: (v: "orijinal" | "maskeli" | "kaydedilen") => void;
  previewPage: number;
  setPreviewPage: (p: number) => void;
  queue: string[];
  saved: Record<string, MaskResult>;
  nextInQueue?: string;
  switchDoc: (path: string) => void;
  pickSource: () => void;
  pickFolder: () => void;
  pickTarget: () => void;
  goHome: () => void;
  runMask: () => void;
  runMaskAll?: () => void;
  plannedFiles?: Record<string, { target: string; relative: string }>;
  folderRoot?: string | null;
  folderTargetDir?: string | null;
  updateFolderTargetDir?: (dir: string) => void;
  inspectedRecentTarget?: string | null;
  setInspectedRecentTarget?: (t: string | null) => void;
  batchProgress?: { done: number; total: number; mode: "scan" | "mask" } | null;
  docSummaries?: Record<string, { scanned: boolean; included: number; total: number }>;
  setDone: (d: MaskResult | null) => void;
  openSettings: (profileId?: string) => void;
  openUnlock: () => void;
  vaultLocked: boolean;
  profile: Profile | null;
  profiles?: Profile[];
  selectedProfileId?: string;
  onSelectProfileId?: (id: string) => void;
  methodPreset?: MethodPreset;
  onSelectMethodPreset?: (m: MethodPreset) => void;
  appliedProfileId?: string;
  appliedMethodPreset?: MethodPreset;
  onApplyRules?: () => void;
  dataTypes: DataTypeInfo[];
  allFindings: PdfFinding[];
  included: PdfFinding[];
  sure: PdfFinding[];
  unsure: PdfFinding[];
  groups: CategoryGroup[];
  excluded: Set<string>;
  dropped: Set<number>;
  unlocated: number;
  canSave: boolean;
  saveLabel: string;
  methodOf: (type: string) => string;
  offByRule: (type: string) => boolean;
  scanRules: Rules | null;
  hovered: string | null;
  setHovered: (id: string | null) => void;
  toggleFinding: (id: string) => void;
  toggleGroup: (items: PdfFinding[]) => void;
  setMany: (items: PdfFinding[], hide: boolean) => void;
  toggleDrop: (page: number) => void;
  clearDropped: () => void;
  lastOff: PdfFinding[];
  clearLastOff: () => void;
  setError: (msg: string | null) => void;
  blackoutTypes: string[];
  addBlackout: (types: string[]) => void;
  clearBlackout: () => void;
  homeTab: "belge" | "metin";
  setHomeTab: (t: "belge" | "metin") => void;
  recent: {
    path: string;
    target: string;
    count: number;
    at: number;
    profileName?: string;
    droppedPages?: number;
    encrypted?: boolean;
    byType?: { type: string; label: string; method?: string; methodLabel?: string; count: number }[];
    folderName?: string;
    folderRoot?: string;
    /** Ajan komutuyla yapılan işlemde ajanın adı. */
    agent?: string;
  }[];
  removeRecent?: (target: string | string[]) => void;
  clearRecent: () => void;
  revealInDir: (path: string) => void;
  renderFilePreview?: (filePath: string, page: number, onPage: (p: number) => void) => ReactNode;
  openRecentDoc?: (path: string) => void;
  errorBanner: ReactNode;
  previewNode: (v: "orijinal" | "maskeli" | "kaydedilen") => ReactNode;
  searchHideNode: ReactNode;
  passwordNode: ReactNode;
  /** Kaydetme reddedildiyse (ör. kaçak tespiti) nedeni: kaydet düğmesinin hemen yanında gösterilir. */
  saveErrorNode?: ReactNode;
  saveLineNode: ReactNode;
  leftOpenNode: ReactNode;
}

/* ============================================================================
   TASARIM 3: ÜÇ PANELLİ ÇALIŞMA ALANI (PRO MASAÜSTÜ STÜDYOSU)
   Sol: Belge kuyruğu & Sayfa gezgini | Orta: Belge tuvali | Sağ: Denetçi
   ============================================================================ */

const STUDIO_PANELS_KEY = "bulutbelge.studio-panels";

interface StudioPanelPrefs {
  leftWidth: number;
  rightWidth: number;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
}

function readStudioPanels(): StudioPanelPrefs {
  try {
    const raw = localStorage.getItem(STUDIO_PANELS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StudioPanelPrefs>;
      return {
        leftWidth: Math.min(480, Math.max(180, Number(parsed.leftWidth) || 250)),
        rightWidth: Math.min(560, Math.max(260, Number(parsed.rightWidth) || 348)),
        leftCollapsed: Boolean(parsed.leftCollapsed),
        rightCollapsed: Boolean(parsed.rightCollapsed),
      };
    }
  } catch {
    // yok say
  }
  return { leftWidth: 250, rightWidth: 348, leftCollapsed: false, rightCollapsed: false };
}

interface FolderTreeFile {
  docPath: string;
  name: string;
  idx: number;
}

interface FolderTreeNode {
  name: string;
  pathKey: string;
  folders: FolderTreeNode[];
  files: FolderTreeFile[];
  totalFiles: number;
  doneFiles: number;
}

function buildFolderTree(
  docList: string[],
  plannedFiles: Record<string, { target: string; relative: string }> | undefined,
  isDocDone: (docPath: string) => boolean,
): FolderTreeNode {
  const root: FolderTreeNode = {
    name: "",
    pathKey: "__root__",
    folders: [],
    files: [],
    totalFiles: 0,
    doneFiles: 0,
  };

  docList.forEach((docPath, idx) => {
    const rel = (plannedFiles?.[docPath]?.relative ?? splitPath(docPath).name).replace(/\\/g, "/");
    const parts = rel.split("/").filter(Boolean);
    const fileName = parts[parts.length - 1] ?? splitPath(docPath).name;
    const folderParts = parts.slice(0, -1);

    let curr = root;
    let currentKey = "";
    for (const seg of folderParts) {
      currentKey = currentKey ? `${currentKey}/${seg}` : seg;
      let child = curr.folders.find((f) => f.name === seg);
      if (!child) {
        child = {
          name: seg,
          pathKey: currentKey,
          folders: [],
          files: [],
          totalFiles: 0,
          doneFiles: 0,
        };
        curr.folders.push(child);
      }
      curr = child;
    }
    curr.files.push({ docPath, name: fileName, idx });
  });

  function calcCounts(node: FolderTreeNode) {
    let total = node.files.length;
    let done = node.files.filter((f) => isDocDone(f.docPath)).length;
    for (const sub of node.folders) {
      calcCounts(sub);
      total += sub.totalFiles;
      done += sub.doneFiles;
    }
    node.totalFiles = total;
    node.doneFiles = done;
  }

  calcCounts(root);
  return root;
}

function getAllSubNodes(node: FolderTreeNode, out: FolderTreeNode[] = []): FolderTreeNode[] {
  for (const sub of node.folders) {
    out.push(sub);
    getAllSubNodes(sub, out);
  }
  return out;
}

export interface RecentFolderGroup {
  isFolder: true;
  key: string;
  name: string;
  targetDir?: string;
  items: SharedLayoutProps["recent"];
  totalMasked: number;
  at: number;
}

export interface RecentSingleItem {
  isFolder: false;
  key: string;
  item: SharedLayoutProps["recent"][number];
}

export type RecentGroupedItem = RecentFolderGroup | RecentSingleItem;

export interface RecentTreeNode {
  name: string;
  pathKey: string;
  folders: RecentTreeNode[];
  files: SharedLayoutProps["recent"];
  totalFiles: number;
  totalMasked: number;
}

/** Belgenin hedef klasör köküne göre göreli yolunu hesaplar (örn. "01-Insan-Kaynaklari/2026-Ise-Giris/basvuru-dosyasi.pdf") */
export function extractRelativeRecentPath(
  r: SharedLayoutProps["recent"][number],
  targetDir?: string,
): string {
  const normTarget = r.target.replace(/\\/g, "/");
  const candidates = [targetDir, r.folderRoot].filter(Boolean) as string[];

  for (const c of candidates) {
    const normC = c.replace(/\\/g, "/").replace(/\/+$/, "");
    if (normTarget.startsWith(normC)) {
      const rel = normTarget.slice(normC.length).replace(/^\/+/, "");
      if (rel) return rel;
    }
  }

  if (r.folderName) {
    const needle = `/${r.folderName}/`;
    const idx = normTarget.indexOf(needle);
    if (idx !== -1) {
      return normTarget.slice(idx + needle.length);
    }
  }

  const normPath = r.path.replace(/\\/g, "/");
  for (const c of candidates) {
    const normC = c.replace(/\\/g, "/").replace(/\/+$/, "");
    const unmasked = normC.replace(/_maskeli(_\d+)?$/, "");
    if (normPath.startsWith(unmasked)) {
      const rel = normPath.slice(unmasked.length).replace(/^\/+/, "");
      if (rel) return rel;
    }
  }

  return splitPath(r.target).name;
}

export function buildRecentFolderTree(
  items: SharedLayoutProps["recent"],
  targetDir?: string,
): RecentTreeNode {
  const root: RecentTreeNode = {
    name: "",
    pathKey: "__recent_root__",
    folders: [],
    files: [],
    totalFiles: 0,
    totalMasked: 0,
  };

  for (const r of items) {
    const rel = extractRelativeRecentPath(r, targetDir);
    const parts = rel.split("/").filter(Boolean);
    const folderParts = parts.slice(0, -1);

    let curr = root;
    let currentKey = "";
    for (const seg of folderParts) {
      currentKey = currentKey ? `${currentKey}/${seg}` : seg;
      let child = curr.folders.find((f) => f.name === seg);
      if (!child) {
        child = {
          name: seg,
          pathKey: currentKey,
          folders: [],
          files: [],
          totalFiles: 0,
          totalMasked: 0,
        };
        curr.folders.push(child);
      }
      curr = child;
    }
    curr.files.push(r);
  }

  function calcRecentCounts(node: RecentTreeNode) {
    let total = node.files.length;
    let masked = node.files.reduce((acc, f) => acc + (f.count || 0), 0);
    for (const sub of node.folders) {
      calcRecentCounts(sub);
      total += sub.totalFiles;
      masked += sub.totalMasked;
    }
    node.totalFiles = total;
    node.totalMasked = masked;
  }

  calcRecentCounts(root);
  return root;
}

export function getAllRecentSubNodes(
  node: RecentTreeNode,
  out: RecentTreeNode[] = [],
): RecentTreeNode[] {
  for (const sub of node.folders) {
    out.push(sub);
    getAllRecentSubNodes(sub, out);
  }
  return out;
}

/** Belgenin hedef klasör içindeki alt dizin yolunu hesaplar (örn. "01-Insan-Kaynaklari › 2026-Ise-Giris") */
export function getRecentSubDir(r: SharedLayoutProps["recent"][number], targetDir?: string): string {
  const base = targetDir || r.folderRoot;
  if (!base) return "";
  const normBase = base.replace(/\\/g, "/").replace(/\/+$/, "");
  const normTarget = r.target.replace(/\\/g, "/");
  if (normTarget.startsWith(normBase)) {
    const rel = normTarget.slice(normBase.length).replace(/^\/+/, "");
    const parts = rel.split("/").filter(Boolean);
    if (parts.length > 1) {
      return parts.slice(0, parts.length - 1).join(" › ");
    }
  }
  return "";
}

export function groupRecentList(recentList: SharedLayoutProps["recent"]): RecentGroupedItem[] {
  const result: RecentGroupedItem[] = [];
  const folderMap = new Map<string, RecentFolderGroup>();

  for (const r of recentList) {
    let fName = r.folderName;
    let fRoot = r.folderRoot;
    if (!fName) {
      // Inferred from target path if contains _maskeli (kökten derine doğru ilk eşleşen)
      const norm = r.target.replace(/\\/g, "/");
      const parts = norm.split("/").filter(Boolean);
      for (let i = 0; i < parts.length - 1; i++) {
        if (parts[i].includes("_maskeli")) {
          fName = parts[i];
          const isWin = r.target.includes("\\");
          const pfx = r.target.startsWith("/") ? "/" : "";
          fRoot = pfx + parts.slice(0, i + 1).join(isWin ? "\\" : "/");
          break;
        }
      }
    }

    if (fName) {
      const existing = folderMap.get(fName);
      if (existing) {
        existing.items.push(r);
        existing.totalMasked += r.count;
        if (r.at > existing.at) existing.at = r.at;
        if (!existing.targetDir && fRoot) existing.targetDir = fRoot;
      } else {
        const grp: RecentFolderGroup = {
          isFolder: true,
          key: `folder:${fName}`,
          name: fName,
          targetDir: fRoot,
          items: [r],
          totalMasked: r.count,
          at: r.at,
        };
        folderMap.set(fName, grp);
        result.push(grp);
      }
    } else {
      result.push({
        isFolder: false,
        key: r.target,
        item: r,
      });
    }
  }

  return result;
}

export function StudioWorkspace(p: SharedLayoutProps) {
  const t = useT();
  const [openCats, setOpenCats] = useState<Record<string, boolean>>({});
  const [findingsPanelOpen, setFindingsPanelOpen] = useState(false);
  const [unsurePanelOpen, setUnsurePanelOpen] = useState(false);
  const prevFolderRootRef = useRef<string | undefined>(p.folderRoot);
  const prevQueueLenRef = useRef<number>(p.queue.length);
  const [ruleMenuOpen, setRuleMenuOpen] = useState(false);
  const [collapsedFolders, setCollapsedFolders] = useState<Record<string, boolean>>({});
  const [expandedRecentFolders, setExpandedRecentFolders] = useState<Record<string, boolean>>({});
  const [collapsedRecentNodes, setCollapsedRecentNodes] = useState<Record<string, boolean>>({});

  function recentNodeHasActive(n: RecentTreeNode): boolean {
    if (n.files.some((f) => f.target === inspectedRecentTarget)) return true;
    return n.folders.some((sub) => recentNodeHasActive(sub));
  }

  function isRecentNodeCollapsed(nodeKey: string, node: RecentTreeNode): boolean {
    if (collapsedRecentNodes[nodeKey] !== undefined) {
      return collapsedRecentNodes[nodeKey];
    }
    return !recentNodeHasActive(node);
  }

  const [recentTreeHeight, setRecentTreeHeight] = useState<number>(() => {
    try {
      const v = localStorage.getItem("bulutbelge.recent-tree-height");
      return v ? Math.max(140, Math.min(800, parseInt(v, 10))) : 280;
    } catch {
      return 280;
    }
  });
  const [isResizingRecent, setIsResizingRecent] = useState(false);

  function startRecentResize(e: React.PointerEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsResizingRecent(true);
    const startY = e.clientY;
    const startH = recentTreeHeight;

    const onPointerMove = (moveEv: PointerEvent) => {
      const delta = moveEv.clientY - startY;
      const nextH = Math.max(120, Math.min(window.innerHeight - 160, startH + delta));
      setRecentTreeHeight(nextH);
    };

    const onPointerUp = (upEv: PointerEvent) => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      setIsResizingRecent(false);
      const delta = upEv.clientY - startY;
      const finalH = Math.max(120, Math.min(window.innerHeight - 160, startH + delta));
      try {
        localStorage.setItem("bulutbelge.recent-tree-height", String(finalH));
      } catch {}
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  }

  function resetRecentResize(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setRecentTreeHeight(280);
    try {
      localStorage.setItem("bulutbelge.recent-tree-height", "280");
    } catch {}
  }

  const [panelPrefs, setPanelPrefs] = useState<StudioPanelPrefs>(readStudioPanels);
  const [resizingSide, setResizingSide] = useState<"left" | "right" | null>(null);
  const [localInspectedRecentTarget, setLocalInspectedRecentTarget] = useState<string | null>(null);
  const inspectedRecentTarget =
    p.inspectedRecentTarget !== undefined ? p.inspectedRecentTarget : localInspectedRecentTarget;
  const setInspectedRecentTarget = p.setInspectedRecentTarget || setLocalInspectedRecentTarget;
  const [confirmDeleteRecent, setConfirmDeleteRecent] = useState<
    | { mode: "single"; target: string; name: string }
    | { mode: "folder"; target: string; name: string; targets: string[]; count: number }
    | { mode: "all"; count: number }
    | null
  >(null);
  const [folderTargetModalOpen, setFolderTargetModalOpen] = useState(false);
  const [editTargetParent, setEditTargetParent] = useState("");
  const [editTargetFolderName, setEditTargetFolderName] = useState("");
  const [compareMode, setCompareMode] = useState<"split" | "before" | "after">("split");
  const [comparePage, setComparePage] = useState(1);
  const [dynamicRecentTypes, setDynamicRecentTypes] = useState<
    { type: string; label: string; method?: string; methodLabel?: string; count: number }[] | null
  >(null);

  const inspectedRecent = inspectedRecentTarget
    ? p.recent.find((r) => r.target === inspectedRecentTarget) ?? null
    : null;

  useEffect(() => {
    // Yeni bir klasör seçildiğinde veya kuyruk sıfırdan başladığında varsayılan kapalı başlat
    const isDifferentFolder = prevFolderRootRef.current !== p.folderRoot;
    const isNewQueueStart = prevQueueLenRef.current === 0 && p.queue.length > 0;
    if (isDifferentFolder || isNewQueueStart) {
      setFindingsPanelOpen(false);
      setUnsurePanelOpen(false);
      setOpenCats({});
    }
    prevFolderRootRef.current = p.folderRoot;
    prevQueueLenRef.current = p.queue.length;
  }, [p.folderRoot, p.queue.length]);

  useEffect(() => {
    // Yeni belge açıldığında veya seçildiğinde son yapılanlar detay görünümünden çık
    if (p.source) {
      setInspectedRecentTarget(null);
    }
    // NOT: p.source veya p.scan değiştiğinde findingsPanelOpen SIFIRLANMAZ.
    // Kullanıcı bir belgede açtıysa klasördeki tüm belgelerde açık kalır, kapattıysa kapalı kalır.
  }, [p.source]);

  useEffect(() => {
    setComparePage(1);
    setDynamicRecentTypes(null);
    if (!inspectedRecent) return;
    if (inspectedRecent.byType && inspectedRecent.byType.length > 0) {
      setDynamicRecentTypes(inspectedRecent.byType);
      return;
    }
    let cancelled = false;
    engineCall<ScanResult>("doc.scan", {
      path: inspectedRecent.path,
      rules: p.scanRules ?? {},
    })
      .then((res) => {
        if (cancelled) return;
        const active = res.findings.filter((f) => !p.offByRule(f.type));
        const list = active.length > 0 ? active : res.findings;
        const map = new Map<
          string,
          { type: string; label: string; method: string; methodLabel: string; count: number }
        >();
        for (const f of list) {
          const existing = map.get(f.type);
          if (existing) {
            existing.count += 1;
          } else {
            const dt = p.dataTypes.find((d) => d.key === f.type);
            const mKey = p.methodOf(f.type);
            const mLabel = dt?.methods.find((m) => m.key === mKey)?.label ?? mKey;
            map.set(f.type, {
              type: f.type,
              label: dt?.label ?? f.type,
              method: mKey,
              methodLabel: mLabel,
              count: 1,
            });
          }
        }
        setDynamicRecentTypes(Array.from(map.values()));
      })
      .catch(() => {
        if (!cancelled) setDynamicRecentTypes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [inspectedRecent?.target, inspectedRecent?.path]);

  useEffect(() => {
    try {
      localStorage.setItem(STUDIO_PANELS_KEY, JSON.stringify(panelPrefs));
    } catch {
      // yok say
    }
  }, [panelPrefs]);

  function startResize(side: "left" | "right", e: React.MouseEvent) {
    e.preventDefault();
    const startX = e.clientX;
    const startLeft = panelPrefs.leftWidth;
    const startRight = panelPrefs.rightWidth;
    setResizingSide(side);

    function onMove(ev: MouseEvent) {
      const dx = ev.clientX - startX;
      if (side === "left") {
        const nextW = Math.min(480, Math.max(180, startLeft + dx));
        setPanelPrefs((prev) => ({ ...prev, leftWidth: nextW, leftCollapsed: false }));
      } else {
        const nextW = Math.min(560, Math.max(260, startRight - dx));
        setPanelPrefs((prev) => ({ ...prev, rightWidth: nextW, rightCollapsed: false }));
      }
    }

    function onUp() {
      setResizingSide(null);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function toggleLeftCollapse() {
    setPanelPrefs((prev) => ({ ...prev, leftCollapsed: !prev.leftCollapsed }));
  }

  function toggleRightCollapse() {
    setPanelPrefs((prev) => ({ ...prev, rightCollapsed: !prev.rightCollapsed }));
  }

  const pagesCount = p.scan?.pages ?? 1;
  const docList = p.queue.length > 0 ? p.queue : p.source ? [p.source] : [];
  const isDocDone = (x: string) => Boolean(p.saved[x] || (x === p.source && p.done));
  const completedCount = docList.filter(isDocDone).length;
  const folderTree = p.folderRoot ? buildFolderTree(docList, p.plannedFiles, isDocDone) : null;

  function hasActiveDoc(node: FolderTreeNode): boolean {
    if (node.files.some((f) => f.docPath === p.source)) return true;
    return node.folders.some(hasActiveDoc);
  }

  function isNodeCollapsed(node: FolderTreeNode): boolean {
    if (collapsedFolders[node.pathKey] !== undefined) {
      return Boolean(collapsedFolders[node.pathKey]);
    }
    return !hasActiveDoc(node);
  }

  function toggleFolder(pathKey: string, currentEffectiveCollapsed: boolean) {
    setCollapsedFolders((prev) => ({ ...prev, [pathKey]: !currentEffectiveCollapsed }));
  }

  function renderDocButton(f: FolderTreeFile, compactSub?: string) {
    const { docPath, name, idx } = f;
    const isCurrent = docPath === p.source && !inspectedRecent;
    const isDone = isDocDone(docPath);
    const sum = p.docSummaries?.[docPath];
    const rel = p.plannedFiles?.[docPath]?.relative;
    return (
      <li key={docPath}>
        <button
          type="button"
          className={["studio-doc-item", isCurrent ? "active" : "", isDone ? "done" : "", isCurrent && (p.batchProgress || p.busy) ? "calisiyor" : ""].join(" ")}
          onClick={() => {
            setInspectedRecentTarget(null);
            if (docPath !== p.source) p.switchDoc(docPath);
          }}
          title={rel ? `${rel}\n(${docPath})` : docPath}
        >
          <span className="studio-doc-idx">
            {isDone ? <Icon name="check" size={12} /> : idx + 1}
          </span>
          <ExtBadge path={docPath} />
          <span className="studio-doc-meta">
            <b>{name}</b>
            {compactSub && <small>{compactSub}</small>}
          </span>
          {sum?.scanned && (
            <span className={sum.included > 0 ? "studio-doc-count" : "studio-doc-count clean"}>
              {sum.included > 0 ? `${sum.included}` : "0"}
            </span>
          )}
        </button>
      </li>
    );
  }

  function renderFolderNode(node: FolderTreeNode, depth = 0): ReactNode {
    const isCollapsed = isNodeCollapsed(node);
    return (
      <li key={node.pathKey} className="studio-tree-node">
        <button
          type="button"
          className={isCollapsed ? "studio-tree-folder collapsed" : "studio-tree-folder open"}
          style={{ paddingLeft: `${8 + depth * 12}px` }}
          onClick={() => toggleFolder(node.pathKey, isCollapsed)}
          aria-expanded={!isCollapsed}
        >
          <span className={isCollapsed ? "studio-tree-caret" : "studio-tree-caret open"}>
            <Icon name="chevron" size={12} />
          </span>
          <span className="studio-tree-folder-icon">
            <Icon name="folder" size={14} />
          </span>
          <span className="studio-tree-folder-name" title={node.pathKey}>
            {node.name}
          </span>
          <span className={node.doneFiles === node.totalFiles && node.totalFiles > 0 ? "studio-tree-badge done" : "studio-tree-badge"}>
            {node.doneFiles > 0 ? `${node.doneFiles}/${node.totalFiles}` : `${node.totalFiles}`}
          </span>
        </button>
        {!isCollapsed && (
          <ul className="studio-tree-children">
            {node.folders.map((sub) => renderFolderNode(sub, depth + 1))}
            {node.files.map((f) => renderDocButton(f))}
          </ul>
        )}
      </li>
    );
  }

  const profiles = p.profiles ?? (p.profile ? [p.profile] : []);
  const selectedProfileId = p.selectedProfileId ?? p.profile?.id ?? "";
  const selectedProfileObj = profiles.find((pr) => pr.id === selectedProfileId) ?? p.profile;
  const hasUnappliedRuleChange =
    !!p.scan && selectedProfileId !== (p.appliedProfileId ?? selectedProfileId);

  function toggleCatExpand(key: string) {
    setOpenCats((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  const shellStyle = {
    "--studio-left-w": panelPrefs.leftCollapsed ? "0px" : `${panelPrefs.leftWidth}px`,
    "--studio-right-w": panelPrefs.rightCollapsed ? "0px" : `${panelPrefs.rightWidth}px`,
  } as CSSProperties;

  return (
    <div
      className={["studio-shell", resizingSide ? "is-resizing" : "", isResizingRecent ? "is-resizing-v" : ""].join(" ")}
      style={shellStyle}
    >
      {/* SOL PANEL: BELGELER, SAYFA GEZGİNİ VE KURAL BİLGİSİ */}
      <aside
        className={panelPrefs.leftCollapsed ? "studio-left collapsed" : "studio-left"}
        aria-label={t("Belgeler ve sayfalar")}
      >
        <div className="studio-left-top">
          <div className="studio-sec-head">
            <span>{t("BELGELER")} {docList.length > 0 ? `(${completedCount}/${docList.length})` : ""}</span>
            <button
              type="button"
              className="studio-panel-collapse-btn"
              onClick={toggleLeftCollapse}
              title={t("Sol paneli daralt")}
              aria-label={t("Sol paneli daralt")}
            >
              «
            </button>
          </div>

          {p.folderRoot && folderTree && (
            <div className="studio-folder-chip" title={p.folderRoot}>
              <Icon name="folder" size={14} />
              <div className="studio-folder-chip-text">
                <b>{splitPath(p.folderRoot).name}</b>
                <small>
                  {folderTree.folders.length > 0
                    ? t("{f} ana klasör · toplam {n} belge", { f: folderTree.folders.length, n: docList.length })
                    : t("{n} belge", { n: docList.length })}
                </small>
              </div>
              {folderTree.folders.length > 0 && (
                <button
                  type="button"
                  className="studio-tree-collapse-all"
                  onClick={() => {
                    const allNodes: FolderTreeNode[] = [
                      ...(folderTree.files.length > 0
                        ? [
                            {
                              name: t("Ana Klasördeki Belgeler"),
                              pathKey: "__root_files__",
                              folders: [],
                              files: folderTree.files,
                              totalFiles: folderTree.files.length,
                              doneFiles: 0,
                            },
                          ]
                        : []),
                      ...getAllSubNodes(folderTree),
                    ];
                    const anyOpen = allNodes.some((n) => !isNodeCollapsed(n));
                    const next: Record<string, boolean> = {};
                    for (const n of allNodes) {
                      next[n.pathKey] = anyOpen;
                    }
                    setCollapsedFolders(next);
                  }}
                  title={t("Tüm klasörleri tek tıkla aç veya daralt")}
                >
                  {[
                    ...(folderTree.files.length > 0
                      ? [
                          {
                            name: t("Ana Klasördeki Belgeler"),
                            pathKey: "__root_files__",
                            folders: [],
                            files: folderTree.files,
                            totalFiles: folderTree.files.length,
                            doneFiles: 0,
                          },
                        ]
                      : []),
                    ...getAllSubNodes(folderTree),
                  ].some((n) => !isNodeCollapsed(n))
                    ? t("Tümünü Daralt")
                    : t("Tümünü Aç")}
                </button>
              )}
            </div>
          )}

          {p.folderTargetDir && (
            <div className="studio-folder-target-banner" title={p.folderTargetDir}>
              <div className="studio-folder-target-meta">
                <span className="studio-folder-target-tag">{t("Hedef:")}</span>
                <b className="studio-folder-target-name">{splitPath(p.folderTargetDir).name}</b>
              </div>
              <button
                type="button"
                className="link-btn studio-folder-target-edit-link"
                onClick={() => {
                  if (p.folderTargetDir) {
                    const parts = splitPath(p.folderTargetDir);
                    setEditTargetParent(parts.dir || "");
                    setEditTargetFolderName(parts.name || "");
                  }
                  setFolderTargetModalOpen(true);
                }}
                title={t("Maskeli belgelerin kaydedileceği konumu ve klasör adını değiştir")}
              >
                {t("Konum / İsim Değiştir")}
              </button>
            </div>
          )}

          {docList.length === 0 ? (
            <div className="studio-empty-queue">
              <p>{t("Henüz açık belge yok.")}</p>
              <div className="studio-quick-btns">
                <button type="button" className="btn small" onClick={p.pickSource}>
                  <Icon name="upload" size={14} /> {t("Belge seç")}
                </button>
                <button type="button" className="btn small" onClick={p.pickFolder}>
                  <Icon name="folder" size={14} /> {t("Klasör seç")}
                </button>
              </div>
            </div>
          ) : folderTree ? (
            <ul className="studio-tree-root">
              {folderTree.files.length > 0 && folderTree.folders.length > 0 ? (
                renderFolderNode(
                  {
                    name: t("Ana Klasördeki Belgeler"),
                    pathKey: "__root_files__",
                    folders: [],
                    files: folderTree.files,
                    totalFiles: folderTree.files.length,
                    doneFiles: folderTree.files.filter((f) => isDocDone(f.docPath)).length,
                  },
                  0,
                )
              ) : (
                folderTree.files.map((f) => renderDocButton(f))
              )}
              {folderTree.folders.map((sub) => renderFolderNode(sub, 0))}
            </ul>
          ) : (
            <ul className="studio-doc-list">
              {docList.map((docPath, idx) =>
                renderDocButton(
                  { docPath, name: splitPath(docPath).name, idx },
                  splitPath(docPath).dir,
                ),
              )}
            </ul>
          )}

          {/* Çok sayfalı belgelerde sayfa gezgini */}
          {p.source && p.scan && pagesCount > 1 && (
            <div className="studio-pages-sec">
              <div className="studio-sec-head">
                <span>{t("SAYFALAR ({n})", { n: pagesCount })}</span>
                {p.dropped.size > 0 && (
                  <button type="button" className="link-btn subtle" onClick={p.clearDropped}>
                    {t("Çıkarmayı geri al")}
                  </button>
                )}
              </div>
              <ul className="studio-page-list">
                {Array.from({ length: pagesCount }, (_, i) => i + 1).map((pg) => {
                  const pgFindings = p.allFindings.filter((f) => f.page === pg);
                  const pgActive = pgFindings.filter((f) => !p.excluded.has(f.id)).length;
                  const isDropped = p.dropped.has(pg);
                  return (
                    <li key={pg} className={pg === p.previewPage ? "on" : undefined}>
                      <button
                        type="button"
                        className="studio-page-btn"
                        onClick={() => p.setPreviewPage(pg)}
                      >
                        <span className="studio-page-num">{t("Sayfa {n}", { n: pg })}</span>
                        {isDropped ? (
                          <span className="studio-page-tag dropped">{t("Çıkarıldı")}</span>
                        ) : pgFindings.length > 0 ? (
                          <span className="studio-page-tag">{t("{a}/{b} maskeli", { a: pgActive, b: pgFindings.length })}</span>
                        ) : (
                          <span className="studio-page-tag clean">{t("Temiz")}</span>
                        )}
                      </button>
                      {p.format === "pdf" && !p.done && (
                        <button
                          type="button"
                          className={["icon-btn studio-drop-page", isDropped ? "on" : ""].join(" ")}
                          title={isDropped ? t("Sayfayı kopyaya geri ekle") : t("Bu sayfayı kopyadan tamamen çıkar")}
                          onClick={() => p.toggleDrop(pg)}
                        >
                          <Icon name={isDropped ? "undo" : "trash"} size={13} />
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Son yapılanlar (Başlangıçta veya alt bölümde) */}
          {p.recent.length > 0 && (
            <div className="studio-recent-sec">
              <div className="studio-sec-head">
                <span>{t("SON YAPILANLAR")}</span>
                <button
                  type="button"
                  className="link-btn subtle"
                  onClick={() => {
                    setConfirmDeleteRecent({ mode: "all", count: p.recent.length });
                  }}
                >
                  {t("Temizle")}
                </button>
              </div>
              <ul className="studio-recent-list">
                {groupRecentList(p.recent).map((item) => {
                  if (item.isFolder) {
                    const isAnyInspected = item.items.some((it) => it.target === inspectedRecentTarget);
                    const isFolderOpen =
                      expandedRecentFolders[item.key] !== undefined
                        ? expandedRecentFolders[item.key]
                        : isAnyInspected;
                    const tree = buildRecentFolderTree(item.items, item.targetDir);
                    const hasSubFolders = tree.folders.length > 0;
                    const rootFilesNode: RecentTreeNode = {
                      name: t("Ana Klasördeki Belgeler"),
                      pathKey: "__root_files__",
                      folders: [],
                      files: tree.files,
                      totalFiles: tree.files.length,
                      totalMasked: tree.files.reduce((a, b) => a + (b.count || 0), 0),
                    };
                    const allSubNodes: RecentTreeNode[] = [
                      ...(hasSubFolders && tree.files.length > 0 ? [rootFilesNode] : []),
                      ...getAllRecentSubNodes(tree),
                    ];
                    const anyRecentSubNodeOpen = allSubNodes.some(
                      (n) => !isRecentNodeCollapsed(`${item.key}:${n.pathKey}`, n)
                    );

                    const renderRecentFileItem = (r: SharedLayoutProps["recent"][number]): ReactNode => {
                      const isInspected = inspectedRecent?.target === r.target;
                      const fileName = splitPath(r.path).name;
                      return (
                        <li
                          key={r.target}
                          className={["studio-recent-item sub-item", isInspected ? "active" : ""].join(" ")}
                          onClick={() =>
                            setInspectedRecentTarget(inspectedRecentTarget === r.target ? null : r.target)
                          }
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setInspectedRecentTarget(inspectedRecentTarget === r.target ? null : r.target);
                            }
                          }}
                          title={t("İşlem detayını ve öncesi/sonrasını görüntülemek için tıklayın")}
                        >
                          <ExtBadge path={r.path} />
                          <div className="studio-recent-text">
                            <b title={r.target}>{fileName}</b>
                            <small>{t("{n} maskelendi", { n: r.count })}{r.agent ? ` · ${t("Ajan")} (${r.agent})` : ""}</small>
                          </div>
                          <button
                            type="button"
                            className="icon-btn studio-recent-del-btn"
                            title={t("Listeden sil")}
                            aria-label={t("{name} kaydını listeden sil", { name: fileName })}
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteRecent({
                                mode: "single",
                                target: r.target,
                                name: fileName,
                              });
                            }}
                          >
                            <Icon name="trash" size={12} />
                          </button>
                        </li>
                      );
                    };

                    const renderRecentTreeNode = (node: RecentTreeNode, depth = 0): ReactNode => {
                      const nodeKey = `${item.key}:${node.pathKey}`;
                      const isCollapsed = isRecentNodeCollapsed(nodeKey, node);
                      const hasActive = recentNodeHasActive(node);
                      return (
                        <li key={nodeKey} className="studio-tree-node recent-tree-node">
                          <button
                            type="button"
                            className={[
                              "studio-tree-folder recent-tree-folder",
                              isCollapsed ? "collapsed" : "open",
                              hasActive ? "has-active" : "",
                            ].join(" ")}
                            onClick={() => {
                              setCollapsedRecentNodes((prev) => ({
                                ...prev,
                                [nodeKey]: !isCollapsed,
                              }));
                            }}
                            aria-expanded={!isCollapsed}
                            title={t("{name} klasörünü aç / daralt", { name: node.name })}
                          >
                            <span className={["studio-tree-caret", isCollapsed ? "" : "open"].join(" ")}>
                              <Icon name="chevron" size={12} />
                            </span>
                            <span className="studio-tree-folder-icon">
                              <Icon name="folder" size={13} />
                            </span>
                            <span className="studio-tree-folder-name" title={node.name}>
                              {node.name}
                            </span>
                            <span className="studio-tree-badge">{node.totalFiles}</span>
                          </button>
                          {!isCollapsed && (
                            <ul className="studio-tree-children recent-tree-children">
                              {node.folders.map((sub) => renderRecentTreeNode(sub, depth + 1))}
                              {node.files.map((r) => renderRecentFileItem(r))}
                            </ul>
                          )}
                        </li>
                      );
                    };

                    return (
                      <li key={item.key} className={["studio-recent-folder-group", isFolderOpen ? "is-open" : ""].join(" ")}>
                        <div
                          className={["studio-recent-item folder-head", isAnyInspected ? "has-active" : ""].join(" ")}
                          onClick={() => {
                            setExpandedRecentFolders((prev) => ({
                              ...prev,
                              [item.key]: !isFolderOpen,
                            }));
                          }}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setExpandedRecentFolders((prev) => ({
                                ...prev,
                                [item.key]: !isFolderOpen,
                              }));
                            }
                          }}
                          title={t("Klasör içindeki belgeleri aç / kapat")}
                        >
                          <span className={["studio-recent-caret", isFolderOpen ? "open" : ""].join(" ")}>
                            <Icon name="chevron" size={12} />
                          </span>
                          <span className="studio-recent-folder-icon">
                            <Icon name="folder" size={13} />
                          </span>
                          <div className="studio-recent-text">
                            <b title={item.targetDir || item.name}>{item.name}</b>
                            <small>
                              {t("{n} belge · {m} maskelendi", { n: item.items.length, m: item.totalMasked })}
                            </small>
                          </div>
                          <div className="studio-recent-folder-actions" onClick={(e) => e.stopPropagation()}>
                            {item.targetDir && (
                              <button
                                type="button"
                                className="icon-btn studio-recent-reveal-btn"
                                title={t("Klasörü göster")}
                                aria-label={t("{name} klasörünü göster", { name: item.name })}
                                onClick={() => p.revealInDir(item.targetDir!)}
                              >
                                <Icon name="folder" size={13} />
                              </button>
                            )}
                            <button
                              type="button"
                              className="icon-btn studio-recent-del-btn"
                              title={t("Klasör kayıtlarını sil")}
                              aria-label={t("{name} klasörüne ait kayıtları sil", { name: item.name })}
                              onClick={() => {
                                setConfirmDeleteRecent({
                                  mode: "folder",
                                  name: item.name,
                                  target: item.items[0]?.target || "",
                                  targets: item.items.map((it) => it.target),
                                  count: item.items.length,
                                });
                              }}
                            >
                              <Icon name="trash" size={13} />
                            </button>
                          </div>
                        </div>

                        {isFolderOpen && (
                          <div className="studio-recent-sub-wrap">
                            {hasSubFolders && (
                              <div className="studio-recent-tree-head">
                                <span>{t("{n} alt klasör", { n: tree.folders.length })}</span>
                                <button
                                  type="button"
                                  className="studio-tree-collapse-all"
                                  onClick={() => {
                                    const next: Record<string, boolean> = { ...collapsedRecentNodes };
                                    for (const n of allSubNodes) {
                                      next[`${item.key}:${n.pathKey}`] = anyRecentSubNodeOpen;
                                    }
                                    setCollapsedRecentNodes(next);
                                  }}
                                  title={t("Tüm alt klasörleri tek tıkla aç veya daralt")}
                                >
                                  {anyRecentSubNodeOpen ? t("Tümünü Daralt") : t("Tümünü Aç")}
                                </button>
                              </div>
                            )}
                            <ul
                              className="studio-recent-sub-list"
                              style={{ maxHeight: `${recentTreeHeight}px` }}
                            >
                              {hasSubFolders ? (
                                <>
                                  {tree.files.length > 0 && renderRecentTreeNode(rootFilesNode, 0)}
                                  {tree.folders.map((sub) => renderRecentTreeNode(sub, 0))}
                                </>
                              ) : (
                                tree.files.map((r) => renderRecentFileItem(r))
                              )}
                            </ul>
                            <div
                              className={[
                                "studio-recent-resize-handle",
                                isResizingRecent ? "active" : "",
                              ].join(" ")}
                              onPointerDown={startRecentResize}
                              onDoubleClick={resetRecentResize}
                              title={t("Kutuyu yukarı/aşağı genişletmek için sürükleyin (sıfırlamak için çift tıklayın)")}
                            >
                              <span className="studio-recent-resize-grip" />
                            </div>
                          </div>
                        )}
                      </li>
                    );
                  }

                  const r = item.item;
                  const isInspected = inspectedRecent?.target === r.target;
                  return (
                    <li
                      key={r.target}
                      className={isInspected ? "studio-recent-item active" : "studio-recent-item"}
                      onClick={() =>
                        setInspectedRecentTarget(inspectedRecentTarget === r.target ? null : r.target)
                      }
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setInspectedRecentTarget(inspectedRecentTarget === r.target ? null : r.target);
                        }
                      }}
                      title={t("Yapılan işlemi, öncesi ve sonrasını görüntülemek için tıklayın")}
                    >
                      <ExtBadge path={r.path} />
                      <div className="studio-recent-text">
                        <b title={r.target}>{splitPath(r.path).name}</b>
                        <small>{t("{n} bilgi maskelendi", { n: r.count })}{r.agent ? ` · ${t("Ajan")} (${r.agent})` : ""}</small>
                      </div>
                      <button
                        type="button"
                        className="icon-btn studio-recent-del-btn"
                        title={t("Listeden sil")}
                        aria-label={t("{name} kaydını listeden sil", { name: splitPath(r.path).name })}
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDeleteRecent({
                            mode: "single",
                            target: r.target,
                            name: splitPath(r.path).name,
                          });
                        }}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        {/* Sol Alt: Güvenlik Rozeti */}
        <div className="studio-left-foot">
          <div className="studio-trust-pill">
            <Icon name="shield" size={14} />
            <span>{t("Belge bilgisayarınızdan çıkmaz · Orijinale dokunulmaz")}</span>
          </div>
        </div>
      </aside>

      {/* SOL PANEL BOYUTLANDIRICI (SÜRÜKLE GENİŞLET/DARALT) */}
      <div
        className={["studio-resizer left", resizingSide === "left" ? "active" : ""].join(" ")}
        role="separator"
        aria-orientation="vertical"
        aria-label={t("Sol panel genişliğini ayarla")}
        title={t("Genişletmek veya daraltmak için sürükleyin (sıfırlamak için çift tıklayın)")}
        onMouseDown={(e) => startResize("left", e)}
        onDoubleClick={() => setPanelPrefs((prev) => ({ ...prev, leftWidth: 250, leftCollapsed: false }))}
      >
        <button
          type="button"
          className="studio-resizer-toggle"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={toggleLeftCollapse}
          title={panelPrefs.leftCollapsed ? t("Sol paneli aç") : t("Sol paneli daralt")}
        >
          {panelPrefs.leftCollapsed ? "»" : "«"}
        </button>
      </div>

      {/* ORTA PANEL: BELGE TUVALİ VE ÜST ARAÇ ÇUBUĞU */}
      <main className="studio-center" aria-label={t("Çalışma alanı")}>
        <div className="studio-toolbar">
          <div className="studio-toolbar-left">
            {panelPrefs.leftCollapsed && (
              <button
                type="button"
                className="btn small studio-expand-pill"
                onClick={toggleLeftCollapse}
                title={t("Sol paneli genişlet")}
              >
                » {t("Belgeler")} {docList.length > 0 ? `(${docList.length})` : ""}
              </button>
            )}
            {inspectedRecent ? (
              <>
                <ExtBadge path={inspectedRecent.path} />
                <b className="studio-file-title" title={inspectedRecent.path}>
                  {splitPath(inspectedRecent.path).name}
                </b>
                <span className="studio-stat-pill">
                  {t("{n} bilgi maskelendi", { n: inspectedRecent.count })}
                </span>
              </>
            ) : p.source ? (
              <>
                <ExtBadge path={p.source} />
                <b className="studio-file-title" title={p.source}>
                  {splitPath(p.source).name}
                </b>
                {p.scan ? (
                  <span className="studio-stat-pill">
                    {t("{n} maskelenecek · {m} açık", { n: p.included.length, m: p.allFindings.length - p.included.length })}
                  </span>
                ) : (
                  <span className="studio-stat-pill pending">
                    {t("Kural seçip Uygula'ya basın")}
                  </span>
                )}
              </>
            ) : (
              <div className="studio-home-tabs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={p.homeTab === "belge"}
                  className={p.homeTab === "belge" ? "on" : undefined}
                  onClick={() => p.setHomeTab("belge")}
                >
                  <Icon name="files" size={15} /> {t("Belge Çalışma Alanı")}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={p.homeTab === "metin"}
                  className={p.homeTab === "metin" ? "on" : undefined}
                  onClick={() => p.setHomeTab("metin")}
                >
                  <Icon name="text" size={15} /> {t("Metin Yapıştır")}
                </button>
              </div>
            )}
          </div>

          <div className="studio-toolbar-right">
            {inspectedRecent ? (
              <>
                <div className="segmented view-toggle studio-compare-toggle" role="tablist" aria-label={t("Öncesi ve Sonrası Görünümü")}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={compareMode === "split"}
                    className={compareMode === "split" ? "on" : undefined}
                    onClick={() => setCompareMode("split")}
                  >
                    {t("Yan Yana")}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={compareMode === "before"}
                    className={compareMode === "before" ? "on" : undefined}
                    onClick={() => setCompareMode("before")}
                  >
                    {t("Öncesi")}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={compareMode === "after"}
                    className={compareMode === "after" ? "on" : undefined}
                    onClick={() => setCompareMode("after")}
                  >
                    {t("Sonrası")}
                  </button>
                </div>
                <button
                  type="button"
                  className="btn small studio-home-compare-btn"
                  onClick={p.goHome}
                  title={t("Ana Sayfaya dön")}
                >
                  <Icon name="home" size={13} /> {t("Ana Sayfa")}
                </button>
                <button
                  type="button"
                  className="btn small studio-close-compare-btn"
                  onClick={() => setInspectedRecentTarget(null)}
                  title={t("İncelemeyi kapat")}
                >
                  <Icon name="x" size={13} /> {t("Kapat")}
                </button>
              </>
            ) : (
              <>
                {p.source && p.scan && !p.done && (
                  <div className="segmented view-toggle" role="tablist" aria-label={t("Görünüm")}>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={p.view === "orijinal"}
                      className={p.view === "orijinal" ? "on" : undefined}
                      onClick={() => p.setView("orijinal")}
                    >
                      {t("Orijinal")}
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={p.view !== "orijinal"}
                      className={p.view !== "orijinal" ? "on" : undefined}
                      onClick={() => p.setView("maskeli")}
                    >
                      {t("Maskelenmiş hâli")}
                    </button>
                  </div>
                )}
                {p.done &&
                  (p.done.leaked?.length ? (
                    <span className="studio-done-badge warn">
                      <Icon name="alert" size={14} /> {sonucBasligi(t, p.done)}
                    </span>
                  ) : (
                    <span className="studio-done-badge">
                      <Icon name="check" size={14} /> {t("Güvenli kopya kaydedildi")}
                    </span>
                  ))}
              </>
            )}
            {panelPrefs.rightCollapsed && (
              <button
                type="button"
                className="btn small studio-expand-pill"
                onClick={toggleRightCollapse}
                title={t("Sağ paneli genişlet")}
              >
                {t("« Denetçi")}
              </button>
            )}
          </div>
        </div>

        <div className="studio-canvas">
          {p.errorBanner}

          {inspectedRecent ? (
            <div className="studio-compare-stage">
              <div className={`studio-compare-grid mode-${compareMode}`}>
                {(compareMode === "split" || compareMode === "before") && (
                  <div className="studio-compare-pane before">
                    <div className="studio-compare-head">
                      <span className="studio-compare-tag before">{t("ÖNCESİ · Orijinal")}</span>
                      <span className="studio-compare-fname" title={inspectedRecent.path}>
                        {splitPath(inspectedRecent.path).name}
                      </span>
                    </div>
                    <div className="studio-compare-body">
                      {p.renderFilePreview ? (
                        p.renderFilePreview(inspectedRecent.path, comparePage, setComparePage)
                      ) : (
                        <p className="hint">{t("Önizleme yükleniyor…")}</p>
                      )}
                    </div>
                  </div>
                )}

                {(compareMode === "split" || compareMode === "after") && (
                  <div className="studio-compare-pane after">
                    <div className="studio-compare-head">
                      <span className="studio-compare-tag after">
                        {t("SONRASI · Maskelenmiş ({n} maskeli)", { n: inspectedRecent.count })}
                      </span>
                      <span className="studio-compare-fname" title={inspectedRecent.target}>
                        {splitPath(inspectedRecent.target).name}
                      </span>
                    </div>
                    <div className="studio-compare-body">
                      {inspectedRecent.encrypted ? (
                        <div className="studio-compare-encrypted">
                          <Icon name="lock" size={28} />
                          <b>{t("Maskelenmiş kopya parola korumalıdır")}</b>
                          <p>
                            {t("Bu belge kaydedilirken parola ile şifrelendiği için doğrudan önizlenemiyor. Dosyayı klasörde açarak parolanızla görüntüleyebilirsiniz.")}
                          </p>
                          <button
                            type="button"
                            className="btn small"
                            onClick={() => p.revealInDir(inspectedRecent.target)}
                          >
                            <Icon name="folder" size={14} /> {t("Klasörde göster")}
                          </button>
                        </div>
                      ) : p.renderFilePreview ? (
                        p.renderFilePreview(inspectedRecent.target, comparePage, setComparePage)
                      ) : (
                        <p className="hint">{t("Önizleme yükleniyor…")}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : !p.source && p.homeTab === "metin" ? (
            <div className="studio-paste-wrap">
              <PasteScreen rules={p.scanRules} offByRule={p.offByRule} methodOf={p.methodOf} />
            </div>
          ) : !p.source ? (
            <div className="studio-drop-wrap">
              <button type="button" className="home-drop studio-drop-card" onClick={p.pickSource}>
                <span className="home-drop-icon">
                  <Icon name="upload" size={34} />
                </span>
                <b>{t("Belgeleri veya klasörü çalışma alanına bırakın")}</b>
                <div className="studio-drop-steps">
                  <div className="studio-drop-step">
                    <span className="studio-drop-step-num">1</span>
                    <span>{t("Belge veya klasör seçin")}</span>
                  </div>
                  <div className="studio-drop-step">
                    <span className="studio-drop-step-num">2</span>
                    <span>
                      {rich(t("Sağ panelden maskeleme kural takımını seçip {uygula}'ya basın"), { uygula: <b>{t("Uygula")}</b> })}
                    </span>
                  </div>
                  <div className="studio-drop-step">
                    <span className="studio-drop-step-num">3</span>
                    <span>
                      {rich(t("Bulguları seçip {kaydet} ile tamamlayın"), { kaydet: <b>{t("Maskele ve Kaydet")}</b> })}
                    </span>
                  </div>
                </div>
                <span className="home-pick">{t("Bilgisayardan belge seç")}</span>
                <span className="home-formats">
                  {t("PDF · Word · Excel · PowerPoint · Fotoğraf · XML, CSV, JSON, TXT, LOG · Çoklu belge ve klasör desteklenir")}
                </span>
              </button>
              <p className="home-alt">
                {t("Bir klasördeki tüm belgeleri sırayla işlemek için:")}{" "}
                <button type="button" className="link-btn" onClick={p.pickFolder}>
                  {t("Klasör seçin")}
                </button>
              </p>
            </div>
          ) : p.busy === "scan" || p.batchProgress?.mode === "scan" ? (
            <div className="studio-center-loading">
              <div className="loading-card">
                <span className="tara-belge" aria-hidden><i /><i /><i /><i /></span>
                <b>{t("Seçilen kural uygulanıyor ve kişisel bilgiler taranıyor…")}</b>
                <span>{splitPath(p.source).name}</span>
                {p.batchProgress?.mode === "scan" && (
                  <>
                    <span className="ilerleme-serit" aria-hidden>
                      <i style={{ width: `${Math.round((p.batchProgress.done / Math.max(1, p.batchProgress.total)) * 100)}%` }} />
                    </span>
                    <small>{t("Taranıyor ({done}/{total})…", { done: p.batchProgress.done, total: p.batchProgress.total })}</small>
                  </>
                )}
                {(p.format === "gorsel" || p.format === "pdf") && (
                  <small>{t("Fotoğraf ve taranmış sayfalarda OCR biraz sürebilir.")}</small>
                )}
              </div>
            </div>
          ) : (
            <div className="studio-doc-stage">
              {p.done?.encrypted && (
                <p className="hint enc-note">
                  <Icon name="lock" size={14} /> {t("Kopya parolalı olduğu için burada kaydedilmeden önceki görünüm gösteriliyor.")}
                </p>
              )}
              {p.previewNode(
                !p.scan
                  ? "orijinal"
                  : p.done
                  ? p.done.encrypted
                    ? "maskeli"
                    : "kaydedilen"
                  : p.view === "kaydedilen"
                  ? "maskeli"
                  : p.view,
              )}
            </div>
          )}
        </div>
      </main>

      {/* SAĞ PANEL BOYUTLANDIRICI (SÜRÜKLE GENİŞLET/DARALT) */}
      <div
        className={["studio-resizer right", resizingSide === "right" ? "active" : ""].join(" ")}
        role="separator"
        aria-orientation="vertical"
        aria-label={t("Sağ panel genişliğini ayarla")}
        title={t("Genişletmek veya daraltmak için sürükleyin (sıfırlamak için çift tıklayın)")}
        onMouseDown={(e) => startResize("right", e)}
        onDoubleClick={() => setPanelPrefs((prev) => ({ ...prev, rightWidth: 348, rightCollapsed: false }))}
      >
        <button
          type="button"
          className="studio-resizer-toggle"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={toggleRightCollapse}
          title={panelPrefs.rightCollapsed ? t("Sağ paneli aç") : t("Sağ paneli daralt")}
        >
          {panelPrefs.rightCollapsed ? "«" : "»"}
        </button>
      </div>

      {/* SAĞ PANEL: MASKELEME KURALI SEÇİMİ, BULGULAR DENETÇİSİ VE KAYDETME EYLEMLERİ */}
      <aside
        className={panelPrefs.rightCollapsed ? "studio-right collapsed" : "studio-right"}
        aria-label={t("Bulgular ve denetçi")}
      >
        {inspectedRecent ? (
          <div className="studio-recent-detail">
            <div className="studio-sec-head">
              <span>{t("YAPILAN İŞLEM DETAYI")}</span>
              <button
                type="button"
                className="studio-panel-collapse-btn"
                onClick={toggleRightCollapse}
                title={t("Sağ paneli daralt")}
                aria-label={t("Sağ paneli daralt")}
              >
                »
              </button>
            </div>

            <div className="studio-recent-summary-card">
              <div className="studio-recent-summary-top">
                <span className="done-icon">
                  <Icon name="check" size={22} />
                </span>
                <div>
                  <b>{splitPath(inspectedRecent.path).name}</b>
                  <small>{t("{n} kişisel bilgi maskelendi ve doğrulandı", { n: inspectedRecent.count })}</small>
                </div>
              </div>

              <div className="studio-recent-meta-grid">
                <div className="studio-recent-meta-row">
                  <span>{t("Kural Takımı")}</span>
                  <b>{t(inspectedRecent.profileName ?? selectedProfileObj?.name ?? "Varsayılan")}</b>
                </div>
                <div className="studio-recent-meta-row">
                  <span>{t("İşlem Zamanı")}</span>
                  <b>
                    {new Date(inspectedRecent.at).toLocaleString(localeCode(), {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </b>
                </div>
                <div className="studio-recent-meta-row">
                  <span>{t("Durum")}</span>
                  <b className="ok">{t("Doğrulandı · Üstveri temiz")}</b>
                </div>
                {!!inspectedRecent.droppedPages && (
                  <div className="studio-recent-meta-row">
                    <span>{t("Çıkarılan Sayfa")}</span>
                    <b>{t("{n} sayfa çıkarıldı", { n: inspectedRecent.droppedPages })}</b>
                  </div>
                )}
              </div>
            </div>

            <div className="studio-recent-types-sec">
              <div className="studio-sec-head">
                <span>{t("GİZLENEN BİLGİ TÜRLERİ")}</span>
                <span>{t("{n} adet", { n: inspectedRecent.count })}</span>
              </div>
              {dynamicRecentTypes === null ? (
                <p className="hint">{t("İşlem detayları yükleniyor…")}</p>
              ) : dynamicRecentTypes.length === 0 ? (
                <p className="hint">{t("Bu belgede toplam {n} kişisel bilgi maskelendi.", { n: inspectedRecent.count })}</p>
              ) : (
                <ul className="studio-recent-type-list">
                  {dynamicRecentTypes.map((item) => (
                    <li key={item.type} className="studio-recent-type-item">
                      <div className="studio-recent-type-info">
                        <b>{t(item.label)}</b>
                        <span className="studio-recent-method-pill">{t(item.methodLabel ?? "")}</span>
                      </div>
                      <span className="studio-recent-type-count">{t("{n} adet", { n: item.count })}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="studio-recent-paths-sec">
              <div className="studio-sec-head">
                <span>{t("DOSYA KONUMLARI")}</span>
              </div>
              <div className="studio-recent-path-card">
                <div className="studio-recent-path-head">
                  <span className="studio-compare-tag before">{t("ÖNCESİ (Orijinal)")}</span>
                  <button
                    type="button"
                    className="link-btn subtle"
                    onClick={() => p.revealInDir(inspectedRecent.path)}
                  >
                    <Icon name="folder" size={12} /> {t("Klasörde göster")}
                  </button>
                </div>
                <code className="studio-recent-path-code" title={inspectedRecent.path}>
                  {inspectedRecent.path}
                </code>
              </div>

              <div className="studio-recent-path-card">
                <div className="studio-recent-path-head">
                  <span className="studio-compare-tag after">{t("SONRASI (Maskeli)")}</span>
                  <button
                    type="button"
                    className="link-btn subtle"
                    onClick={() => p.revealInDir(inspectedRecent.target)}
                  >
                    <Icon name="folder" size={12} /> {t("Klasörde göster")}
                  </button>
                </div>
                <code className="studio-recent-path-code" title={inspectedRecent.target}>
                  {inspectedRecent.target}
                </code>
              </div>
            </div>

            <div className="studio-recent-actions">
              {p.openRecentDoc && (
                <button
                  type="button"
                  className="btn primary full"
                  onClick={() => {
                    const docPath = inspectedRecent.path;
                    setInspectedRecentTarget(null);
                    p.openRecentDoc?.(docPath);
                  }}
                >
                  <Icon name="scan" size={15} /> {t("Belgeyi Çalışma Alanında Yeniden Aç")}
                </button>
              )}
              <button
                type="button"
                className="btn full"
                onClick={() => p.revealInDir(inspectedRecent.target)}
              >
                <Icon name="folder" size={15} /> {t("Maskeli Kopyayı Klasörde Göster")}
              </button>
            </div>
          </div>
        ) : !p.source ? (
          <div className="studio-right-empty">
            <div className="studio-sec-head">
              <span>{t("MASKELEME VE DENETÇİ")}</span>
              <button
                type="button"
                className="studio-panel-collapse-btn"
                onClick={toggleRightCollapse}
                title={t("Sağ paneli daralt")}
                aria-label={t("Sağ paneli daralt")}
              >
                »
              </button>
            </div>

            {selectedProfileObj && (
              <section className="studio-method-card" aria-label={t("Maskeleme kuralı seçimi")} style={{ marginTop: 10 }}>
                <div className="studio-method-head">
                  <div>
                    <span className="studio-step-pill">{t("1. Adım")}</span>
                    <h3>{t("Maskeleme Kuralı")}</h3>
                  </div>
                </div>

                <div className="studio-right-rule-picker">
                  <div className={ruleMenuOpen ? "studio-preset-row on open" : "studio-preset-row on"}>
                    <button
                      type="button"
                      className="studio-preset-main-btn"
                      onClick={() => setRuleMenuOpen((v) => !v)}
                      aria-expanded={ruleMenuOpen}
                    >
                      <span className="studio-preset-radio">
                        <Icon name="check" size={11} />
                      </span>
                      <span className="studio-preset-text">
                        <b>{selectedProfileObj.name}</b>
                        <small>{t("{n} bilgi türü maskelenir", { n: enabledTypeCount(selectedProfileObj) })}</small>
                      </span>
                      <span className="studio-rule-trigger">
                        {ruleMenuOpen ? t("Kapat") : t("Değiştir")} <Icon name="chevron" size={13} />
                      </span>
                    </button>
                    <button
                      type="button"
                      className="icon-btn studio-rule-edit-btn"
                      title={t("{name} kuralını düzenle", { name: selectedProfileObj.name })}
                      aria-label={t("{name} kuralını düzenle", { name: selectedProfileObj.name })}
                      onClick={(e) => {
                        e.stopPropagation();
                        p.openSettings(selectedProfileObj.id);
                      }}
                    >
                      <Icon name="pen" size={14} />
                    </button>
                  </div>

                  {ruleMenuOpen && (
                    <div className="studio-preset-dropdown" role="radiogroup" aria-label={t("Kural Takımı")}>
                      {profiles.map((prof) => {
                        const active = prof.id === selectedProfileId;
                        return (
                          <div
                            key={prof.id}
                            className={active ? "studio-preset-row on" : "studio-preset-row"}
                          >
                            <button
                              type="button"
                              role="radio"
                              aria-checked={active}
                              className="studio-preset-main-btn"
                              onClick={() => {
                                p.onSelectProfileId?.(prof.id);
                                setRuleMenuOpen(false);
                              }}
                            >
                              <span className="studio-preset-radio">
                                {active && <Icon name="check" size={11} />}
                              </span>
                              <span className="studio-preset-text">
                                <b>{t(prof.name)}</b>
                                <small>{t("{n} bilgi türü maskelenir", { n: enabledTypeCount(prof) })}</small>
                              </span>
                            </button>
                            <button
                              type="button"
                              className="icon-btn studio-rule-edit-btn"
                              title={t("{name} kuralını düzenle", { name: t(prof.name) })}
                              aria-label={t("{name} kuralını düzenle", { name: t(prof.name) })}
                              onClick={(e) => {
                                e.stopPropagation();
                                p.openSettings(prof.id);
                              }}
                            >
                              <Icon name="pen" size={14} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </section>
            )}

            <div className="studio-inspector-placeholder">
              <Icon name="scan" size={28} />
              <b>{t("Belge veya klasör bekleniyor")}</b>
              <p>
                {rich(t("Sol panelden veya ortadaki alandan belge ya da klasör seçin. Ardından yukarıdaki maskeleme kural takımını {uygula} diyerek bulguları listeleyebilirsiniz."), { uygula: <b>{t("Uygula")}</b> })}
              </p>
            </div>
          </div>
        ) : p.done ? (
          <div className="studio-right-done">
            <div className="studio-done-head">
              <span className={p.done.leaked?.length ? "done-icon warn" : "done-icon"}>
                <Icon name={p.done.leaked?.length ? "alert" : "check"} size={26} />
              </span>
              <div>
                <h2 className="side-title">{sonucBasligi(t, p.done)}</h2>
                <p className="side-sub">
                  {p.done.leaked?.length
                    ? sonucAciklamasi(t, p.done)
                    : t("{n} kişisel bilgi belgeden gerçekten silindi ve dosya yeniden okunarak kontrol edildi.", { n: p.done.masked })}
                </p>
              </div>
            </div>

            <ul className="done-list">
              <li>
                <Icon name="check" size={14} /> {t("Yazar, yorum, konum gibi gizli bilgiler temizlendi")}
              </li>
              {!!p.done.dropped && (
                <li>
                  <Icon name="check" size={14} /> {t("{n} sayfa kopyadan çıkarıldı", { n: p.done.dropped })}
                </li>
              )}
              {p.done.encrypted && (
                <li>
                  <Icon name="lock" size={14} /> {t("Parolayla korundu; parolayı alıcıya ayrı iletin")}
                </li>
              )}
              <li>
                <Icon name="check" size={14} /> {t("Orijinal dosyaya dokunulmadı")}
              </li>
              <li>
                <Icon name="check" size={14} /> {t("Hiçbir yere gönderilmedi")}
              </li>
              {p.done.warnings.map((w) => (
                <li key={w} className="done-warning">
                  <Icon name="alert" size={14} /> {t(w)}
                </li>
              ))}
            </ul>

            {p.leftOpenNode}
            <PathChanged reason={p.done.changed} />
            <code className="path-line">{p.done.target}</code>

            <div className="studio-spacer" />

            <div className="side-actions">
              {p.nextInQueue ? (
                <>
                  <button type="button" className="btn primary big" onClick={() => p.switchDoc(p.nextInQueue!)}>
                    {t("Sıradaki belge")} <Icon name="arrowRight" />
                  </button>
                  <p className="hint center next-name">{splitPath(p.nextInQueue).name}</p>
                  <button type="button" className="btn big" onClick={() => p.revealInDir(p.done!.target)}>
                    <Icon name="folder" /> {t("Klasörde göster")}
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className="btn primary big" onClick={() => p.revealInDir(p.done!.target)}>
                    <Icon name="folder" /> {t("Klasörde göster")}
                  </button>
                  <button type="button" className="btn big" onClick={p.goHome}>
                    {p.queue.length > 1 ? t("Bitti, başa dön") : t("Yeni belge")}
                  </button>
                </>
              )}
              <button type="button" className="link-btn center" onClick={() => p.setDone(null)}>
                {t("Seçimleri değiştirip yeniden kaydet")}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="studio-right-scroll">
              {/* ADIM 1: MASKELEME KURALI (KURAL TAKIMI) SEÇİMİ + UYGULA */}
              <section className="studio-method-card" aria-label={t("Maskeleme kuralı seçimi")}>
                <div className="studio-method-head">
                  <div>
                    <span className="studio-step-pill">{t("1. Adım")}</span>
                    <h3>{t("Maskeleme Kuralı")}</h3>
                  </div>
                  <div className="studio-head-btns">
                    <button
                      type="button"
                      className="studio-panel-collapse-btn"
                      onClick={toggleRightCollapse}
                      title={t("Sağ paneli daralt")}
                      aria-label={t("Sağ paneli daralt")}
                    >
                      »
                    </button>
                  </div>
                </div>

                {selectedProfileObj && (
                  <div className="studio-right-rule-picker">
                    <div className={ruleMenuOpen ? "studio-preset-row on open" : "studio-preset-row on"}>
                      <button
                        type="button"
                        className="studio-preset-main-btn"
                        onClick={() => setRuleMenuOpen((v) => !v)}
                        aria-expanded={ruleMenuOpen}
                      >
                        <span className="studio-preset-radio">
                          <Icon name="check" size={11} />
                        </span>
                        <span className="studio-preset-text">
                          <b>{selectedProfileObj.name}</b>
                          <small>{t("{n} bilgi türü maskelenir", { n: enabledTypeCount(selectedProfileObj) })}</small>
                        </span>
                        <span className="studio-rule-trigger">
                          {ruleMenuOpen ? t("Kapat") : t("Değiştir")} <Icon name="chevron" size={13} />
                        </span>
                      </button>
                      <button
                        type="button"
                        className="icon-btn studio-rule-edit-btn"
                        title={t("{name} kuralını düzenle", { name: selectedProfileObj.name })}
                        aria-label={t("{name} kuralını düzenle", { name: selectedProfileObj.name })}
                        onClick={(e) => {
                          e.stopPropagation();
                          p.openSettings(selectedProfileObj.id);
                        }}
                      >
                        <Icon name="pen" size={14} />
                      </button>
                    </div>

                    {ruleMenuOpen && (
                      <div className="studio-preset-dropdown" role="radiogroup" aria-label={t("Kural Takımı")}>
                        {profiles.map((prof) => {
                          const active = prof.id === selectedProfileId;
                          return (
                            <div
                              key={prof.id}
                              className={active ? "studio-preset-row on" : "studio-preset-row"}
                            >
                              <button
                                type="button"
                                role="radio"
                                aria-checked={active}
                                className="studio-preset-main-btn"
                                onClick={() => {
                                  p.onSelectProfileId?.(prof.id);
                                  setRuleMenuOpen(false);
                                }}
                              >
                                <span className="studio-preset-radio">
                                  {active && <Icon name="check" size={11} />}
                                </span>
                                <span className="studio-preset-text">
                                  <b>{t(prof.name)}</b>
                                  <small>{t("{n} bilgi türü maskelenir", { n: enabledTypeCount(prof) })}</small>
                                </span>
                              </button>
                              <button
                                type="button"
                                className="icon-btn studio-rule-edit-btn"
                                title={t("{name} kuralını düzenle", { name: t(prof.name) })}
                                aria-label={t("{name} kuralını düzenle", { name: t(prof.name) })}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  p.openSettings(prof.id);
                                }}
                              >
                                <Icon name="pen" size={14} />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                <button
                  type="button"
                  className={
                    (!p.scan || hasUnappliedRuleChange ? "btn primary studio-apply-btn" : "btn studio-apply-btn") +
                    (p.busy === "scan" || p.batchProgress?.mode === "scan" ? " is-busy" : "")
                  }
                  style={
                    p.batchProgress?.mode === "scan"
                      ? ({ "--ilerleme": `${Math.round((p.batchProgress.done / Math.max(1, p.batchProgress.total)) * 100)}%` } as CSSProperties)
                      : undefined
                  }
                  disabled={p.busy !== null || p.batchProgress !== null}
                  onClick={() => p.onApplyRules?.()}
                >
                  <Icon name="scan" size={16} />
                  {p.batchProgress?.mode === "scan"
                    ? t("Taranıyor ({done}/{total})…", { done: p.batchProgress.done, total: p.batchProgress.total })
                    : p.busy === "scan"
                    ? t("Uygulanıyor…")
                    : !p.scan
                    ? docList.length > 1
                      ? t("Tüm Belgelere Uygula ({n} belge)", { n: docList.length })
                      : t("Uygula")
                    : hasUnappliedRuleChange
                    ? docList.length > 1
                      ? t("Seçilen Kuralı Tümüne Uygula ({n})", { n: docList.length })
                      : t("Seçilen Kuralı Uygula")
                    : docList.length > 1
                    ? t("Kuralı Tümüne Yeniden Uygula")
                    : t("Kuralı Yeniden Uygula")}
                </button>
              </section>

              {!p.scan ? (
                <div className="studio-inspector-placeholder studio-await-apply">
                  <Icon name="shield" size={24} />
                  <b>{t("Kural takımını seçip “Uygula” butonuna basın")}</b>
                  <p>
                    {docList.length > 1 ? (
                      <>
                        {rich(t("Yukarıdan maskeleme kural takımını seçip {uygula} dediğinizde klasördeki {tamami} tek seferde taranacaktır."), { uygula: <b>{t("Tüm Belgelere Uygula")}</b>, tamami: <b>{t("{n} belgenin tamamı", { n: docList.length })}</b> })}
                      </>
                    ) : (
                      <>
                        {rich(t("Yukarıdan maskeleme kural takımını seçtikten sonra {uygula} dediğinizde belgedeki kişisel bilgiler taranacak ve seçim yapmanız için burada listelenecektir."), { uygula: <b>{t("Uygula")}</b> })}
                      </>
                    )}
                  </p>
                </div>
              ) : (
                <>
                  {/* ADIM 2: BULUNAN BULGULAR (VARSAYILAN KAPALI, İSTENİRSE AÇILIR) */}
                  <section className="studio-findings-box" aria-label={t("Bulunan bulgular")}>
                    <button
                      type="button"
                      className={findingsPanelOpen ? "studio-findings-toggle open" : "studio-findings-toggle"}
                      onClick={() => setFindingsPanelOpen((v) => !v)}
                      aria-expanded={findingsPanelOpen}
                    >
                      <div className="studio-findings-toggle-left">
                        <span className="studio-step-pill">{t("2. Adım · Seçim Yapın")}</span>
                        <b>{t("Bulunan Bulgular ({n})", { n: p.allFindings.length })}</b>
                        <small>
                          {t("{n} bilgi maskelenecek · {m} açık kalacak", { n: p.included.length, m: p.allFindings.length - p.included.length })}
                        </small>
                      </div>
                      <span className="studio-rule-trigger">
                        {findingsPanelOpen ? t("Kapat") : t("Bulguları Aç")} <Icon name="chevron" size={14} />
                      </span>
                    </button>

                    {findingsPanelOpen && (
                      <div className="studio-findings-body">
                        {p.sure.length > 0 && (
                          <div className="studio-findings-toolbar">
                            <div className="studio-bulk-btns">
                              <button
                                type="button"
                                className="studio-pill-btn"
                                onClick={() => p.setMany(p.sure, true)}
                                title={t("Tüm bilgileri maskelenecek olarak işaretle")}
                              >
                                {t("Tümünü seç")}
                              </button>
                              <button
                                type="button"
                                className="studio-pill-btn subtle"
                                onClick={() => p.setMany(p.sure, false)}
                                title={t("Tüm seçimleri kaldır (açık bırak)")}
                              >
                                {t("Seçimi kaldır")}
                              </button>
                            </div>
                            {p.groups.length > 0 && (
                              <button
                                type="button"
                                className="studio-pill-btn subtle"
                                onClick={() => {
                                  const anyOpen = p.groups.some((g) => openCats[g.category.key]);
                                  if (anyOpen) {
                                    setOpenCats({});
                                  } else {
                                    const next: Record<string, boolean> = {};
                                    for (const g of p.groups) next[g.category.key] = true;
                                    setOpenCats(next);
                                  }
                                }}
                              >
                                {p.groups.some((g) => openCats[g.category.key]) ? t("Detayları daralt") : t("Detayları aç")}
                              </button>
                            )}
                          </div>
                        )}

                        {/* Ara ve Maskele */}
                        <div className="studio-search-box">{p.searchHideNode}</div>

                        {/* Kategori Grupları ve Açılabilir Tekil Bulgular */}
                        {p.groups.length === 0 ? (
                          <div className="studio-no-findings">
                            <Icon name="shield" size={22} />
                            <b>{t("Kişisel bilgi bulunamadı")}</b>
                            <span>{t("Gözden kaçan bir yer varsa belgede Alan Seç ile işaretleyebilirsiniz.")}</span>
                          </div>
                        ) : (
                          <div className="studio-cat-list">
                            {p.groups.map((g) => {
                              const allOn = g.on === g.items.length;
                              const state = allOn ? "on" : g.on ? "part" : "off";
                              const isExpanded = !!openCats[g.category.key];
                              return (
                                <div key={g.category.key} className={`studio-cat-item ${state}`}>
                                  <div className="studio-cat-row">
                                    <button
                                      type="button"
                                      className="studio-cat-toggle"
                                      aria-pressed={allOn}
                                      onClick={() => p.toggleGroup(g.items)}
                                      title={allOn ? t("Grubun tamamını açık bırak") : t("Grubun tamamını maskele")}
                                    >
                                      <span className="cat-check" aria-hidden>
                                        {state !== "off" && <Icon name={state === "on" ? "check" : "minus"} size={12} />}
                                      </span>
                                    </button>
                                    <button
                                      type="button"
                                      className="studio-cat-main"
                                      onClick={() => toggleCatExpand(g.category.key)}
                                      aria-expanded={isExpanded}
                                    >
                                      <Icon name={g.category.icon} size={18} />
                                      <div className="studio-cat-text">
                                        <b>{t(g.category.label)}</b>
                                        <span>{groupText(g, p.dataTypes, p.methodOf)}</span>
                                      </div>
                                      <span className="studio-cat-badge">{g.on}/{g.items.length}</span>
                                      <span className={isExpanded ? "studio-cat-chevron open" : "studio-cat-chevron"}>
                                        <Icon name="chevron" size={14} />
                                      </span>
                                    </button>
                                  </div>

                                  {isExpanded && (
                                    <ul className="studio-finding-list">
                                      {g.items.map((f) => {
                                        const isHidden = !p.excluded.has(f.id);
                                        return (
                                          <li
                                            key={f.id}
                                            className={isHidden ? "on" : "off"}
                                            onMouseEnter={() => p.setHovered(f.id)}
                                            onMouseLeave={() => p.setHovered(null)}
                                          >
                                            <button
                                              type="button"
                                              className="studio-finding-btn"
                                              onClick={() => {
                                                if (f.page && f.page !== p.previewPage) p.setPreviewPage(f.page);
                                                p.toggleFinding(f.id);
                                              }}
                                            >
                                              <span className="studio-finding-check">
                                                {isHidden && <Icon name="check" size={11} />}
                                              </span>
                                              <span className="studio-finding-val">
                                                {f.value || t(f.type_label)}
                                                <small>{t(f.type_label)}</small>
                                              </span>
                                              {f.page > 0 && <span className="studio-finding-page">{t("S.{n}", { n: f.page })}</span>}
                                            </button>
                                          </li>
                                        );
                                      })}
                                    </ul>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {docList.length > 1 && (
                          <div className="studio-sync-hint">
                            <Icon name="sparkle" size={13} />
                            <span>
                              {t("Seçimler klasördeki tüm belgelere ({n} belge) otomatik senkronize edilir.", { n: docList.length })}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </section>

                  {/* Emin olamadıklarımız, KVKK Tanınabilirlik uyarısı ve Öğrenme çubuğu */}
                  <div className="studio-extras">
                    <ReviewExtras
                      unsure={p.unsure}
                      sure={p.sure}
                      excluded={p.excluded}
                      onToggle={p.toggleFinding}
                      onSetMany={p.setMany}
                      lastOff={p.lastOff}
                      onClearLastOff={p.clearLastOff}
                      onError={p.setError}
                      methodOf={p.methodOf}
                      onBlackout={p.addBlackout}
                      unsureOpen={unsurePanelOpen}
                      onToggleUnsureOpen={() => setUnsurePanelOpen((v) => !v)}
                    />
                  </div>

                  {(p.scan.warnings.length > 0 || p.vaultLocked) && (
                    <details className="notes studio-notes">
                      <summary>
                        <Icon name="alert" size={14} /> {t("Bilmeniz gerekenler")}
                      </summary>
                      <ul>
                        {p.vaultLocked && (
                          <li>
                            {t("Özel ifadeleriniz kilitli olduğu için aranmadı.")}{" "}
                            <button type="button" className="link-btn" onClick={p.openUnlock}>
                              {t("Kilidi aç")}
                            </button>
                          </li>
                        )}
                        {p.scan.warnings.map((w) => (
                          <li key={w}>{t(w)}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              )}
            </div>

            {/* ADIM 3: SAĞ ALT SABİT MASKELEME VE KAYDETME ALANI */}
            {p.scan && (
              <div className="studio-right-foot">
                {p.unlocated > 0 && (
                  <p className="warn-text">
                    {t("{n} bilginin belgedeki yeri bulunamadı.", { n: p.unlocated })}
                  </p>
                )}
                {p.passwordNode}
                {p.folderTargetDir ? (
                  <div className="studio-folder-save-box">
                    <div className="studio-folder-save-head">
                      <span className="studio-folder-save-label">
                        <Icon name="folder" size={13} /> {t("Kayıt Konumu:")}
                      </span>
                      <button
                        type="button"
                        className="btn small studio-change-target-btn"
                        onClick={() => {
                          if (p.folderTargetDir) {
                            const parts = splitPath(p.folderTargetDir);
                            setEditTargetParent(parts.dir || "");
                            setEditTargetFolderName(parts.name || "");
                          }
                          setFolderTargetModalOpen(true);
                        }}
                        title={t("Maskeli belgelerin kaydedileceği ana klasörü ve klasör adını değiştir")}
                      >
                        <Icon name="pen" size={12} /> {t("Konum / İsim Değiştir")}
                      </button>
                    </div>
                    <div className="studio-folder-save-path" title={p.folderTargetDir}>
                      <span className="studio-folder-save-parent">{splitPath(p.folderTargetDir).dir}/</span>
                      <span className="studio-folder-save-name">{splitPath(p.folderTargetDir).name}</span>
                    </div>
                  </div>
                ) : (
                  p.saveLineNode
                )}
                {docList.length > 1 && p.runMaskAll ? (
                  <div className="studio-save-group">
                    <button
                      type="button"
                      className={"btn primary big studio-save-btn" + (p.batchProgress?.mode === "mask" ? " is-busy" : "")}
                      style={
                        p.batchProgress?.mode === "mask"
                          ? ({ "--ilerleme": `${Math.round((p.batchProgress.done / Math.max(1, p.batchProgress.total)) * 100)}%` } as CSSProperties)
                          : undefined
                      }
                      disabled={p.busy !== null || p.batchProgress !== null}
                      onClick={p.runMaskAll}
                    >
                      <Icon name="shield" size={17} />
                      {p.batchProgress?.mode === "mask"
                        ? t("Kaydediliyor ({done}/{total})…", { done: p.batchProgress.done, total: p.batchProgress.total })
                        : t("Tüm Belgeleri Maskele ve Kaydet ({n} belge)", { n: docList.length })}
                    </button>
                    <button
                      type="button"
                      className="btn big studio-save-single-btn-prominent"
                      disabled={!p.canSave || p.batchProgress !== null}
                      onClick={p.runMask}
                      title={t("Yalnızca şu an görüntülenen bu belgeyi maskeleyip güvenli kopyasını kaydeder")}
                    >
                      <Icon name="doc" size={15} />
                      <span>{t("Yalnızca Bu Belgeyi Maskele ve Kaydet ({n} bilgi)", { n: p.included.length })}</span>
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className={"btn primary big studio-save-btn" + (p.busy === "mask" ? " is-busy" : "")}
                    disabled={!p.canSave}
                    onClick={p.runMask}
                  >
                    <Icon name="shield" size={17} />
                    {p.allFindings.length === 0 && p.dropped.size === 0 ? t("Maskelenecek bilgi yok") : p.saveLabel}
                  </button>
                )}
                {p.saveErrorNode}
              </div>
            )}
          </>
        )}
      </aside>

      {(p.busy === "mask" || p.batchProgress?.mode === "mask") && p.source && (
        <div className="maske-ortu" role="status" aria-live="polite">
          <div className="loading-card">
            <span className="tara-belge maske" aria-hidden><i /><i /><i /><i /></span>
            <b>
              {p.batchProgress?.mode === "mask"
                ? t("Kaydediliyor ({done}/{total})…", { done: p.batchProgress.done, total: p.batchProgress.total })
                : t("Kaydediliyor…")}
            </b>
            <span>{splitPath(p.source).name}</span>
            {p.batchProgress?.mode === "mask" && (
              <span className="ilerleme-serit" aria-hidden>
                <i style={{ width: `${Math.round((p.batchProgress.done / Math.max(1, p.batchProgress.total)) * 100)}%` }} />
              </span>
            )}
          </div>
        </div>
      )}

      {confirmDeleteRecent && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => e.target === e.currentTarget && setConfirmDeleteRecent(null)}
        >
          <div className="modal studio-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-del-title">
            <div className="modal-head">
              <span className="file-icon danger">
                <Icon name="trash" size={18} />
              </span>
              <div>
                <h2 id="confirm-del-title">
                  {confirmDeleteRecent.mode === "all"
                    ? t("Tüm işlem geçmişi silinsin mi?")
                    : confirmDeleteRecent.mode === "folder"
                    ? t("Klasör işlem geçmişi silinsin mi?")
                    : t("İşlem kaydı silinsin mi?")}
                </h2>
                <p className="hint">
                  {confirmDeleteRecent.mode === "all" ? (
                    <>
                      {rich(t("Son yapılanlar listesindeki {n} belgenin işlem geçmişi programın veritabanından kalıcı olarak silinecek. Onaylıyor musunuz?"), { n: <b>{confirmDeleteRecent.count}</b> })}
                    </>
                  ) : confirmDeleteRecent.mode === "folder" ? (
                    <>
                      {rich(t("{name} klasöründeki {n} belgenin işlem kaydı programın veritabanından kalıcı olarak silinecek. Onaylıyor musunuz?"), { name: <b>“{confirmDeleteRecent.name}”</b>, n: <b>{confirmDeleteRecent.count}</b> })}
                    </>
                  ) : (
                    <>
                      {rich(t("{name} belgesine ait işlem kaydı programın veritabanından kalıcı olarak silinecek. Onaylıyor musunuz?"), { name: <b>“{confirmDeleteRecent.name}”</b> })}
                    </>
                  )}
                </p>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label={t("Kapat")}
                onClick={() => setConfirmDeleteRecent(null)}
              >
                <Icon name="x" size={14} />
              </button>
            </div>
            <div className="studio-confirm-actions">
              <button
                type="button"
                className="btn"
                onClick={() => setConfirmDeleteRecent(null)}
              >
                {t("Vazgeç")}
              </button>
              <button
                type="button"
                className="btn danger"
                onClick={() => {
                  if (confirmDeleteRecent.mode === "all") {
                    setInspectedRecentTarget(null);
                    p.clearRecent();
                  } else if (confirmDeleteRecent.mode === "folder") {
                    if (confirmDeleteRecent.targets.includes(inspectedRecentTarget || "")) {
                      setInspectedRecentTarget(null);
                    }
                    p.removeRecent?.(confirmDeleteRecent.targets);
                  } else {
                    if (inspectedRecentTarget === confirmDeleteRecent.target) {
                      setInspectedRecentTarget(null);
                    }
                    p.removeRecent?.(confirmDeleteRecent.target);
                  }
                  setConfirmDeleteRecent(null);
                }}
              >
                <Icon name="trash" size={14} />{" "}
                {confirmDeleteRecent.mode === "all"
                  ? t("Evet, Tümünü Sil")
                  : confirmDeleteRecent.mode === "folder"
                  ? t("Evet, Klasör Kayıtlarını Sil")
                  : t("Evet, Kaydı Sil")}
              </button>
            </div>
          </div>
        </div>
      )}

      {folderTargetModalOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => e.target === e.currentTarget && setFolderTargetModalOpen(false)}
        >
          <div className="modal studio-target-modal" role="dialog" aria-modal="true" aria-labelledby="target-modal-title">
            <div className="modal-head">
              <span className="file-icon">
                <Icon name="folder" size={18} />
              </span>
              <div>
                <h2 id="target-modal-title">{t("Klasör Kayıt Konumu ve Adı")}</h2>
                <p className="hint">
                  {t("Maskeli kopyaların oluşturulacağı ana dizini ve yeni klasör adını belirleyin.")}
                </p>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label={t("Kapat")}
                onClick={() => setFolderTargetModalOpen(false)}
              >
                <Icon name="x" size={14} />
              </button>
            </div>

            <div className="studio-target-form">
              <div className="studio-target-field">
                <label htmlFor="target-parent-input">{t("Kayıt Konumu (Ana Dizin)")}</label>
                <div className="studio-target-input-row">
                  <input
                    id="target-parent-input"
                    type="text"
                    className="input"
                    value={editTargetParent}
                    onChange={(e) => setEditTargetParent(e.target.value)}
                    placeholder={t("Örn: /Users/kullanici/Desktop")}
                  />
                  <button
                    type="button"
                    className="btn"
                    onClick={async () => {
                      const picked = await open({
                        directory: true,
                        multiple: false,
                        title: t("Maskeli Belgelerin Kaydedileceği Ana Dizini Seçin"),
                      });
                      if (typeof picked === "string" && picked.trim()) {
                        setEditTargetParent(picked.trim());
                      }
                    }}
                  >
                    <Icon name="folder" size={14} /> {t("Gözat…")}
                  </button>
                </div>
              </div>

              <div className="studio-target-field">
                <label htmlFor="target-name-input">{t("Yeni Klasör Adı")}</label>
                <input
                  id="target-name-input"
                  type="text"
                  className="input"
                  value={editTargetFolderName}
                  onChange={(e) => setEditTargetFolderName(e.target.value)}
                  placeholder={t("Örn: Belgeler_maskeli")}
                />
              </div>

              <div className="studio-target-preview-box">
                <small>{t("Maskelenmiş Dosyaların Kaydedileceği Tam Yol:")}</small>
                <code>
                  {editTargetParent.trim().replace(/[/\\]+$/, "")}
                  {editTargetParent.includes("\\") ? "\\" : "/"}
                  {editTargetFolderName.trim()}
                </code>
              </div>
            </div>

            <div className="studio-confirm-actions">
              <button
                type="button"
                className="btn"
                onClick={() => setFolderTargetModalOpen(false)}
              >
                {t("Vazgeç")}
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={!editTargetParent.trim() || !editTargetFolderName.trim()}
                onClick={() => {
                  const cleanParent = editTargetParent.trim().replace(/[/\\]+$/, "");
                  const cleanName = editTargetFolderName.trim().replace(/^[/\\]+|[/\\]+$/g, "");
                  if (!cleanParent || !cleanName) return;
                  const isWin = cleanParent.includes("\\");
                  const sep = isWin ? "\\" : "/";
                  const newFull = `${cleanParent}${sep}${cleanName}`;
                  p.updateFolderTargetDir?.(newFull);
                  setFolderTargetModalOpen(false);
                }}
              >
                <Icon name="check" size={14} /> {t("Kaydet ve Uygula")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================================
   TASARIM 4: ADIM ADIM SİHİRBAZ (REHBERLİ AKIŞ + AMAÇ SEÇİMİ)
   1. Belge ve Amaç Seçimi ➔ 2. Bulguları Gözden Geçir ➔ 3. Güvenli Kopya Hazır
   ============================================================================ */

export function WizardWorkspace(p: SharedLayoutProps) {
  const t = useT();
  const [purposeId, setPurposeId] = useState<string>("musteri");
  const currentPurpose = PURPOSES.find((x) => x.id === purposeId) ?? PURPOSES[0];
  const step: 1 | 2 | 3 = !p.source ? 1 : p.done ? 3 : 2;

  return (
    <div className="wizard-shell">
      {/* ÜST ADIM ÇUBUĞU (STEPPER) */}
      <nav className="wizard-stepper" aria-label={t("Maskeleme adımları")}>
        <div className="wizard-stepper-inner">
          <button
            type="button"
            className={["wizard-step", step === 1 ? "active" : "done"].join(" ")}
            onClick={p.goHome}
          >
            <span className="wizard-step-num">
              {step > 1 ? <Icon name="check" size={14} /> : "1"}
            </span>
            <span className="wizard-step-text">
              <b>{t("1. Belge ve Amaç Seçimi")}</b>
              <small>{p.source ? splitPath(p.source).name : t("Belge yükleyin ve paylaşım amacını seçin")}</small>
            </span>
          </button>

          <span className="wizard-step-line" aria-hidden />

          <button
            type="button"
            disabled={!p.source}
            className={["wizard-step", step === 2 ? "active" : step > 2 ? "done" : "upcoming"].join(" ")}
            onClick={() => (p.done ? p.setDone(null) : undefined)}
          >
            <span className="wizard-step-num">
              {step > 2 ? <Icon name="check" size={14} /> : "2"}
            </span>
            <span className="wizard-step-text">
              <b>{t("2. Bulguları Gözden Geçir")}</b>
              <small>
                {p.scan ? t("{n}/{m} bilgi maskelenecek", { n: p.included.length, m: p.allFindings.length }) : t("Tespit edilen verileri onaylayın")}
              </small>
            </span>
          </button>

          <span className="wizard-step-line" aria-hidden />

          <div className={["wizard-step", step === 3 ? "active done-step" : "upcoming"].join(" ")}>
            <span className="wizard-step-num">
              {step === 3 ? <Icon name="check" size={14} /> : "3"}
            </span>
            <span className="wizard-step-text">
              <b>{t("3. Güvenli Kopya Hazır")}</b>
              <small>{p.done ? t("Temizlendi ve doğrulandı") : t("İz bırakmadan kaydedilir")}</small>
            </span>
          </div>
        </div>
      </nav>

      {/* SİHİRBAZ GÖVDESİ */}
      <div className="wizard-container">
        {p.errorBanner}

        {/* ADIM 1: BELGE VE AMAÇ SEÇİMİ */}
        {step === 1 && (
          <div className="wizard-step1">
            <section className="wizard-purpose-card" aria-label={t("Paylaşım amacı")}>
              <div className="wizard-purpose-head">
                <div>
                  <span className="wizard-badge">{t("Adım 1A · Amaç Seçimi")}</span>
                  <h2>{t("Bu kopya ne için paylaşılacak?")}</h2>
                  <p>{t("Seçtiğiniz amaç işlem özetine işlenir ve uygun kontrol akışını hazırlar.")}</p>
                </div>
                {p.profile && (
                  <span className="wizard-profile-pill">
                    {rich(t("Kural takımı: {name}"), { name: <b>{t(p.profile.name)}</b> })}{" "}
                    <button type="button" className="link-btn" onClick={() => p.openSettings()}>
                      {t("Değiştir")}
                    </button>
                  </span>
                )}
              </div>

              <div className="wizard-purpose-grid">
                {PURPOSES.map((item) => {
                  const active = item.id === purposeId;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={active ? "wizard-purpose-item on" : "wizard-purpose-item"}
                      onClick={() => setPurposeId(item.id)}
                    >
                      <div className="wizard-purpose-top">
                        <span className="wizard-purpose-icon">
                          <Icon name={item.icon} size={18} />
                        </span>
                        <span className="wizard-purpose-check">
                          {active && <Icon name="check" size={13} />}
                        </span>
                      </div>
                      <b>{t(item.label)}</b>
                      <span>{item.desc}</span>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="wizard-upload-card" aria-label={t("Belge seçimi")}>
              <div className="wizard-upload-head">
                <span className="wizard-badge">{t("Adım 1B · Belge veya Metin Yükleme")}</span>
                <div className="home-tabs" role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={p.homeTab === "belge"}
                    className={p.homeTab === "belge" ? "on" : undefined}
                    onClick={() => p.setHomeTab("belge")}
                  >
                    <Icon name="files" size={16} /> {t("Belge Yükle")}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={p.homeTab === "metin"}
                    className={p.homeTab === "metin" ? "on" : undefined}
                    onClick={() => p.setHomeTab("metin")}
                  >
                    <Icon name="text" size={16} /> {t("Metin Yapıştır")}
                  </button>
                </div>
              </div>

              {p.homeTab === "metin" ? (
                <PasteScreen rules={p.scanRules} offByRule={p.offByRule} methodOf={p.methodOf} />
              ) : (
                <>
                  <button type="button" className="home-drop wizard-drop" onClick={p.pickSource}>
                    <span className="home-drop-icon">
                      <Icon name="upload" size={34} />
                    </span>
                    <b>{t("Belgeleri buraya bırakın ve 2. Adıma geçin")}</b>
                    <span>
                      {rich(t("Seçilen amaç: {amac}. Kişisel bilgileri otomatik bulacağız; kaydetmeden önce hepsini gözden geçireceksiniz."), { amac: <b>{currentPurpose.label}</b> })}
                    </span>
                    <span className="home-pick">{t("Bilgisayardan seç")}</span>
                    <span className="home-formats">
                      {t("PDF · Word · Excel · PowerPoint · Fotoğraf · XML, CSV, JSON, TXT, LOG")}
                    </span>
                  </button>
                  <p className="home-alt center">
                    {t("Bir klasördeki bütün belgeleri toplu işlemek için:")}{" "}
                    <button type="button" className="link-btn" onClick={p.pickFolder}>
                      {t("Klasör seçin")}
                    </button>
                  </p>
                </>
              )}
            </section>
          </div>
        )}

        {/* ADIM 2: BULGULARI GÖZDEN GEÇİR */}
        {step === 2 && (
          <div className="wizard-step2">
            {/* Çoklu belge varsa üst sıra */}
            {p.queue.length > 1 && (
              <nav className="queue wizard-queue" aria-label={t("Belgeler")}>
                <span className="queue-count">
                  {t("{n}/{m} kaydedildi", { n: p.queue.filter((x) => p.saved[x]).length, m: p.queue.length })}
                </span>
                <div className="queue-list">
                  {p.queue.map((docPath, i) => (
                    <button
                      key={docPath}
                      type="button"
                      className={["queue-item", docPath === p.source ? "on" : "", p.saved[docPath] ? "done" : ""].join(" ")}
                      onClick={() => p.switchDoc(docPath)}
                    >
                      <span className="queue-num">{p.saved[docPath] ? <Icon name="check" size={12} /> : i + 1}</span>
                      <span className="queue-name">{splitPath(docPath).name}</span>
                    </button>
                  ))}
                </div>
              </nav>
            )}

            {/* Kompakt Amaç Seçimi Çubuğu */}
            <div className="wizard-purpose-bar">
              <span className="wizard-purpose-label">
                <Icon name="shield" size={15} /> {t("Paylaşım Amacı:")}
              </span>
              <div className="wizard-purpose-pills">
                {PURPOSES.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={item.id === purposeId ? "on" : undefined}
                    onClick={() => setPurposeId(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {!p.scan ? (
              <div className="wizard-loading-wrap">
                <div className="loading-card">
                  <span className="tara-belge" aria-hidden><i /><i /><i /><i /></span>
                  <b>{t("Adım 2 Hazırlanıyor: Kişisel bilgiler aranıyor…")}</b>
                  <span>{splitPath(p.source!).name}</span>
                </div>
              </div>
            ) : (
              <>
                <div className="wizard-split-grid">
                  {/* SOL SÜTUN: KATEGORİ KARTLARI VE KONTROLLER */}
                  <div className="wizard-left-col">
                    <div className="wizard-card">
                      <div className="wizard-card-head">
                        <span className="file-chip">
                          <ExtBadge path={p.source!} /> {splitPath(p.source!).name}
                        </span>
                        <h2>
                          {p.allFindings.length
                            ? t("Bu belgede {n} kişisel bilgi bulduk", { n: p.allFindings.length })
                            : t("Kişisel bilgi bulamadık")}
                        </h2>
                        <p>
                          {p.sure.length
                            ? t("Maskelenecek kategoriler işaretli. Açık kalmasını istediğiniz karta dokunun; sağdaki önizleme anında güncellenir.")
                            : t("Gözden kaçan bir yer varsa sağdaki belgede Alan Seç ile işaretleyebilirsiniz.")}
                        </p>
                      </div>

                      {p.groups.length > 0 && (
                        <div className="cat-grid wizard-cat-grid">
                          {p.groups.map((g) => {
                            const allOn = g.on === g.items.length;
                            const state = allOn ? "on" : g.on ? "part" : "off";
                            return (
                              <button
                                key={g.category.key}
                                type="button"
                                className={`wizard-cat-card ${state}`}
                                aria-pressed={allOn}
                                onClick={() => p.toggleGroup(g.items)}
                              >
                                <span className="wizard-cat-icon">
                                  <Icon name={g.category.icon} size={15} />
                                </span>
                                <span className="wizard-cat-info">
                                  <b>{t(g.category.label)}</b>
                                  <span>{groupText(g, p.dataTypes, p.methodOf)}</span>
                                </span>
                                <span className="cat-check" aria-hidden>
                                  {state !== "off" && <Icon name={state === "on" ? "check" : "minus"} size={11} />}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      )}

                      <ReviewExtras
                        unsure={p.unsure}
                        sure={p.sure}
                        excluded={p.excluded}
                        onToggle={p.toggleFinding}
                        onSetMany={p.setMany}
                        lastOff={p.lastOff}
                        onClearLastOff={p.clearLastOff}
                        onError={p.setError}
                        methodOf={p.methodOf}
                        onBlackout={p.addBlackout}
                      />

                      {p.searchHideNode}

                      <div className="wizard-options-box">
                        {p.saveLineNode}
                        {p.passwordNode}
                      </div>
                    </div>
                  </div>

                  {/* SAĞ SÜTUN: CANLI BELGE ÖNİZLEMESİ */}
                  <div className="wizard-right-col">
                    <div className="wizard-preview-card">
                      <div className="wizard-preview-head">
                        <div>
                          <b>{t("Canlı Belge Önizlemesi")}</b>
                          <small>{t("Kutulara tıklayarak tek tek açıp kapatabilirsiniz")}</small>
                        </div>
                        <div className="segmented view-toggle" role="tablist">
                          <button
                            type="button"
                            role="tab"
                            aria-selected={p.view === "orijinal"}
                            className={p.view === "orijinal" ? "on" : undefined}
                            onClick={() => p.setView("orijinal")}
                          >
                            {t("Orijinal")}
                          </button>
                          <button
                            type="button"
                            role="tab"
                            aria-selected={p.view !== "orijinal"}
                            className={p.view !== "orijinal" ? "on" : undefined}
                            onClick={() => p.setView("maskeli")}
                          >
                            {t("Maskelenmiş hâli")}
                          </button>
                        </div>
                      </div>
                      <div className="wizard-preview-body">
                        {p.previewNode(p.view === "kaydedilen" ? "maskeli" : p.view)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* SİHİRBAZ ALT ADIM ÇUBUĞU */}
                <div className="wizard-bottom-bar">
                  <button type="button" className="btn" onClick={p.goHome}>
                    <Icon name="arrowLeft" size={15} /> {t("Adım 1: Başka Belge Seç")}
                  </button>
                  <div className="wizard-bottom-right">
                    <div className="wizard-bottom-summary">
                      <span>
                        {rich(t("Amaç: {amac}"), { amac: <b>{currentPurpose.label}</b> })}
                      </span>
                      <span>·</span>
                      <span>
                        {rich(t("{n} kişisel bilgi maskelenecek"), { n: <b>{p.included.length}</b> })}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn primary big wizard-next-btn"
                      disabled={!p.canSave}
                      onClick={p.runMask}
                    >
                      {t("Adım 3: {label}", { label: p.saveLabel })} <Icon name="arrowRight" size={16} />
                    </button>
                    {p.saveErrorNode}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ADIM 3: GÜVENLİ KOPYA HAZIR */}
        {step === 3 && p.done && (
          <div className="wizard-step3">
            <div className="wizard-done-banner">
              <span className={p.done.leaked?.length ? "done-icon warn" : "done-icon"}>
                <Icon name={p.done.leaked?.length ? "alert" : "check"} size={28} />
              </span>
              <div className="wizard-done-text">
                <span className="wizard-badge ok">{t("Adım 3 Tamamlandı · Paylaşım Amacı: {amac}", { amac: currentPurpose.label })}</span>
                <h1>{sonucBasligi(t, p.done)}</h1>
                <p>{sonucAciklamasi(t, p.done)}</p>
                <SonucNotu />
              </div>
              <div className="wizard-done-cta">
                {p.nextInQueue ? (
                  <button type="button" className="btn primary big" onClick={() => p.switchDoc(p.nextInQueue!)}>
                    {t("Sıradaki belge")} <Icon name="arrowRight" />
                  </button>
                ) : (
                  <button type="button" className="btn primary big" onClick={() => p.revealInDir(p.done!.target)}>
                    <Icon name="folder" /> {t("Klasörde göster")}
                  </button>
                )}
                <button type="button" className="btn big" onClick={() => p.setDone(null)}>
                  {t("← Adım 2'ye dön (Seçimleri değiştir)")}
                </button>
                <button type="button" className="btn big" onClick={p.goHome}>
                  {t("Yeni belge (Adım 1)")}
                </button>
              </div>
            </div>

            <div className="wizard-split-grid">
              <div className="wizard-left-col">
                <div className="wizard-card">
                  <h3>{t("Güvenlik ve Doğrulama Özeti")}</h3>
                  <ul className="done-list">
                    <li>
                      <Icon name="check" size={14} /> {rich(t("Paylaşım amacı: {amac}"), { amac: <b>{currentPurpose.label}</b> })}
                    </li>
                    <li>
                      <Icon name="check" size={14} /> {t("Yazar, yorum, konum gibi gizli bilgiler temizlendi")}
                    </li>
                    {!!p.done.dropped && (
                      <li>
                        <Icon name="check" size={14} /> {t("{n} sayfa kopyadan çıkarıldı", { n: p.done.dropped })}
                      </li>
                    )}
                    {p.done.encrypted && (
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
                    {p.done.warnings.map((w) => (
                      <li key={w} className="done-warning">
                        <Icon name="alert" size={14} /> {t(w)}
                      </li>
                    ))}
                  </ul>
                  {p.leftOpenNode}
                  <PathChanged reason={p.done.changed} />
                  <code className="path-line">{p.done.target}</code>
                </div>
              </div>

              <div className="wizard-right-col">
                <div className="wizard-preview-card">
                  <div className="wizard-preview-head">
                    <b>{t("Kaydedilen Güvenli Kopya")}</b>
                  </div>
                  <div className="wizard-preview-body">
                    {p.previewNode(p.done.encrypted ? "maskeli" : "kaydedilen")}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
