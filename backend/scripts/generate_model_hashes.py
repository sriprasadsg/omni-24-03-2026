"""Generate SHA-256 sidecar files for all .joblib models in backend/models/.

Run after training or updating any model:
    python backend/scripts/generate_model_hashes.py

ml_service._safe_load_model() requires a matching .sha256 sidecar or it
refuses to load the model. The sidecar format matches sha256sum output:
    <hexdigest>  <filename>
"""
import hashlib
import pathlib
import sys

models_dir = pathlib.Path(__file__).parent.parent / "models"
joblibs = list(models_dir.glob("*.joblib"))

if not joblibs:
    print(f"No .joblib files found in {models_dir} — nothing to hash.")
    sys.exit(0)

for p in sorted(joblibs):
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    sidecar = p.with_suffix(".joblib.sha256")
    sidecar.write_text(f"{digest}  {p.name}\n", encoding="utf-8")
    print(f"Written: {sidecar.name}  ({digest[:16]}…)")

print(f"\n{len(joblibs)} sidecar(s) generated.")
