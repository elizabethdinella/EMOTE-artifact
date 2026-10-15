#!/usr/bin/env python3
"""Build the list of (project, class, method) targets for run_evo_sf100.sh.

Projects are the SF100 directories named <N>_<name>. Projects in --exhaustive
keep every method (the SOAP setup for projects 1-5). All other projects are
randomly sampled down to --cap methods with a fixed --seed, so the sample is
reproducible.

Methods that never yield a modular test are filtered out before sampling:
private, abstract, native, synthetic/bridge, interface methods and static
initializers (<clinit>). On the SOAP data (projects 1-5) this drops ~16% of
targets and loses 1 of ~830 methods that produced valid tests in all trials.
Use --no-filter to keep everything (exactly what MethodExtractor lists).

Output: TSV with columns project, class, method (no header).

Example:
  python3 scripts/build_manifest.py --sf100 SF100 --cap 75 --seed 2026 \
      --exhaustive 1-5 --out manifests/sf100.tsv
"""
import argparse
import os
import random
import re
import subprocess
import sys

SKIP_FLAGS = {"private", "abstract", "native", "synthetic", "bridge", "clinit", "interface"}


def parse_range(spec):
    """'1-5,8,10-12' -> {1,2,3,4,5,8,10,11,12}"""
    out = set()
    if not spec:
        return out
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


def project_dirs(sf100, wanted):
    projs = []
    for d in os.listdir(sf100):
        m = re.match(r"^(\d+)_", d)
        if m and os.path.isdir(os.path.join(sf100, d)):
            n = int(m.group(1))
            if not wanted or n in wanted:
                projs.append((n, d))
    return [d for _, d in sorted(projs)]


def class_files(proj_path):
    out = []
    for root, dirs, files in os.walk(proj_path):
        # dependency jars live in lib/ and are never extracted, but be safe
        dirs[:] = [x for x in dirs if not (root == proj_path and x in ("lib", "evosuite-files"))]
        for f in files:
            if f.endswith(".class"):
                out.append(os.path.join(root, f))
    return sorted(out)


def list_methods(java, cp, files):
    proc = subprocess.run(
        [java, "-cp", cp, "MethodLister"],
        input="\n".join(files), capture_output=True, text=True, check=True,
    )
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append(parts)
    return rows


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sf100", default=os.path.join(here, "SF100"), help="SF100 directory (jars already extracted by setup_sf100.sh)")
    ap.add_argument("--projects", default="", help="project numbers to include, e.g. 1-100 (default: all found)")
    ap.add_argument("--exhaustive", default="1-5", help="projects to keep in full, no sampling (default: 1-5)")
    ap.add_argument("--cap", type=int, default=75, help="max methods per sampled project (default: 75)")
    ap.add_argument("--seed", type=int, default=2026, help="sampling seed (default: 2026)")
    ap.add_argument("--no-filter", action="store_true", help="keep private/abstract/synthetic/<clinit> methods")
    ap.add_argument("--java", default=os.environ.get("JAVA", "java"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cp = os.pathsep.join([os.path.join(here, "lib", "asm-9.5.jar"),
                          os.path.join(here, "lib", "asm-tree-9.5.jar"),
                          os.path.join(here, "src")])
    if not os.path.exists(os.path.join(here, "src", "MethodLister.class")):
        sys.exit("src/MethodLister.class missing: run `cd src && ./compile.sh` first")

    exhaustive = parse_range(args.exhaustive)
    total = 0
    summary = []
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as out:
        for proj in project_dirs(args.sf100, parse_range(args.projects)):
            n = int(proj.split("_")[0])
            files = class_files(os.path.join(args.sf100, proj))
            if not files:
                print(f"WARNING {proj}: no extracted .class files (run setup_sf100.sh?)", file=sys.stderr)
                summary.append((proj, 0, 0, 0))
                continue
            rows = list_methods(args.java, cp, files)
            n_all = len(rows)
            if not args.no_filter:
                rows = [r for r in rows if not (set(r[2].split(",")) & SKIP_FLAGS)]
            n_eligible = len(rows)
            if n not in exhaustive and len(rows) > args.cap:
                # per-project RNG so adding/removing projects does not change other samples
                rng = random.Random(f"{args.seed}:{proj}")
                rows = rng.sample(rows, args.cap)
            rows.sort()
            for cls, method, _ in rows:
                out.write(f"{proj}\t{cls}\t{method}\n")
            total += len(rows)
            summary.append((proj, n_all, n_eligible, len(rows)))

    print(f"{'project':<28}{'methods':>9}{'eligible':>10}{'selected':>10}")
    for proj, a, e, s in summary:
        print(f"{proj:<28}{a:>9}{e:>10}{s:>10}")
    print(f"\n{len(summary)} projects, {total} target methods -> {args.out}")


if __name__ == "__main__":
    main()
