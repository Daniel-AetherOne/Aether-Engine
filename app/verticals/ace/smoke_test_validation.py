from pathlib import Path
from app.verticals.ace.data_validators.common import validate_dataset

dataset = Path("app/verticals/ace/data/active")

res = validate_dataset(dataset)

print("OK:", res.ok)
print("Errors:", len(res.errors))
for e in res.errors:
    print(e)

print("Warnings:", len(res.warnings))
