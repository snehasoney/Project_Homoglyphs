import argparse
import random
from pathlib import Path

def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--input", required=True)
	ap.add_argument("--output", required=True)
	ap.add_argument("--n", type=int, required=True)
	ap.add_argument("--seed", type=int, default=42)
	args = ap.parse_args()
	random.seed(args.seed)
	with Path(args.input).open("r", encoding="utf-8") as f:
		lines = f.readlines()
	sampled = random.sample(lines, args.n)
	out = Path(args.output)
	out.parent.mkdir(parents=True, exist_ok=True)
	with out.open("w", encoding="utf-8") as f:
		f.writelines(sampled)
	print("Sampling complete")
	
if __name__ == "__main__":
	main()


# Notes:
# Sampling only did for keyword variants
# n = 250


    
    
    
 
