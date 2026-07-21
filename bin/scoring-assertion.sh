#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Scoring-assertion CI script
#
#   1. Runs unit tests (skipping integration and fuzz)
#   2. Runs the in-distribution recall benchmark
#   3. Extracts per-type P/R/F1 from the latest results
#   4. Exits non-zero if any critical type has R < 0.80 or P < 0.50
#
# Usage:
#   bash bin/scoring-assertion.sh              # uses uv run
#   UV_RUN="uv run" bash bin/scoring-assertion.sh
#   UV_RUN="poetry run" bash bin/scoring-assertion.sh
#   UV_RUN="" PYTHON=python3 bash bin/scoring-assertion.sh  # raw venv python
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || realpath "$(dirname "$0")/..")"
PROJECT_ROOT=$(pwd)

# Resolve the Python runner ---------------------------------------------------
UV_RUN="${UV_RUN:-uv run}"
PYTHON="${PYTHON:-}"

if [ -n "$PYTHON" ]; then
    RUNNER="$PYTHON"
elif command -v uv &>/dev/null && [ -f pyproject.toml ]; then
    RUNNER="$UV_RUN python"
else
    RUNNER="python3"
fi

echo "═══════════════════════════════════════════════════════════════════════"
echo "  PIIFilter Scoring Assertion — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "  Project root: $PROJECT_ROOT"
echo "  Runner:       $RUNNER"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""

# Step 1: Run unit tests (skip integration + fuzz) ---------------------------
echo "▶ Step 1: pytest (unit, ignoring integration + fuzz)"
echo "────────────────────────────────────────────────────────"
set +e
$RUNNER -m pytest -q \
    --ignore=tests/integration \
    --ignore=tests/fuzz \
    --tb=short 2>&1
PYTEST_EXIT=$?
set -e
echo ""

if [ $PYTEST_EXIT -ne 0 ]; then
    echo "✗ pytest FAILED (exit=$PYTEST_EXIT) — aborting"
    exit $PYTEST_EXIT
fi
echo "✓ pytest passed"
echo ""

# Step 2: Run the in-distribution recall benchmark ----------------------------
echo "▶ Step 2: In-distribution recall benchmark"
echo "────────────────────────────────────────────────────────"
set +e
# Run with held-out=0.2 for a reliable test-set evaluation
$RUNNER benchmarks/recall.py \
    --detectors regex \
    --output /dev/null \
    --held-out 0.2 \
    --without-arbitration 2>&1 | tee /tmp/scoring-assertion-bench.log
BENCH_EXIT=$?
set -e
echo ""

if [ $BENCH_EXIT -ne 0 ]; then
    echo "✗ benchmark FAILED (exit=$BENCH_EXIT) — aborting"
    exit $BENCH_EXIT
fi

# Step 3: Read the latest results file ----------------------------------------
LATEST_RESULTS=$(ls -t benchmarks/recall-results-heldout-raw.json 2>/dev/null || echo "")
if [ -z "$LATEST_RESULTS" ] || [ ! -f "$LATEST_RESULTS" ]; then
    LATEST_RESULTS=$(ls -t benchmarks/recall-results-*.json 2>/dev/null | head -1 || echo "")
fi

if [ -z "$LATEST_RESULTS" ] || [ ! -f "$LATEST_RESULTS" ]; then
    echo "✗ No results file found — cannot validate P/R thresholds"
    exit 1
fi

echo "▶ Step 3: Checking P/R thresholds against $LATEST_RESULTS"
echo "────────────────────────────────────────────────────────"

# Read the scoring-assertion file if it exists
if [ -f "benchmarks/scoring-assertion.json" ]; then
    echo "  Scoring assertion:"
    python3 -c "
import json
d = json.load(open('benchmarks/scoring-assertion.json'))
print(f'    commit:        {d[\"git_commit_hash\"]}')
print(f'    total patterns: {d[\"total_patterns\"]}')
for et, cnt in sorted(d.get('pattern_counts', {}).items()):
    print(f'    {et}: {cnt} patterns')
"
fi
echo ""

# Step 4: Extract P/R/F1 and enforce quality gates ---------------------------
VIOLATIONS=0
CRITICAL_TYPES=""
python3 -c "
import json, sys

with open('$LATEST_RESULTS') as f:
    report = json.load(f)

violations = []

# Check all detectors
for dname, dresults in report.get('detectors', {}).items():
    print(f'  Detector: {dname}')
    print(f'  {\"─\"*60}')
    per_type = dresults.get('per_type', {})
    for et in sorted(per_type.keys()):
        m = per_type[et]
        rec = m.get('recall', 0)
        prec = m.get('precision', 0)
        f1 = m.get('f1', 0)
        n = m.get('n_total', m.get('n', 0))
        status = '✓'
        issues = []
        if rec < 0.80:
            issues.append(f'R={rec:.3f} < 0.80')
        if prec < 0.50:
            issues.append(f'P={prec:.3f} < 0.50')
        if issues:
            status = '✗'
            violations.append(f'{dname}.{et}: {\" | \".join(issues)}')
        print(f'    {status} {et:25s}  N={n:>4d}  P={prec:.4f}  R={rec:.4f}  F1={f1:.4f}')
    print()

if violations:
    print(f'  CRITICAL: {len(violations)} violation(s) found')
    for v in violations:
        print(f'    ✗ {v}')
    sys.exit(1)
else:
    print(f'  ✓ All types meet thresholds (R≥0.80, P≥0.50)')
    sys.exit(0)
" || VIOLATIONS=$?

echo ""
echo "═══════════════════════════════════════════════════════════════════════"

# Also ensure scoring-assertion.json was created
HAS_ASSERTION=0
[ -f "benchmarks/scoring-assertion.json" ] && HAS_ASSERTION=1

echo "  scoring-assertion.json created: $([ $HAS_ASSERTION -eq 1 ] && echo 'yes' || echo 'no')"

if [ $HAS_ASSERTION -eq 0 ]; then
    echo "  ⚠ scoring-assertion.json was NOT created — the benchmark may not"
    echo "    have run far enough to generate it."
fi

if [ $VIOLATIONS -ne 0 ]; then
    echo "  ✗ Assertion FAILED — $VIOLATIONS type(s) below thresholds"
    exit 1
else
    echo "  ✓ Assertion PASSED"
    exit 0
fi