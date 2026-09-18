import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BookOpen,
  Layers3,
  ChevronRight,
  ShieldCheck,
  FileSearch,
  GitCompare,
  LayoutDashboard,
  Menu,
  Moon,
  ScanSearch,
  Settings,
  Sun,
  X,
} from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/knowledge-base", label: "Policies", icon: BookOpen },
  { to: "/workspace", label: "Extraction", icon: ScanSearch },
  { to: "/evidence", label: "Evidence", icon: FileSearch },
  { to: "/compare", label: "Compare", icon: GitCompare },
  { to: "/settings", label: "Settings", icon: Settings },
];

function useDarkMode() {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    const stored = localStorage.getItem("policylens-theme");
    if (stored) return stored === "dark";
    return false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("policylens-theme", dark ? "dark" : "light");
  }, [dark]);

  return { dark, toggle: () => setDark((d) => !d) };
}

export default function Layout() {
  const { dark, toggle } = useDarkMode();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen w-full items-stretch" style={{ width: "100%", maxWidth: "none" }}>
      <aside className="sidebar-rail hidden w-[232px] shrink-0 lg:flex lg:flex-col">
        <div className="flex h-[65px] shrink-0 items-center border-b border-white/10 px-4">
          <BrandHeader compact showSubtitle />
        </div>
        <nav aria-label="Main navigation" className="space-y-1 px-4 py-5">
          <div className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Workspace
          </div>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx("nav-link", isActive && "nav-link-active")
              }
            >
              <item.icon className="h-4 w-4 shrink-0 opacity-80" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-4 pb-5 pt-8">
          <div className="rounded-xl border border-white/10 bg-white/[.025] p-4">
            <ShieldCheck className="h-5 w-5 text-teal-300" />
            <p className="mt-3 text-xs font-medium text-slate-200">Built around the source</p>
            <p className="mt-2 text-[11px] leading-5 text-slate-400">
              Policy answers with traceable page citations.
            </p>
          </div>
          <div className="mt-4 border-t border-white/10 pt-4">
            <button
              type="button"
              onClick={toggle}
              className="btn-secondary w-full border-white/15 bg-white/5 text-slate-200 hover:bg-white/10"
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {dark ? "Light mode" : "Dark mode"}
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-[rgb(11_31_58_/0.5)]"
            aria-label="Close menu"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="sidebar-rail relative flex h-full w-72 flex-col shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 p-4">
              <BrandHeader compact />
              <button type="button" aria-label="Close navigation" className="btn-ghost p-2 text-slate-200" onClick={() => setMobileOpen(false)}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <nav className="flex-1 space-y-0.5 px-3 py-4">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    clsx("nav-link", isActive && "nav-link-active")
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </aside>
        </div>
      )}

      <div className="flex min-h-screen min-w-0 flex-1 flex-col" style={{ width: "100%", maxWidth: "none" }}>
        <header className="flex items-center justify-between border-b border-border bg-surface-raised px-4 py-3 sm:px-6 lg:hidden">
          <button type="button" aria-label="Open navigation" className="btn-ghost p-2" onClick={() => setMobileOpen(true)}>
            <Menu className="h-5 w-5" />
          </button>
          <BrandHeader compact light />
          <button type="button" aria-label="Toggle color theme" className="btn-ghost p-2" onClick={toggle}>
            {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
        </header>

        <div className="hidden h-[65px] shrink-0 items-center justify-between border-b border-border bg-surface-raised px-9 lg:flex">
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <span>Workspace</span>
            <ChevronRight className="h-3 w-3" />
            <span className="font-medium text-ink">
              {navItems.find((item) => item.to === location.pathname)?.label ?? "Policy review"}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-ink-muted">GMC Policy Intelligence</span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-50 text-[11px] font-semibold text-brand-700 dark:bg-brand-950">
              PL
            </span>
          </div>
        </div>
        <a href="#main-content" className="sr-only focus:not-sr-only">
          Skip to content
        </a>
        <main
          id="main-content"
          className="paper-bg min-w-0 w-full flex-1 overflow-x-hidden"
          style={{ width: "100%", maxWidth: "none" }}
        >
          <Outlet />
        </main>

        <footer className="border-t border-border bg-surface-raised px-4 py-3 text-center text-xs text-ink-faint sm:px-6">
          PolicyLens · Document intelligence workspace
        </footer>
      </div>
    </div>
  );
}

function BrandHeader({
  compact = false,
  light = false,
  showSubtitle = false,
}: {
  compact?: boolean;
  light?: boolean;
  showSubtitle?: boolean;
}) {
  return (
    <div
      className={clsx(
        "flex items-center gap-3",
        !compact && "border-b border-white/10 px-4 py-5",
      )}
    >
      <div className={clsx(
        "flex items-center justify-center rounded-md bg-brand-600 text-white shadow-sm",
        compact ? "h-9 w-9" : "h-10 w-10",
      )}>
        <Layers3 className={compact ? "h-4 w-4" : "h-5 w-5"}/>
      </div>
      <div>
        <div
          className={clsx(
            "font-headline font-semibold tracking-tight leading-none",
            compact ? "text-lg" : "text-xl",
            light ? "text-ink" : "text-white",
          )}
        >
          PolicyLens
        </div>
        {(!compact || showSubtitle) && (
          <div className="mt-1 text-[9px] font-medium uppercase tracking-[0.12em] text-slate-400">
            Document Intelligence
          </div>
        )}
      </div>
    </div>
  );
}

function clsx(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
