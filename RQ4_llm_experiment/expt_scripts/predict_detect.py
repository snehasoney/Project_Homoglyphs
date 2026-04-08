import argparse
import json
import time
import requests
from tqdm import tqdm

# local deployment
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
#structured prompt
prompt_A = """You are a static analysis tool. Output valid JSON only. No markdown.
Given the following {language} program, do BOTH:
1) Determine whether it contains any homoglyph/confusable Unicode characters that could be mistaken for ASCII in identifiers, keywords, operators, or delimiters.
2) Predict whether it will compile/run successfully. If not, classify the most likely error class.
Use ONLY this output schema:
{{
  "has_homoglyph": boolean,
  "homoglyph_items": [
    {{
      "text": string,
      "category": "identifier|keyword|operator|delimiter|unknown",
      "explanation": string
    }}
  ],
  "will_compile": boolean,
  "error_class": "NONE|LEXICAL|SYNTAX|TYPE|NAME|LINK|RUNTIME|OTHER",
  "reason": string
}}
Program:k
{code}
"""
# constrained prompt
prompt_B = """Task: Analyze the following {language} program.
Answer in exactly 2 lines. You must answer using EXACTLY the following format.
Do not add explanations.
Line 1: HOMOGLYPH=YES or HOMOGLYPH=NO
Line 2: COMPILE=YES or COMPILE=NO ; ERROR=NONE|LEXICAL|SYNTAX|TYPE|NAME|LINK|RUNTIME|OTHER
Program:
{code}
"""

def call_ollama(model, prompt, max_tokens):
    message = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "max_tokens": max_tokens},
    }
    response = requests.post(OLLAMA_URL, json=message, timeout=300)
    response.raise_for_status()
    data = response.json()
    return (data.get("message") or {}).get("content", "")

def parse_prompta(text):
    try:
        return json.loads(text.strip())
    except Exception:
        return None

def parse_promptb(text):
    out = {"homoglyph": "INVALID", "compile": "INVALID", "error": "INVALID"}
    lines = [x.strip().upper().replace(" ", "") for x in text.strip().splitlines() if x.strip()]
    if len(lines) >= 1 and lines[0].startswith("HOMOGLYPH="):
        v = lines[0].split("=", 1)[1]
        if v in {"YES", "NO"}:
            out["homoglyph"] = v
    if len(lines) >= 2:
        for part in lines[1].split(";"):
            if part.startswith("COMPILE="):
                v = part.split("=", 1)[1]
                if v in {"YES", "NO"}:
                    out["compile"] = v
            elif part.startswith("ERROR="):
                v = part.split("=", 1)[1]
                if v in {"NONE","LEXICAL","SYNTAX","TYPE","NAME","LINK","RUNTIME","OTHER"}:
                    out["error"] = v
    return out

def run_prompt(model, prompt, max_tokens, parser):
    t0 = time.time()
    raw = call_ollama(model, prompt, max_tokens)
    t1 = time.time()
    return raw, parser(raw), t1-t0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default="llama3.2:3b")
    args = ap.parse_args()
    with open(args.input, "r", encoding="utf-8") as f_in, open(args.output, "w", encoding="utf-8") as f_out:
        for line in tqdm(f_in, desc="LLM inference"):
            program = json.loads(line)
            language = program.get("language", "unknown")
            code = program.get("code", "")
            raw_a, parsed_a, dt_a = run_prompt(args.model, prompt_A.format(language=language, code=code), 300, parse_prompta)
            raw_b, parsed_b, dt_b = run_prompt(args.model, prompt_B.format(language=language, code=code), 100, parse_promptb)
            out = {
                "id": program.get("id"),
                "language": language,
                "variant_type": program.get("variant_type"),
                "target": program.get("target"),
                "program_folder": program.get("program_folder"),
                "path": program.get("path"),
                "code_sha256": program.get("code_sha256"),
                "model": args.model,
                "promptA_raw": raw_a,
                "promptA_json": parsed_a,
                "promptA_seconds": dt_a,
                "promptB_raw": raw_b,
                "promptB_parsed": parsed_b,
                "promptB_seconds": dt_b,
            }
            f_out.write(json.dumps(out, ensure_ascii=False) + "\n")
    print("Prediction complete")

if __name__ == "__main__":
    main()
    
    
# Notes
# Models used : Qwen2.5 Coder 3B and Llama 3.2 3B
