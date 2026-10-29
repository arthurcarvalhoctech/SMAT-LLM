import { promises as fs } from "node:fs";
import path from "node:path";

import { safeResolve } from "@/lib/smat-data";

export const dynamic = "force-dynamic";

const textExtensions = new Set([
  "",
  ".csv",
  ".java",
  ".json",
  ".jsonl",
  ".log",
  ".md",
  ".properties",
  ".py",
  ".sh",
  ".ts",
  ".tsx",
  ".txt",
  ".xml",
  ".yaml",
  ".yml",
]);

export async function GET(
  _request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path: segments } = await context.params;

  try {
    const file = safeResolve(...segments);
    const stat = await fs.stat(file);
    if (!stat.isFile()) {
      return new Response("Not found", { status: 404 });
    }

    const data = await fs.readFile(file);
    const extension = path.extname(file).toLowerCase();
    const contentType =
      extension === ".json"
        ? "application/json; charset=utf-8"
        : textExtensions.has(extension)
          ? "text/plain; charset=utf-8"
          : "application/octet-stream";
    const filename = path.basename(file).replace(/"/g, "");

    return new Response(new Uint8Array(data), {
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `inline; filename="${filename}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
