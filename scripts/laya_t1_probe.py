#!/usr/bin/env python3
"""Testa a Laya com a entrada no formato usado no treino (smat_dataset), fora do fluxo do SMAT.

O treino de triagem usou um estado em texto (corpo de B, L e R em uma linha, resumos, atributos e
construtores, em português) e a pergunta T1 ("As mudanças de Left e Right podem interagir neste
método?"). O fluxo do SMAT envia um dicionário com as quatro versões e três perguntas em inglês.
Este script monta o estado no formato do treino e compara variantes de entrada:

  v1  estado do treino (B, L, R) + pergunta T1
  v2  v1 com o corpo do merge (M) acrescentado + pergunta T1
  v3  v1 + as três perguntas de critério do SMAT (inglês)
  v1pt, v3pt  como v1 e v3, com resumos em português (só nos casos sintéticos)

Os valores iniciais literais dos campos entram no início do corpo como atribuições, para que
mudanças em campos fiquem visíveis (o treino não tem outro lugar para elas).

Roda dentro do container (precisa de `laya` e do pacote `nimrod`):
  PYTHONPATH=/app/SMAT python3 scripts/laya_t1_probe.py --out <json>
"""
import argparse
import json
import os
import re
import sys

BRANCHES = ("base", "left", "right", "merge")
T1 = {"T1": {"type": "noul", "instructions": "As mudanças de Left e Right podem interagir neste método?"}}


PT = {
    "n01_mapa_chaves_distintas": ("remove as chaves a e b do mapa", "adiciona a chave e ao mapa"),
    "n02_texto_ordem_independente": ("normaliza espaços depois de remover comentários", "remove palavras repetidas antes de remover comentários"),
    "n03_mesma_mudanca_dos_dois_lados": ("muda a alíquota padrão de 10 para 20", "muda a alíquota padrão de 10 para 20"),
    "n04_campos_independentes": ("aplica desconto de dez por cento ao subtotal", "frete grátis quando o subtotal passa de cem"),
    "n05_mudanca_so_de_um_lado": ("muda o passo do incremento de um para dois", "adiciona um método reset que não é chamado"),
    "n06_refatoracao_e_comportamento": ("reescreve a constante do limite como soma sem mudar o valor", "retorna zero em vez de número negativo de requisições"),
    "n07_validacao_em_entradas_distintas": ("adiciona guarda que retorna falso para nome nulo", "remove espaços do nome antes de medir, mantendo nulo"),
    "n08_casos_novos_no_switch": ("adiciona caso para o status CANCELLED", "adiciona caso para o status SHIPPED"),
    "c2a_lista_acumulada": ("adiciona um novo valor à lista", "adiciona outro valor à mesma lista"),
    "c2b_taxa_e_arredondamento": ("soma taxa fixa de cinco ao total", "arredonda o total para cima em múltiplos de dez"),
    "c2c_texto_espacos_duplicados": ("normaliza espaços duplicados antes de remover comentários", "remove palavras repetidas consecutivas depois de remover comentários"),
    "c2d_guarda_nula_antes_do_trim": ("adiciona guarda que retorna falso para nome nulo", "remove espaços do nome antes de medir o tamanho"),
    "c3a_xyz_apostila": ("muda o valor inicial de x de zero para um", "muda o valor inicial de y de zero para um"),
    "c3b_peso_total": ("aumenta o peso do primeiro item de quarenta para sessenta", "aumenta o peso do segundo item de quarenta para sessenta"),
    "c3c_capacidade": ("aumenta o espaço usado de quatro para sete", "define uma carga de entrada de três"),
    "d1_taxa_sobrescrita": ("muda a taxa inicial de cinco para dez", "atribui nova taxa de vinte depois de definir a tarifa"),
    "d2_regra_de_preco": ("soma acréscimo de dez ao preço antes do desconto vip", "dobra o preço depois do desconto vip"),
    "d3_titulo_formatado": ("converte o título para maiúsculas", "acrescenta marca de rascunho ao título"),
    "e1_taxa_e_capacidade": ("soma taxa fixa de cinco ao total e aumenta o espaço usado para sete", "arredonda o total para múltiplos de dez e define carga de entrada de três"),
    "e2_custo_e_sobrepeso": ("soma acréscimo de dez ao custo e aumenta o primeiro peso para sessenta", "dobra o custo depois do desconto vip e aumenta o segundo peso para sessenta"),
}


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def balanced(src, start, open_ch, close_ch):
    depth, i = 1, start
    while i < len(src) and depth:
        depth += (src[i] == open_ch) - (src[i] == close_ch)
        i += 1
    return src[start:i - 1]


