#!/usr/bin/env python3
"""Classify tool domains using Claude (Anthropic API). Requires ANTHROPIC_API_KEY."""

import argparse
import base64
import csv
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import pandas as pd
import requests

DOMAIN_CATEGORIES = [
    "RNA-seq",
    "Single-cell",
    "Genomics",
    "Proteomics",
    "Metagenomics",
    "Epigenomics",
    "Structural Biology",
    "Phylogenetics",
    "Imaging",
    "Other",
]

CLASSIFICATION_PROMPT_TEMPLATE = """You are a bioinformatics expert. Classify the following bioinformatics tool into ONE of these categories:

Categories:
- RNA-seq: Tools for RNA sequencing analysis, differential expression, transcriptomics
- Single-cell: Tools for single-cell RNA-seq, ATAC-seq, or other single-cell omics
- Genomics: Tools for genome assembly, variant calling, sequencing alignment, genome analysis
- Proteomics: Tools for mass spectrometry, protein analysis, peptide identification
- Metagenomics: Tools for microbiome analysis, 16S sequencing, metagenomic assembly
- Epigenomics: Tools for ChIP-seq, ATAC-seq, methylation analysis, chromatin analysis
- Structural Biology: Tools for protein structure prediction, molecular dynamics, docking, PDB analysis
- Phylogenetics: Tools for phylogenetic tree construction, evolutionary analysis
- Imaging: Tools for microscopy image analysis, cell segmentation, image processing
- Other: If the tool doesn't clearly fit any of the above categories

Tool name: {tool_name}

README content:
{readme_content}

Respond with ONLY the category name (e.g., "RNA-seq" or "Structural Biology"). Do not include any explanation or markdown formatting."""


def normalize_tool_name(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_")


def get_repo_url_from_csv(repos_csv: str, tool_name: str) -> Optional[str]:
    try:
        with open(repos_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                repo_url = row.get("repo_url", "").strip()
                if not repo_url:
                    continue
                repo_name = repo_url.split("/")[-1].replace(".git", "")
                if normalize_tool_name(repo_name) == normalize_tool_name(tool_name):
                    return repo_url
    except Exception:
        pass
    return None


def fetch_readme_from_github(repo_url: str, github_token: Optional[str] = None) -> Optional[str]:
    parsed = urlparse(repo_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        return None
    owner, repo = path_parts[0], path_parts[1].replace(".git", "")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    try:
        r = requests.get(api_url, headers=headers, timeout=10)
        if r.status_code == 200:
            return (r.text or "")[:8000]
        if r.status_code == 404:
            for name in ["README.md", "readme.md", "README.txt", "README.rst"]:
                alt = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{name}",
                    headers=headers,
                    timeout=10,
                )
                if alt.status_code == 200 and isinstance(alt.json(), dict):
                    d = alt.json()
                    if "content" in d and "encoding" in d:
                        return base64.b64decode(d["content"]).decode("utf-8", errors="ignore")[:8000]
    except Exception:
        pass
    return None


def extract_readme(
    results_dir: str,
    tool_name: str,
    repos_csv: str,
    github_token: Optional[str] = None,
) -> Optional[str]:
    if results_dir and results_dir != ".":
        results_path = Path(results_dir)
        for tool_dir in [results_path / tool_name, results_path / f"{tool_name}_repo"]:
            if tool_dir.exists():
                for name in ["repo/README.md", "repo/readme.md", "repo/README.txt", "repo/README.rst"]:
                    p = tool_dir / name
                    if p.exists():
                        try:
                            return p.read_text(encoding="utf-8", errors="ignore")[:8000]
                        except Exception:
                            pass
    repo_url = get_repo_url_from_csv(repos_csv, tool_name)
    if repo_url:
        return fetch_readme_from_github(repo_url, github_token)
    return None


def classify_with_claude(
    readme_content: str,
    tool_name: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> Optional[str]:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise SystemExit("Install anthropic: pip install anthropic")

    client = Anthropic(api_key=api_key)
    prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        readme_content=(readme_content or "(no README)")[:6000],
    )
    msg = client.messages.create(
        model=model,
        max_tokens=64,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in msg.content:
        if hasattr(block, "text"):
            text += block.text
    classification = text.strip().strip('"\'')
    if classification.startswith("```"):
        lines = classification.split("\n")
        classification = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
    classification = classification.strip('"\'')
    if classification in DOMAIN_CATEGORIES:
        return classification
    classification_lower = classification.lower()
    for cat in DOMAIN_CATEGORIES:
        if cat.lower() in classification_lower or classification_lower in cat.lower():
            return cat
    return "Other"


def main():
    parser = argparse.ArgumentParser(description="Classify tool domains with Claude")
    parser.add_argument("--aggregated_csv", required=True)
    parser.add_argument("--repos_csv", required=True)
    parser.add_argument("--results_dir", default="")
    parser.add_argument("--output_csv", required=True)
    parser.add_argument("--github_token", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only_other", action="store_true")
    parser.add_argument("--batch_size", type=int, default=20)
    parser.add_argument("--delay_seconds", type=float, default=1.0)
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--verbose", action="store_true", help="Print each tool")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY")

    df = pd.read_csv(args.aggregated_csv)
    if "domain" not in df.columns:
        df["domain"] = "Other"

    to_process = (
        df[df["domain"] == "Other"].index.tolist()
        if args.only_other
        else df.index.tolist()
    )
    if args.limit:
        to_process = to_process[: args.limit]
    n = len(to_process)

    if not args.github_token and not os.environ.get("GITHUB_TOKEN"):
        print("WARNING: No GitHub token set. README fetches will hit rate limits after ~60 requests.")
        print("  Set --github_token or export GITHUB_TOKEN to classify all tools properly.")

    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")
    results_dir = args.results_dir if args.results_dir and Path(args.results_dir).exists() else ""
    for i, idx in enumerate(to_process):
        tool_name = str(df.at[idx, "tool_name"])
        readme = extract_readme(results_dir or ".", tool_name, args.repos_csv, github_token)
        df.at[idx, "domain"] = classify_with_claude(
            readme or "", tool_name, api_key, model=args.model
        ) or "Other"
        if args.verbose:
            print(f"{i+1}/{n} {tool_name} -> {df.at[idx, 'domain']}")
        elif (i + 1) % args.batch_size == 0:
            print(f"{i+1}/{n}")
        if (i + 1) % args.batch_size == 0:
            df.to_csv(args.output_csv, index=False)
        time.sleep(args.delay_seconds)

    df.to_csv(args.output_csv, index=False)
    print(f"Wrote {args.output_csv} ({n} tools)")
    print(df["domain"].value_counts().to_string())


if __name__ == "__main__":
    main()
