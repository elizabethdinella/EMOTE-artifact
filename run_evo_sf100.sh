#!/usr/bin/env bash
# Run EvoSuite modular testing (plain or EMOTE) on every target in a manifest.
# Generalizes run_evo.sh from the first five SF100 projects to all 100.
#
# Differences from run_evo.sh:
#   - targets come from a manifest (scripts/build_manifest.py), so projects can be sampled
#   - each run has a hard timeout, so a hung method cannot stall the whole run
#   - each run gets its own scratch working directory (no collisions on evosuite-report/)
#   - every attempt is logged to <out>/runs.tsv; failed targets are retried on re-run
#     up to --max-attempts times
#   - output goes straight to outputs/<label>-trial-<k>/<project>/<class>/<method>/,
#     the layout eval.py reads
# EvoSuite flags are identical to run_evo.sh.
#
# Usage:
#   ./run_evo_sf100.sh --tool emote --trial 1 --manifest manifests/sf100.tsv
#   ./run_evo_sf100.sh --tool og    --trial 1 --manifest manifests/sf100.tsv --jobs 48
#
# Re-running the same command resumes: finished targets are skipped.
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

TOOL=""
TRIAL=1
MANIFEST=""
JOBS=48
BUDGET=120
A_BUDGET=20
SEED=47
MEM=30000
HARD_TIMEOUT=""
MAX_ATTEMPTS=2
LOG_LIMIT=${LOG_LIMIT:-2000000}   # max bytes kept per evosuite.log (some projects log ~700 MB per run)
OK_LOG_LIMIT=${OK_LOG_LIMIT:-100000}  # successful runs keep only the first 100 KB
SF100="$HERE/SF100"
OUT_ROOT="$HERE/outputs"
JAR=""
LABEL=""
JAVA=${JAVA:-java}

usage() {
    cat <<EOF
Usage: $0 --tool og|emote|<label> --trial K --manifest FILE [options]

  --tool og|emote      og    -> evosuite-original-1.1.0.jar, label "original"
                       emote -> muse.jar, label "muse"  (labels match eval.py)
                       any other value needs --jar and is used as the label
  --jar PATH           EvoSuite jar to use (e.g. an ablation build)
  --label NAME         output label (outputs/NAME-trial-K)
  --trial K            trial number (default 1)
  --manifest FILE      TSV from scripts/build_manifest.py
  --jobs N             parallel EvoSuite runs (default 48)
  --budget S           search budget in seconds (default 120)
  --seed N             EvoSuite seed (default 47, as in run_evo.sh)
  --mem MB             EvoSuite -mem (default 30000, as in run_evo.sh)
  --timeout S          hard wall-clock limit per run (default 3*budget+180)
  --max-attempts N     attempts per target across re-runs (default 2)
  --sf100 DIR          SF100 directory (default ./SF100)
  --out DIR            outputs root (default ./outputs)
Environment: JAVA=/path/to/java11/bin/java to pick the JVM.
EOF
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --tool) TOOL=$2; shift 2 ;;
        --jar) JAR=$2; shift 2 ;;
        --label) LABEL=$2; shift 2 ;;
        --trial) TRIAL=$2; shift 2 ;;
        --manifest) MANIFEST=$2; shift 2 ;;
        --jobs) JOBS=$2; shift 2 ;;
        --budget) BUDGET=$2; shift 2 ;;
        --seed) SEED=$2; shift 2 ;;
        --mem) MEM=$2; shift 2 ;;
        --timeout) HARD_TIMEOUT=$2; shift 2 ;;
        --max-attempts) MAX_ATTEMPTS=$2; shift 2 ;;
        --sf100) SF100=$2; shift 2 ;;
        --out) OUT_ROOT=$2; shift 2 ;;
        -h|--help) usage ;;
        *) echo "unknown option: $1"; usage ;;
    esac
done

[ -n "$TOOL" ] && [ -n "$MANIFEST" ] || usage
case "$TOOL" in
    og)    JAR=${JAR:-$HERE/evosuite-original-1.1.0.jar}; LABEL=${LABEL:-original} ;;
    emote) JAR=${JAR:-$HERE/emote.jar};                    LABEL=${LABEL:-muse} ;;
    *)     [ -n "$JAR" ] || { echo "--jar is required for --tool $TOOL"; exit 1; }
           LABEL=${LABEL:-$TOOL} ;;
esac
HARD_TIMEOUT=${HARD_TIMEOUT:-$((3 * BUDGET + 180))}

# absolute paths: each run executes in its own scratch directory
abspath() { (cd "$(dirname "$1")" && echo "$(pwd)/$(basename "$1")"); }
JAR=$(abspath "$JAR"); MANIFEST=$(abspath "$MANIFEST")
SF100=$(cd "$SF100" && pwd); mkdir -p "$OUT_ROOT"; OUT_ROOT=$(cd "$OUT_ROOT" && pwd)
[ -f "$JAR" ] || { echo "jar not found: $JAR"; exit 1; }

