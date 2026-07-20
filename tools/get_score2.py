"""Get Opus 4.8 score for the fix."""
import json, boto3, subprocess

client = boto3.client('bedrock-runtime', region_name='us-east-1')

diff = subprocess.run(['git', 'diff', 'HEAD~1'], capture_output=True, text=True, cwd='/home/ucefkh/projects/privacy-proxy-ai').stdout
log = subprocess.run(['git', 'log', '--oneline', '-3'], capture_output=True, text=True, cwd='/home/ucefkh/projects/privacy-proxy-ai').stdout
bench = json.load(open('/tmp/bench_final.json'))

prompt = f"""You are evaluating a fix to the PIIFilter project. Score from 1-10 based on impact, correctness, and completeness.

## Changes:
{log}
{diff[:2000]}

## Benchmark results (balanced):
Overall: precision={bench['overall']['precision']:.4f}, recall={bench['overall']['recall']:.4f}, f1={bench['overall']['f1']:.4f}
Issues: MASKED_SSN FP fixed

## Summary:
1. Fixed MASKED_SSN FP — bare mask pattern matched 'XXX-XX-6789' in non-SSN context
2. Split into context-keyword variant (0.70) + word-bounded bare variant (0.45)
3. Fixed benchmark score normalization (raw_score vs confidence)

Score:"""

response = client.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': prompt}]}],
    inferenceConfig={'maxTokens': 300, 'temperature': 1.0},
    additionalModelRequestFields={'thinking': {'type': 'adaptive'}}
)

# Debug: print what we got
content = response['output']['message']['content']
print(f"Content structure: {type(content)}")
for i, item in enumerate(content):
    print(f"  Item {i}: {list(item.keys())}")
    if 'text' in item:
        print(f"  Text: {item['text']}")
    if 'thinking' in item:
        print(f"  Thinking: {item['thinking'][:200]}")

# Try to extract score
text = content[0].get('text', '')
if not text:
    # Maybe it's in a different format
    text = str(content)
    
result = {"score": "unknown", "raw_output": text[:500]}
with open('/tmp/piifilter_last_score.txt', 'w') as f:
    f.write(json.dumps(result))
print(f"\nScore saved to /tmp/piifilter_last_score.txt")
print(f"Raw response: {text[:500]}")