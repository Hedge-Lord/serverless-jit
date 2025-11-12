#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/.." && pwd)"
if [[ -f "${REPO_ROOT}/local.env" ]]; then source "${REPO_ROOT}/local.env"; fi

JAVA="${JAVA:-java}"
BASE_FLAGS="${BASE_FLAGS:-}"
EXTRA_FLAGS=""
JAR="${ROOT}/dacapo-23.11-MR2-chopin.jar"
BENCH=""
WORKFLOW="default"   # default | mdoreplay | leyden
INVOCATIONS=20       # DaCapo runs warmups 1..(n-1) then final timed iteration
REPEATS=1
OUT="${ROOT}/out.csv"
SIZE="small"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --java) JAVA="$2"; shift 2 ;;
    --bench) BENCH="$2"; shift 2 ;;
    --workflow) WORKFLOW="$2"; shift 2 ;;
    --invocations) INVOCATIONS="$2"; shift 2 ;;
    --repeats) REPEATS="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --extra-flags) EXTRA_FLAGS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "${JAR}" ]]; then
  echo "DaCapo jar not found at ${JAR}. Place dacapo-23.11-MR2-chopin.jar alongside run.sh." >&2
  exit 2
fi
if [[ -z "${BENCH}" ]]; then
  echo "--bench required (e.g., avrora batik ... zxing)" >&2
  exit 2
fi

SUITE="dacapo"
MDO_FILE="/tmp/dacapo_${BENCH}.mdo"
AOT_CONF="/tmp/dacapo_${BENCH}.aotconf"
AOT_CACHE="/tmp/dacapo_${BENCH}.aot"

TMPDIR="$(mktemp -d /tmp/dacapo_out_XXXXXX)"
trap 'rm -rf "${TMPDIR}"' EXIT
echo "suite,bench,workflow,phase,repeat,iteration,duration_ms" > "${OUT}"

parse_and_emit() {
  local wf="$1" phase="$2" rep="$3" file="$4"

  # Warmup lines: "completed warmup N in X msec"
  # Final line:   "PASSED ... in X msec"
  # Emit warmups as iteration = N, and final PASSED as iteration = last+1, units = milliseconds.

  local iter=0
  # Warmups
  # Extract "N X" pairs; N = warmup index, X = msec
  while IFS= read -r line; do
    # N
    local n
    n="$(printf '%s\n' "$line" | sed -E 's/.*completed warmup[[:space:]]+([0-9]+)[[:space:]]+in[[:space:]]+([0-9]+)[[:space:]]+msec.*/\1/')" || true
    # X (ms)
    local ms
    ms="$(printf '%s\n' "$line" | sed -E 's/.*completed warmup[[:space:]]+([0-9]+)[[:space:]]+in[[:space:]]+([0-9]+)[[:space:]]+msec.*/\2/')" || true
     # If parse worked, emit (milliseconds)
    if [[ "$n" =~ ^[0-9]+$ ]] && [[ "$ms" =~ ^[0-9]+$ ]]; then
      iter="$n"
       printf "%s,%s,%s,%s,%s,%d,%d\n" \
         "$SUITE" "$BENCH" "$wf" "$phase" "$rep" "$iter" "$ms" >> "$OUT"
    fi
  done < <(grep -F "completed warmup" "$file" || true)

  # PASSED line → iteration = last warmup + 1
  local ms_passed
  ms_passed="$(grep -E 'PASSED.* in [0-9]+[[:space:]]+msec' "$file" \
               | tail -n1 \
               | sed -E 's/.*PASSED.* in[[:space:]]+([0-9]+)[[:space:]]+msec.*/\1/')" || true
  if [[ "$ms_passed" =~ ^[0-9]+$ ]]; then
    printf "%s,%s,%s,%s,%s,%d,%d\n" \
      "$SUITE" "$BENCH" "$wf" "$phase" "$rep" "$((iter+1))" "$ms_passed" >> "$OUT"
  fi
}


run_phase() {
  local wf="$1" phase="$2" rep="$3"
  shift 3
  local tmp="${TMPDIR}/${BENCH}_${wf}_${phase}_r${rep}.out"
  local flags=( ${BASE_FLAGS} ${EXTRA_FLAGS} "$@" )
  # Run DaCapo; if it fails, surface the log and exit
  if ! "${JAVA}" "${flags[@]}" -jar "${JAR}" "${BENCH}" -s "${SIZE}" -n "${INVOCATIONS}" > "${tmp}" 2>&1; then
    echo "DaCapo failed (workflow=${wf}, phase=${phase}, repeat=${rep}). Showing log:" >&2
    sed -n '1,200p' "${tmp}" >&2 || true
    exit 1
  fi
  parse_and_emit "${wf}" "${phase}" "${rep}" "${tmp}"
}

run_default() {
  for r in $(seq 1 "${REPEATS}"); do
    run_phase "default" "run" "${r}" -Xshare:off
  done
}

run_mdoreplay() {
  for r in $(seq 1 "${REPEATS}"); do
    rm -f "${MDO_FILE}" || true
    # cold dump
    run_phase "mdoreplay" "cold_dump" "${r}" -XX:+UnlockDiagnosticVMOptions -XX:+DumpMDOAtExit -XX:MDOReplayDumpFile="${MDO_FILE}" -Xshare:off
    # warm load
    run_phase "mdoreplay" "warm_load" "${r}" -XX:+UnlockDiagnosticVMOptions -XX:+LoadMDOAtStartup -XX:MDOReplayLoadFile="${MDO_FILE}" -Xshare:off
  done
}

run_leyden() {
  for r in $(seq 1 "${REPEATS}"); do
    rm -f "${AOT_CONF}" "${AOT_CACHE}" || true
    # record (measured)
    run_phase "leyden" "record" "${r}" -XX:AOTMode=record -XX:AOTConfiguration="${AOT_CONF}"
    # create (unmeasured)
    "${JAVA}" ${BASE_FLAGS} ${EXTRA_FLAGS} -XX:AOTMode=create -XX:AOTConfiguration="${AOT_CONF}" -XX:AOTCache="${AOT_CACHE}" >/dev/null 2>&1 || true
    # run (measured)
    run_phase "leyden" "run" "${r}" -XX:AOTCache="${AOT_CACHE}"
  done
}

case "${WORKFLOW}" in
  default)  run_default ;;
  mdoreplay) run_mdoreplay ;;
  leyden)   run_leyden ;;
  *) echo "Unknown --workflow: ${WORKFLOW} (expected default|mdoreplay|leyden)" >&2; exit 2 ;;
esac

echo "Wrote ${OUT}"


