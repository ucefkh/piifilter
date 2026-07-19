"""Get Opus score for the improvement."""
import json, boto3, re

client = boto3.client('bedrock-runtime', region_name='us-east-1')

eval_prompt = """You are evaluating PIIFilter, a PII detection library. Two changes were just made:

1. **CREDIT_CARD IBAN FP fix**: Added lookbehind to prevent low-confidence CC pattern (#11, \\b\\d{4}[- ]\\d{4}[- ]\\d{4}[- ]\\d{2,4}\\b) from matching trailing IBAN groups. Impact: CREDIT_CARD precision 0.7059 -> 0.8000, FP 5->3.

2. **COMPANY two-cap-word FP fix**: Replaced overly-broad two-capitalized-words pattern (matched ANY two capitalized words like "Alice Johnson", "Fifth Avenue", "Main Street") with a restricted version requiring the second word to be a known company/industry term (Technologies, Research, Systems, etc.). Impact: COMPANY precision 0.6667 -> 1.0000 (perfect), FP 4->0. Overall regex precision 0.8125 -> 0.8786.

Tests: 450/450 passed.

Rate this improvement out of 10. Consider: impact on precision, specificity of fix, zero regression on recall, test cleanliness. Provide a brief justification and then the score as "SCORE: X/10"."""

response = client.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': eval_prompt}]}],
    additionalModelRequestFields={'thinking': {'type': 'adaptive'}},
    inferenceConfig={
        'temperature': 1.0,
        'maxTokens': 2048
    }
)

# Extract all text blocks from content
full_text = ''
for block in response['output']['message']['content']:
    if 'text' in block:
        full_text += block['text']
    elif 'reasoningContent' in block:
        rc = block['reasoningContent']
        if 'reasoningText' in rc and 'text' in rc['reasoningText']:
            pass  # Skip reasoning

print(full_text)

score_match = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)\s*/?\s*10', full_text)
if score_match:
    score = float(score_match.group(1))
    with open('/tmp/piifilter_last_score.txt', 'w') as f:
        f.write(str(score))
    print(f'\nScore saved: {score}')
else:
    print('\nCould not extract SCORE:')
    score_match2 = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', full_text)
    if score_match2:
        score = float(score_match2.group(1))
        with open('/tmp/piifilter_last_score.txt', 'w') as f:
            f.write(str(score))
        print(f'Score saved (alt): {score}')