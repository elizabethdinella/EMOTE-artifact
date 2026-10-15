#!/usr/bin/env python3
"""Paper results from the run folders: Table 1 rows, the coverage heatmap, and the
per-project change chart.

Method selection and averaging follow eval.py, so the totals match it:
  * methods are those with a statistics.csv in the first EvoSuite trial
  * EMOTE must have a valid result (tests generated) in every EMOTE trial
  * an EvoSuite trial with no valid result counts as 0 covered branches
  * methods whose goal counts disagree between tools are skipped

Outputs (in --out-dir):
  table_rows.tex       rows for Table 1 (projects 1-5, 6-100, total)
  heatmap.pdf          per-method coverage, EvoSuite (x) vs EMOTE (y)
  project_delta.pdf    change in coverage per project, sorted
  per_method.csv       one row per method, for anything else you want to check
  appendix_table.tex   per-project table for the appendix (two halves side by side)
  overhead.tex         RQ4 row: search iterations per second for each tool

Usage:
  python3 scripts/make_results.py \
      --og outputs/original-trial-1 --og outputs/original-trial-2 --og outputs/original-trial-3 \
      --emote outputs/muse-trial-1 --emote outputs/muse-trial-2 --emote outputs/muse-trial-3 \
      --out-dir results
Needs: numpy, scipy, matplotlib
"""
import argparse
import csv
import os
import re

import numpy as np
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

plt.rcParams.update({"font.size": 13, "pdf.fonttype": 42, "ps.fonttype": 42})


def read_stats(d):
    """(goals, covered) for a target folder, or None if missing/invalid (no tests)."""
    f = os.path.join(d, "statistics.csv")
    if not os.path.exists(f):
        return None
    tests = False
    for root, _, files in os.walk(d):
        for name in files:
            if name.endswith("_ESTest.java"):
                if "EvoSuite did not generate any tests" in open(os.path.join(root, name), errors="replace").read():
                    return None
                tests = True
    if not tests:
        return None
    try:
        row = list(csv.reader(open(f)))[1]
        return int(row[3]), int(row[4])
    except Exception:
        return None


def targets(run):
    for proj in sorted(os.listdir(run)):
        p = os.path.join(run, proj)
        if not os.path.isdir(p) or proj.startswith("."):
            continue
        for cls in os.listdir(p):
            c = os.path.join(p, cls)
            if os.path.isdir(c):
                for m in os.listdir(c):
                    if os.path.exists(os.path.join(c, m, "statistics.csv")):
                        yield proj, cls, m


def collect(og_runs, emote_runs):
    rows = []
    skipped = {"emote missing": 0, "goal mismatch": 0, "no baseline": 0}
    for proj, cls, m in targets(og_runs[0]):
        em = [read_stats(os.path.join(r, proj, cls, m)) for r in emote_runs]
        if any(x is None for x in em):
            skipped["emote missing"] += 1
            continue
        goals = em[0][0]
        if any(g != goals for g, _ in em):
            skipped["goal mismatch"] += 1
            continue
        og_cov = []
        og_goals = None
        for r in og_runs:
            x = read_stats(os.path.join(r, proj, cls, m))
            if x is None or (og_goals is not None and x[0] != og_goals):
                og_cov.append(0)  # eval.py: invalid baseline run counts as 0
                continue
            og_goals = x[0]
            og_cov.append(x[1])
        if og_goals is None:
            skipped["no baseline"] += 1
            og_goals = goals
        if og_goals != goals:
            skipped["goal mismatch"] += 1
            continue
        rows.append({"project": proj, "class": cls, "method": m, "goals": goals,
                     "og": float(np.mean(og_cov)), "emote": float(np.mean([c for _, c in em]))})
    return rows, skipped


def proj_num(p):
    m = re.match(r"(\d+)_", p)
    return int(m.group(1)) if m else 0


def fmt_p(p):
    if p is None or np.isnan(p):
        return "--"
    return "$<$0.001" if p < 0.001 else f"{p:.3f}"


def summarize(rows):
    rows = [r for r in rows if r["goals"] > 0]
    g = sum(r["goals"] for r in rows)
    og = sum(r["og"] for r in rows)
    em = sum(r["emote"] for r in rows)
    up = sum(r["emote"] > r["og"] + 1e-9 for r in rows)
    down = sum(r["emote"] < r["og"] - 1e-9 for r in rows)
    same = len(rows) - up - down
    x = np.array([r["og"] / r["goals"] for r in rows])
    y = np.array([r["emote"] / r["goals"] for r in rows])
    p = a12 = float("nan")
    if len(rows) and np.any(x != y):
        p = stats.wilcoxon(y, x).pvalue
    if len(rows) and len(x):
        # Vargha-Delaney A12: P(EMOTE > EvoSuite) + 0.5 P(tie), via the Mann-Whitney U statistic
        u = stats.mannwhitneyu(y, x, alternative="two-sided").statistic
        a12 = u / (len(y) * len(x))
    return {"methods": len(rows), "branches": g, "og_pct": 100 * og / g if g else 0,
            "emote_pct": 100 * em / g if g else 0, "up": up, "down": down, "same": same,
            "p": p, "a12": a12}


