import argparse
import json
import re
from pathlib import Path
from collections import defaultdict

def correct_path(p: str) -> str:
    p = (p or "").strip().replace("\\", "/")
    return p[4:] if p.startswith("out/") else p

def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def pred_key(r: dict) -> str:
    p = r.get("path") or r.get("file_path") or r.get("source_file")
    if isinstance(p, str) and p.strip():
        return correct_path(p)

    rid = r.get("id", "")
    if isinstance(rid, str):
        for token in ("cpp/", "c/", "python/", "java/", "go/", "ruby/", "php/", "javascript/", "typescript/", "csharp/"):
            i = rid.find(token)
            if i != -1:
                return correct_path(rid[i:])
    return ""

def has_homoglyph(raw: str):
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            v = obj.get("has_homoglyph")
            if isinstance(v, bool):
                return v
    except json.JSONDecodeError:
        pass
    m = re.search(r'"has_homoglyph"\s*:\s*(true|false)', raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower() == "true"
    return None

def write_csv(path: Path, rows: list, cols: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(
                str(r.get(c, "")).replace("\n", " ").replace(",", ";")
                for c in cols
            ) + "\n")
            
def compute_metrics(rows):
    eval_rows = [
        r for r in rows
        if isinstance(r["pred_has_homoglyph"], bool)
    ]
    tp = 0
    fn = 0
    for r in eval_rows:
        if r["pred_has_homoglyph"] is True:
            tp += 1
        else:
            fn += 1
    n = len(eval_rows)
    recall = tp / n if n else 0
    miss_rate = fn / n if n else 0
    invalid_or_missing =len(rows) - n
    return {"n_joined": len(rows),"n_eval_detection": len(eval_rows),"tp": tp,"fn": fn,"recall": recall,"miss_rate": miss_rate,"invalid_or_missing": invalid_or_missing,}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="llama or qwen")
    ap.add_argument("--pred-root", default="results")
    ap.add_argument("--out-root", default="rq4_presence_eval_results")
    args = ap.parse_args()
    model = args.model
    pred_root = Path(args.pred_root)
    out_root = Path(args.out_root) / model
    out_root.mkdir(parents=True, exist_ok=True)
    preds = {}
    preds_by_lang_count = defaultdict(int)
    model_dir = pred_root / model
    for compiler_dir in sorted(model_dir.iterdir()):
        if not compiler_dir.is_dir():
            continue
        l = compiler_dir.name.lower()
        for i in sorted(compiler_dir.glob("*.jsonl")):
            for r in load_jsonl(i):
                k = pred_key(r)
                if not k:
                    continue
                lang = (r.get("language") or l).lower()
                raw = r.get("promptA_raw")
                preds[k] = {
                    "file_path": k,
                    "language": lang,
                    "variant_type": r.get("variant_type", ""),
                    "target": r.get("target", ""),
                    "program_folder": r.get("program_folder", ""),
                    "promptA_raw_present": isinstance(raw, str) and bool(raw.strip()),
                    "pred_has_homoglyph": has_homoglyph(raw),
                    "pred_id": r.get("id", ""),
                    "pred_path_raw": r.get("path", ""),
                    "pred_file": str(i),
                }
                preds_by_lang_count[lang] += 1
    rows = list(preds.values())
    cols = ["file_path","language","variant_type","target","program_folder","promptA_raw_present","pred_has_homoglyph","pred_id","pred_path_raw","pred_file",]
    write_csv(out_root / "joined_all.csv", rows, cols)
    by_lang = defaultdict(list)
    for r in rows:
        by_lang[r["language"]].append(r)
    for lang, rws in sorted(by_lang.items()):
        write_csv(out_root / f"joined_{lang}.csv", rws, cols)
    missed_rows = [r for r in rows if r["pred_has_homoglyph"] is not True]
    write_csv(out_root / "missed_homoglyphs.csv", missed_rows, cols)
    metrics = {
        "model": model,
        "pred_total": len(preds),
        "pred_by_lang_count": dict(preds_by_lang_count),
        "overall_detection": compute_metrics(rows),
        "by_language": {},
    }
    for lang, rws in sorted(by_lang.items()):
        metrics["by_language"][lang] = compute_metrics(rws)
    with (out_root / "metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

if __name__ == "__main__":
    main()
