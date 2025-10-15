import yaml
from pathlib import Path

def load_yaml(path):
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"[YAML] Failed to load {path}: {e}")
            return {}

def save_yaml(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,   # ✅ writes real Unicode characters (like —)
            width=120,            # ✅ prevents awkward line wrapping
        )

