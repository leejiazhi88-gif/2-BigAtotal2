"""Refresh the data actually used by the dashboard and report elapsed time."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-refresh", action="store_true", help="Also refresh older daily history revisions.")
    args = parser.parse_args()
    started = time.perf_counter()
    for script in ("build_real_sector_data.py", "build_company_data.py"):
        phase = time.perf_counter()
        command = [sys.executable, "-u", str(ROOT / "work" / script)]
        if args.full_refresh and script == "build_real_sector_data.py":
            command.append("--full-refresh")
        subprocess.run(command, cwd=ROOT, check=True)
        print(f"{script}: {time.perf_counter() - phase:.2f}s", flush=True)
    print(f"Dashboard data refreshed in {time.perf_counter() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