def method_body(src, signature):
    """Corpo do primeiro método com o nome dado; se for um campo, o inicializador."""
    name = signature.split("(")[0].split(".")[-1]
    src = strip_comments(src)
    m = re.search(r"\b" + re.escape(name) + r"\s*\([^;{]*\)\s*(?:throws [\w., ]+)?\s*\{", src)
    if m:
        return squash(balanced(src, m.end(), "{", "}"))
    m = re.search(r"\b" + re.escape(name) + r"\b\s*(?:\[\s*\])?\s*=\s*", src)
    if m:
        i, depth = m.end(), 0
        while i < len(src) and not (src[i] == ";" and depth == 0):
            depth += (src[i] in "{(") - (src[i] in "})")
            i += 1
        return squash(src[m.end():i])
    return ""


FIELD = re.compile(
    r"^ {4}(?:public |private |protected )?(?:static )?(?:final )?"
    r"([\w<>\[\]?.]+(?:, ?[\w<>\[\]?.]+)*) +(\w+)(?: *= *([^;]+))?;", re.M)
LITERAL = re.compile(r'^(-?\d+(?:\.\d+)?|true|false|"[^"]*")$')


def used_fields(src, body):
    """Campos da classe citados no corpo: (nome, tipo, valor inicial literal ou None)."""
    out = []
    for type_, name, init in FIELD.findall(strip_comments(src)):
        if type_ in ("return", "new", "throw", "else"):
            continue
        if re.search(r"\b" + re.escape(name) + r"\b", body):
            init = init.strip() if init and LITERAL.match(init.strip()) else None
            out.append((name, type_.replace(", ", ","), init))
    return out


def with_field_inits(body, fields):
    """Valores iniciais dos campos como atribuições no início do corpo (como no treino: 'a = 0; b = 1;')."""
    inits = " ".join("%s = %s;" % (n, v) for n, _, v in fields if v is not None)
    return (inits + " " + body).strip()


def build_state(label, bodies, left_summary, right_summary, fields, with_merge):
    lines = [
        "Método: " + label,
        "Corpo da base (B):", bodies["base"],
        "Corpo de Left (L):", bodies["left"],
        "Corpo de Right (R):", bodies["right"],
    ]
    if with_merge:
        lines += ["Corpo do merge (M):", bodies["merge"]]
    lines += [
        "Resumo de Left: " + (left_summary or "não informado"),
        "Resumo de Right: " + (right_summary or "não informado"),
        "Atributos: " + (", ".join("%s: %s" % (n, t) for n, t, _ in fields) if fields else "nenhum"),
        "Construtores: padrão",
    ]
    return "\n".join(lines)


