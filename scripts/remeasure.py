#!/usr/bin/env python3
"""Re-measure the coverage of already generated tests with a given EvoSuite jar.

Used for the RQ2 ablation: the ablation build reports plain branch coverage
(which also counts branches reached through other methods), so its tests are
re-measured with emote.jar, whose coverage counts only modular coverage.

For every target in --run that has a generated test, this compiles the test and
its scaffolding, then runs EvoSuite's -measureCoverage with -Dtarget_method set.

Sanity checks before trusting the numbers (both should match the original runs):
  remeasure EMOTE's tests with emote.jar        -> same coverage as muse-trial-1
  remeasure the ablation's tests with ablation.jar -> same coverage as ablation-trial-1

Usage:
  python3 scripts/remeasure.py --run outputs/ablation-trial-1 --jar emote.jar \
      --manifest manifests/sf100.tsv --out remeasure_ablation_modular.tsv [--jobs 48] [--limit 20]
"""
import argparse
import concurrent.futures as cf
import csv
import glob
import os
import shutil
import subprocess
import sys
import tempfile


def method_map(manifest):
    """(project, class, method dir name) -> method descriptor as EvoSuite expects it."""
    m = {}
    for line in open(manifest):
        f = line.rstrip("\n").split("\t")
        if len(f) == 3 and all(f):
            m[(f[0], f[1], f[2].replace("/", "_"))] = f[2]
    return m


def project_cp(sf100, proj):
    d = os.path.join(sf100, proj)
    return ":".join(sorted(glob.glob(os.path.join(d, "*.jar"))) + sorted(glob.glob(os.path.join(d, "lib", "*.jar"))))


def read_stats(path):
    try:
        rows = list(csv.reader(open(path)))
        h, r = rows[0], rows[1]
        return int(r[h.index("Total_Goals")]), int(r[h.index("Covered_Goals")])
    except Exception:
        return None


def one(task, a):
    proj, cls, mdir, method = task
    tdir = os.path.join(a.run, proj, cls, mdir)
    tests = [f for f in glob.glob(os.path.join(tdir, "**", "*_ESTest.java"), recursive=True)]
    if not tests:
        return (proj, cls, mdir, "", "", "no_test")
    src = open(tests[0], errors="replace").read()
    if "EvoSuite did not generate any tests" in src:
        return (proj, cls, mdir, "", "", "no_test")
    scaff = tests[0].replace("_ESTest.java", "_ESTest_scaffolding.java")
    pkg = ""
    for line in src.splitlines():
        if line.startswith("package "):
            pkg = line[len("package "):].strip().rstrip(";")
            break
    test_class = (pkg + "." if pkg else "") + os.path.basename(tests[0])[:-5]
    cp = project_cp(a.sf100, proj)
    work = tempfile.mkdtemp(dir=a.scratch)
    try:
        out = os.path.join(work, "classes")
        os.makedirs(out)
        files = [tests[0]] + ([scaff] if os.path.exists(scaff) else [])
        r = subprocess.run([a.javac, "-nowarn", "-cp", f"{a.jar}:{cp}", "-d", out] + files,
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return (proj, cls, mdir, "", "", "compile_error: " + (r.stderr.strip().splitlines() or ["?"])[0][:150])
        report = os.path.join(work, "report")
        cmd = [a.java, "-cp", a.jar, "shaded.org.evosuite.EvoSuite", "-measureCoverage",
               "-class", cls, "-Djunit=" + test_class, "-projectCP", f"{cp}:{out}",
               "-criterion", "branch", "-Dtarget_method=" + method,
               "-Dreport_dir=" + report, "-Dshow_progress=false", "-mem", str(a.mem)]
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=a.timeout)
        s = read_stats(os.path.join(report, "statistics.csv"))
        if s is None:
            tail = (r.stdout + r.stderr).strip().splitlines()
            return (proj, cls, mdir, "", "", "measure_failed: " + (tail[-1][:150] if tail else "?"))
        return (proj, cls, mdir, s[0], s[1], "ok")
    except subprocess.TimeoutExpired:
        return (proj, cls, mdir, "", "", "timeout")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="run folder whose tests to re-measure")
    ap.add_argument("--jar", required=True, help="EvoSuite jar used for measuring")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True, help="output TSV")
    ap.add_argument("--sf100", default="SF100")
    ap.add_argument("--jobs", type=int, default=48)
    ap.add_argument("--mem", type=int, default=4000)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--limit", type=int, default=0, help="only the first N targets (for a quick test)")
    ap.add_argument("--project", action="append", help="only these projects")
    a = ap.parse_args()

    a.jar = os.path.abspath(a.jar)
    a.run = os.path.abspath(a.run)
    a.sf100 = os.path.abspath(a.sf100)
    a.java = os.environ.get("JAVA", "java")
    jdir = os.path.dirname(shutil.which(a.java) or a.java)
    a.javac = os.path.join(jdir, "javac") if os.path.exists(os.path.join(jdir, "javac")) else "javac"
    a.scratch = tempfile.mkdtemp(prefix="remeasure-", dir=os.path.dirname(os.path.abspath(a.out)) or ".")

    mm = method_map(a.manifest)
    tasks = []
    for proj in sorted(os.listdir(a.run)):
        if a.project and proj not in a.project:
            continue
        p = os.path.join(a.run, proj)
        if not os.path.isdir(p) or proj.startswith("."):
            continue
        for cls in sorted(os.listdir(p)):
            for mdir in sorted(os.listdir(os.path.join(p, cls))):
                if os.path.exists(os.path.join(p, cls, mdir, "statistics.csv")) and (proj, cls, mdir) in mm:
                    tasks.append((proj, cls, mdir, mm[(proj, cls, mdir)]))
    if a.limit:
        tasks = tasks[:a.limit]
    print(f"re-measuring {len(tasks)} targets from {a.run} with {os.path.basename(a.jar)}", flush=True)

    done = 0
    status = {}
    with open(a.out, "w", newline="") as fh, cf.ThreadPoolExecutor(a.jobs) as ex:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["project", "class", "method", "goals", "covered", "status"])
        for row in ex.map(lambda t: one(t, a), tasks):
            w.writerow(row)
            fh.flush()
            key = row[5].split(":")[0]
            status[key] = status.get(key, 0) + 1
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(tasks)} {status}", flush=True)
    shutil.rmtree(a.scratch, ignore_errors=True)
    print(f"done: {status}\nwrote {a.out}")
    if status.get("ok", 0) == 0:
        print("nothing measured successfully; check the status column for the first error", file=sys.stderr)


if __name__ == "__main__":
    main()
