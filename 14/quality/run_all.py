import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Дочірні скрипти друкують «−» та кирилицю; консоль Windows (cp1251) без цього падає.
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for script in ("profile.py", "dedup.py", "conflicts.py", "gate.py", "after.py"):
        print("→", script, flush=True)
        subprocess.run([sys.executable, str(ROOT / "quality" / script)], check=True, cwd=ROOT, env=ENV)
    subprocess.run([sys.executable, "-m", "pytest", "quality/tests", "-q"], check=True, cwd=ROOT, env=ENV)


if __name__ == "__main__":
    main()
