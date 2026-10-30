#!/usr/bin/env python3
"""Busca de limiar e AUC ROC sobre as saídas reais da Laya no SMAT (mergedataset ampliado).

Lê `classification/run_*/*.json` de cada execução (ordem de processamento = ordem do gabarito) e,
para cada pontuação candidata (cada critério, máximo e média dos três), calcula a AUC ROC e procura
o limiar (busca aleatória; Optuna se instalado) que maximiza a acurácia balanceada numa metade dos
cenários. A outra metade (holdout) mede o resultado. Repete para subconjuntos do dataset.

Uso: python tune_smat_threshold.py --gold gold.json [--flags flags.json] --run nome=dir [--run ...]
"""
import argparse
import glob
import json
import random

CRITERIA = ["criterion_1_global_divergence", "criterion_2_parent_change_loss", "criterion_3_merge_new_effect"]


def load(run_dir, gold, flags):
    files = sorted(glob.glob(f"{run_dir}/classification/run_*/*.json"))
    assert len(files) == len(gold), (len(files), len(gold))
    recs = []
    for f, g, fl in zip(files, gold, flags):
        if g["interference"] is None:
            continue
        p = json.load(open(f, encoding="utf-8"))["probabilities"]
        c = [float(p[k]) for k in CRITERIA]
        recs.append({"id": f"{g['project']}/{g['commit']}", "y": g["interference"], "flag": fl,
                     "scores": {"c1": c[0], "c2": c[1], "c3": c[2], "max": max(c), "media": sum(c) / 3}})
    return recs


def auc(ys, ps):
    pos = [p for y, p in zip(ys, ps) if y]
    neg = [p for y, p in zip(ys, ps) if not y]
    if not pos or not neg:
        return None
    s = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return s / (len(pos) * len(neg))


def conf(ys, ps, t):
    tp = sum(p >= t and y for y, p in zip(ys, ps))
    fp = sum(p >= t and not y for y, p in zip(ys, ps))
    fn = sum(p < t and y for y, p in zip(ys, ps))
    tn = sum(p < t and not y for y, p in zip(ys, ps))
    tpr = tp / (tp + fn) if tp + fn else 0.0
    tnr = tn / (tn + fp) if tn + fp else 0.0
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn, "bal_acc": round((tpr + tnr) / 2, 3)}


def search(ys, ps, trials, seed):
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        lo, hi = min(ps), max(ps)
        st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
        st.optimize(lambda tr: conf(ys, ps, tr.suggest_float("t", lo, hi))["bal_acc"], n_trials=trials)
        return st.best_params["t"]
    except ImportError:
        rng = random.Random(seed)
        lo, hi = min(ps), max(ps)
        best_t, best_v = 0.5, -1
        for _ in range(trials):
            t = rng.uniform(lo, hi)
            v = conf(ys, ps, t)["bal_acc"]
            if v > best_v:
                best_t, best_v = t, v
        return best_t


