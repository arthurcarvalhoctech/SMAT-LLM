import Link from "next/link";
import type { ReactNode } from "react";

export type BadgeTone =
  | "slate"
  | "indigo"
  | "emerald"
  | "amber"
  | "rose"
  | "cyan";

const badgeToneClasses: Record<BadgeTone, string> = {
  slate: "border-zinc-300 bg-zinc-100 text-zinc-700",
  indigo: "border-red-200 bg-red-50 text-red-700",
  emerald: "border-zinc-300 bg-zinc-100 text-zinc-700",
  amber: "border-red-200 bg-red-50 text-red-700",
  rose: "border-red-200 bg-red-50 text-red-700",
  cyan: "border-zinc-300 bg-zinc-100 text-zinc-700",
};

const statToneClasses: Record<BadgeTone, string> = {
  slate: "from-zinc-200/60",
  indigo: "from-zinc-200/60",
  emerald: "from-zinc-200/60",
  amber: "from-zinc-200/60",
  rose: "from-zinc-200/60",
  cyan: "from-zinc-200/60",
};

export function Badge({
  children,
  tone = "slate",
  className = "",
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-wide ${badgeToneClasses[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "indigo",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: BadgeTone;
}) {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-gradient-to-br ${statToneClasses[tone]} to-transparent p-5`}
    >
      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold tracking-tight text-white">
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow ? (
          <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-indigo-300/80">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-white">
          {title}
        </h2>
        {description ? (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-8 text-center">
      <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] font-mono text-lg text-slate-500">
        ∅
      </div>
      <h3 className="mt-4 text-base font-semibold text-slate-200">{title}</h3>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">
        {description}
      </p>
      {children ? <div className="mt-5">{children}</div> : null}
    </div>
  );
}

export function Breadcrumbs({
  items,
}: {
  items: Array<{ href?: string; label: string }>;
}) {
  return (
    <nav className="mb-5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`} className="flex items-center gap-2">
          {index > 0 ? <span className="text-slate-700">/</span> : null}
          {item.href ? (
            <Link
              href={item.href}
              className="transition hover:text-slate-300"
            >
              {item.label}
            </Link>
          ) : (
            <span className="text-slate-400">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
