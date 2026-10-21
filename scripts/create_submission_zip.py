import os
import zipfile

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
desktop_dir = os.path.abspath(os.path.join(base_dir, ".."))

zip_local = os.path.join(base_dir, "marianos_scraper_azure_submission.zip")
zip_desktop = os.path.join(desktop_dir, "marianos_scraper_azure_submission.zip")
zip_esdo = os.path.join(desktop_dir, "esdo table", "marianos_scraper_azure_submission.zip")

exclude_dirs = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", ".idea", ".vscode"}
exclude_extensions = {".pyc", ".pyo", ".pyd", ".zip"}

target_zips = [zip_local, zip_desktop]
if os.path.exists(os.path.join(desktop_dir, "esdo table")):
    target_zips.append(zip_esdo)

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

    print(f"Created clean submission package: {target_zip} ({os.path.getsize(target_zip) / 1024:.2f} KB)")
