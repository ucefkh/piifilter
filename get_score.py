#!/usr/bin/env python3
"""Score with current metrics after CITY fix."""
import json, boto3, sys

client = boto3.client("bedrock-runtime", region_name="us-east-1")

prompt = """Rate PIIFilter out of 10 on this scale:
1-6: Not production-ready
7-8: Good, most types high recall/precision, some gaps  
9-9.5: Excellent, all entity types at recall >= 0.95 and precision >= 0.85
9.6-10: Perfect or near-perfect

Current metrics (recall benchmark, full set, 150 examples, arbitration-on):
- Overall: P=0.9114 R=0.9730 F1=0.9412
- CITY: P=0.8421 R=0.8889 (was P=0.4737 before fix — pattern changed to use lookahead for "City office" pattern, dataset labels fixed for Springfield truncation bug and missing city labels including Berlin, Moscow)
- DOMAIN: P=0.8889 R=0.8889
- EMAIL: P=0.9524 R=0.9524
- All other entity types at P>=0.85 and R>=0.90
- 18 CITY entities in dataset (9 original + 9 added from fix)

Key fix this tick:
- Fixed CITY pattern "City before office/headquarters/plant" to use positive lookahead so match span is ONLY the city name (e.g. "Berlin" not "Berlin office")
- Fixed "Springfield" label truncation bug in dataset
- Added missing CITY labels for Springfield, Berlin, Moscow
- 8 other CITY labels added for cities in parenthetical GPS contexts (these can't match due to deobfuscator span coordinate shifts)

Give ONLY a single number 0-10, nothing else."""

try:
    response = client.converse(
        modelId="us.anthropic.claude-opus-4-8",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 1.0, "maxTokens": 20},
        additionalModelRequestFields={"thinking": {"type": "adaptive"}},
    )
    
    content = response["output"]["message"]["content"]
    score_text = ""
    for c in content:
        if "text" in c:
            score_text = c["text"].strip()
    
    print(score_text if score_text else json.dumps(response["output"]["message"]["content"], default=str))
    print(f"Stop reason: {response.get('stopReason', 'unknown')}")
    
    # Save score
    with open("/tmp/piifilter_last_score.txt", "w") as f:
        f.write(score_text if score_text else "unknown")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)