def evaluate(recs, trials, seed):
    ids = sorted({r["id"] for r in recs})
    random.Random(seed).shuffle(ids)
    half = set(ids[: len(ids) // 2])
    out = {}
    for name in ["c1", "c2", "c3", "max", "media"]:
        ys = [r["y"] for r in recs]
        ps = [r["scores"][name] for r in recs]
        s = [r for r in recs if r["id"] in half]
        h = [r for r in recs if r["id"] not in half]
        t = search([r["y"] for r in s], [r["scores"][name] for r in s], trials, seed)
        out[name] = {"auc": None if auc(ys, ps) is None else round(auc(ys, ps), 3),
                     "auc_holdout": None if not h or auc([r["y"] for r in h], [r["scores"][name] for r in h]) is None
                     else round(auc([r["y"] for r in h], [r["scores"][name] for r in h]), 3),
                     "limiar": round(t, 3),
                     "em_0.5": conf(ys, ps, 0.5),
                     "holdout_limiar": conf([r["y"] for r in h], [r["scores"][name] for r in h], t)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--flags", default="", help="JSON com um rótulo de subconjunto por método, na ordem do gabarito (opcional)")
    ap.add_argument("--run", action="append", required=True, help="nome=pasta")
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    gold = json.load(open(a.gold, encoding="utf-8"))
    flags = json.load(open(a.flags, encoding="utf-8")) if a.flags else ["todos"] * len(gold)
    result = {}
    for spec in a.run:
        name, d = spec.split("=", 1)
        recs = load(d, gold, flags)
        subsets = {"todos": recs, "ambos_mudaram": [r for r in recs if r["flag"] == "ambos mudaram"]}
        result[name] = {}
        for sname, sub in subsets.items():
            n_pos = sum(r["y"] for r in sub)
            print(f"\n== {name} | {sname} | n={len(sub)} (Yes {n_pos}, No {len(sub) - n_pos})")
            ev = evaluate(sub, a.trials, a.seed)
            result[name][sname] = {"n": len(sub), "yes": n_pos, "scores": ev}
            print(f"{'score':<7}{'AUC':>7}{'AUC_ho':>8}{'limiar':>8}  em 0.5 (TP/FP/TN/FN)   holdout no limiar escolhido")
            for k, v in ev.items():
                c, h = v["em_0.5"], v["holdout_limiar"]
                print(f"{k:<7}{v['auc']:>7}{str(v['auc_holdout']):>8}{v['limiar']:>8}  "
                      f"{c['TP']}/{c['FP']}/{c['TN']}/{c['FN']}   {h['TP']}/{h['FP']}/{h['TN']}/{h['FN']} bal={h['bal_acc']}")
    if a.out:
        json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)



# ---- Limiar por critério (regra OU: interferência se algum critério passa do seu limiar) ----

def conf_or(recs, ts):
    ys = [r["y"] for r in recs]
    ps = [any(r["scores"][c] >= t for c, t in zip(("c1", "c2", "c3"), ts)) for r in recs]
    tp = sum(p and y for p, y in zip(ps, ys)); fp = sum(p and not y for p, y in zip(ps, ys))
    fn = sum((not p) and y for p, y in zip(ps, ys)); tn = sum((not p) and (not y) for p, y in zip(ps, ys))
    tpr = tp / (tp + fn) if tp + fn else 0.0
    tnr = tn / (tn + fp) if tn + fp else 0.0
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn, "bal_acc": (tpr + tnr) / 2}


def margin_auc(recs, ts):
    """AUC da pontuação max_i(p_i - t_i), equivalente à regra OU com limiar 0."""
    s = [max(r["scores"][c] - t for c, t in zip(("c1", "c2", "c3"), ts)) for r in recs]
    return auc([r["y"] for r in recs], s)


def search_per_criterion(recs, trials, seed):
    lo = [min(r["scores"][c] for r in recs) for c in ("c1", "c2", "c3")]
    hi = [max(r["scores"][c] for r in recs) for c in ("c1", "c2", "c3")]
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
        def obj(tr):
            ts = [tr.suggest_float(f"t{i + 1}", lo[i], hi[i]) for i in range(3)]
            return conf_or(recs, ts)["bal_acc"]
        st.optimize(obj, n_trials=trials)
        return [st.best_params[f"t{i + 1}"] for i in range(3)]
    except ImportError:
        rng = random.Random(seed)
        best, best_v = [0.5] * 3, -1
        for _ in range(trials):
            ts = [rng.uniform(lo[i], hi[i]) for i in range(3)]
            v = conf_or(recs, ts)["bal_acc"]
            if v > best_v:
                best, best_v = ts, v
        return best


def per_criterion_report(recs, trials, seeds):
    """Repete a divisão busca/holdout com várias sementes e resume o holdout."""
    rows = []
    for seed in seeds:
        ids = sorted({r["id"] for r in recs})
        random.Random(seed).shuffle(ids)
        half = set(ids[: len(ids) // 2])
        s = [r for r in recs if r["id"] in half]
        h = [r for r in recs if r["id"] not in half]
        ts = search_per_criterion(s, trials, seed)
        c = conf_or(h, ts)
        rows.append({"seed": seed, "ts": [round(t, 3) for t in ts], "holdout": c,
                     "auc_holdout": margin_auc(h, ts), "bal_search": conf_or(s, ts)["bal_acc"]})
    mean = lambda k: sum(r["holdout"][k] for r in rows) / len(rows)
    aucs = [r["auc_holdout"] for r in rows if r["auc_holdout"] is not None]
    return {"rows": rows,
            "holdout_medio": {"TP": round(mean("TP"), 1), "FP": round(mean("FP"), 1), "TN": round(mean("TN"), 1),
                              "FN": round(mean("FN"), 1), "bal_acc": round(mean("bal_acc"), 3)},
            "auc_holdout_medio": round(sum(aucs) / len(aucs), 3) if aucs else None,
            "bal_search_medio": round(sum(r["bal_search"] for r in rows) / len(rows), 3)}


def main_per_criterion():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--flags", default="")
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    gold = json.load(open(a.gold, encoding="utf-8"))
    flags = json.load(open(a.flags, encoding="utf-8")) if a.flags else ["todos"] * len(gold)
    result = {}
    for spec in a.run:
        name, d = spec.split("=", 1)
        recs = load(d, gold, flags)
        for sname, sub in {"todos": recs, "ambos_mudaram": [r for r in recs if r["flag"] == "ambos mudaram"]}.items():
            rep = per_criterion_report(sub, a.trials, range(a.seeds))
            result.setdefault(name, {})[sname] = rep
            h = rep["holdout_medio"]
            print(f"{name:<10}{sname:<15} busca bal={rep['bal_search_medio']}  holdout médio TP={h['TP']} FP={h['FP']} "
                  f"TN={h['TN']} FN={h['FN']} bal={h['bal_acc']}  AUC_ho={rep['auc_holdout_medio']}")
    if a.out:
        json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    if "--por-criterio" in sys.argv:
        sys.argv.remove("--por-criterio")
        main_per_criterion()
    else:
        main()
