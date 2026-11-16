"""Повний прогін ЛР13. Ключ API потрібен лише для методу Б, і лише якщо кешу ще немає."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script, *args):
    command = [sys.executable, str(ROOT / "src" / script), *args]
    print("→", " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)


def main():
    run("build_corpus.py")
    run("extract_rules.py")
    run("extract_llm.py", "--self-test")
    if "--no-llm" not in sys.argv:
        run("extract_llm.py")
    run("evaluate.py")
    run("link_graph.py")
    run("patterns.py")


if __name__ == "__main__":
    main()