RUN_DIR="$OUT_ROOT/${LABEL}-trial-${TRIAL}"
SCRATCH="$RUN_DIR/.scratch"
mkdir -p "$RUN_DIR" "$SCRATCH"
LOG="$RUN_DIR/runs.tsv"
[ -f "$LOG" ] || printf 'project\tclass\tmethod\tstatus\texit\tseconds\tattempt\n' > "$LOG"

export LOG_LIMIT OK_LOG_LIMIT JAVA JAR SF100 RUN_DIR SCRATCH LOG BUDGET A_BUDGET SEED MEM HARD_TIMEOUT MAX_ATTEMPTS

# ---- one EvoSuite run; called by xargs with: project class method ----
run_one() {
    local proj=$1 class=$2 method=$3
    local proj_dir="$SF100/$proj"
    local out_dir="$RUN_DIR/$proj/$class/${method//\//_}"

    [ -f "$out_dir/statistics.csv" ] && return 0
    mkdir -p "$out_dir"
    local attempts=0
    [ -f "$out_dir/.attempts" ] && attempts=$(cat "$out_dir/.attempts")
    [ "$attempts" -ge "$MAX_ATTEMPTS" ] && return 0
    attempts=$((attempts + 1)); echo "$attempts" > "$out_dir/.attempts"

    # classpath: top-level project jars + lib/*.jar (same as run_evo.sh)
    local cp="" j
    for j in "$proj_dir"/*.jar "$proj_dir"/lib/*.jar; do
        [ -f "$j" ] && cp="${cp:+$cp:}$j"
    done

    local work; work=$(mktemp -d "$SCRATCH/run.XXXXXX")
    local start=$SECONDS rc
    # timeout signals its whole process group, so EvoSuite's client JVM dies too
    ( cd "$work" && timeout --kill-after=30 "$HARD_TIMEOUT" \
        "$JAVA" -cp "$JAR" shaded.org.evosuite.EvoSuite \
            -class "$class" \
            -projectCP "$cp" \
            -seed "$SEED" \
            -Dsearch_budget="$BUDGET" \
            -Dassertion_timeout="$A_BUDGET" \
            -Dtest_dir="$out_dir" \
            -Dtarget_method="$method" \
            -criterion branch \
            -Dshow_progress=false \
            -Djunit_check=false \
            -Dfilter_assertions=false \
            -Dtest_comments=false \
            -mem "$MEM" \
            -Dsort_calls \
            -Dtimeline_interval=15000 \
            -Dreport_dir="$work/report" \
        2>&1 | head -c "$LOG_LIMIT" > "$out_dir/evosuite.log"; exit "${PIPESTATUS[0]}" )
    rc=$?
    local secs=$((SECONDS - start)) status

    if [ -f "$work/report/statistics.csv" ]; then
        mv "$work/report/statistics.csv" "$out_dir/"
        status=ok
        truncate -s "<$OK_LOG_LIMIT" "$out_dir/evosuite.log" 2>/dev/null
    elif [ $rc -eq 124 ] || [ $rc -eq 137 ]; then
        status=timeout
    else
        status=fail
    fi
    rm -rf "$work"
    # per-target status file is the reliable record; runs.tsv is a convenience log
    # (concurrent appends can lose or mix lines on network filesystems such as NFS)
    printf '%s\t%s\t%s\n' "$status" "$rc" "$secs" > "$out_dir/.status"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$proj" "$class" "$method" "$status" "$rc" "$secs" "$attempts" >> "$LOG"
    echo "[$status ${secs}s] $proj $class $method"
}
export -f run_one

# keep only well-formed lines (3 tab-separated fields); a blank or broken line
# would shift every later (project, class, method) triple
CLEAN="$RUN_DIR/.manifest.tsv"
awk -F'\t' 'NF==3 && $1!="" && $2!="" && $3!=""' "$MANIFEST" > "$CLEAN"
skipped=$(( $(grep -c '' "$MANIFEST") - $(grep -c '' "$CLEAN") ))
[ "$skipped" -gt 0 ] && echo "WARNING: skipped $skipped blank or malformed manifest lines"
total=$(grep -c . "$CLEAN")
echo "tool=$LABEL trial=$TRIAL jar=$(basename "$JAR") budget=${BUDGET}s timeout=${HARD_TIMEOUT}s jobs=$JOBS targets=$total"
echo "output: $RUN_DIR"

# manifest is tab-separated: project, class, method
tr '\t' '\n' < "$CLEAN" | xargs -d '\n' -n 3 -P "$JOBS" bash -c 'run_one "$@"' _

rmdir "$SCRATCH" 2>/dev/null
done_n=$(find "$RUN_DIR" -name statistics.csv | wc -l)
echo
echo "Finished: $done_n / $total targets have statistics.csv"
echo "Status of last attempt per target (from .status files):"
find "$RUN_DIR" -name .status -exec cut -f1 {} + | sort | uniq -c
