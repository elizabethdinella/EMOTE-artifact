#!/usr/bin/env bash
# Extract the project jars of every SF100 project so their .class files can be
# listed as targets. Generalizes setup.sh to all 100 projects.
#
# Expects the SF100 layout used in this repo:  SF100/<N>_<name>/*.jar  (+ lib/*.jar)
# Projects that already contain extracted .class files (e.g. 1-5 after setup.sh)
# are left untouched so the SOAP target set does not change.
#
# Usage: ./setup_sf100.sh [SF100_DIR]
set -u
SF100=${1:-SF100}

for proj_dir in "$SF100"/[0-9]*_*/; do
    proj_dir=${proj_dir%/}
    if find "$proj_dir" -name '*.class' -not -path "$proj_dir/lib/*" -print -quit | grep -q .; then
        echo "skip (already extracted): $proj_dir"
        continue
    fi
    shopt -s nullglob
    jars=("$proj_dir"/*.jar)
    shopt -u nullglob
    if [ ${#jars[@]} -eq 0 ]; then
        echo "WARNING: no top-level jar in $proj_dir"
        continue
    fi
    for jar in "${jars[@]}"; do
        echo "extract: $jar"
        (cd "$proj_dir" && jar xf "$(basename "$jar")") || echo "WARNING: failed to extract $jar"
    done
done
