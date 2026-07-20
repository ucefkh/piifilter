"""Find all SOCIAL_SECURITY golden entries via benchmark subprocess."""
import subprocess, json

result = subprocess.run(
    ['python3', '-c', '''
import json
corpus = json.load(open("benchmarks/data/golden_corpus.json"))
examples = corpus["examples"]
for i, ex in enumerate(examples):
    for e in ex.get("entities", []):
        if e["type"] == "SOCIAL_SECURITY":
            start, end = e["start"], e["end"]
            txt = ex["text"][start:end]
            ctx = ex["text"][max(0,start-15):end+10]
            print(f"Ex {i}: span={start}-{end} val={repr(txt)} ctx={repr(ctx)}")
'''],
    capture_output=True, text=True, cwd='/home/ucefkh/projects/privacy-proxy-ai'
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:500])