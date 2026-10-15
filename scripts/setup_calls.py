#!/usr/bin/env python3
"""RQ4: what setup calls do the generated tests make before calling the target method?

For every target method in a run, parses the minimized EvoSuite test suite
(*_ESTest.java) and classifies each statement that runs before the call to the
target method (the test "prefix"):

  ctor_target   new T(...) where T is the target class
  ctor_other    new U(...) for any other class (often a parameter object)
  call_target   a call to a different method of the target class (same-class setup)
  call_other    a call to a method of another class (e.g. item.setItemId(...))
  call_static   a static call (Class.method(...))
  field_write   assignment to an object's field (x.f = ...)
  mock          a Mockito mock/stub created by EvoSuite
  env           EvoSuite's environment helpers (MockFile, NetworkHandling, ...),
                which set up files/sockets rather than program state

Assertions EvoSuite inserts between statements (assertEquals(x, obj.getY()))
are skipped, so getters used only as observers are not counted as setup.

Each setup call also gets a role:
  state   its return value is discarded, so it runs for its side effect
          (e.g. cart.setItem(...), list.add(x))
  value   its return value is used later in the test, so it builds a value
          (e.g. List.of(...), Config.getInstance(), obj.getChild())

Values (literals, arrays, casts) are not counted. EvoSuite minimizes tests, so
anything left in the prefix contributed to coverage.

Usage:
  python3 scripts/setup_calls.py --run outputs/muse-trial-1 [--run outputs/muse-trial-2 ...]
        [--baseline outputs/original-trial-1 ...] [--calls-out calls.csv] [--latex]
"""
import argparse
import collections
import csv
import os
import re
import sys

import javalang

CATS = ["ctor_target", "ctor_other", "call_target", "call_other", "call_static", "field_write", "mock", "env"]
ENV_CLASSES = {"NetworkHandling", "FileSystemHandling", "SystemInUtil", "Runtime", "System"}
SETUP_CALLS = ("call_target", "call_other", "call_static")  # what plain modular mode cannot do


def n_params(descriptor):
    """Number of parameters in a JVM method descriptor like (ILjava_lang_String;[I)V."""
    inner = descriptor[descriptor.index("(") + 1:descriptor.index(")")]
    n, i = 0, 0
    while i < len(inner):
        while inner[i] == "[":
            i += 1
        if inner[i] == "L":
            i = inner.index(";", i)
        n += 1
        i += 1
    return n


def name_prefix(m):
    """Verb prefix of a method name, used to group setup calls (setX -> set)."""
    p = re.match(r"[a-z]+", m)
    return p.group(0) if p else m[:1].lower()


def iter_statements(stmts):
    """Flatten statements in order, descending into try blocks and plain blocks."""
    for s in stmts or []:
        if isinstance(s, javalang.tree.TryStatement):
            yield from iter_statements(s.block)
        elif isinstance(s, javalang.tree.BlockStatement):
            yield from iter_statements(s.statements)
        else:
            yield s


def is_assertion(st):
    e = getattr(st, "expression", None)
    return (isinstance(e, javalang.tree.MethodInvocation) and not e.qualifier
            and (e.member.startswith("assert") or e.member in ("fail", "verifyException")))


def is_target_call(node, target, nargs):
    return (isinstance(node, javalang.tree.MethodInvocation) and node.member == target
            and len(node.arguments) == nargs)


def simple(t):
    return t.split(".")[-1].split("<")[0] if t else t


def analyze_test(body, target_cls, target, nargs):
    """Return (reached_target, list of (category, callee_class, callee_method, role)) for one test."""
    types = {}          # variable -> simple type name
    events = []
    for st in iter_statements(body):
        if isinstance(st, javalang.tree.LocalVariableDeclaration):
            for d in st.declarators:
                types[d.name] = st.type.name
        if any(is_target_call(n, target, nargs) for _, n in st):
            return True, events
        if is_assertion(st):
            continue
        for _, n in st:
            if isinstance(n, javalang.tree.ClassCreator):
                c = simple(n.type.name)
                cat = "ctor_target" if c == target_cls else "ctor_other"
                if c.startswith("Mock") and c != target_cls:
                    cat = "env"
                events.append((cat, c, "<init>", "value"))
            elif isinstance(n, javalang.tree.MethodInvocation):
                if n.member in ("mock", "doReturn", "when", "anyString", "anyInt", "any"):
                    if n.member == "mock":
                        events.append(("mock", "", "mock", "value"))
                    continue
                q = n.qualifier or ""
                base = q.split(".")[0]
                if base in types and "." not in q:
                    cls = simple(types[base])
                    cat = "call_target" if cls == target_cls else "call_other"
                elif base[:1].isupper():          # Class.method(...)
                    cls, cat = simple(q), "call_static"
                elif q == "":                     # unqualified: a method of the test class
                    continue
                else:                             # x.field.method(...): object reached through a field
                    cls, cat = "?", "call_other"
                if cls.startswith("Mock") or cls in ENV_CLASSES:
                    cat = "env"
                discarded = isinstance(st, javalang.tree.StatementExpression) and st.expression is n
                events.append((cat, cls, n.member, "state" if discarded else "value"))
            elif isinstance(n, javalang.tree.Assignment):
                lhs = n.expressionl
                if isinstance(lhs, javalang.tree.MemberReference) and lhs.qualifier:
                    events.append(("field_write", "", lhs.member, "state"))
    return False, events