def table_rows(rows):
    subsets = [("Projects 1--5", [r for r in rows if 1 <= proj_num(r["project"]) <= 5]),
               ("Projects 6--100", [r for r in rows if proj_num(r["project"]) >= 6]),
               (None, None),
               ("Total", rows)]
    out, counts = [], []
    for name, rs in subsets:
        if name is None:
            out.append("\\midrule")
            continue
        s = summarize(rs)
        d = s["emote_pct"] - s["og_pct"]
        out.append(f"{name:<16}& {s['methods']:>5} & {s['branches']:>6} & {s['og_pct']:.2f} & "
                   f"{s['emote_pct']:.2f} & {d:+.2f} & {fmt_p(s['p'])} \\\\")
        counts.append(f"{name}: improved {s['up']}, worse {s['down']}, same {s['same']}")
    return "\n".join(out), counts


def appendix_table(rows, path):
    """Full per-project table: a table* with two halves side by side, sorted by project number."""
    by = {}
    for r in rows:
        b = by.setdefault(r["project"], [0, 0, 0.0, 0.0])
        b[0] += 1
        b[1] += r["goals"]
        b[2] += r["og"]
        b[3] += r["emote"]
    lines = []
    for proj in sorted(by, key=proj_num):
        n, g, o, e = by[proj]
        name = proj.split("_", 1)[1] if "_" in proj else proj
        name = name.replace("_", "\\_")
        if g:
            lines.append(f"{proj_num(proj)} & {name} & {n} & {g} & {100 * o / g:.1f} & {100 * e / g:.1f} & {100 * (e - o) / g:+.1f} \\\\")
        else:
            lines.append(f"{proj_num(proj)} & {name} & {n} & 0 & -- & -- & -- \\\\")
    tn = sum(v[0] for v in by.values())
    tg = sum(v[1] for v in by.values())
    to = sum(v[2] for v in by.values())
    te = sum(v[3] for v in by.values())
    total = (f" & Total & {tn} & {tg} & {100 * to / tg:.1f} & {100 * te / tg:.1f} & {100 * (te - to) / tg:+.1f} \\\\"
             if tg else " & Total & 0 & 0 & -- & -- & -- \\\\")
    half = (len(lines) + 1) // 2
    head = ("\\begin{tabular}[t]{rlrrrrr}\n\\toprule\n"
            " & Project & Meth. & Br. & EvoS. & \\textsc{emote} & $\\Delta$ \\\\\n\\midrule\n")
    tail = "\\bottomrule\n\\end{tabular}"
    out = ("% generated by scripts/make_results.py\n"
           "\\begin{table*}[p]\n\\centering\n\\scriptsize\n"
           "\\caption{Modular branch coverage (\\%) per SF100 project. Meth.\\ and Br.\\ are the number of "
           "methods and branches compared; $\\Delta$ is the difference in percentage points. Projects with no methods compared by both tools are omitted.}\n"
           "\\label{tab:appendix}\n"
           + head + "\n".join(lines[:half]) + "\n" + tail + "\\hfill\n"
           + head + "\n".join(lines[half:]) + "\n\\midrule\n" + total + "\n" + tail + "\n\\end{table*}\n")
    open(path, "w").write(out)


