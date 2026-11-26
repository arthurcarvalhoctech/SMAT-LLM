"""Download only real mergedataset Java sources (never JARs or synthetic cases)."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/spgroup/mergedataset"


def get(url):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "SMAT-Laya-dataset-preparation"})
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / ".laya_smat/mergedataset_sources")
    parser.add_argument("--revision", default="04a180179b6098bac96a9cd83fe4f5ff5d45ea86")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text())
        if index["revision"] != args.revision:
            raise ValueError("Cached dataset revision differs; use a separate --out directory")
    else:
        revision = args.revision
        tree = json.loads(get(API + f"/git/trees/{revision}?recursive=1"))
        if tree.get("truncated"):
            raise RuntimeError("GitHub truncated the dataset tree; refusing incomplete discovery")
        index = {"revision": revision, "tree": tree["tree"]}
        index_path.write_text(json.dumps(index), encoding="utf-8")
    with (ROOT / "mergedataset-full/semantic-conflicts/sample-semantic-conflicts.csv").open(encoding="utf-8-sig") as handle:
        cases = [{k.strip(): v.strip() for k, v in row.items()} for row in csv.DictReader(handle)]
    commits = {row["Commit"] for row in cases}
    files = [entry for entry in index["tree"] if entry["type"] == "blob"
             and len(entry["path"].split("/")) > 3
             and entry["path"].split("/")[2] == "source" and entry["path"].endswith(".java")
             and entry["path"].split("/")[1] in commits]

    def fetch(entry):
        target = args.out / entry["path"]
        if target.exists():
            data = target.read_bytes()
        else:
            quoted = urllib.parse.quote(entry['path'], safe="/")
            data = get(f"https://raw.githubusercontent.com/spgroup/mergedataset/{index['revision']}/{quoted}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if digest != entry["sha"]:
            raise RuntimeError(f"Source hash mismatch: {entry['path']}")
        return entry["path"]

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch, entry): entry["path"] for entry in files}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                future.result()
            except Exception as error:
                failures.append({"path": futures[future], "error": str(error)})
            if i % 50 == 0:
                print(f"Sources checked: {i}/{len(files)}", flush=True)
    report = {"revision": index["revision"], "files": len(files), "failures": failures}
    (args.out / "download_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
