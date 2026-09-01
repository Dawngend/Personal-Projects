from __future__ import annotations

from pathlib import Path
import re

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent
PRODUCTION_ROOT = PROJECT_ROOT / "deploy" / "production"
LEGACY_DATA_ROOT = "/home/andreipamesa20/School-Works/All In One Reviewer"
DATA_ROOT_EXPRESSION = f"${{ANDYHUB_DATA_HOST_ROOT:-{LEGACY_DATA_ROOT}}}"


@pytest.mark.parametrize("script_name", ("cutover.sh", "rollback.sh"))
def test_production_scripts_never_derive_data_root_from_code_root(
    script_name: str,
) -> None:
    script = (PRODUCTION_ROOT / script_name).read_text(encoding="utf-8")

    assert f'readonly DATA_HOST_ROOT="${{ANDYHUB_DATA_HOST_ROOT:-{LEGACY_DATA_ROOT}}}"' in script
    assert 'export ANDYHUB_DATA_HOST_ROOT="${DATA_HOST_ROOT}"' in script
    assert "ANDYHUB_APP_ROOT" not in script

    data_root_assignments = (
        line
        for line in script.splitlines()
        if re.search(r"(?:DATA_HOST_ROOT|ANDYHUB_DATA_HOST_ROOT)=", line)
    )
    for assignment in data_root_assignments:
        assert "SCRIPT_DIR" not in assignment
        assert "APP_ROOT" not in assignment


def test_production_compose_uses_legacy_host_data_not_code_checkout() -> None:
    compose = (PRODUCTION_ROOT / "compose.production.yaml").read_text(
        encoding="utf-8"
    )

    assert "ANDYHUB_APP_ROOT" not in compose
    assert compose.count(DATA_ROOT_EXPRESSION) == 4
    for source, target in (
        ("Database", "/data/Database"),
        ("uploads", "/data/uploads"),
        ("extraction_cache", "/data/extraction_cache"),
        ("course_brain_db", "/data/course_brain_db"),
    ):
        assert f"{DATA_ROOT_EXPRESSION}/{source}:{target}" in compose


def test_cutover_preflight_checks_host_data_and_names_both_roots() -> None:
    cutover = (PRODUCTION_ROOT / "cutover.sh").read_text(encoding="utf-8")

    assert '[[ -d "${DATA_HOST_ROOT}/${directory}" ]]' in cutover
    assert "required data directory is missing: ${DATA_HOST_ROOT}/${directory}" in cutover
    assert "code root: ${APP_ROOT}; data root: ${DATA_HOST_ROOT}" in cutover
