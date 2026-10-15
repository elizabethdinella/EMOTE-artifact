#!/usr/bin/env python3
"""RQ2 (modular coverage ablation) from the re-measured ablation tests.

Two modes:

  --check   compare a re-measured TSV against the run it came from
            (e.g. EMOTE tests re-measured with emote.jar vs. muse-trial-1):
            reports how often the covered-branch counts agree.

  default   the RQ2 numbers. For methods with results from all three sources:
              ablation reported   coverage the ablation build reported (plain coverage)
              ablation modular    the ablation's tests re-measured with emote.jar
              EMOTE modular       EMOTE's own (modular) coverage
            Inflation = reported - modular for the ablation.

Usage:
  python3 scripts/rq2.py --check --remeasure check_emote.tsv --run outputs/muse-trial-1
  python3 scripts/rq2.py --remeasure remeasure_ablation_modular.tsv \
      --ablation outputs/ablation-trial-1 --emote outputs/muse-trial-1 [--projects 6-100]
Needs: numpy, scipy
"""
import argparse
import csv
import os
import re

import numpy as np
from scipy import stats


def run_stats(run, key):
    f = os.path.join(run, *key, "statistics.csv")
    try:
        rows = list(csv.reader(open(f)))
        h, r = rows[0], rows[1]
        return int(r[h.index("Total_Goals")]), int(r[h.index("Covered_Goals")])
    except Exception:
        return None


def load_remeasure(path):
    out = {}
    for r in csv.DictReader(open(path), delimiter="\t"):
        if r["status"] == "ok":
            out[(r["project"], r["class"], r["method"])] = (int(r["goals"]), int(r["covered"]))
    return out


def proj_ok(proj, rng):
    if not rng:
        return True
    lo, hi = map(int, rng.split("-"))
    m = re.match(r"(\d+)_", proj)
    return bool(m) and lo <= int(m.group(1)) <= hi


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remeasure", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--run", help="(--check) the run the re-measured tests came from")
    ap.add_argument("--ablation", help="ablation run folder")
    ap.add_argument("--emote", action="append", default=[], help="EMOTE run folder(s); averaged")
    ap.add_argument("--projects", help="project number range, e.g. 6-100")
    a = ap.parse_args()

    rm = {k: v for k, v in load_remeasure(a.remeasure).items() if proj_ok(k[0], a.projects)}

    if a.check:
        same = diff = missing = 0
        examples = []
        for k, (g, c) in rm.items():
            s = run_stats(a.run, k)
            if s is None:
                missing += 1
            elif s == (g, c):
                same += 1
            else:
                diff += 1
                if len(examples) < 10:
                    examples.append(f"  run {s[1]}/{s[0]}  re-measured {c}/{g}  {k[0]} {k[1].split('.')[-1]}.{k[2][:50]}")
        n = max(same + diff, 1)
        print(f"re-measured OK: {len(rm)}   identical to the run: {same} ({100 * same / n:.0f}%)   "
              f"different: {diff}   no result in run: {missing}")
        if examples:
            print("differences:\n" + "\n".join(examples))
        return

    rows = []
    for k, (g, mod) in rm.items():
        rep = run_stats(a.ablation, k)
        em = [run_stats(r, k) for r in a.emote]
        if rep is None or any(x is None for x in em) or rep[0] != g or any(x[0] != g for x in em) or g == 0:
            continue
        rows.append((g, rep[1], mod, float(np.mean([x[1] for x in em]))))
    if not rows:
        print("no methods with results from all sources")
        return
    r = np.array(rows)
    g, rep, mod, em = r[:, 0], r[:, 1], r[:, 2], r[:, 3]
    G = g.sum()
    print(f"methods: {len(r)}   branches: {int(G)}")
    print(f"ablation reported coverage:   {100 * rep.sum() / G:.2f}%")
    print(f"ablation modular coverage:    {100 * mod.sum() / G:.2f}%")
    print(f"  inflation: {100 * (rep.sum() - mod.sum()) / G:.2f} pp; methods with inflated coverage: "
          f"{int((rep > mod).sum())} ({100 * (rep > mod).mean():.1f}%)")
    print(f"EMOTE modular coverage:       {100 * em.sum() / G:.2f}%")
    d = em / g - mod / g
    p = stats.wilcoxon(em / g, mod / g).pvalue if np.any(d != 0) else float("nan")
    print(f"  EMOTE - ablation (modular): {100 * (em.sum() - mod.sum()) / G:+.2f} pp, p={fmt_p(p)}; "
          f"EMOTE higher on {int((d > 1e-9).sum())}, lower on {int((d < -1e-9).sum())}, same on {int((abs(d) <= 1e-9).sum())}")


if __name__ == "__main__":
    main()
