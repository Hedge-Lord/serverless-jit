JAVA=/Users/georgezhou/personal/research/serverless-jit/jdk25u/build/macosx-aarch64-server-release/jdk/bin/java
JAR=${JAR:-/Users/georgezhou/personal/research/serverless-jit/renaissance-gpl-0.16.0.jar}

BENCH=${1:-akka-uct}
MEAS_REPS=${2:-10}

MDO=/tmp/${BENCH}.mdo

rm -f "$MDO"
"$JAVA" -Xms2g -Xmx2g \
  -XX:+UnlockDiagnosticVMOptions -XX:+DumpMDOAtExit -XX:MDOReplayDumpFile="$MDO" \
  -Xlog:compilation=info \
  -jar "$JAR" "$BENCH" -r "$MEAS_REPS" --csv "/tmp/${BENCH}-baseline.csv"


"$JAVA" -Xms2g -Xmx2g \
  -XX:+UnlockDiagnosticVMOptions -XX:+LoadMDOAtStartup -XX:MDOReplayLoadFile="$MDO" \
  -Xlog:compilation=info \
  -jar "$JAR" "$BENCH" -r "$MEAS_REPS" --csv "/tmp/${BENCH}-replay.csv"
