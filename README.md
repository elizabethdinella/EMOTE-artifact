## EMOTE: Effective Modular Testing with EvoSuite

This repository contains the evaluation artifact for EMOTE, a modification to EvoSuite's
modular testing mode that allows test prefixes to include setup calls to non-target methods.

The EMOTE source code is at [elizabethdinella/emote](https://github.com/elizabethdinella/emote).
The built jar is included in this repository.

### Versions

Each paper has a tag pointing to the exact version of the artifact used for its results.

| Tag | Paper |
|-----|-------|
| `soap26` | Elizabeth Dinella. *On the Effectiveness of Modular Testing in EvoSuite.* SOAP 2026. [DOI](https://doi.org/10.1145/3814987.3814989), [arXiv](https://arxiv.org/abs/2604.27112) |
| `sttt26` | Extended version of the SOAP paper (under review) |

To use the artifact for the SOAP 2026 paper:

```
git clone https://github.com/elizabethdinella/EMOTE-artifact
cd EMOTE-artifact
git checkout soap26
```

This repository was previously named `SOAP-2-artifact`. Links to the old name redirect here.

### Reproducing the SOAP 2026 results

The `soap26` version contains:
1. Target benchmark jars (the first five projects of SF100)
2. EvoSuite jars (plain EvoSuite 1.1.0 and EMOTE, as `muse.jar`)
3. Evaluation script (`eval.py`)
4. Tests from our evaluation (`outputs.zip`)

To reproduce the evaluation, first run `setup.sh` to expand the SF100 jar files.
Next, run `run_evo.sh`, setting the flags for which EvoSuite jar to use (`OG`).

Prerequisites are included in the Dockerfile. To run without Docker, you need:
- Java 11.0.11
- Python 3

### Reproducing the STTT 2026 results

The `sttt26` version extends the evaluation to all 100 SF100 projects. It contains:
1. EvoSuite jars (plain EvoSuite 1.1.0 and EMOTE, as `emote.jar`)
2. Runner scripts (`run_evo_sf100.sh`, `run_evo_timeline.sh`)
3. Target method manifests (`manifests/`)
4. Analysis scripts (`scripts/`)
5. The analysis outputs used in the paper (`results/`)

Prerequisites are included in the Docerfile. To run without Docker, you need:
- Java 11.0.11
- Python 3 
- Pip libraries: `numpy`, `scipy`, `matplotlib`, and `javalang` 

**Setup.** Download the [SF100 benchmark](https://www.evosuite.org/experimental-data/sf100/) into `SF100/` and run `setup_sf100.sh`.

**Running the tools.** Each tool runs three trials on the 4,697 sampled methods (120 s budget, seed 47):

```
for k in 1 2 3; do
  ./run_evo_sf100.sh --tool og    --trial $k --manifest manifests/sf100.tsv
  ./run_evo_sf100.sh --tool emote --trial $k --manifest manifests/sf100.tsv
done
```

Results go to `outputs/original-trial-<k>/` (EvoSuite) and `outputs/muse-trial-<k>/` For projects 1–5, the paper reuses the SOAP 2026 runs from `outputs.zip`.

**RQ1 (Table 1, Figure 4, Table 4) and RQ4.**
```
python3 scripts/make_results.py \
  --og outputs/original-trial-1 --og outputs/original-trial-2 --og outputs/original-trial-3 \
  --emote outputs/muse-trial-1 --emote outputs/muse-trial-2 --emote outputs/muse-trial-3 \
  --out-dir results
```

**Figure 5.**
```
./run_evo_timeline.sh --tool og    --trial 1 --manifest manifests/timeline.tsv --out outputs-timeline
./run_evo_timeline.sh --tool emote --trial 1 --manifest manifests/timeline.tsv --out outputs-timeline
python3 scripts/plot_timeline.py --og outputs-timeline/original-trial-1 \
  --emote outputs-timeline/muse-trial-1 --interval 5 --out results/timeline.pdf
```

**RQ2 (ablation).** Build the ablation in the EMOTE repository with `scripts/make_ablation.py` (instructions in the script), copy the jar here as `ablation.jar`, then:
```
./run_evo_sf100.sh --tool ablation --jar ablation.jar --trial 1 --manifest manifests/sf100.tsv
python3 scripts/remeasure.py --run outputs/ablation-trial-1 --jar emote.jar \
  --manifest manifests/sf100.tsv --out results/remeasure_ablation_modular.tsv
python3 scripts/rq2.py --remeasure results/remeasure_ablation_modular.tsv \
  --ablation outputs/ablation-trial-1 --emote outputs/muse-trial-1 --projects 6-100
```

**RQ3 (Tables 2 and 3).**
```
python3 scripts/setup_calls.py --run outputs/muse-trial-1 --baseline outputs/original-trial-1 \
  --methods results/per_method.csv --calls-out results/calls.tsv --latex
```
