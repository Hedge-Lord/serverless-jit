#!/usr/bin/env python3
import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


PRONG_ROOT = Path(__file__).resolve().parent
DEFAULT_BENCHES = [
    "html-rendering",
    "matrix-multiplication",
    "simple-hash",
    "word-count",
]


def read_jdk25_path() -> str:
    """Discover JDK 25 java binary.

    Prefers the packaged images/jdk when available to avoid CDS errors with exploded builds.
    Falls back to JAVA from renaissance/run.sh or system 'java' if not found.
    """
    run_sh = PRONG_ROOT.parent / "renaissance" / "run.sh"
    java_path = None
    if run_sh.exists():
        try:
            for line in run_sh.read_text().splitlines():
                if line.startswith("JAVA="):
                    cand = line.split("=", 1)[1]
                    cand = cand.strip().strip('"')
                    # Prefer images/jdk if available
                    if "/build/" in cand and "/jdk/bin/java" in cand:
                        images_cand = cand.replace("/jdk/bin/java", "/images/jdk/bin/java")
                        if Path(images_cand).exists():
                            java_path = images_cand
                        else:
                            java_path = cand
                    else:
                        java_path = cand
                    break
        except Exception:
            pass
    # Allow env override
    env_java = os.environ.get("JDK25_JAVA")
    if env_java:
        java_path = env_java
    return java_path or "java"


def ensure_install_dist(bench_dir: Path) -> None:
    libdir = bench_dir / "build" / "install" / "function" / "lib"
    if not libdir.exists() or not any(libdir.glob("*")):
        r = subprocess.run(["gradle", "-q", "installDist"], cwd=bench_dir)
        if r.returncode != 0:
            raise RuntimeError(f"installDist failed in {bench_dir}")


def compute_classpath(bench_dir: Path) -> str:
    libdir = bench_dir / "build" / "install" / "function" / "lib"
    jars = sorted(glob.glob(str(libdir / "*")))
    if not jars:
        raise RuntimeError(f"No jars found in {libdir}; did installDist succeed?")
    return ":".join(jars)


