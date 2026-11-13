import {
  Clapperboard, Factory, FileText, FlaskConical, Gauge, History, Images, LayoutDashboard, LayoutTemplate, Library,
  ListChecks, Megaphone, Package, Palette, PenLine, ScanSearch, Settings, Sparkles, SquareStack, WandSparkles, Workflow, type LucideIcon,
} from "lucide-react";

export interface NavItem { href: string; label: string; icon: LucideIcon; match?: string[] }
export interface NavGroup { label: string; items: NavItem[] }

export const NAV: NavGroup[] = [
  { label: "", items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }] },
  {
    label: "Studio",
    items: [
      { href: "/create", label: "Create", icon: Sparkles },
      { href: "/scale", label: "Scale", icon: SquareStack },
      { href: "/playbooks", label: "Playbooks", icon: Workflow },
      { href: "/labs", label: "Labs", icon: FlaskConical },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/listings", label: "Listing builder", icon: FileText },
      { href: "/studio", label: "Image studio", icon: Images },
      { href: "/edit", label: "Spot edit", icon: WandSparkles },
      { href: "/aplus", label: "A+ content", icon: LayoutTemplate },
      { href: "/videos", label: "Videos", icon: Clapperboard },
      { href: "/ads", label: "Ads studio", icon: Megaphone },
      { href: "/grader", label: "Listing grader", icon: Gauge },
      { href: "/inspire", label: "Steal the look", icon: ScanSearch },
      { href: "/factory", label: "Factory", icon: Factory },
    ],
  },
  {
    label: "Catalog",
    items: [
      { href: "/brands", label: "Brand profile", icon: Palette },
      { href: "/products", label: "Products", icon: Package },
    ],
  },
  {
    label: "Library",
    items: [
      { href: "/sessions", label: "Recent work", icon: History },
      { href: "/projects", label: "Designs", icon: PenLine, match: ["/editor"] },
      { href: "/library", label: "Assets", icon: Library },
      { href: "/jobs", label: "Jobs", icon: ListChecks },
    ],
  },
  { label: "System", items: [{ href: "/settings", label: "Settings", icon: Settings }] },
];

export const ALL_NAV = NAV.flatMap((g) => g.items);
