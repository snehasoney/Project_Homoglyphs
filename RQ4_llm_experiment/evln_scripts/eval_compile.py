import argparse
import json
import re
from pathlib import Path
from collections import defaultdict

# to adjust file path for comparing prediction and compilation results
def correct_path(p: str) -> str:
    p = (p or "").strip().replace("\\", "/")
    return p[4:] if p.startswith("out/") else p

def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def pred_key(r: dict) -> str:
    p = r.get("path") or r.get("file_path") or r.get("source_file")
    if isinstance(p, str) and p.strip():
        return correct_path(p)
    rid = r.get("id", "")
    if isinstance(rid, str):
        for token in ("cpp/", "c/", "python/", "java/", "go/","ruby/", "php/", "javascript/", "typescript/", "csharp/"):
            i = rid.find(token)
            if i != -1:
                return correct_path(rid[i:])
    return ""

def compiler_results_key(r: dict) -> str:
    p = r.get("file_path") or r.get("source_file") or r.get("source_file_path") or r.get("path")
    return correct_path(p if isinstance(p, str) else "")


def parse_pred_compile(r: dict):
    prmta = r.get("promptA_json")
    if isinstance(prmta, dict):
        v = prmta.get("will_compile")
        if isinstance(v, bool):
            return v
    prmtb = (r.get("promptB_raw") or "").upper().replace(" ", "")
    if "COMPILE=YES" in prmtb:
        return True
    if "COMPILE=NO" in prmtb:
        return False
    return None

# for c and cpp results
def choose_bool(a, b):
    if isinstance(a, bool) and isinstance(b, bool):
        return a and b
    if isinstance(a, bool):
        return a
    if isinstance(b, bool):
        return b
    return None

def parse_compiler_results(language: str, r: dict):
    lang = (language or r.get("language") or "").lower()
    if lang == "c":
        gcc = r.get("gcc", {})
        clang = r.get("clang", {})
        if isinstance(gcc, dict) and isinstance(clang, dict) and ("compile_ok" in gcc or "compile_ok" in clang):
            return (
                choose_bool(gcc.get("compile_ok"), clang.get("compile_ok")),
                choose_bool(gcc.get("run_ok"), clang.get("run_ok")),
            )
    if lang in ("cpp", "c++"):
        gcc_ok = r.get("gcc_compile_ok")
        clang_ok = r.get("clang_compile_ok")
        if isinstance(gcc_ok, bool) or isinstance(clang_ok, bool):
            return (
                choose_bool(gcc_ok, clang_ok),
                choose_bool(r.get("gcc_run_ok"), r.get("clang_run_ok")),
            )
    comp = r.get("compile", {})
    run = r.get("run", {})
    compile_ok = comp.get("ok") if isinstance(comp, dict) else None
    run_ok = run.get("ok") if isinstance(run, dict) else None
    return (
        compile_ok if isinstance(compile_ok, bool) else None,
        run_ok if isinstance(run_ok, bool) else None,
    )


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
        if isinstance(r["compiler_results_compile_ok"], bool) and isinstance(r["pred_compile_ok"], bool)
    ]
    tp = fp = tn = fn = 0
    for r in eval_rows:
        o = r["compiler_results_compile_ok"]
        p = r["pred_compile_ok"]
        if p and o:
            tp += 1
        elif p and not o:
            fp += 1
        elif not p and not o:
            tn += 1
        else:
            fn += 1
    acc = (tp + tn)/len(eval_rows) if eval_rows else 0.0
    prec = tp/(tp + fp) if (tp + fp) else 0.0
    rec = tp/(tp + fn) if (tp + fn) else 0.0
    return {
        "n_joined": len(rows),"n_eval_compile": len(eval_rows),"tp": tp,"fp": fp,"tn": tn,"fn": fn,"accuracy": acc,"precision": prec,"recall": rec,}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="llama or qwen")
    ap.add_argument("--compile-root", default="rq4_compile_results")
    ap.add_argument("--pred-root", default="results")
    ap.add_argument("--out-root", default="rq4_eval_results")
    args = ap.parse_args()
    model = args.model
    compile_root = Path(args.compile_root)
    pred_root = Path(args.pred_root)
    out_root = Path(args.out_root)/model
    out_root.mkdir(parents=True, exist_ok=True)
    compiler_results = {}
    compiler_results_by_lang_count = defaultdict(int)
    for compiler_dir in sorted(compile_root.iterdir()):
        if not compiler_dir.is_dir():
            continue
        lang = compiler_dir.name.lower()
        jsonl = compiler_dir/f"{compiler_dir.name}.jsonl"
        if not jsonl.exists():
            continue
        for r in load_jsonl(jsonl):
            k = compiler_results_key(r)
            if not k:
                continue
            c_ok, r_ok = parse_compiler_results(lang, r)
            compiler_results[k] = {
                "language": lang,
                "compiler_results_compile_ok": c_ok,
                "compiler_results_run_ok": r_ok,
            }
            compiler_results_by_lang_count[lang] += 1

    preds = {}
    preds_by_lang_count = defaultdict(int)
    model_dir = pred_root/model
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
                preds[k] = {
                    "language": lang,
                    "pred_compile_ok": parse_pred_compile(r),
                    "pred_id": r.get("id", ""),
                    "pred_path_raw": r.get("path", ""),
                    "pred_file": str(i),
                }
                preds_by_lang_count[lang] += 1
    rows = []
    missing_compiler_results = []
    for k, p in preds.items():
        o = compiler_results.get(k)
        if not o:
            missing_compiler_results.append({"file_path": k, **p})
            continue
        rows.append({
            "file_path": k,
            "language": o["language"],
            "compiler_results_compile_ok": o["compiler_results_compile_ok"],
            "compiler_results_run_ok": o["compiler_results_run_ok"],
            "pred_compile_ok": p["pred_compile_ok"],
            "pred_id": p["pred_id"],
            "pred_path_raw": p["pred_path_raw"],
            "pred_file": p["pred_file"],
        })
    missing_pred = [
        {"file_path": k, **o}
        for k, o in compiler_results.items()
        if k not in preds
    ]
    cols = ["file_path","language","oracle_compile_ok","oracle_run_ok","pred_compile_ok","pred_id","pred_path_raw","pred_file",]

    write_csv(out_root/"joined_all.csv", rows, cols)
    write_csv(out_root/"missing_compiler_results.csv",missing_compiler_results,["file_path", "language", "pred_compile_ok", "pred_id", "pred_path_raw", "pred_file"],)
    write_csv(out_root/"missing_pred.csv",missing_pred,["file_path", "language", "oracle_compile_ok", "oracle_run_ok"],)
    by_lang = defaultdict(list)
    for r in rows:
        by_lang[r["language"]].append(r)
    metrics = {
        "model": model,
        "compiler_results_total": len(compiler_results),
        "pred_total": len(preds),
        "joined_total": len(rows),
        "missing_compiler_results_total": len(missing_compiler_results),
        "missing_pred_total": len(missing_pred),
        "compiler_results_by_lang_count": dict(compiler_results_by_lang_count),
        "pred_by_lang_count": dict(preds_by_lang_count),
        "overall": compute_metrics(rows),
        "by_language": {},
    }
    for lang, rws in sorted(by_lang.items()):
        write_csv(out_root/f"joined_{lang}.csv", rws, cols)
        metrics["by_language"][lang] = compute_metrics(rws)
    with (out_root/"metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

if __name__ == "__main__":
    main()