def target_dirs(run):
    """Yield (project, class, method_dir_path) for every target in a run."""
    for proj in sorted(os.listdir(run)):
        p = os.path.join(run, proj)
        if not os.path.isdir(p) or proj.startswith("."):
            continue
        for cls in sorted(os.listdir(p)):
            c = os.path.join(p, cls)
            if os.path.isdir(c):
                for m in sorted(os.listdir(c)):
                    if os.path.isdir(os.path.join(c, m)):
                        yield proj, cls, os.path.join(c, m)


def coverage(mdir):
    f = os.path.join(mdir, "statistics.csv")
    try:
        with open(f) as fh:
            r = list(csv.reader(fh))
        return int(r[1][3]), int(r[1][4])
    except Exception:
        return None


def analyze_run(run):
    """Return {(proj, cls, method): {"tests": [...events per test], "cov": (goals, covered)}}."""
    out = {}
    for proj, cls, mdir in target_dirs(run):
        method = os.path.basename(mdir)
        cov = coverage(mdir)
        if cov is None:
            continue
        name, nargs = method[:method.index("(")], n_params(method)
        tcls = cls.split(".")[-1]
        tests = []
        for root, _, files in os.walk(mdir):
            for f in files:
                if not f.endswith("_ESTest.java"):
                    continue
                src = open(os.path.join(root, f), errors="replace").read()
                if "EvoSuite did not generate any tests" in src:
                    continue
                try:
                    tree = javalang.parse.parse(src)
                except Exception:
                    continue
                for _, md in tree.filter(javalang.tree.MethodDeclaration):
                    if any(a.name == "Test" for a in md.annotations):
                        reached, ev = analyze_test(md.body, tcls, name, nargs)
                        if reached:
                            tests.append(ev)
        out[(proj, cls, method)] = {"tests": tests, "cov": cov}
    return out


