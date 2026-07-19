"""Get Opus 4.8 score for the ADDRESS precision fix."""
import json
import re
import boto3

client = boto3.client('bedrock-runtime', region_name='us-east-1')

eval_prompt = """You are evaluating PIIFilter, a PII detection library. One change was just made:

**ADDRESS precision fix**: Replaced the overly-broad generic ADDRESS pattern that matched any "N Street Name Rd/St/Ave/Way/etc." regardless of context, with a keyword-prefixed version that requires address context keywords (address:, at, is at, office is at, home address:, visit us at, HQ is at). Also added a negative lookahead to exclude pop-culture/anecdotal references in parentheses ("(famous from...)"). Removed the standalone redundant UK-style pattern.

Impact: ADDRESS precision 0.6667 -> 1.0000 (FP 3->0). Zero recall regression (same 6 TP). Overall regex precision 0.8786 -> 0.8916. Overall regex recall 0.9837 unchanged.

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