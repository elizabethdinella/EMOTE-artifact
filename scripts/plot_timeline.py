#!/usr/bin/env python3
"""Coverage over time (Figure 5) from the timeline runs.

Reads BranchCoverageTimeline_T1..Tn from each target's statistics.csv
(written by run_evo_timeline.sh) and plots one line per method: EMOTE's coverage
over the search, colored by how EMOTE's final coverage compares to EvoSuite's.

Also prints a sanity check: how many timelines sit at 0 until the last point and
then jump to the final value (a sign the intermediate points were not recorded).

Usage:
  python3 scripts/plot_timeline.py --og outputs-timeline/original-trial-1 \
      --emote outputs-timeline/muse-trial-1 --interval 5 --out timeline.pdf
Needs: numpy, matplotlib
"""
import argparse
import csv
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.size": 13, "pdf.fonttype": 42, "ps.fonttype": 42})


def read(d):
    """(final coverage, goals, [timeline values]) or None."""
    f = os.path.join(d, "statistics.csv")
    if not os.path.exists(f):
        return None
    try:
        rows = list(csv.reader(open(f)))
        head, row = rows[0], rows[1]
    except Exception:
        return None
    idx = [i for i, h in enumerate(head) if h.startswith("BranchCoverageTimeline_T")]
    if not idx:
        return None
    idx.sort(key=lambda i: int(head[i].rsplit("T", 1)[1]))
    try:
        return float(row[head.index("Coverage")]), int(row[head.index("Total_Goals")]), [float(row[i]) for i in idx]
    except Exception:
        return None


def targets(run):
    for root, _, files in os.walk(run):
        if "statistics.csv" in files:
            yield os.path.relpath(root, run)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--og", required=True)
    ap.add_argument("--emote", required=True)
    ap.add_argument("--interval", type=float, default=5.0, help="timeline interval in seconds")
    ap.add_argument("--out", default="timeline.pdf")
    a = ap.parse_args()

    pairs = []
    for t in targets(a.emote):
        e, o = read(os.path.join(a.emote, t)), read(os.path.join(a.og, t))
        if e and o and e[1] == o[1] and e[1] > 0:
            pairs.append((t, o, e))
    print(f"methods with timelines from both tools: {len(pairs)}")
    if not pairs:
        return

    # sanity check: zero until the last point, then a jump to the final value
    for name, k in (("EvoSuite", 1), ("EMOTE", 2)):
        tl = [p[k][2] for p in pairs]
        jump = sum(all(v == 0 for v in x[:-1]) and x[-1] > 0 for x in tl)
        mism = sum(abs(x[-1] - p[k][0]) > 0.05 for x, p in zip(tl, pairs))
        print(f"{name}: zero-until-last-point {jump}/{len(tl)}, last point differs from final coverage {mism}/{len(tl)}")

    groups = {"EMOTE = EvoSuite": ("#9ecae1", 0.9, 1),
              "EMOTE > EvoSuite": ("#2b6cb0", 1.4, 3),
              "EvoSuite > EMOTE": ("#c53030", 1.4, 2)}
    counts = dict.fromkeys(groups, 0)
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    for _, o, e in pairs:
        if abs(e[0] - o[0]) < 1e-9:
            g = "EMOTE = EvoSuite"
        elif e[0] > o[0]:
            g = "EMOTE > EvoSuite"
        else:
            g = "EvoSuite > EMOTE"
        counts[g] += 1
        color, lw, z = groups[g]
        xs = [0] + [a.interval * (i + 1) for i in range(len(e[2]))]
        ax.plot(xs, [0] + e[2], color=color, lw=lw, zorder=z, alpha=0.9)
    for g, (color, lw, _) in groups.items():
        ax.plot([], [], color=color, lw=2, label=f"{g} ({counts[g]})")
    ax.set_xlabel("Search time (seconds)")
    ax.set_ylabel("EMOTE coverage")
    ax.set_xlim(0, a.interval * len(pairs[0][2][2]))
    ax.set_ylim(0, 1.02)
    ax.grid(color="#e5e5e5", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=10, loc="lower right")
    fig.tight_layout()
    fig.savefig(a.out)
    print(f"groups: {counts}\nwrote {a.out}")


if __name__ == "__main__":
    main()
