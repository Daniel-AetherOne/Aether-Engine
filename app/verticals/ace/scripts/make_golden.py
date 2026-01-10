import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.contract_reference import generate_quote_v1

fixtures = ROOT / "tests" / "fixtures"

inp = json.loads((fixtures / "input.v1.sample.json").read_text(encoding="utf-8"))
out = generate_quote_v1(inp)

(fixtures / "output.v1.golden.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    encoding="utf-8",
)

print("Wrote tests/fixtures/output.v1.golden.json")
