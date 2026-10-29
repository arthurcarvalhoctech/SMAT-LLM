import Link from "next/link";

const links = [
  { href: "/executions", label: "Execuções" },
  { href: "/laya", label: "Laya" },
  { href: "/reports", label: "Relatórios" },
  { href: "/files", label: "Arquivos" },
];

export function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-white/5 bg-slate-950/80 backdrop-blur">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-3">
          <span className="brand-mark flex h-9 w-9 items-center justify-center rounded-xl font-mono text-sm font-bold text-white shadow-glow">
            S
          </span>
          <span className="hidden flex-col leading-tight sm:flex">
            <span className="text-sm font-semibold tracking-tight text-white">
              SMAT Scenario Explorer
            </span>
            <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
              merge intelligence
            </span>
          </span>
        </Link>

        <nav className="flex items-center gap-1 overflow-x-auto text-sm">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="whitespace-nowrap rounded-lg px-3 py-2 text-slate-400 transition hover:bg-white/5 hover:text-white"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
