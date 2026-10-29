"""
build_exe.py
------------
Builds the standalone Windows Executable (.exe) for Printer Agent System Tray.
Runs PyInstaller in windowed mode (--noconsole) with a custom .ico icon,
producing a portable single-file binary: dist/PrinterAgent.exe
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
RELEASE_DIR = BASE_DIR / "release"
ASSETS_DIR = BASE_DIR / "assets"
ICO_PATH = ASSETS_DIR / "printer_agent.ico"


def step_banner(title: str):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def generate_icon_if_missing():
    step_banner("[1/4] Generating Application Icon (.ico)")
    if not ICO_PATH.exists():
        from printer_agent.generate_icon import generate_ico
        generate_ico()
    else:
        print(f"Icon already exists at {ICO_PATH}")


def clean_previous_builds():
    step_banner("[2/4] Cleaning previous build artifacts")
    for folder in [DIST_DIR, BUILD_DIR, RELEASE_DIR]:
        if folder.exists():
            try:
                shutil.rmtree(folder)
                print(f"Removed {folder.name}/")
            except Exception as e:
                print(f"Warning: Could not remove {folder}: {e}")

    spec_file = BASE_DIR / "PrinterAgent.spec"
    if spec_file.exists():
        try:
            spec_file.unlink()
        except Exception:
            pass


def run_pyinstaller():
    step_banner("[3/4] Compiling Standalone Windows Executable with PyInstaller")

    # Entry point
    entry_point = BASE_DIR / "printer_agent" / "tray_app.py"

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",                           # Silent system tray app (no CMD window)
        "--onefile",                             # Single standalone .exe
        "--name", "PrinterAgent",                # Output binary name: PrinterAgent.exe
        "--icon", str(ICO_PATH),                 # Application icon
        "--add-data", f"{BASE_DIR / 'printer_agent'};printer_agent",
        "--hidden-import", "pystray",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._imaging",
        "--hidden-import", "win32print",
        "--hidden-import", "win32api",
        "--hidden-import", "win32con",
        "--hidden-import", "win32event",
        "--hidden-import", "win32gui",
        "--hidden-import", "win32process",
        "--hidden-import", "colorama",
        "--clean",
        str(entry_point),
    ]

    print(f"Running command:\n{' '.join(pyinstaller_cmd)}\n")
    result = subprocess.run(pyinstaller_cmd, cwd=str(BASE_DIR))

    if result.returncode != 0:
        print(f"\n❌ PyInstaller build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    print("\n✅ PyInstaller compilation finished successfully!")


def prepare_release_package():
    step_banner("[4/4] Assembling Release Distribution Package")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    exe_source = DIST_DIR / "PrinterAgent.exe"
    if not exe_source.exists():
        print(f"❌ Error: Expected executable not found at {exe_source}")
        sys.exit(1)

    # 1. Copy PrinterAgent.exe
    shutil.copy2(exe_source, RELEASE_DIR / "PrinterAgent.exe")
    print("  + Copied PrinterAgent.exe")

    # 2. Generate clean shop_config.json
    shop_config = {
        "server_url": "http://localhost:8000",
        "shop_id": "counter-1",
        "api_key": "shop-secret-key-1",
        "printer_name": "",
        "auto_print": True,
        "poll_interval": 3.0,
        "desktop_notifications": True,
    }
    import json
    with open(RELEASE_DIR / "shop_config.json", "w", encoding="utf-8") as f:
        json.dump(shop_config, f, indent=4)
    print("  + Created default shop_config.json")

    # 3. Create shopkeeper instructions
    instructions = (
        "====================================================================\n"
        "           PRINTER AGENT - SHOPKEEPER CLIENT SETUP                  \n"
        "====================================================================\n\n"
        "QUICK START GUIDE:\n\n"
        "1. Open 'shop_config.json' in Notepad.\n"
        "2. Set your configuration:\n"
        "   - 'server_url' : The web link provided by your admin (e.g. https://prints.yourdomain.com)\n"
        "   - 'shop_id'    : Your unique shop ID (e.g. malik-cafe)\n"
        "   - 'printer_name': Leave empty to use your Windows default printer,\n"
        "                    or type your printer's exact name (e.g. HP LaserJet P1108)\n\n"
        "3. Double-click 'PrinterAgent.exe' to run!\n"
        "   - The printer icon will appear in your Windows System Tray (near the clock).\n"
        "   - Right-click the icon anytime to:\n"
        "     * Print a Hardware Test Page\n"
        "     * Check Connection Status\n"
        "     * Open the Web Dashboard\n"
        "     * View Customer Orders\n\n"
        "4. Auto-Start with Windows (Optional):\n"
        "   Press Win+R, type 'shell:startup', and copy a shortcut of 'PrinterAgent.exe' here.\n\n"
        "====================================================================\n"
    )
    with open(RELEASE_DIR / "HOW_TO_RUN.txt", "w", encoding="utf-8") as f:
        f.write(instructions)
    print("  + Created HOW_TO_RUN.txt")

    print(f"\n🎉 Distribution Package Ready at:\n   {RELEASE_DIR.resolve()}\n")


def main():
    print("=================================================================")
    print("       PRINTER AGENT - WINDOWS EXECUTABLE BUILD UTILITY          ")
    print("=================================================================")

    generate_icon_if_missing()
    clean_previous_builds()
    run_pyinstaller()
    prepare_release_package()


if __name__ == "__main__":
    main()
