import java.io.BufferedWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class WordCountBenchmark {

    /* Same constants as the FaaS handler */
    private static final int WORD_MIN       = 2_500;
    private static final int WORD_MAX       = 50_000;
    private static final double SCALE       = (WORD_MAX / 20.0);

    private static final Random RNG = new Random(42);

    private final List<String> data;

    public WordCountBenchmark(String resourcePath) throws IOException {
        data = Files.readAllLines(Paths.get(resourcePath), StandardCharsets.UTF_8);
    }

    /* --- core logic ported verbatim -------------------------------------- */

    private static int wordCount(String s) {
        if (s == null || s.isEmpty()) return 0;
        int wc = 0;
        boolean inWord = false;
        int end = s.length() - 1;
        char[] ch = s.toCharArray();
        for (int i = 0; i < ch.length; i++) {
            if (Character.isLetter(ch[i]) && i != end) {
                inWord = true;
            } else if (!Character.isLetter(ch[i]) && inWord) {
                wc++; inWord = false;
            } else if (Character.isLetter(ch[i]) && i == end) {
                wc++;
            }
        }
        return wc;
    }

    private static double generateWorkload(double mutability) {
        double g = RNG.nextGaussian() * (Math.sqrt(mutability) * SCALE)
                   + (WORD_MIN + WORD_MAX) / 2.0;
        return Math.max(WORD_MIN, Math.min(WORD_MAX, g));
    }

    /** returns microseconds */
    private long benchmark(double mutability) {
        int lines = (int) generateWorkload(mutability);
        String slice = String.join("\n", data.subList(0, Math.min(lines, data.size())));
        long start = System.nanoTime();
        wordCount(slice);
        long end = System.nanoTime();
        return (end - start) / 1_000;  // µs
    }

    /* --------------------------------------------------------------------- */

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.err.println("Usage: java WordCountBenchmark <mutability> <invocations> <out.csv> [resource.txt]");
            System.exit(1);
        }

        double mutability   = Double.parseDouble(args[0]);
        int invocations     = Integer.parseInt(args[1]);
        String outCsv       = args[2];
        String resourcePath = (args.length >= 4) ? args[3] : "resource.txt";

        WordCountBenchmark bench = new WordCountBenchmark(resourcePath);

        List<Long> samples = new ArrayList<>(invocations);
        try (Writer w = Files.newBufferedWriter(Paths.get(outCsv), StandardCharsets.UTF_8);
             PrintWriter pw = new PrintWriter(new BufferedWriter(w))) {

            pw.println("invocation,time_us");

            for (int i = 1; i <= invocations; i++) {
                long t = bench.benchmark(mutability);
                samples.add(t);
                pw.printf("%d,%d%n", i, t);
            }
        }

        /* Optional quick summary */
        samples.sort(Long::compare);
        long sum = samples.stream().mapToLong(Long::longValue).sum();
        double avg = sum / (double) invocations;
        long p95 = samples.get((int) Math.ceil(0.95 * invocations) - 1);

        System.out.printf("Ran %,d invocations%n", invocations);
        System.out.printf("Average: %.1f µs | p95: %d µs%n", avg, p95);
    }
}
 
