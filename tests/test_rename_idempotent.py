import subprocess


def test_rename_project_check_idempotent() -> None:
    result = subprocess.run(
        ["python", "scripts/rename_project.py", "--name", "AegisFlux", "--module", "aegisflux", "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