def run_runner(java: str, bench_dir: Path, cp: str, mutability: float, invocations: int, aot_cache: str = None) -> List[int]:
    args = [java]
    if aot_cache:
        args.append(f"-XX:AOTCache={aot_cache}")
    args += ["-cp", cp, "com.openfaas.function.Runner", str(mutability), str(invocations)]
    res = subprocess.run(args, cwd=bench_dir, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"Runner failed in {bench_dir.name} rc={res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
    lines = [ln.strip() for ln in (res.stdout or "").strip().splitlines() if ln.strip()]
    try:
        vals = [int(ln) for ln in lines if ln.isdigit()]
    except ValueError:
        # Fall back to regex parse digits
        import re

        m = re.compile(r"(\d+)")
        vals = []
        for ln in lines:
            mm = m.search(ln)
            if mm:
                vals.append(int(mm.group(1)))
    return vals


def train_aot(java: str, bench_dir: Path, cp: str, config_name: str, cache_name: str, mutability: float, invocations: int) -> str:
    # Clean old artifacts
    for name in [config_name, cache_name]:
        p = bench_dir / name
        if p.exists():
            p.unlink()

    rec_cmd = [java, "-XX:AOTMode=record", f"-XX:AOTConfiguration={config_name}", "-cp", cp, "com.openfaas.function.Runner", str(mutability), str(invocations)]
    rec = subprocess.run(rec_cmd, cwd=bench_dir, capture_output=True, text=True)
    if rec.returncode != 0:
        raise RuntimeError(f"AOT record failed in {bench_dir.name}:\nSTDOUT:\n{rec.stdout}\nSTDERR:\n{rec.stderr}")

    crt_cmd = [java, "-XX:AOTMode=create", f"-XX:AOTConfiguration={config_name}", f"-XX:AOTCache={cache_name}", "-cp", cp]
    crt = subprocess.run(crt_cmd, cwd=bench_dir, capture_output=True, text=True)
    if crt.returncode != 0:
        raise RuntimeError(f"AOT create failed in {bench_dir.name}:\nSTDOUT:\n{crt.stdout}\nSTDERR:\n{crt.stderr}")
    return cache_name


def run_benchmark(java: str, bench_name: str, mutability: float, invocations: int, repeats: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    bench_dir = PRONG_ROOT / bench_name
    ensure_install_dist(bench_dir)
    cp = compute_classpath(bench_dir)

    # Train AOT with same invocations for reproducibility
    aot_cache = train_aot(java, bench_dir, cp, f"{bench_name}.aotconf", f"{bench_name}.aot", mutability, invocations)

    baseline_runs: List[List[int]] = []
    aot_runs: List[List[int]] = []

    for _ in range(repeats):
        baseline_runs.append(run_runner(java, bench_dir, cp, mutability, invocations))
    for _ in range(repeats):
        aot_runs.append(run_runner(java, bench_dir, cp, mutability, invocations, aot_cache=aot_cache))

    # Normalize lengths and compute means
    min_len = min(min(len(x) for x in baseline_runs), min(len(x) for x in aot_runs))
    base_mat = np.array([x[:min_len] for x in baseline_runs], dtype=float)
    aot_mat = np.array([x[:min_len] for x in aot_runs], dtype=float)

    # Raw long-form
    rows = []
    for r, series in enumerate(baseline_runs):
        for i, v in enumerate(series[:min_len]):
            rows.append({"bench": bench_name, "variant": "baseline", "repeat": r, "invocation": i + 1, "us": v})
    for r, series in enumerate(aot_runs):
        for i, v in enumerate(series[:min_len]):
            rows.append({"bench": bench_name, "variant": "aot", "repeat": r, "invocation": i + 1, "us": v})
    raw_df = pd.DataFrame(rows)

    avg_df = pd.DataFrame({
        "bench": bench_name,
        "invocation": np.arange(1, min_len + 1),
        "baseline_mean_us": base_mat.mean(axis=0),
        "aot_mean_us": aot_mat.mean(axis=0),
    })

    return raw_df, avg_df


def plot_averaged(all_avg: pd.DataFrame, outdir: Path) -> None:
    benches = list(all_avg["bench"].unique())
    benches_sorted = [b for b in DEFAULT_BENCHES if b in benches] or benches
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    axes = axes.flatten()
    for ax, bench in zip(axes, benches_sorted):
        sub = all_avg[all_avg["bench"] == bench]
        ax.plot(sub["invocation"], sub["baseline_mean_us"], label="baseline (avg of 5)")
        ax.plot(sub["invocation"], sub["aot_mean_us"], label="aot (avg of 5)")
        ax.set_title(bench)
        ax.set_ylabel("Latency (µs)")
        ax.grid(True, alpha=0.3)
    axes[-2].set_xlabel("Invocation #")
    axes[-1].set_xlabel("Invocation #")
    axes[0].legend(loc="upper right")
    plt.suptitle("Baseline vs AOT (avg of 5 runs, raw latencies, single JVM, µs)", y=1.02)
    plt.tight_layout()
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / "avg_raw.png", dpi=150)

def plot_averaged_xlim_30(all_avg: pd.DataFrame, outdir: Path) -> None:
    benches = list(all_avg["bench"].unique())
    benches_sorted = [b for b in DEFAULT_BENCHES if b in benches] or benches
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    axes = axes.flatten()
    for ax, bench in zip(axes, benches_sorted):
        sub = all_avg[all_avg["bench"] == bench]
        ax.plot(sub["invocation"], sub["baseline_mean_us"], label="baseline (avg of 5)")
        ax.plot(sub["invocation"], sub["aot_mean_us"], label="aot (avg of 5)")
        ax.set_title(bench)
        ax.set_ylabel("Latency (µs)")
        ax.grid(True, alpha=0.3)
    axes[-2].set_xlabel("Invocation #")
    axes[-1].set_xlabel("Invocation #")
    axes[0].legend(loc="upper right")
    plt.suptitle("Baseline vs AOT (avg of 5 runs, raw latencies, single JVM, µs)", y=1.02)
    plt.tight_layout()
    plt.xlim(0, 30)
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / "avg_raw_xlim_30.png", dpi=150)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pronghorn Java benchmarks baseline vs AOT, 5x repeats, and plot averages.")
    parser.add_argument("--jdk", dest="java_path", default=None, help="Path to java binary to use (default: JDK25 images path discovered)")
    parser.add_argument("--benches", nargs="*", default=DEFAULT_BENCHES, help="Benchmarks to run")
    parser.add_argument("--mutability", type=float, default=0.5, help="Mutability parameter passed to benchmarks")
    parser.add_argument("--invocations", type=int, default=500, help="Number of invocations per run")
    parser.add_argument("--repeats", type=int, default=5, help="Number of repeats per variant (baseline/AOT)")
    parser.add_argument("--out", dest="outdir", default=str(PRONG_ROOT / "out"), help="Output directory for CSVs and plots")
    args = parser.parse_args()

    java = args.java_path or read_jdk25_path()
    print(f"Using java: {java}")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    all_raw: List[pd.DataFrame] = []
    all_avg: List[pd.DataFrame] = []

    for bench in args.benches:
        print(f"\n=== {bench} ===")
        raw_df, avg_df = run_benchmark(java, bench, args.mutability, args.invocations, args.repeats)
        all_raw.append(raw_df)
        all_avg.append(avg_df)
        raw_path = outdir / f"{bench}_raw.csv"
        avg_path = outdir / f"{bench}_avg.csv"
        raw_df.to_csv(raw_path, index=False)
        avg_df.to_csv(avg_path, index=False)
        print(f"Wrote {raw_path} and {avg_path}")

    all_raw_df = pd.concat(all_raw, ignore_index=True)
    all_avg_df = pd.concat(all_avg, ignore_index=True)
    all_raw_df.to_csv(outdir / "all_raw.csv", index=False)
    all_avg_df.to_csv(outdir / "all_avg.csv", index=False)
    print(f"Wrote {outdir/'all_raw.csv'} and {outdir/'all_avg.csv'}")

    plot_averaged(all_avg_df, outdir)
    print(f"Saved plot to {outdir/'avg_raw.png'}")

    plot_averaged_xlim_30(all_avg_df, outdir)
    print(f"Saved plot to {outdir/'avg_raw_xlim_30.png'}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)


