package com.openfaas.function;

import java.util.HashMap;
import java.util.Map;
import com.openfaas.model.Request;

public class Runner {
    public static void main(String[] args) {
        double mutability = 0.5;
        int count = 500;
        if (args.length >= 1) {
            try { mutability = Double.parseDouble(args[0]); } catch (Exception ignored) {}
        }
        if (args.length >= 2) {
            try { count = Integer.parseInt(args[1]); } catch (Exception ignored) {}
        }

        Handler handler = new Handler();
        Map<String, String> headers = new HashMap<String, String>();
        String query = "mutability=" + mutability;
        for (int i = 0; i < count; i++) {
            long start = System.nanoTime();
            handler.Handle(new Request("", headers, query, ""));
            long finish = System.nanoTime();
            long micros = (finish - start) / 1000;
            System.out.println(micros);
        }
    }
}


