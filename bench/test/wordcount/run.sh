JAVA=/Users/georgezhou/personal/research/serverless-jit/jdk25u/build/macosx-aarch64-server-release/jdk/bin/java

rm /tmp/mdo.log

echo "Running MDO Dump"
$JAVA  -XX:+UnlockDiagnosticVMOptions -XX:+DumpMDOAtExit -XX:MDOReplayDumpFile=/tmp/mdo.log -Xlog:compilation=info WordCountBenchmark.java 0 1000 cold.csv resource.txt 

echo "Running Baseline"
$JAVA   WordCountBenchmark.java 0 1000 cold.csv resource.txt 
echo "Running Warm"
$JAVA -XX:+UnlockDiagnosticVMOptions -XX:+LoadMDOAtStartup -XX:MDOReplayLoadFile=/tmp/mdo.log -Xlog:compilation=info WordCountBenchmark.java 0 1000 warm.csv resource.txt
