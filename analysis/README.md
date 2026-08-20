# Analysis code

Reproducible analysis for the accompanying manuscript.
It consumes the per-repository measurements produced by the Cancer Complexity Toolkit (CCT) Nextflow pipeline (in the repository root) and produces the statistics and figures in the paper.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/) via `analysis/pyproject.toml`, and `analysis/uv.lock` pins the exact versions last used for the manuscript.

```bash
# from the repository root
uv sync --project analysis                          # core deps (figures/modeling)
uv sync --project analysis --extra data-collection  # add repo discovery / classification deps
```

Run any code through uv so it uses the locked environment; work **from the repository root** so relative default paths resolve:

```bash
uv run --project analysis python analysis/modeling/stars_shap_model.py --help
```

All code uses argparse with sensible defaults.
Pass `--help` to any script to see its options.

## Data

The code reads from and writes to `data/final_results/`.
That directory is intentionally **ignored** (it holds large derived data).
Ignored data is released separately with the manuscript.
Once the archive is deposited, its DOI is recorded in the repository's `CITATION.cff` (under `references:`) and in the Data and Code Availability section of the paper.
To reproduce, download the released data bundle and place it at `data/final_results/` so the default paths resolve.
Key files:

| File | Contents |
|---|---|
| `almanack_metrics.csv` | One row per tool, all Almanack metrics (built from the CCT JSON outputs) |
| `combined_almanack_full_classified_with_joss.csv` | Full joined table: Almanack checks + JOSS scores + CZI mentions + domain labels (the canonical analysis table) |
| `aggregated_data_llm_classified.csv` | `tool_name`, `domain` (LLM-classified) |
| `weights_logistic_refit.csv` | nf-core-calibrated logistic weights per check |
| `nf_core_almanack_metrics.csv` | Almanack metrics for nf-core pipelines |

Some code consumes **raw inputs that are not in the data bundle** because they are large or regenerable: the per-repo Almanack JSON directory (CCT pipeline output) consumed by `build_almanack_metrics_table.py`.
All data needed for the figures is in the released tables.

## Pipeline (run order)

```mermaid
flowchart TD
    dc["<b>data_collection/</b><br/>discover repos, link CZI/PubMed, classify domains"]
    cct[["CCT Nextflow pipeline runs each repo<br/>&rarr; Almanack + JOSS JSONs"]]
    dp["<b>data_processing/</b><br/>build feature table, add literature signals, merge, weight, verify"]
    md["<b>modeling/</b><br/>gradient-boosting + SHAP (adoption predictors), domain analysis"]
    vis["<b>visualization/</b><br/>manuscript figures"]

    dc --> cct --> dp --> md --> vis
```

## Which code produces which result

Described by output content rather than manuscript figure numbers, which can change as the manuscript is revised.

| Result | Script |
|---|---|
| Conceptual framework; cohort funnel | `visualization/generate_conceptual_figures.py` |
| Check pass rates; domain violin | `visualization/generate_results_figures.py` |
| SHAP adoption predictors (stars) | `modeling/stars_shap_model.py` |
| Mentions panel / robustness | `modeling/mentions_shap_model.py` |
| Longitudinal evolution, grading | `visualization/benchmark_analysis.py` |
| Domain ANOVA + residuals | `modeling/stars_domain_analysis.py`, `data_processing/apply_logistic_weights_and_domain_anova.py`, `modeling/weighted_scores_statistical_analysis.py` |
| Score distributions (supplementary) | `visualization/plot_almanack_score_distributions.py` |

## Reproducing the headline results

```bash
# Sustainability-only adoption predictors (license, citability, modern branch top-ranked)
uv run --project analysis python analysis/modeling/stars_shap_model.py --sustainability_only

# Full adoption model (social signals included)
uv run --project analysis python analysis/modeling/stars_shap_model.py

# Domain analysis
uv run --project analysis python analysis/modeling/stars_domain_analysis.py

# Check pass rates + domain violin
uv run --project analysis python analysis/visualization/generate_results_figures.py
```

Outputs land in `data/final_results/` (tables) and `docs/manuscript_drafts/figures/` (figures).

## Notes

- **Run from the repository root** so relative default paths (`data/final_results/...`) resolve.
- **API keys** are loaded from a git-ignored `.env` file (or the real environment), never hardcoded.
  Copy `.env.template` (repo root) to `.env` and fill in what you need: `GITHUB_TOKEN` and `ANTHROPIC_API_KEY` for the data-collection/classification scripts, plus `GEMINI_API_KEY` / `OPENAI_API_KEY` for the alternate classifiers in `analysis/archive/`.
- Personal/operational scripts (S3 reparse, shell helpers) and superseded data-assembly steps (`recompute_logistic_weights`, `combine_external_datasets`) live in `analysis/archive/` and are not needed to reproduce the paper; the tables they would produce are in the released bundle.
- Domains were classified with `data_collection/classify_domains_primary.py` (primary, Anthropic API) and `data_collection/classify_domains_other.py` ("Other" bucket, via Bedrock).
  Alternate LLM-provider classifiers that were not used live in `analysis/archive/`.
- Random seeds are fixed (42) and bootstrap/permutation steps are seeded, so results are deterministic.