def summarize(label, runs, keep=None):
    """Aggregate over trials. Returns (rows for printing, per-method dict)."""
    per_method = collections.defaultdict(lambda: {"tests": [], "cov": []})
    for r in runs:
        for k, v in r.items():
            if keep is not None and k not in keep:
                continue
            per_method[k]["tests"].extend(v["tests"])
            per_method[k]["cov"].append(v["cov"])
    tests = [t for v in per_method.values() for t in v["tests"]]
    with_tests = [k for k, v in per_method.items() if v["tests"]]
    uses = [k for k in with_tests
            if any(e[0] in SETUP_CALLS for t in per_method[k]["tests"] for e in t)]
    n = max(len(tests), 1)
    print(f"\n== {label}: {len(runs)} trial(s), {len(per_method)} methods, "
          f"{len(with_tests)} with tests, {len(tests)} tests ==")
    print(f"methods where some test makes a setup call: {len(uses)} / {len(with_tests)} "
          f"({100 * len(uses) / max(len(with_tests), 1):.1f}%)")
    print(f"tests with >=1 setup call: "
          f"{sum(any(e[0] in SETUP_CALLS for e in t) for t in tests)} / {len(tests)}")
    print(f"mean prefix length (counted statements per test): {sum(map(len, tests)) / n:.2f}")
    print(f"{'category':<14}{'tests using':>12}{'% tests':>9}{'calls/test':>12}")
    for c in CATS:
        k = sum(any(e[0] == c for e in t) for t in tests)
        m = sum(sum(e[0] == c for e in t) for t in tests)
        print(f"{c:<14}{k:>12}{100 * k / n:>8.1f}%{m / n:>12.2f}")
    return per_method


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", required=True, help="EMOTE run dir (repeat per trial)")
    ap.add_argument("--baseline", action="append", default=[], help="plain EvoSuite run dir (repeat per trial)")
    ap.add_argument("--calls-out", help="write every setup call to this CSV")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--methods", help="per_method.csv from make_results.py: only analyze these methods "
                                      "(so the counts match Table 1)")
    a = ap.parse_args()

    keep = None
    if a.methods:
        keep = {(r["project"], r["class"], r["method"]) for r in csv.DictReader(open(a.methods))}
        print(f"restricting to the {len(keep)} methods in {a.methods}")
    emote = summarize("EMOTE", [analyze_run(r) for r in a.run], keep)
    base = summarize("EvoSuite", [analyze_run(r) for r in a.baseline], keep) if a.baseline else None

    calls = [(k, e) for k, v in emote.items() for t in v["tests"] for e in t if e[0] in SETUP_CALLS]
    print(f"\nEMOTE setup calls by verb prefix (top {a.top}):")
    for p, c in collections.Counter(name_prefix(e[2]) for _, e in calls).most_common(a.top):
        print(f"  {p:<12}{c:>6}  ({100 * c / max(len(calls), 1):.1f}%)")
    roles = collections.Counter(e[3] for _, e in calls)
    nc = max(len(calls), 1)
    print(f"\nEMOTE setup calls by role: state setup (result discarded) {roles['state']} "
          f"({100 * roles['state'] / nc:.1f}%), value construction (result used) {roles['value']} "
          f"({100 * roles['value'] / nc:.1f}%)")
    for role in ("state", "value"):
        rc = collections.Counter(e[0] for _, e in calls if e[3] == role)
        print(f"  {role}: " + ", ".join(f"{c} {n}" for c, n in rc.most_common()))
    meth_roles = collections.Counter()
    for k, v in emote.items():
        rs = {e[3] for t in v["tests"] for e in t if e[0] in SETUP_CALLS}
        if rs:
            meth_roles["both" if len(rs) == 2 else rs.pop()] += 1
    print(f"  methods using only state setup {meth_roles['state']}, only value construction "
          f"{meth_roles['value']}, both {meth_roles['both']}")
    for role in ("state", "value"):
        print(f"\nEMOTE {role} calls by verb prefix (top 8):")
        sub = [e for _, e in calls if e[3] == role]
        for p, c in collections.Counter(name_prefix(e[2]) for e in sub).most_common(8):
            print(f"  {p:<12}{c:>6}  ({100 * c / max(len(sub), 1):.1f}%)")
    print(f"\nEMOTE setup calls by callee (top {a.top}):")
    for (cls, m), c in collections.Counter((e[1], e[2]) for _, e in calls).most_common(a.top):
        print(f"  {cls}.{m}: {c}")

    if base:
        # does using setup calls go with a coverage gain? (methods with tests in both tools)
        groups = {"uses setup calls": [], "no setup calls": []}
        gain = {"uses setup calls": 0.0, "no setup calls": 0.0}
        lost = {"uses setup calls": 0.0, "no setup calls": 0.0}
        for k, v in emote.items():
            if not v["tests"] or k not in base:
                continue
            ec = [c for g, c in v["cov"]]
            bc = [c for g, c in base[k]["cov"]]
            goals = v["cov"][0][0]
            if not goals or not bc:
                continue
            d = (sum(ec) / len(ec) - sum(bc) / len(bc)) / goals * 100
            u = any(e[0] in SETUP_CALLS for t in v["tests"] for e in t)
            g = "uses setup calls" if u else "no setup calls"
            groups[g].append(d)
            diff = sum(ec) / len(ec) - sum(bc) / len(bc)
            if diff > 0:
                gain[g] += diff
            else:
                lost[g] -= diff
        print("\nCoverage change (pp) vs. plain EvoSuite, by whether EMOTE's tests make setup calls:")
        for g, ds in groups.items():
            if ds:
                gained = sum(d > 0 for d in ds)
                print(f"  {g:<18} methods={len(ds):<5} mean={sum(ds) / len(ds):+6.2f}  "
                      f"improved={gained} ({100 * gained / len(ds):.0f}%)  "
                      f"branches gained={gain[g]:.1f} ({100 * gain[g] / max(sum(gain.values()), 1e-9):.0f}% of all gains)  "
                      f"lost={lost[g]:.1f}")

    if a.calls_out:
        with open(a.calls_out, "w", newline="") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(["project", "class", "method", "category", "callee_class", "callee_method", "role"])
            for (proj, cls, m), e in calls:
                w.writerow([proj, cls, m, *e])
        print(f"\nWrote {len(calls)} setup calls to {a.calls_out}")


if __name__ == "__main__":
    sys.exit(main())
