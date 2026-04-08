import os
import json
import hashlib
import argparse
import re
from pathlib import Path

EXTENSIONS = { "c": {".c"},"cpp": {".cpp"},"csharp": {".cs"},"go": {".go"},"java": {".java"},"javascript": {".js"},"php": {".php"},"python": {".py"},"ruby": {".rb"},"typescript": {".ts", ".ts"},}

FOLDERS = [("function_variants", "keyword_variants"),("function_variants", "opdelim_variants"),("variable_variants", "keyword_variants"),("variable_variants", "opdelim_variants"),] # class names not considered in this expt

def natural_key(s: str): 
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def build_dataset(output: Path, lang: str, identifier_type: str, token_type: str):
    base = output/lang/identifier_type/token_type
    dataset = []
    extn = EXTENSIONS.get(lang)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort(key=natural_key)
        filenames.sort(key=natural_key)
        for fn in filenames:
            p = Path(dirpath)/fn
            if not p.is_file() or p.suffix.lower() not in extn:
                continue
            code = p.read_text(encoding="utf-8", errors="replace")
            rel_path = p.relative_to(output)
            parts = p.relative_to(base).parts
            program_folder = parts[0]
            dataset.append({
                "id": str(rel_path).replace(os.sep, ":"),
                "language": lang,
                "variant_type": identifier_type,
                "target": token_type,
                "program_folder": program_folder,
                "path": str(p),
                "code_sha256": hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest(),
                "code": code,
            })
    return dataset

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True, help="Select : c, cpp, chsarp, go, java, javascript, php, python, ruby, typescript")
    ap.add_argument("--out", default="out") # variant programs from rq1 in out folder
    ap.add_argument("--dest", default="datasets")
    args = ap.parse_args()
    output = Path(args.out)
    dest = Path(args.dest)/args.lang
    total = 0
    for identifier_type, token_type in FOLDERS:
        dataset = build_dataset(output, args.lang, identifier_type, token_type)
        path = dest/identifier_type/f"{token_type}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
    	    for r in dataset:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"Wrote {len(dataset):5d} -> {path}")
        total += len(dataset)
    print(f"\nTOTAL programs for {args.lang}: {total}")

if __name__ == "__main__":
    main()
    
# Notes
# Terminal Input : <program name> --lang <lang_name>
# Step1 - Dataset Building for compilation prediction
# Input : ´out´ containing compilation results from rq1
# Results : JSONl files under folder ´dataset´
# only keyword variants and variable variants are considered 
