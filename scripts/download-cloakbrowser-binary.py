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

from cloakbrowser import ensure_binary


def main():
    target_dir = Path(__file__).parent.parent / "src-tauri" / "bundle-resources" / "cloakbrowser"

    # Binary already exists — skip re-download
    if target_dir.exists() and (target_dir / "chrome.exe").exists():
        print(f"[SKIP] CloakBrowser already exists at {target_dir}")
        print(f"  Delete {target_dir} and re-run to re-download")
        return

    if target_dir.exists():
        shutil.rmtree(target_dir)

    print("Downloading CloakBrowser stealth Chromium binary...")
    binary_path = ensure_binary()

    # Copy the ENTIRE extracted directory (not just chrome.exe)
    # Chrome needs chrome.dll, locales, resources.pak, etc. to run
    source_dir = Path(binary_path).parent
    print(f"Copying full CloakBrowser directory: {source_dir}")
    shutil.copytree(source_dir, target_dir)

    total_size = sum(f.stat().st_size for f in target_dir.rglob("*") if f.is_file())
    print(f"[OK] CloakBrowser copied to {target_dir}")
    print(f"     Size: {total_size / 1024 / 1024:.1f} MB")
    print(f"     Files: {sum(1 for _ in target_dir.rglob('*') if _.is_file())}")


if __name__ == "__main__":
    main()
