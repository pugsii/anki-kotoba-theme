"""Build dist/kotoba_theme.ankiaddon: the add-on folder as Anki installs it (Tools → Add-ons → Install from file).

    python3 tools/package.py

Leaves out your settings (meta.json) and compiled files.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "kotoba_theme"
OUT = ROOT / "dist" / "kotoba_theme.ankiaddon"


def main():
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(ADDON.rglob("*")):
            rel = path.relative_to(ADDON)
            if path.is_file() and "__pycache__" not in rel.parts and path.suffix != ".pyc" and rel.name != "meta.json":
                z.write(path, rel.as_posix())  # Anki wants the add-on's files at the top
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