def load_cases(synthetic_input, synthetic_gold, merge_input, merge_gold, dataset_root):
    from nimrod.source_code import find_source_code_paths

    cases = []
    gold = json.load(open(synthetic_gold))
    for scen, g in zip(json.load(open(synthetic_input)), gold):
        cls = next(iter(scen["targets"]))
        item = scen["targets"][cls][0]
        short = cls.split(".")[-1]
        root = os.path.dirname(os.path.dirname(scen["scenarioJars"]["base"]))
        root = os.path.dirname(root)  # .../cases/<id>
        paths = {b: os.path.join(root, "source", short, b + ".java") for b in BRANCHES}
        cases.append(dict(set="sintetico", id=g["commit"], cls=cls, method=item["method"], paths=paths,
                          ls=item["leftChangesSummary"], rs=item["rightChangesSummary"],
                          label="Yes" if g["interference"] else "No", criteria=g["criteria"]))

    glabel = {(m["commit"], m["class"], m["method"]): m["label"] for m in json.load(open(merge_gold))["methods"]}
    for scen in json.load(open(merge_input)):
        jars = {b: v.replace("${PATH_DATASET}", dataset_root) for b, v in scen["scenarioJars"].items()}
        commit = re.search(r"/([0-9a-f]{40})/", jars["merge"]).group(1)
        for cls, items in scen["targets"].items():
            for item in items:
                paths = find_source_code_paths(jars["left"] or jars["right"], scen["jarType"], cls)
                if not all(paths.get(b) for b in BRANCHES):
                    print("sem source:", cls, file=sys.stderr)
                    continue
                cases.append(dict(set="mergedataset", id=commit[:7] + "/" + cls.split(".")[-1] + "." + item["method"],
                                  cls=cls, method=item["method"], paths=paths,
                                  ls=item.get("leftChangesSummary", ""), rs=item.get("rightChangesSummary", ""),
                                  label=glabel.get((commit, cls, item["method"]), "-"), criteria=[]))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--ft", default="/laya_smat/laya_finetuned_smat_multilingual")
    ap.add_argument("--dataset-root", default=os.environ.get("PATH_DATASET", ""))
    args = ap.parse_args()

    from laya import Router, load
    from nimrod.laya_interference.criteria import build_questions, CRITERIA

    crit_q = {k: v for k, v in build_questions().items() if k in {c.id for c in CRITERIA}}
    cases = load_cases("/app/dataset-sintetico/input-smat-sintetico.json", "/app/dataset-sintetico/gold-sintetico.json",
                       "/app/input-smat-mergedataset.json", "/app/template/gold-13-methods.json", args.dataset_root)
    models = {"ajustado": load(args.ft), "base": Router()}

    def ask(name, state, questions):
        if name == "base":
            res = models[name].predict(state, questions, model="multilingual", max_len=args.max_len)
        else:
            res = models[name].predict(state, questions, max_len=args.max_len)
        return {q: round(float(a["noul"]), 4) for q, a in res["answers"].items() if "noul" in a}

    results = []
    for case in cases:
        src = {b: open(case["paths"][b], errors="replace").read() for b in BRANCHES}
        raw = {b: method_body(src[b], case["method"]) for b in BRANCHES}
        flds = {b: used_fields(src[b], raw[b]) for b in BRANCHES}
        bodies = {b: with_field_inits(raw[b], flds[b]) for b in BRANCHES}
        fields = flds["base"]
        label = "%s.%s" % (case["cls"].split(".")[-1], case["method"])
        pt_l, pt_r = PT.get(case["id"], (None, None))
        variants = {
            "v1": (build_state(label, bodies, case["ls"], case["rs"], fields, False), T1),
            "v2": (build_state(label, bodies, case["ls"], case["rs"], fields, True), T1),
            "v3": (build_state(label, bodies, case["ls"], case["rs"], fields, False), crit_q),
        }
        if pt_l:
            variants["v1pt"] = (build_state(label, bodies, pt_l, pt_r, fields, False), T1)
            variants["v3pt"] = (build_state(label, bodies, pt_l, pt_r, fields, False), crit_q)
        row = {k: case[k] for k in ("set", "id", "label", "criteria")}
        row["empty_body"] = [b for b in BRANCHES if not raw[b]]
        for vname, (state, questions) in variants.items():
            for mname in models:
                row["%s/%s" % (vname, mname)] = ask(mname, state, questions)
        row["state_v1"] = variants["v1"][0]
        results.append(row)
        print(row["id"], row["label"], {k: v for k, v in row.items() if "/" in k and k.startswith("v1")}, flush=True)

    json.dump(results, open(args.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
