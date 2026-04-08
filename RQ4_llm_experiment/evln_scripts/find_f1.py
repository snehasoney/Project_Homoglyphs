import json

with open("metrics.json") as f:
    data = json.load(f)
def f1(p, r):
    if p+r == 0:
        return 0.0
    return 2*p*r/(p+r)
p = data["overall"]["precision"]
r = data["overall"]["recall"]
data["overall"]["f1"] = f1(p, r)
for lang, result in data["by_language"].items():
    p = result["precision"]
    r = result["recall"]
    result["f1"] = f1(p, r)
with open("metrics_with_f1.json", "w") as f:
    json.dump(data, f, indent=2)
