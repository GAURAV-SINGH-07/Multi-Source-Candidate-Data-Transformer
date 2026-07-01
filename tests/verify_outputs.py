"""Verify all 5 output files exist and have correct structure."""
import json, sys
sys.path.insert(0, "d:/EightFold")

# candidate.json
with open("outputs/candidate.json") as f:
    c = json.load(f)
assert "candidate_id" in c
keys_preview = list(c)[:6]
print(f"candidate.json: id={c['candidate_id']}, keys={keys_preview}...")

# explanation.json
with open("outputs/explanation.json") as f:
    exp = json.load(f)
print(f"explanation.json: {len(exp)} fields explained")
assert "full_name" in exp

# metrics.json
with open("outputs/metrics.json") as f:
    m = json.load(f)
print(f"metrics.json: confidence={m['overall_confidence']}, elapsed={m['execution_time_seconds']}s")
assert 0 < m["overall_confidence"] <= 1.0

# decision_log.json
with open("outputs/decision_log.json") as f:
    dl = json.load(f)
print(f"decision_log.json: {len(dl)} decisions recorded")
assert isinstance(dl, list)

# report.html
with open("outputs/report.html", encoding="utf-8") as f:
    html_content = f.read()
assert "<html" in html_content
assert "Priya Sharma" in html_content
assert "Pipeline Metrics" in html_content
print(f"report.html: {len(html_content):,} bytes, structure verified")

print()
print("ALL OUTPUT FILES VERIFIED")
