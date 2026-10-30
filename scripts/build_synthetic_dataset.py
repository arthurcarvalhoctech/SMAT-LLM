#!/usr/bin/env python3
"""Gera o dataset sintético pequeno para avaliar os 3 critérios de interferência do Laya.

Cada caso é uma classe Java pequena com as quatro versões (base, left, right, merge). As versões
left e right são a base com edições em regiões disjuntas, e o merge aplica as duas edições, como
um merge textual sem conflito.

O rótulo não é decidido à mão: o script compila e executa as quatro versões com um harness que
imprime os elementos de estado observados, e aplica os critérios da apostila (cap. 6.6 e 10.2):

  C1: existe x tal que B, L e R calculam valores pairwise diferentes;
  C2: existe x tal que L (ou R) calcula valor diferente de B e de M (mudança perdida);
  C3: existe x tal que B, L e R calculam o mesmo valor e M calcula outro (efeito novo no merge).

Saídas, em <saída>/:
  cases/<id>/source/<Classe>/{base,left,right,merge}.java
  input-smat-sintetico.json   (input do SMAT, só triagem Laya: os JARs são fictícios)
  gold-sintetico.json         (rótulo por execução, na ordem do input)
  README.md

Uso: python build_synthetic_dataset.py --output ../dataset-sintetico --container-prefix /app/dataset-sintetico
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile

BRANCHES = ("base", "left", "right", "merge")

CLEANER = r'''package demo;

public class NAME {
    public String text = "the the  dog # note";

    public void removeComments() {
        text = text.replaceAll("\\s*#.*$", "");
    }

    public void normalizeWhitespace() {
        text = text.replaceAll("\\s+", " ").trim();
    }

    public void removeDuplicateWords() {
        String[] tokens = text.split(" ", -1);
        String last = null;
        for (int i = 0; i < tokens.length; i++) {
            if (tokens[i].isEmpty()) {
                continue;
            }
            if (tokens[i].equals(last)) {
                tokens[i] = "";
            } else {
                last = tokens[i];
            }
        }
        text = String.join(" ", tokens);
    }

    public void cleanText() {
        removeComments();
    }
}
'''

CLEANER_HARNESS = r'''NAME t = new NAME();
t.cleanText();
p("hasDoubleSpace", t.text.contains("  "));
p("hasDuplicateWord", java.util.regex.Pattern.compile("\\b(\\w+) \\1\\b").matcher(t.text).find());'''

VALIDATOR = '''package demo;

public class NAME {
    public boolean valid(String name) {
        String s = name;
        int min = 2;
        boolean present = true;
        int n = s.length();
        return present && n >= min;
    }
}
'''

VALIDATOR_HARNESS = '''NAME t = new NAME();
p("valid(null)", t(() -> t.valid(null)));
p("valid(\\" a \\")", t(() -> t.valid(" a ")));'''

VALIDATOR_GUARD = ('        boolean present = true;\n',
                   '        if (s == null) {\n            return false;\n        }\n        boolean present = true;\n')


def ins_after(anchor, new):
    return (anchor, anchor + new)


CASES = [
    # ------------------------------------------------------------------ sem interferência
    dict(
        id="n01_mapa_chaves_distintas", cls="TableTypes", method="init()", intent=[],
        base='''package demo;

import java.util.HashMap;
import java.util.Map;

public class TableTypes {
    public Map<String, String> types = new HashMap<>();

    public void init() {
        types.put("a", "A");
        types.put("b", "B");
        types.put("c", "C");
        types.put("d", "D");
    }
}
''',
        left=[('        types.put("a", "A");\n        types.put("b", "B");\n', '')],
        right=[ins_after('        types.put("d", "D");\n', '        types.put("e", "E");\n')],
        harness='''TableTypes t = new TableTypes();
t.init();
for (String k : new String[] {"a", "b", "c", "d", "e"}) {
    p("get(" + k + ")", t.types.get(k));
}''',
        ls="Left removes the entries for keys a and b from the map",
        rs="Right adds the entry for key e to the map",
    ),
    dict(
        id="n02_texto_ordem_independente", cls="Text", method="cleanText()", intent=[],
        base=CLEANER.replace("NAME", "Text"),
        left=[('        removeComments();\n    }\n}\n',
               '        removeComments();\n        normalizeWhitespace();\n    }\n}\n')],
        right=[('    public void cleanText() {\n        removeComments();',
                '    public void cleanText() {\n        removeDuplicateWords();\n        removeComments();')],
        harness=CLEANER_HARNESS.replace("NAME", "Text"),
        ls="Left adds a call to normalizeWhitespace after removeComments",
        rs="Right adds a call to removeDuplicateWords before removeComments",
    ),
    dict(
        id="n03_mesma_mudanca_dos_dois_lados", cls="TaxCalculator", method="apply(int)", intent=[],
        base='''package demo;

public class TaxCalculator {
    public int rate = 10;
    public int tax;
    public int net;

    public void apply(int gross) {
        tax = gross * rate / 100;
        net = gross - tax;
    }
}
''',
        left=[('    public int rate = 10;', '    public int rate = 20;')],
        right=[('    public int rate = 10;', '    public int rate = 20;')],
        harness='''TaxCalculator t = new TaxCalculator();
t.apply(200);
p("tax", t.tax);
p("net", t.net);''',
        ls="Left changes the default tax rate from 10 to 20",
        rs="Right changes the default tax rate from 10 to 20",
    ),
    dict(
        id="n04_campos_independentes", cls="Cart", method="checkout(int,int)", intent=[],
        base='''package demo;

public class Cart {
    public int subtotal;
    public int calls;
    public int shipping;

    public void checkout(int items, int price) {
        subtotal = items * price;
        calls++;
        shipping = 10;
    }
}
''',
        left=[('        subtotal = items * price;', '        subtotal = items * price * 9 / 10;')],
        right=[('        shipping = 10;', '        shipping = subtotal > 100 ? 0 : 10;')],
        harness='''Cart t = new Cart();
t.checkout(3, 40);
p("subtotal", t.subtotal);
p("shipping", t.shipping);''',
        ls="Left applies a ten percent discount to the subtotal",
        rs="Right makes the shipping free when the subtotal is above one hundred",
    ),
    dict(
        id="n05_mudanca_so_de_um_lado", cls="Counter", method="increment()", intent=[],
        base='''package demo;

public class Counter {
    public int value;
    public int steps;

    public void increment() {
        value = value + 1;
        steps = steps + 1;
    }
}
''',
        left=[('        value = value + 1;', '        value = value + 2;')],
        right=[('    }\n}\n', '    }\n\n    public void reset() {\n        value = 0;\n    }\n}\n')],
        harness='''Counter t = new Counter();
t.increment();
p("value", t.value);
p("steps", t.steps);''',
        ls="Left changes the increment step of value from one to two",
        rs="Right adds a reset method that is not called by increment",
    ),
    dict(
        id="n06_refatoracao_e_comportamento", cls="Limiter", method="allowed(int)", intent=[],
        base='''package demo;

public class Limiter {
    public int allowed(int requests) {
        int limit = 10;
        if (requests > limit) {
            return limit;
        }
        return requests;
    }
}
''',
        left=[('        int limit = 10;', '        int limit = 5 + 5;')],
        right=[('        return requests;\n    }', '        return requests > 0 ? requests : 0;\n    }')],
        harness='''Limiter t = new Limiter();
p("allowed(15)", t.allowed(15));
p("allowed(-3)", t.allowed(-3));''',
        ls="Left rewrites the limit constant as a sum without changing its value",
        rs="Right returns zero instead of a negative number of requests",
    ),
    dict(
        id="n07_validacao_em_entradas_distintas", cls="Validator", method="valid(java.lang.String)", intent=[],
        base=VALIDATOR.replace("NAME", "Validator"),
        left=[VALIDATOR_GUARD],
        right=[('        String s = name;', '        String s = name == null ? null : name.trim();')],
        harness=VALIDATOR_HARNESS.replace("NAME", "Validator"),
        ls="Left adds a guard that returns false for a null name",
        rs="Right trims the name before measuring its length, keeping null as null",
    ),
    dict(
        id="n08_casos_novos_no_switch", cls="OrderLabel", method="label(java.lang.String)", intent=[],
        base='''package demo;

public class OrderLabel {
    public String label(String status) {
        switch (status) {
            case "NEW":
                return "Novo";
            case "PAID":
                return "Pago";
            default:
                return "Desconhecido";
        }
    }
}
''',
        left=[ins_after('                return "Novo";\n',
                        '            case "CANCELLED":\n                return "Cancelado";\n')],
        right=[('            default:\n',
                '            case "SHIPPED":\n                return "Enviado";\n            default:\n')],
        harness='''OrderLabel t = new OrderLabel();
for (String s : new String[] {"NEW", "PAID", "CANCELLED", "SHIPPED"}) {
    p("label(" + s + ")", t.label(s));
}''',
        ls="Left adds a case for the CANCELLED status",
        rs="Right adds a case for the SHIPPED status",
    ),
    # ------------------------------------------------------------------ C2 (mudança perdida)
    dict(
        id="c2a_lista_acumulada", cls="Keywords", method="init()", intent=["C2"],
        base='''package demo;

import java.util.ArrayList;
import java.util.List;

public class Keywords {
    public List<String> words = new ArrayList<>();

    public void init() {
        words.add("if");
        words.add("else");
        words.add("switch");
    }
}
''',
        left=[ins_after('        words.add("if");\n', '        words.add("while");\n')],
        right=[ins_after('        words.add("switch");\n', '        words.add("for");\n')],
        harness='''Keywords t = new Keywords();
t.init();
p("size", t.words.size());
p("contains(while)", t.words.contains("while"));
p("contains(for)", t.words.contains("for"));''',
        ls="Left adds a new value into a list",
        rs="Right adds a different new value into the same list",
    ),
    dict(
        id="c2b_taxa_e_arredondamento", cls="Invoice", method="compute()", intent=["C2"],
        base='''package demo;

public class Invoice {
    public int amount = 40;
    public int total;

    private int round(int v) {
        return v;
    }

    public void compute() {
        total = amount;
        total = round(total);
    }
}
''',
        left=[('        total = amount;', '        total = amount + 5;')],
        right=[('        return v;', '        return (v + 9) / 10 * 10;')],
        harness='''Invoice t = new Invoice();
t.compute();
p("total", t.total);''',
        ls="Left adds a flat fee of five to the total",
        rs="Right rounds the total up to a multiple of ten",
    ),
    dict(
        id="c2c_texto_espacos_duplicados", cls="TextCleaner", method="cleanText()", intent=["C2"],
        base=CLEANER.replace("NAME", "TextCleaner"),
        left=[('    public void cleanText() {\n        removeComments();',
               '    public void cleanText() {\n        normalizeWhitespace();\n        removeComments();')],
        right=[('        removeComments();\n    }\n}\n',
                '        removeComments();\n        removeDuplicateWords();\n    }\n}\n')],
        harness=CLEANER_HARNESS.replace("NAME", "TextCleaner"),
        ls="Left adds a call to normalizeWhitespace before removeComments",
        rs="Right adds a call to removeDuplicateWords after removeComments",
    ),
    dict(
        id="c2d_guarda_nula_antes_do_trim", cls="NameCheck", method="valid(java.lang.String)", intent=["C2"],
        base=VALIDATOR.replace("NAME", "NameCheck"),
        left=[VALIDATOR_GUARD],
        right=[('        String s = name;', '        String s = name.trim();')],
        harness=VALIDATOR_HARNESS.replace("NAME", "NameCheck"),
        ls="Left adds a guard that returns false for a null name",
        rs="Right trims the name before measuring its length",
    ),
    # ------------------------------------------------------------------ C3 (efeito novo no merge)
    dict(
        id="c3a_xyz_apostila", cls="Flags", method="run()", intent=["C3"],
        base='''package demo;

public class Flags {
    public int x = 0;
    public int z;
    public int y = 0;

    public void run() {
        if (x + y > 1) {
            z = 1;
        } else {
            z = 0;
        }
    }
}
''',
        left=[('    public int x = 0;', '    public int x = 1;')],
        right=[('    public int y = 0;', '    public int y = 1;')],
        harness='''Flags t = new Flags();
t.run();
p("x", t.x);
p("y", t.y);
p("z", t.z);''',
        ls="Left changes the initial value of x from zero to one",
        rs="Right changes the initial value of y from zero to one",
    ),
    dict(
        id="c3b_peso_total", cls="Parcel", method="check()", intent=["C3"],
        base='''package demo;

public class Parcel {
    public int a = 40;
    public int count = 1;
    public int b = 40;
    public boolean big;

    public void check() {
        big = a + b > 100;
    }
}
''',
        left=[('    public int a = 40;', '    public int a = 60;')],
        right=[('    public int b = 40;', '    public int b = 60;')],
        harness='''Parcel t = new Parcel();
t.check();
p("a", t.a);
p("b", t.b);
p("big", t.big);''',
        ls="Left raises the weight of the first item from forty to sixty",
        rs="Right raises the weight of the second item from forty to sixty",
    ),
    dict(
        id="c3c_capacidade", cls="Storage", method="check()", intent=["C3"],
        base='''package demo;

public class Storage {
    public int used = 4;
    public int capacity = 9;
    public int incoming = 0;
    public boolean hasRoom;

    public void check() {
        hasRoom = used + incoming <= capacity;
    }
}
''',
        left=[('    public int used = 4;', '    public int used = 7;')],
        right=[('    public int incoming = 0;', '    public int incoming = 3;')],
        harness='''Storage t = new Storage();
t.check();
p("used", t.used);
p("incoming", t.incoming);
p("hasRoom", t.hasRoom);''',
        ls="Left increases the used space from four to seven",
        rs="Right sets an incoming load of three",
    ),
    # ------------------------------------------------------------------ C1 + C2 (valores todos diferentes)
    dict(
        id="d1_taxa_sobrescrita", cls="PriceTable", method="quote(int)", intent=["C1", "C2"],
        base='''package demo;

public class PriceTable {
    public int total;

    public void quote(int qty) {
        int rate = 5;
        int fee = 1;
        total = qty * rate + fee;
    }
}
''',
        left=[('        int rate = 5;', '        int rate = 10;')],
        right=[ins_after('        int fee = 1;\n', '        rate = 20;\n')],
        harness='''PriceTable t = new PriceTable();
t.quote(2);
p("total", t.total);''',
        ls="Left changes the initial rate from five to ten",
        rs="Right assigns a new rate of twenty after the fee is set",
    ),
    dict(
        id="d2_regra_de_preco", cls="PriceRule", method="price(int)", intent=["C1", "C2"],
        base='''package demo;

public class PriceRule {
    public int price(int base) {
        int p = base;
        boolean vip = base > 50;
        if (vip) {
            p = p - 5;
        }
        return p;
    }
}
''',
        left=[ins_after('        int p = base;\n', '        p = p + 10;\n')],
        right=[('        }\n        return p;', '        }\n        p = p * 2;\n        return p;')],
        harness='''PriceRule t = new PriceRule();
p("price(100)", t.price(100));''',
        ls="Left adds a surcharge of ten to the price before the vip discount",
        rs="Right doubles the price after the vip discount",
    ),
    dict(
        id="d3_titulo_formatado", cls="TitleFormatter", method="title(java.lang.String)", intent=["C1", "C2"],
        base='''package demo;

public class TitleFormatter {
    public String title(String name) {
        String t = name;
        int n = t.length();
        return t;
    }
}
''',
        left=[ins_after('        String t = name;\n', '        t = t.toUpperCase();\n')],
        right=[ins_after('        int n = t.length();\n', '        t = t + " (draft)";\n')],
        harness='''TitleFormatter t = new TitleFormatter();
p("title(ana)", t.title("ana"));''',
        ls="Left converts the title to upper case",
        rs="Right appends a draft marker to the title",
    ),
    # ------------------------------------------------------------------ vários critérios
    dict(
        id="e1_taxa_e_capacidade", cls="Checkout", method="compute()", intent=["C2", "C3"],
        base='''package demo;

public class Checkout {
    public int amount = 40;
    public int used = 4;
    public int cap = 9;
    public int incoming = 0;
    public int total;
    public boolean hasRoom;

    private int round(int v) {
        return v;
    }

    public void compute() {
        total = amount;
        hasRoom = used + incoming <= cap;
        total = round(total);
    }
}
''',
        left=[('        total = amount;', '        total = amount + 5;'),
              ('    public int used = 4;', '    public int used = 7;')],
        right=[('        return v;', '        return (v + 9) / 10 * 10;'),
               ('    public int incoming = 0;', '    public int incoming = 3;')],
        harness='''Checkout t = new Checkout();
t.compute();
p("total", t.total);
p("hasRoom", t.hasRoom);''',
        ls="Left adds a flat fee of five to the total and raises the used space to seven",
        rs="Right rounds the total up to a multiple of ten and sets an incoming load of three",
    ),
    dict(
        id="e2_custo_e_sobrepeso", cls="Shipment", method="plan(int)", intent=["C1", "C2", "C3"],
        base='''package demo;

public class Shipment {
    public int weight = 40;
    public int tag = 0;
    public int extra = 40;
    public int cost;
    public boolean oversize;

    public void plan(int base) {
        int p = base;
        boolean vip = base > 50;
        if (vip) {
            p = p - 5;
        }
        cost = p;
        oversize = weight + extra > 100;
    }
}
''',
        left=[('    public int weight = 40;', '    public int weight = 60;'),
              ins_after('        int p = base;\n', '        p = p + 10;\n')],
        right=[('    public int extra = 40;', '    public int extra = 60;'),
               ('        }\n        cost = p;', '        }\n        p = p * 2;\n        cost = p;')],
        harness='''Shipment t = new Shipment();
t.plan(100);
p("cost", t.cost);
p("oversize", t.oversize);''',
        ls="Left adds a surcharge of ten to the cost and raises the first weight to sixty",
        rs="Right doubles the cost after the vip discount and raises the second weight to sixty",
    ),
]

HARNESS = '''import demo.*;

public class Harness {
    static void p(String k, Object v) {
        System.out.println(k + "=" + v);
    }

    static Object t(java.util.concurrent.Callable<Object> c) {
        try {
            return c.call();
        } catch (Throwable e) {
            return "EXC";
        }
    }

    public static void main(String[] args) throws Exception {
%s
    }
}
'''


def apply_edits(text, edits):
    for old, new in edits:
        assert text.count(old) == 1, "âncora ausente ou repetida: %r" % old
        text = text.replace(old, new)
    return text


def build_versions(case):
    base = case["base"]
    left = apply_edits(base, case["left"])
    right = apply_edits(base, case["right"])
    merge_edits = list(case["left"]) + [e for e in case["right"] if e not in case["left"]]
    merge = apply_edits(base, merge_edits)
    return {"base": base, "left": left, "right": right, "merge": merge}


def observe(case, source, workdir):
    os.makedirs(os.path.join(workdir, "demo"), exist_ok=True)
    with open(os.path.join(workdir, "demo", case["cls"] + ".java"), "w") as f:
        f.write(source)
    body = "\n".join("        " + line for line in case["harness"].splitlines())
    with open(os.path.join(workdir, "Harness.java"), "w") as f:
        f.write(HARNESS % body)
    out = os.path.join(workdir, "out")
    subprocess.run(["javac", "-d", out, os.path.join(workdir, "demo", case["cls"] + ".java"),
                    os.path.join(workdir, "Harness.java")], check=True, capture_output=True, text=True)
    run = subprocess.run(["java", "-cp", out, "Harness"], check=True, capture_output=True, text=True)
    values = {}
    for line in run.stdout.splitlines():
        key, _, value = line.partition("=")
        values[key] = value
    return values


def criteria(values):
    triggered = {"C1": [], "C2": [], "C3": []}
    for key in values["base"]:
        b, l, r, m = (values[branch][key] for branch in BRANCHES)
        if len({b, l, r}) == 3:
            triggered["C1"].append(key)
        if (l != b and l != m) or (r != b and r != m):
            triggered["C2"].append(key)
        if b == l == r and m != b:
            triggered["C3"].append(key)
    return {name: elements for name, elements in triggered.items() if elements}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", required=True)
    ap.add_argument("--container-prefix", default="/app/dataset-sintetico",
                    help="prefixo dos JARs fictícios no input (caminho dentro do container)")
    args = ap.parse_args()

    cases_dir = os.path.join(args.output, "cases")
    if os.path.isdir(cases_dir):
        shutil.rmtree(cases_dir)

    scenarios, gold = [], []
    for case in CASES:
        versions = build_versions(case)
        root = os.path.join(cases_dir, case["id"])
        for branch, source in versions.items():
            path = os.path.join(root, "source", case["cls"], branch + ".java")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(source)

        values = {}
        for branch, source in versions.items():
            with tempfile.TemporaryDirectory() as tmp:
                values[branch] = observe(case, source, tmp)
        found = criteria(values)
        intended = sorted(case["intent"])
        assert sorted(found) == intended, "%s: previsto %s, executado %s" % (case["id"], intended, found)

        class_name = "demo." + case["cls"]
        prefix = "%s/cases/%s/original" % (args.container_prefix.rstrip("/"), case["id"])
        scenarios.append({
            "projectName": "sintetico",
            "runAnalysis": True,
            "scenarioCommits": {"base": "", "left": "", "right": "", "merge": case["id"]},
            "targets": {class_name: [{
                "method": case["method"],
                "leftChangesSummary": case["ls"],
                "rightChangesSummary": case["rs"],
            }]},
            "scenarioJars": {b: "%s/%s/%s.jar" % (prefix, b, b) for b in BRANCHES},
            "jarType": "original",
        })
        interference = bool(found)
        gold.append({
            "project": "sintetico", "commit": case["id"], "class": class_name, "method": case["method"],
            "label": "Yes" if interference else "No", "interference": interference,
            "criteria": sorted(found), "elements": found, "observed": values,
        })

    with open(os.path.join(args.output, "input-smat-sintetico.json"), "w") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(args.output, "gold-sintetico.json"), "w") as f:
        json.dump(gold, f, indent=2, ensure_ascii=False)
        f.write("\n")

    by_set = {}
    for item in gold:
        by_set.setdefault("+".join(item["criteria"]) or "nenhum", []).append(item["commit"])
    print("casos:", len(gold), "| com interferência:", sum(g["interference"] for g in gold))
    for name, ids in sorted(by_set.items()):
        print("  %-12s %d  %s" % (name, len(ids), ", ".join(ids)))


if __name__ == "__main__":
    main()
