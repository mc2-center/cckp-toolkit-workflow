#!/usr/bin/env python3
"""Record whether each cohort repository is owned by an organization or an individual.

Author: Dave Bunten (ORCID 0000-0001-6041-3665).

Section 4.3 argues that shared infrastructure raises sustainability, evidenced by nf-core
adoption and by portfolio rescoring. Owner type gives a cohort-wide version of the same
question at no analytical cost: organization accounts carry shared conventions, review
practice and continuity across maintainers, where a personal account usually does not.

GitHub exposes the distinction as the owner's type. The original implementation fetches it one
repository at a time, one REST request each; the same field is available through GraphQL, so
batching 100 repositories per query covers the cohort in about 110 requests.

Keys results on the slug that was requested rather than the one returned. GitHub silently
resolves renamed repositories, so trusting the response name drops every renamed repository
from the join.
"""

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH = 100


def build_query(slugs: list[str]) -> str:
    parts = []
    for i, slug in enumerate(slugs):
        owner, name = slug.split("/", 1)
        parts.append(
            f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
            f"{{ nameWithOwner owner {{ __typename login }} }}"
        )
    return "query {\n" + "\n".join(parts) + "\n}"


def run_batch(slugs: list[str]) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={build_query(slugs)}"],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        print(f"  batch failed: {result.stderr.strip()[:150]}")
        return []
    rows = []
    for alias, entry in (json.loads(result.stdout).get("data") or {}).items():
        requested = slugs[int(alias[1:])]
        if not entry:
            rows.append({"canonical_repo": requested, "owner_type": None})
            continue
        owner = entry.get("owner") or {}
        rows.append(
            {
                "canonical_repo": requested,
                "owner_login": owner.get("login"),
                "owner_type": owner.get("__typename"),
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--metrics_csv", default="data/final_results/combined_almanack_joss_static_tests.csv"
    )
    ap.add_argument("--output", default="data/final_results/owner_type.csv")
    args = ap.parse_args()

    frame = pd.read_csv(REPO_ROOT / args.metrics_csv, low_memory=False)
    slugs = sorted(frame["canonical_repo"].dropna().unique())
    print(f"fetching owner type for {len(slugs)} repositories")

    rows = []
    for start in range(0, len(slugs), BATCH):
        rows.extend(run_batch(slugs[start : start + BATCH]))
        if (start // BATCH) % 20 == 0:
            print(f"  {min(start + BATCH, len(slugs))}/{len(slugs)}", flush=True)

    out = pd.DataFrame(rows)
    path = REPO_ROOT / args.output
    out.to_csv(path, index=False)
    print(f"\nresolved {int(out['owner_type'].notna().sum())} of {len(out)}")
    print(out["owner_type"].value_counts(dropna=False).to_string())
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
