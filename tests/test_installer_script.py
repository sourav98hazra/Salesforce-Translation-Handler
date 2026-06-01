"""Tests for the Windows installer infrastructure.

Validates:
- The .iss file exists and contains required Inno Setup sections
- build_installer.py is importable and has a main() function
- The .iss file references the correct app name and version
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ISS_FILE = ROOT / "installer" / "stx_installer.iss"
BUILD_INSTALLER = ROOT / "installer" / "build_installer.py"
SIGN_SCRIPT = ROOT / "installer" / "sign_executable.ps1"
WORKFLOW_FILE = ROOT / ".github" / "workflows" / "build-installer.yml"
DOCS_FILE = ROOT / "docs" / "INSTALLER.md"


class TestIssFileExists:
    """Verify the .iss file and supporting files exist."""

    def test_iss_file_exists(self):
        assert ISS_FILE.is_file(), f"Inno Setup script not found: {ISS_FILE}"

    def test_build_installer_exists(self):
        assert BUILD_INSTALLER.is_file(), f"build_installer.py not found: {BUILD_INSTALLER}"

    def test_sign_script_exists(self):
        assert SIGN_SCRIPT.is_file(), f"sign_executable.ps1 not found: {SIGN_SCRIPT}"

    def test_workflow_exists(self):
        assert WORKFLOW_FILE.is_file(), f"CI workflow not found: {WORKFLOW_FILE}"

    def test_docs_exists(self):
        assert DOCS_FILE.is_file(), f"INSTALLER.md not found: {DOCS_FILE}"


class TestIssFileSections:
    """Verify the .iss file contains all required Inno Setup sections."""

    @pytest.fixture
    def iss_content(self) -> str:
        return ISS_FILE.read_text(encoding="utf-8")

    def test_has_setup_section(self, iss_content: str):
        assert "[Setup]" in iss_content, "Missing [Setup] section"

    def test_has_files_section(self, iss_content: str):
        assert "[Files]" in iss_content, "Missing [Files] section"

    def test_has_icons_section(self, iss_content: str):
        assert "[Icons]" in iss_content, "Missing [Icons] section"

    def test_has_run_section(self, iss_content: str):
        assert "[Run]" in iss_content, "Missing [Run] section"

    def test_has_uninstalldelete_section(self, iss_content: str):
        assert "[UninstallDelete]" in iss_content, "Missing [UninstallDelete] section"

    def test_has_tasks_section(self, iss_content: str):
        assert "[Tasks]" in iss_content, "Missing [Tasks] section"

    def test_has_code_section(self, iss_content: str):
        assert "[Code]" in iss_content, "Missing [Code] section"


class TestIssFileContent:
    """Verify the .iss file references the correct app name and version."""

    @pytest.fixture
    def iss_content(self) -> str:
        return ISS_FILE.read_text(encoding="utf-8")

    def test_app_name_defined(self, iss_content: str):
        assert '#define MyAppName "Salesforce Translation Handler"' in iss_content

    def test_app_version_defined(self, iss_content: str):
        assert '#define MyAppVersion "1.5.0"' in iss_content

    def test_app_exe_name(self, iss_content: str):
        assert "SalesforceTranslationHandler.exe" in iss_content

    def test_references_dist_directory(self, iss_content: str):
        assert "dist\\SalesforceTranslationHandler" in iss_content

    def test_start_menu_shortcut(self, iss_content: str):
        assert "{group}" in iss_content

    def test_desktop_shortcut(self, iss_content: str):
        assert "{autodesktop}" in iss_content
        assert "desktopicon" in iss_content

    def test_uninstaller_entry(self, iss_content: str):
        assert "{uninstallexe}" in iss_content

    def test_license_file_referenced(self, iss_content: str):
        assert "LicenseFile" in iss_content

    def test_icon_file_referenced(self, iss_content: str):
        assert "logo.ico" in iss_content

    def test_compression_set(self, iss_content: str):
        assert "lzma2" in iss_content

    def test_modern_wizard_style(self, iss_content: str):
        assert "WizardStyle=modern" in iss_content


class TestBuildInstallerModule:
    """Verify build_installer.py is importable and has expected interface."""

    def test_importable(self):
        spec = importlib.util.spec_from_file_location("build_installer", BUILD_INSTALLER)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "main"), "build_installer.py must have a main() function"

    def test_main_is_callable(self):
        spec = importlib.util.spec_from_file_location("build_installer", BUILD_INSTALLER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert callable(module.main)

    def test_has_find_iscc(self):
        spec = importlib.util.spec_from_file_location("build_installer", BUILD_INSTALLER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "find_iscc"), "build_installer.py should have find_iscc()"

    def test_help_flag(self):
        """Verify --help works without error."""
        spec = importlib.util.spec_from_file_location("build_installer", BUILD_INSTALLER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with pytest.raises(SystemExit) as exc_info:
            module.main(["--help"])
        assert exc_info.value.code == 0


class TestWorkflowContent:
    """Verify the CI workflow has expected configuration."""

    @pytest.fixture
    def workflow_content(self) -> str:
        return WORKFLOW_FILE.read_text(encoding="utf-8")

    def test_runs_on_windows(self, workflow_content: str):
        assert "windows-latest" in workflow_content

    def test_installs_inno_setup(self, workflow_content: str):
        assert "innosetup" in workflow_content

    def test_uses_python_311(self, workflow_content: str):
        assert "3.11" in workflow_content

    def test_uploads_artifact(self, workflow_content: str):
        assert "upload-artifact" in workflow_content

    def test_release_branch_trigger(self, workflow_content: str):
        assert "release/**" in workflow_content
