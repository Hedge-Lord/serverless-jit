#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

BENCHES_ALL = [
    "avrora", "batik", "biojava", "cassandra", "eclipse", "fop", "graphchi",
    "h2", "h2o", "jme", "jython", "kafka", "luindex", "lusearch", "pmd",
    "spring", "sunflow", "tomcat", "tradebeans", "tradesoap", "xalan", "zxing",
]

# Map run.sh workflow name -> output filename stem
WORKFLOWS = [
    ("default", "baseline"),
    ("leyden", "leyden"),
    ("mdoreplay", "mdoreplay"),
]


def run_one(run_sh: Path, bench: str, workflow: str, out_csv: Path, invocations: int, repeats: int) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    tmp_csv = out_csv.with_suffix(out_csv.suffix + ".tmp")
    cmd = [
        "bash", str(run_sh),
        "--bench", bench,
        "--workflow", workflow,
        "--invocations", str(invocations),
        "--repeats", str(repeats),
        "--out", str(tmp_csv),
    ]
    print(f"[dacapo] {bench} :: {workflow} -> {out_csv}")
    res = subprocess.run(cmd, text=True, capture_output=True)
    if res.returncode != 0:
        sys.stderr.write(f"[dacapo] ERROR bench={bench} workflow={workflow} rc={res.returncode}\n")
        if res.stdout:
            sys.stderr.write(res.stdout + "\n")
        if res.stderr:
            sys.stderr.write(res.stderr + "\n")
        # leave tmp for inspection; do not overwrite final
        return
    try:
        tmp_csv.replace(out_csv)
    except Exception as e:
        sys.stderr.write(f"[dacapo] ERROR moving {tmp_csv} -> {out_csv}: {e}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DaCapo benches and write per-workflow CSVs.")
    parser.add_argument("--benches", nargs="*", default=BENCHES_ALL, help="Subset of benches to run")
    parser.add_argument("--invocations", type=int, default=20, help="DaCapo -n value (warmups printed then final)")
    parser.add_argument("--repeats", type=int, default=1, help="Number of repeats per workflow")
    parser.add_argument("--outdir", default="out", help="Output directory root (default: dacapo/out)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    run_sh = root / "run.sh"
    if not run_sh.exists():
        sys.stderr.write(f"[dacapo] run.sh not found at {run_sh}\n")
        sys.exit(2)

    out_root = root / args.outdir
    for bench in args.benches:
        bench_dir = out_root / bench
        for wf_name, stem in WORKFLOWS:
            out_csv = bench_dir / f"{stem}.csv"
            run_one(run_sh, bench, wf_name, out_csv, args.invocations, args.repeats)

    print(f"[dacapo] Done. Results under {out_root}")


if __name__ == "__main__":
    main()


