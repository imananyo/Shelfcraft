import {
  Clapperboard, Factory, FileText, Images, LayoutDashboard, LayoutTemplate, Library, ListChecks, Package, Palette,
  PenLine, ScanSearch, Settings, Sparkles, WandSparkles, type LucideIcon,
} from "lucide-react";

export interface NavItem { href: string; label: string; icon: LucideIcon; match?: string[] }
export interface NavGroup { label: string; items: NavItem[] }

export const NAV: NavGroup[] = [
  { label: "", items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }] },
  {
    label: "Create",
    items: [
      { href: "/create", label: "New creative", icon: Sparkles },
      { href: "/listings", label: "Listing builder", icon: FileText },
      { href: "/studio", label: "Image studio", icon: Images },
      { href: "/edit", label: "Spot edit", icon: WandSparkles },
      { href: "/aplus", label: "A+ content", icon: LayoutTemplate },
      { href: "/videos", label: "Video creator", icon: Clapperboard },
      { href: "/inspire", label: "Inspire", icon: ScanSearch },
      { href: "/factory", label: "Factory", icon: Factory },
    ],
  },
  {
    label: "Library",
    items: [
      { href: "/projects", label: "Designs", icon: PenLine, match: ["/editor"] },
      { href: "/library", label: "Assets", icon: Library },
      { href: "/jobs", label: "Jobs", icon: ListChecks },
    ],
  },
  {
    label: "Catalog",
    items: [
      { href: "/brands", label: "Brands", icon: Palette },
      { href: "/products", label: "Products", icon: Package },
    ],
  },
  { label: "System", items: [{ href: "/settings", label: "Settings", icon: Settings }] },
];

export const ALL_NAV = NAV.flatMap((g) => g.items);
