# Windows Installer Build Guide

This document covers building, signing, and distributing the Windows installer
for Salesforce Translation Handler.

## Prerequisites

| Tool | Version | Required for |
|------|---------|--------------|
| Python | 3.9+ (3.11 recommended) | Application build |
| PyInstaller | Latest | Executable packaging |
| Inno Setup 6 | 6.x | Installer compilation |
| signtool.exe | Windows SDK | Code-signing (optional) |

### Installing prerequisites

**Python and PyInstaller:**

```bash
pip install -e ".[gui]"
pip install pyinstaller
```

**Inno Setup 6:**

Download from [jrsoftware.org](https://jrsoftware.org/isinfo.php) and install,
or use Chocolatey:

```powershell
choco install innosetup
```

After installation, ensure `ISCC.exe` is on your PATH, or the build script will
look in the default install location (`C:\Program Files (x86)\Inno Setup 6\`).

**signtool (optional):**

Install the [Windows SDK](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/)
which includes signtool.exe. Only needed if you plan to code-sign the installer.

---

## Local Build Instructions

### Quick build (full pipeline)

```bash
python installer/build_installer.py
```

This runs the complete pipeline:
1. Builds the executable with PyInstaller (--onedir mode)
2. Compiles the installer with Inno Setup
3. Produces `dist/installer/SalesforceTranslationHandler_Setup_1.5.0.exe`

### Build options

```bash
# Skip PyInstaller step (reuse existing dist/ output)
python installer/build_installer.py --skip-build

# Build and sign the installer
python installer/build_installer.py --sign

# Use --onefile mode instead of --onedir
python installer/build_installer.py --onefile

# Show all options
python installer/build_installer.py --help
```

### Manual step-by-step build

If you prefer to run each step individually:

```bash
# Step 1: Build executable
python build_exe.py

# Step 2: Compile installer (requires Inno Setup on PATH)
iscc installer/stx_installer.iss

# Step 3 (optional): Sign the installer
powershell -File installer/sign_executable.ps1 -FilePath "dist\installer\SalesforceTranslationHandler_Setup_1.5.0.exe"
```

---

## Code-Signing Setup

Code-signing is optional but recommended for distribution. It prevents Windows
SmartScreen warnings and confirms the software publisher identity.

### Acquiring a certificate

1. Purchase a code-signing certificate from a trusted CA (DigiCert, Sectigo, etc.)
2. Export the certificate as a `.pfx` file with a password
3. Store it securely (never commit to version control)

### Environment variables

The signing script reads these environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `SIGN_CERT_PATH` | Path to .pfx certificate file | `C:\certs\codesign.pfx` |
| `SIGN_CERT_PASSWORD` | Certificate password | (secret) |
| `SIGN_TIMESTAMP_URL` | RFC 3161 timestamp server | `http://timestamp.digicert.com` |

Set them before running the signing step:

```powershell
$env:SIGN_CERT_PATH = "C:\path\to\certificate.pfx"
$env:SIGN_CERT_PASSWORD = "your-password"
$env:SIGN_TIMESTAMP_URL = "http://timestamp.digicert.com"
```

### Running the signing script

```powershell
.\installer\sign_executable.ps1 -FilePath "dist\installer\SalesforceTranslationHandler_Setup_1.5.0.exe"
```

The script will:
- Locate signtool.exe (PATH or Windows SDK)
- Sign with SHA-256
- Timestamp the signature (for long-term validity)
- Verify the signature after signing

---

## CI/CD Pipeline

The GitHub Actions workflow at `.github/workflows/build-installer.yml` automates
the build process.

### Triggers

- **Push to `release/**` branches** - automatically builds the installer
- **Manual dispatch** - trigger from the Actions tab with optional signing

### Workflow steps

1. Checks out the repository
2. Sets up Python 3.11
3. Installs Inno Setup via Chocolatey
4. Installs project dependencies and PyInstaller
5. Builds the executable with `build_exe.py`
6. Compiles the installer with ISCC
7. (Conditional) Signs the installer if secrets are configured
8. Uploads the installer as a workflow artifact

### Secrets for CI signing

Add these repository secrets for automated code-signing:

| Secret | Description |
|--------|-------------|
| `SIGN_CERT_PATH` | Base64-encoded .pfx file or path |
| `SIGN_CERT_PASSWORD` | Certificate password |

The signing step is skipped automatically when secrets are not configured.

### Downloading the artifact

After a successful workflow run:
1. Go to the Actions tab
2. Click the completed workflow run
3. Download `windows-installer` from the Artifacts section

---

## Customizing the Installer

### Changing the version

The version is defined in the `.iss` script header:

```inno
#define MyAppVersion "1.5.0"
```

This should match the version in `src/stx/__init__.py` and `pyproject.toml`.

### Changing the publisher

Edit the `MyAppPublisher` define in `installer/stx_installer.iss`:

```inno
#define MyAppPublisher "Your Organization Name"
```

### Changing install behavior

Key settings in the `[Setup]` section:

| Setting | Current value | Description |
|---------|--------------|-------------|
| `DefaultDirName` | `{autopf}\SalesforceTranslationHandler` | Install location |
| `PrivilegesRequired` | `lowest` | No admin needed (per-user install) |
| `Compression` | `lzma2/ultra64` | Maximum compression |
| `WizardStyle` | `modern` | Inno Setup 6 modern UI |

### Adding files to the installer

Edit the `[Files]` section to include additional resources:

```inno
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs
```

---

## Troubleshooting

### ISCC.exe not found

Ensure Inno Setup 6 is installed and either:
- `ISCC.exe` is on your system PATH, or
- It is installed at `C:\Program Files (x86)\Inno Setup 6\`

### PyInstaller build fails

Run `build_exe.py` standalone first to diagnose:

```bash
python build_exe.py
```

Common issues:
- Missing dependencies: run `pip install -e ".[gui]"` first
- Antivirus interference: add exclusions for the `dist/` and `build/` directories

### Signing fails

- Verify `SIGN_CERT_PATH` points to a valid `.pfx` file
- Verify the password is correct
- Ensure signtool.exe is available (install Windows SDK)
- Check that the timestamp server is reachable

### Installer is too large

The installer packages the entire PyInstaller output. To reduce size:
- Use UPX compression: add `--upx-dir` flag to PyInstaller
- Exclude unused modules with PyInstaller `--exclude-module`
- Review hidden imports in `build_exe.py` for unnecessary entries
