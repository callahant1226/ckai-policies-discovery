"""Default filesystem locations for the exemplar policy library.

See specs/policy_storage.md for the design this implements.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "policies"
RAW_DIR = DATA_DIR / "raw"
MANIFEST_PATH = DATA_DIR / "manifest.json"
DB_PATH = DATA_DIR / "index.db"
