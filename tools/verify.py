"""Воспроизводимая проверка тестов, покрытия и статического анализа."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
EVIDENCE.mkdir(exist_ok=True)


def run(name, args):
    result = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    (EVIDENCE / name).write_text(result.stdout + result.stderr, encoding="utf-8")
    print(f"{name}: exit={result.returncode}")
    if result.returncode:
        print((result.stdout + result.stderr)[-5000:])
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    run("tests.txt", ["-X", "utf8", "-m", "coverage", "run", "-m", "unittest", "discover", "-v"])
    run("coverage.txt", ["-m", "coverage", "report", "-m"])
    run("coverage_export.txt", ["-m", "coverage", "json", "-o", "evidence/coverage.json"])
    run("coverage_html.txt", ["-m", "coverage", "html"])
    run("static_analysis.txt", ["-m", "ruff", "check", "fitdiary", "tests", "tools", "run.py"])
    run("compile.txt", ["-m", "compileall", "-q", "fitdiary", "tests", "tools", "run.py"])
