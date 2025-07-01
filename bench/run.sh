#!/bin/bash

JAVAC=../jdk21u/build/macosx-aarch64-server-release/images/jdk-bundle/jdk-21.0.8.jdk/Contents/Home/bin/javac
JAVA=../jdk21u/build/macosx-aarch64-server-release/images/jdk-bundle/jdk-21.0.8.jdk/Contents/Home/bin/java

$JAVAC WordCountBenchmark.java

rm *.log *.csv

echo "Running benchmark to generate profile data..."
$JAVA \
	-XX:+UnlockDiagnosticVMOptions \
	-XX:CompileCommand=option,WordCountBenchmark::wordCount,DumpReplay \
	WordCountBenchmark 0 2000 warmup_results.csv

echo "Looking for generated replay files..."
ls -la replay_*.log | head -5

echo "Selecting largest replay file for injection..."
REPLAY_FILE=$(ls -S replay_*.log | head -1)
echo "Selected: $REPLAY_FILE"

if [ ! -f "$REPLAY_FILE" ]; then
    echo "ERROR: No replay file found! Profile generation may have failed."
    exit 1
fi

echo "Running benchmark with no profile injection..."
$JAVA \
	-XX:+UnlockDiagnosticVMOptions \
	-XX:+LogCompilation \
	WordCountBenchmark 0 2000 cold_results.csv

echo "Running benchmark with profile injection..."
$JAVA \
	-XX:+UnlockDiagnosticVMOptions \
	-XX:+InjectProfiles \
	-XX:+TraceProfileInjection \
	-XX:ReplayDataFile=$REPLAY_FILE \
	-XX:+LogCompilation \
	WordCountBenchmark 0 2000 warm_results.csv

echo "Results:"
echo "- Cold start: cold_results.csv"
echo "- Warm start: warm_results.csv"
echo "- Profile data used: $REPLAY_FILE"
