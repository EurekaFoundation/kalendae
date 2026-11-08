"""Crea l'applicazione eseguibile con PyInstaller.

Uso (da qualsiasi sistema, nella cartella del progetto):
    pip install -r requirements.txt pyinstaller pillow
    python scripts/build.py

Risultato in dist/:
    Windows  dist/Kalendae/Kalendae.exe
    macOS    dist/Kalendae.app
    Linux    dist/Kalendae/Kalendae
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
PNG = ROOT / "assets" / "kalendae.png"


def make_icon() -> Path:
    """Windows vuole un .ico: lo genera dal PNG con Pillow."""
    if sys.platform != "win32":
        return PNG
    from PIL import Image
    BUILD.mkdir(exist_ok=True)
    ico = BUILD / "kalendae.ico"
    Image.open(PNG).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico


def main() -> None:
    import PyInstaller.__main__

    sys.path.insert(0, str(ROOT))
    from kalendae import __version__

    args = [
        str(ROOT / "packaging" / "entry.py"),
        "--name", "Kalendae",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(make_icon()),
        "--paths", str(ROOT),
        "--collect-data", "eureka_core",   # traduzioni e dati di Eureka Suite
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        # moduli Qt pesanti che Kalendae non usa
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "tkinter",
    ]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "org.kalendae.app"]
    print(f"Build di Kalendae {__version__} per {sys.platform}…")
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
