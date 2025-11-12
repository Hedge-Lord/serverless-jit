package com.openfaas.function;

import java.util.HashMap;
import java.util.Map;
import com.openfaas.model.Request;

public class Main {
    public static void main(String[] args) {
        double mutability = 1.0;
        String env = System.getenv("MUTABILITY");
        if (env != null) {
            try { mutability = Double.parseDouble(env); } catch (Exception ignored) {}
        }
        if (args.length > 0) {
            try { mutability = Double.parseDouble(args[0]); } catch (Exception ignored) {}
        }

        Map<String, String> headers = new HashMap<String, String>();
        String query = "mutability=" + mutability;

        Handler handler = new Handler();
        com.openfaas.model.IResponse res = handler.Handle(new Request("", headers, query, ""));
        System.out.println(res.getBody());
    }
}


