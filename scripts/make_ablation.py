#!/usr/bin/env python3
"""Turn an EMOTE source tree into the RQ2 ablation: relaxed test cluster, plain coverage.

Run from the root of the EMOTE source repo (the folder with pom.xml), on a separate
branch. It disables the checks that restrict coverage to calls made directly on the
target method (modular coverage) and leaves the relaxed test cluster unchanged.
Each check is disabled by prefixing its condition with `false &&`.

Usage (from the EMOTE repo root):
  git checkout -b ablation
  python3 /path/to/make_ablation.py
  git diff            # 5 changed lines in 2 files
  mvn -DskipTests package
"""
import os
import re
import sys

BASE = "client/src/main/java/org/evosuite"
EDITS = [
    (f"{BASE}/coverage/branch/ControlFlowDistanceCalculator.java",
     r"if\s*\(\s*!Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*result\.getTrace\(\)\.getOriginMethods\(\)",
     "if(false && !Properties.TARGET_METHOD.isEmpty() && result.getTrace().getOriginMethods()", 1),
    (f"{BASE}/coverage/branch/ControlFlowDistanceCalculator.java",
     r"if\s*\(\s*Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*result\.getTrace\(\)\.getCoveredMethods\(\)",
     "if(result.getTrace().getCoveredMethods()", 1),
    (f"{BASE}/coverage/branch/ControlFlowDistanceCalculator.java",
     r"if\s*\(\s*!Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*!branchTrace\.originMethod\.equals",
     "if (false && !Properties.TARGET_METHOD.isEmpty() && !branchTrace.originMethod.equals", 1),
    (f"{BASE}/testcase/execution/ExecutionTraceImpl.java",
     r"if\s*\(\s*!Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*!entry\.getValue\(\)\.originMethod\.equals",
     "if (false && !Properties.TARGET_METHOD.isEmpty() && !entry.getValue().originMethod.equals", 2),
]


def main():
    if not os.path.exists("pom.xml") or not os.path.isdir(BASE):
        sys.exit("run this from the root of the EMOTE source repo (the folder with pom.xml)")
    texts = {}
    for f, pat, rep, n in EDITS:
        s = texts.get(f) or open(f).read()
        found = len(re.findall(pat, s))
        if found != n:
            sys.exit(f"{f}: expected {n} match(es) for\n  {pat}\nfound {found}. Nothing was changed.")
        texts[f] = re.sub(pat, rep, s)
    for f, s in texts.items():
        open(f, "w").write(s)
        print(f"edited {f}")
    print("done: 5 edits in 2 files. Review with `git diff`.")


if __name__ == "__main__":
    main()
PYEOFcat > scripts/make_ablation.py <<'PYEOF'
#!/usr/bin/env python3
"""Turn an EMOTE source tree into the RQ2 ablation: relaxed test cluster, plain coverage.

Run from the root of the EMOTE source repo (the folder with pom.xml), on a separate
branch. It disables the checks that restrict coverage to calls made directly on the
target method (modular coverage) and leaves the relaxed test cluster unchanged.
Each check is disabled by prefixing its condition with `false &&`.

Usage (from the EMOTE repo root):
  git checkout -b ablation
  python3 /path/to/make_ablation.py
  git diff            # 5 changed lines in 2 files
  mvn -DskipTests package
"""
import os
import re
import sys

BASE = "client/src/main/java/org/evosuite"
EDITS = [
    (f"{BASE}/coverage/branch/ControlFlowDistanceCalculator.java",
     r"if\s*\(\s*!Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*result\.getTrace\(\)\.getOriginMethods\(\)",
     "if(false && !Properties.TARGET_METHOD.isEmpty() && result.getTrace().getOriginMethods()", 1),
    (f"{BASE}/coverage/branch/ControlFlowDistanceCalculator.java",
     r"if\s*\(\s*Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*result\.getTrace\(\)\.getCoveredMethods\(\)",
     "if(result.getTrace().getCoveredMethods()", 1),
    (f"{BASE}/coverage/branch/ControlFlowDistanceCalculator.java",
     r"if\s*\(\s*!Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*!branchTrace\.originMethod\.equals",
     "if (false && !Properties.TARGET_METHOD.isEmpty() && !branchTrace.originMethod.equals", 1),
    (f"{BASE}/testcase/execution/ExecutionTraceImpl.java",
     r"if\s*\(\s*!Properties\.TARGET_METHOD\.isEmpty\(\)\s*&&\s*!entry\.getValue\(\)\.originMethod\.equals",
     "if (false && !Properties.TARGET_METHOD.isEmpty() && !entry.getValue().originMethod.equals", 2),
]


def main():
    if not os.path.exists("pom.xml") or not os.path.isdir(BASE):
        sys.exit("run this from the root of the EMOTE source repo (the folder with pom.xml)")
    texts = {}
    for f, pat, rep, n in EDITS:
        s = texts.get(f) or open(f).read()
        found = len(re.findall(pat, s))
        if found != n:
            sys.exit(f"{f}: expected {n} match(es) for\n  {pat}\nfound {found}. Nothing was changed.")
        texts[f] = re.sub(pat, rep, s)
    for f, s in texts.items():
        open(f, "w").write(s)
        print(f"edited {f}")
    print("done: 5 edits in 2 files. Review with `git diff`.")


if __name__ == "__main__":
    main()
