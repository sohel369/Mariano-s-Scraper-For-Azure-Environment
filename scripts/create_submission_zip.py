import os
import zipfile
import hashlib

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
desktop_dir = os.path.abspath(os.path.join(base_dir, ".."))

target_zips = [
    os.path.join(base_dir, "marianos_scraper_azure_submission.zip"),
    os.path.join(desktop_dir, "marianos_scraper_azure_submission.zip"),
    os.path.join(base_dir, "mariano new updated.zip"),
    os.path.join(desktop_dir, "mariano new updated.zip"),
    os.path.join(desktop_dir, "Mariano's Scraper For Azure Environment.zip"),
]
if os.path.exists(os.path.join(desktop_dir, "esdo table")):
    target_zips.append(os.path.join(desktop_dir, "esdo table", "marianos_scraper_azure_submission.zip"))

exclude_dirs = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", ".idea", ".vscode"}
exclude_extensions = {".pyc", ".pyo", ".pyd", ".zip"}

for target_zip in target_zips:
    if os.path.exists(target_zip):
        try:
            os.remove(target_zip)
        except Exception:
            pass

    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in exclude_extensions:
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_dir)
                zipf.write(full_path, rel_path)

    hasher = hashlib.sha256()
    with open(target_zip, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256_val = hasher.hexdigest()

    print(f"Created package: {target_zip}")
    print(f"  Size: {os.path.getsize(target_zip) / 1024:.2f} KB | SHA-256: {sha256_val}")
