#!/usr/bin/env python3
import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path
from statistics import median


def run(cmd, cwd=None):
    print("\n$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(cmd)}")
    return proc


def summarize_csv(path: Path):
    times = []
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                times.append(float(row["time_us"]))
            except Exception:
                pass
    if not times:
        return None
    first = times[0]
    avg = sum(times) / len(times)
    med = median(times)
    p95 = sorted(times)[int(0.95 * (len(times) - 1))]
    return {"count": len(times), "first": first, "avg": avg, "median": med, "p95": p95}


def main():
    parser = argparse.ArgumentParser(description="AOT cache verification runner")
    parser.add_argument("--invocations", type=int, default=2000, help="invocations per run")
    parser.add_argument("--rebuild", action="store_true", help="re-record training and re-create cache")
    parser.add_argument("--profiles_only", action="store_true", help="use TrainingData only (no AOT code)")
    parser.add_argument("--strict_cold", action="store_true", help="disable CDS/AOT for baseline")
    args = parser.parse_args()

    ROOT = Path(__file__).resolve().parents[1]
    JDK = ROOT / "jdk25u" / "build" / "macosx-aarch64-server-release" / "images" / "jdk"
    JAVA = JDK / "bin" / "java"
    JAVAC = JDK / "bin" / "javac"
    BENCH = ROOT / "bench"

    if not JAVA.exists():
        raise SystemExit(f"JAVA not found: {JAVA}")
    if not JAVAC.exists():
        raise SystemExit(f"JAVAC not found: {JAVAC}")

    os.chdir(BENCH)
    print(f"Working dir: {Path.cwd()}")

    # Build benchmark
    run([str(JAVAC), "WordCountBenchmark.java"])

    # Clean previous outputs
    for pat in ("*.csv", "*.aot", "*.aotconfig", "hotspot_pid*.log"):
        for p in Path('.').glob(pat):
            try:
                p.unlink()
            except Exception:
                pass

    AOT_CONFIG = Path("wordcount.aotconfig")
    AOT_CACHE = Path("wordcount.aot")

    # Training (record) and assembly (create)
    if args.rebuild or not AOT_CACHE.exists():
        print("\n== Record training data ==")
        run([
            str(JAVA),
            "-XX:+UnlockDiagnosticVMOptions",
            "-XX:AOTMode=record",
            f"-XX:AOTConfiguration={AOT_CONFIG}",
            "-Xlog:aot=info",
            "-cp", ".",
            "WordCountBenchmark", "0", "1000", "warmup_results.csv",
        ])

        print("\n== Create AOT cache ==")
        run([
            str(JAVA),
            "-XX:+UnlockDiagnosticVMOptions",
            "-XX:AOTMode=create",
            f"-XX:AOTConfiguration={AOT_CONFIG}",
            f"-XX:AOTCacheOutput={AOT_CACHE}",
            "-Xlog:aot=info",
            "-version",
        ])

    if not AOT_CACHE.exists():
        raise SystemExit("AOT cache not found; recording/creation failed")

    INV = str(args.invocations)

    # Baseline (strict cold if requested)
    print("\n== Baseline (no AOT cache) ==")
    baseline_cmd = [str(JAVA)]
    if args.strict_cold:
        # Disable CDS to avoid warm state; do not specify AOTMode here (conflicts with -Xshare)
        baseline_cmd += ["-Xshare:off", "-Xlog:cds=info"]
    baseline_cmd += [
        "-Xlog:aot=info",
        "-cp", ".",
        "WordCountBenchmark", "0", INV, "cold_results.csv",
    ]
    run(baseline_cmd)

    # Replay (AOT cache on)
    print("\n== Replay (AOT cache) ==")
    replay_cmd = [
        str(JAVA),
        "-XX:+UnlockDiagnosticVMOptions",
        "-Xlog:aot=info",
        "-XX:AOTMode=on",
        f"-XX:AOTCache={AOT_CACHE}",
        "-cp", ".",
    ]
    if args.profiles_only:
        replay_cmd += ["-XX:+AOTReplayTraining", "-XX:-AOTAdapterCaching", "-XX:-AOTStubCaching"]
    replay_cmd += ["WordCountBenchmark", "0", INV, "warm_results.csv"]
    run(replay_cmd)

    # Summaries
    for label, file in (
        ("baseline", Path("cold_results.csv")),
        ("replay", Path("warm_results.csv")),
    ):
        s = summarize_csv(file)
        if s:
            print(
                f"\n[{label}] count={s['count']} first={s['first']:.1f} µs "
                f"avg={s['avg']:.1f} µs p95={s['p95']:.1f} µs"
            )

    print("\nDone. Inspect aot logs above to verify mapping/usage.")


if __name__ == "__main__":
    main()


