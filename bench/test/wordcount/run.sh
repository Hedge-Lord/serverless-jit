set -euo pipefail

JAVA=/Users/georgezhou/personal/research/serverless-jit/jdk25u/build/macosx-aarch64-server-release/images/jdk/bin/java

rm -f /tmp/wc_mdo.bin

echo "Running cold dump"
$JAVA -XX:+UnlockDiagnosticVMOptions -XX:+DumpMDOAtExit -XX:MDOReplayDumpFile=/tmp/wc_mdo.bin -Xlog:jit+compilation=debug WordCountBenchmark 0 1000 out/cold_dump.csv resource.txt > ./out/cold_dump.log 2>&1

echo "Running warm load"
$JAVA -XX:+UnlockDiagnosticVMOptions -XX:+LoadMDOAtStartup -XX:MDOReplayLoadFile=/tmp/wc_mdo.bin -Xlog:jit+compilation=debug WordCountBenchmark 0 1000 out/warm_load.csv resource.txt > ./out/warm_load.log 2>&1