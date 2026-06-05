# Build & Release Instructions — Salesforce Translation Manager v3.0.0

## Prerequisites (one-time setup on Windows)

1. **Python 3.9+** installed and on PATH
2. **Inno Setup 6** installed from https://jrsoftware.org/isdl.php
3. Repository cloned and on the correct branch

---

## Build Steps

### 1. Open Command Prompt in the project folder

```cmd
cd C:\Users\Sourav\Dropbox\PC\Documents\GitHub\Salesforce-Translation-Handler
```

### 2. Checkout and pull latest

```cmd
git checkout feature/phase-snapshots
git pull
```

### 3. Create a clean build venv

```cmd
python -m venv .build-venv
.build-venv\Scripts\activate
```

### 4. Install app + build tools

```cmd
pip install -e ".[gui]"
pip install pyinstaller
```

### 5. Build the full installer (PyInstaller + Inno Setup)

```cmd
python installer/build_installer.py
```

**Output:** `dist/installer/SalesforceTranslationHandler_Setup_3.0.0.exe`

---

## Alternative Build Options

### Standalone .exe only (no Inno Setup needed)

```cmd
python build_exe.py
```

**Output:** `dist/SalesforceTranslationHandler.exe`

### Recompile installer only (reuse existing PyInstaller output)

```cmd
python installer/build_installer.py --skip-build
```

---

## What Each Script Does

| Script | What it does |
|--------|-------------|
| `build_exe.py` | PyInstaller --onefile (single .exe). When STX_PYINSTALLER_ONEDIR=1 env is set, uses --onedir instead |
| `installer/build_installer.py` | Sets STX_PYINSTALLER_ONEDIR=1 -> runs build_exe.py (produces directory) -> runs Inno Setup ISCC on .iss script |
| `build_secure_setup.py` | Alternative wrapper: --exe for standalone, no flag for full installer |
| `installer/stx_installer.iss` | Inno Setup script - packages dist/SalesforceTranslationHandler/ into a Setup wizard |

---

## Release on GitHub

### 1. Merge to main

```cmd
git checkout main
git merge feature/phase-snapshots
git push origin main
```

### 2. Tag the release

```cmd
git tag -a v3.0.0 -m "Release v3.0.0"
git push origin v3.0.0
```

### 3. Create GitHub Release

1. Go to: https://github.com/sourav98hazra/Salesforce-Translation-Handler/releases/new
2. Select tag: v3.0.0
3. Title: "Salesforce Translation Manager v3.0.0"
4. Attach: `dist/installer/SalesforceTranslationHandler_Setup_3.0.0.exe`
5. Publish

---

## What Users Get

- Download `SalesforceTranslationHandler_Setup_3.0.0.exe` (single file, ~80-120 MB)
- Double-click it
- Standard Windows installer wizard:
  - Choose install location (default: C:\Program Files\Salesforce Translation Manager)
  - Create desktop shortcut (optional)
  - Create Start Menu entry
- After install:
  - Desktop shortcut with the STM logo
  - Start Menu entry: "Salesforce Translation Manager"
  - Uninstaller in Add/Remove Programs

---

## Verify Download Integrity

Recipients can verify the download with:

```cmd
certutil -hashfile SalesforceTranslationHandler_Setup_3.0.0.exe SHA256
```

Compare output with the .sha256 file.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `PyInstaller is not installed` | `pip install pyinstaller` |
| `stx not installed` | `pip install -e ".[gui]"` |
| `ISCC.exe not found` | Install Inno Setup 6, or use `build_exe.py` for standalone .exe |
| `Source file does not exist` in .iss | Run `python installer/build_installer.py` (not ISCC directly) - it runs PyInstaller first |
| `Type is not a valid value` in .iss | Pull latest - fixed `filesandirs` to `files` + `dirifempty` |
| `STX_PYINSTALLER_ONEDIR` not recognized | Use `python installer/build_installer.py` which sets this automatically |

---

## Version History

- v3.0.0 - Phase Snapshots, ETA fix, Reset improvements, Window icon, Validation report xlsx
- v2.0.0 - Six-phase pipeline, Translation Memory, Glossary, Multi-backend support
