#!/usr/bin/env bash
set -euo pipefail

JAVAC=../jdk21u/build/macosx-aarch64-server-release/images/jdk-bundle/jdk-21.0.8.jdk/Contents/Home/bin/javac
JAVA=../jdk21u/build/macosx-aarch64-server-release/images/jdk-bundle/jdk-21.0.8.jdk/Contents/Home/bin/java

$JAVAC WordCountBenchmark.java
rm -f *.log *.csv

echo "Running benchmark to generate profile data..."
$JAVA \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:CompileCommand=option,WordCountBenchmark::wordCount,DumpReplay \
  WordCountBenchmark 0 2000 warmup_results.csv

echo "Selecting largest replay file..."
ORIG_REPLAY=$(ls -S replay_*.log | head -n 1)   # largest
echo "Original replay: $ORIG_REPLAY"

if [[ ! -f "$ORIG_REPLAY" ]]; then
  echo "ERROR: replay dump not found"; exit 1
fi

# ----------------------------------------------------------------------
# Strip all ‘compile …’ lines and save to a new file
# ----------------------------------------------------------------------
STRIPPED_REPLAY=${ORIG_REPLAY/.log/_nocompile.log}
sed -e '/^[[:space:]]*compile[[:space:]]/d' "$ORIG_REPLAY" > "$STRIPPED_REPLAY"
echo "Stripped replay saved as: $STRIPPED_REPLAY"

echo "Running benchmark with no profile injection..."
$JAVA \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+LogCompilation \
  WordCountBenchmark 0 2000 cold_results.csv

echo "Running benchmark with profile injection (no forced compile)..."
$JAVA \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+InjectProfiles \
  -XX:+TraceProfileInjection \
  -XX:ReplayDataFile="$STRIPPED_REPLAY" \
  -XX:+LogCompilation \
  WordCountBenchmark 0 2000 warm_results.csv

echo "Done."
echo "- Cold results : cold_results.csv"
echo "- Warm results : warm_results.csv"
echo "- Profiles used: $STRIPPED_REPLAY"
