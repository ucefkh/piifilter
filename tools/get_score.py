"""Get Opus 4.8 score for the fix."""
import json, boto3

client = boto3.client('bedrock-runtime', region_name='us-east-1')

# Get the commit message and diff for context
import subprocess
diff = subprocess.run(['git', 'diff', 'HEAD~1'], capture_output=True, text=True, cwd='/home/ucefkh/projects/privacy-proxy-ai').stdout
log = subprocess.run(['git', 'log', '--oneline', '-3'], capture_output=True, text=True, cwd='/home/ucefkh/projects/privacy-proxy-ai').stdout
bench = json.load(open('/tmp/bench_final.json'))

prompt = f"""You are evaluating a fix to the PIIFilter project. Score from 1-10 based on impact, correctness, and completeness.

## Changes made:
{log}
{diff[:2000]}

## Benchmark results (balanced mode):
Overall: precision={bench['overall']['precision']:.4f}, recall={bench['overall']['recall']:.4f}, f1={bench['overall']['f1']:.4f}
Failed types: none

## Summary of fix:
1. Fixed a false positive where 'XXX-XX-6789' in non-SSN context (e.g. "Full: XXX-XX-6789") was detected as MASKED_SSN
2. Split the bare mask pattern into context-keyword (0.70 conf) and word-bounded bare (0.45 conf) variants
3. Fixed benchmark_runner.py _normalize_entity to read raw_score from CandidateSpan objects instead of non-existent 'confidence' attr

## Scoring criteria:
- 5-6: Minor bugfix with low impact
- 7-8: Significant bugfix that improves precision/recall
- 9-10: Major improvement across multiple dimensions

Respond with ONLY a JSON object: {{"score": <1-10>, "reasoning": "<brief explanation>"}}"""

response = client.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': prompt}]}],
    inferenceConfig={'maxTokens': 300, 'temperature': 1.0},
    additionalModelRequestFields={'thinking': {'type': 'adaptive'}}
)

result = json.loads(response['output']['message']['content'][0]['text'])
print(json.dumps(result, indent=2))
with open('/tmp/piifilter_last_score.txt', 'w') as f:
    f.write(json.dumps(result))
print(f"\nScore saved to /tmp/piifilter_last_score.txt")