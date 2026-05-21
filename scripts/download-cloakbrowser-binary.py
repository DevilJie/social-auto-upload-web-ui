"""
在 ``tauri build`` 之前运行：下载 CloakBrowser stealth Chromium binary，
存到 ``src-tauri/bundle-resources/cloakbrowser/``。

运行方式：
    pip install cloakbrowser
    python scripts/download-cloakbrowser-binary.py
"""
import shutil
import sys
from pathlib import Path

from cloakbrowser import ensure_binary, binary_info


def main():
    target_dir = Path(__file__).parent.parent / "src-tauri" / "bundle-resources" / "cloakbrowser"
    target_dir.mkdir(parents=True, exist_ok=True)

    binary_name = "chrome.exe" if sys.platform == "win32" else "chrome"
    dest = target_dir / binary_name

    if dest.exists():
        print(f"[SKIP] Binary already exists at {dest}")
        print(f"  Delete {dest} and re-run to re-download")
        return

    print("Downloading CloakBrowser stealth Chromium binary...")
    binary_path = ensure_binary()
    shutil.copy2(binary_path, dest)
    info = binary_info()
    print(f"[OK] CloakBrowser v{info['version']} copied to {dest}")
    print(f"     Platform: {info['platform']}")


if __name__ == "__main__":
    main()