def heatmap(rows, path):
    rs = [r for r in rows if r["goals"] > 0]
    x = [r["og"] / r["goals"] for r in rs]
    y = [r["emote"] / r["goals"] for r in rs]
    edges = np.linspace(0, 1, 11)
    h, _, _ = np.histogram2d(x, y, bins=[edges, edges])
    fig, ax = plt.subplots(figsize=(5.6, 5))
    im = ax.imshow(np.where(h.T > 0, h.T, np.nan), origin="lower", extent=[0, 1, 0, 1],
                   cmap="Blues", norm=LogNorm(vmin=1, vmax=max(h.max(), 2)))
    for i in range(10):
        for j in range(10):
            n = int(h[i, j])
            if n:
                dark = np.log(n) > 0.6 * np.log(max(h.max(), 2))
                ax.text(edges[i] + 0.05, edges[j] + 0.05, str(n), ha="center", va="center",
                        fontsize=8, color="white" if dark else "#333333")
    ax.plot([0, 1], [0, 1], color="#888888", lw=1, ls="--")
    ax.set_xlabel("EvoSuite coverage")
    ax.set_ylabel("EMOTE coverage")
    ax.set_xticks(np.linspace(0, 1, 6))
    ax.set_yticks(np.linspace(0, 1, 6))
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("Methods")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def project_delta(rows, path):
    by = {}
    for r in rows:
        b = by.setdefault(r["project"], [0, 0.0, 0.0])
        b[0] += r["goals"]
        b[1] += r["og"]
        b[2] += r["emote"]
    items = sorted(((p.split("_", 1)[1] if "_" in p else p, 100 * (e - o) / g)
                    for p, (g, o, e) in by.items() if g > 0), key=lambda t: t[1], reverse=True)
    names = [n for n, _ in items]
    vals = [v for _, v in items]
    colors = ["#2b6cb0" if v > 0 else "#c05621" if v < 0 else "#a0a0a0" for v in vals]
    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.bar(range(len(vals)), vals, color=colors, width=0.8)
    ax.axhline(0, color="#555555", lw=0.8)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=90, fontsize=6)
    ax.set_xlim(-0.6, len(vals) - 0.4)
    ax.set_ylabel("$\\Delta$ coverage (pp)")
    ax.grid(axis="y", color="#e0e0e0", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return items


FINISHED = re.compile(r"Search finished after (\d+)s and (\d+) generations, (\d+) statements")


def search_effort(d, min_secs):
    """(generations, statements) per second of search from a target's evosuite.log.

    Only runs that used (nearly) the whole budget count: EvoSuite stops as soon as
    every goal is covered, so a short search says how easy the method was, not how
    fast the tool is.
    """
    f = os.path.join(d, "evosuite.log")
    if not os.path.exists(f):
        return None
    m = FINISHED.search(open(f, errors="replace").read())
    if not m:
        return None
    secs = int(m.group(1))
    if secs < min_secs:
        return None
    return int(m.group(2)) / secs, int(m.group(3)) / secs


def overhead(rows, og_runs, emote_runs, budget):
    """RQ4: search throughput for methods where both tools searched for the full budget."""
    pairs = []
    min_secs = 0.95 * budget
    for r in rows:
        k = (r["project"], r["class"], r["method"])
        o = [x for x in (search_effort(os.path.join(run, *k), min_secs) for run in og_runs) if x]
        e = [x for x in (search_effort(os.path.join(run, *k), min_secs) for run in emote_runs) if x]
        if o and e:
            pairs.append((np.mean([g for g, _ in o]), np.mean([g for g, _ in e]),
                          np.mean([s for _, s in o]), np.mean([s for _, s in e])))
    if not pairs:
        return None, "no methods where both tools used the full search budget"
    a = np.array(pairs)
    lines = []
    for name, oi, ei in (("Iterations/s", 0, 1),):
        o, e = a[:, oi], a[:, ei]
        ok = (o > 0) & (e > 0)
        ratio = np.median(e[ok] / o[ok]) if ok.any() else float("nan")
        p = stats.wilcoxon(e, o).pvalue if np.any(e != o) else float("nan")
        lines.append(f"{name:<15}& {np.median(o):,.2f} & {np.median(e):,.2f} & {ratio:.2f} & {fmt_p(p)} \\\\")
    return "\n".join(lines), f"{len(pairs)} methods where both tools used the full {budget}s budget"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--og", action="append", required=True, help="EvoSuite run dir (repeat per trial)")
    ap.add_argument("--emote", action="append", required=True, help="EMOTE run dir (repeat per trial)")
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--budget", type=int, default=120, help="search budget in seconds (for RQ4)")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    rows, skipped = collect(a.og, a.emote)
    print(f"methods compared: {len(rows)}   skipped: {skipped}")

    with open(os.path.join(a.out_dir, "per_method.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["project", "class", "method", "goals", "og", "emote"])
        w.writeheader()
        w.writerows(rows)

    t, counts = table_rows(rows)
    open(os.path.join(a.out_dir, "table_rows.tex"), "w").write(t + "\n")
    print("\nTable 1 rows (Subset, Methods, Branches, EvoSuite, EMOTE, Delta, p):\n" + t)
    print("\nMethods per subset (for the text):\n  " + "\n  ".join(counts))

    appendix_table(rows, os.path.join(a.out_dir, "appendix_table.tex"))
    heatmap(rows, os.path.join(a.out_dir, "heatmap.pdf"))
    items = project_delta(rows, os.path.join(a.out_dir, "project_delta.pdf"))
    print(f"\nprojects better/worse/same: {sum(v > 0 for _, v in items)}/"
          f"{sum(v < 0 for _, v in items)}/{sum(v == 0 for _, v in items)}")

    o, note = overhead(rows, a.og, a.emote, a.budget)
    print(f"\nRQ4 overhead ({note}):")
    if o:
        print("metric & median EvoSuite & median EMOTE & median ratio (EMOTE/EvoSuite) & p")
        print(o)
        open(os.path.join(a.out_dir, "overhead.tex"), "w").write(o + "\n")
    print(f"\nwrote table_rows.tex, appendix_table.tex, overhead.tex, heatmap.pdf, project_delta.pdf, per_method.csv to {a.out_dir}/")


if __name__ == "__main__":
    main()
