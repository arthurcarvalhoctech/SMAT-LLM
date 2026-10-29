import { MobileLabel } from "@/components/mobile-label";
import { formatBytes, formatDate } from "@/lib/format";
import type { LayaLogFile } from "@/lib/types";

export function LayaLogList({ logs }: { logs: LayaLogFile[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
      <div className="hidden grid-cols-[1.8fr_auto_auto_auto_auto] gap-4 border-b border-zinc-200 bg-zinc-100 px-4 py-3 text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600 sm:grid">
        <span>Arquivo</span>
        <span>Tipo</span>
        <span>Tamanho</span>
        <span>Data</span>
        <span className="sr-only">Abrir</span>
      </div>

      <div className="divide-y divide-zinc-200">
        {logs.map((log) => (
          <a
            key={log.name}
            href={`/api/file/reports/laya/${encodeURIComponent(log.name)}`}
            target="_blank"
            rel="noreferrer"
            className="grid gap-2 px-4 py-4 transition hover:bg-zinc-50 sm:grid-cols-[1.8fr_auto_auto_auto_auto] sm:items-center sm:gap-4"
          >
            <div className="min-w-0">
              <MobileLabel>Arquivo</MobileLabel>
              <span className="block truncate font-mono text-sm text-zinc-900">
                {log.name}
              </span>
            </div>

            <div>
              <MobileLabel>Tipo</MobileLabel>
              <span className="font-mono text-xs uppercase text-zinc-600">
                {log.kind}
              </span>
            </div>

            <div>
              <MobileLabel>Tamanho</MobileLabel>
              <span className="text-xs text-zinc-600">
                {formatBytes(log.bytes)}
              </span>
            </div>

            <div>
              <MobileLabel>Data</MobileLabel>
              <span className="text-xs text-zinc-600">
                {formatDate(log.modified)}
              </span>
            </div>

            <span className="text-xs font-medium text-red-600 sm:text-right">
              Abrir →
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
