import type { ReactNode } from "react";

export function MobileLabel({ children }: { children: ReactNode }) {
  return (
    <span className="mb-1 block text-[10px] uppercase tracking-[0.16em] text-zinc-500 sm:hidden">
      {children}
    </span>
  );
}
