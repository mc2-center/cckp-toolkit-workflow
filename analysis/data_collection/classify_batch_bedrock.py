#!/usr/bin/env python3
"""Classify tools by domain using Claude via AWS Bedrock; writes tool_name,domain CSV."""
import json
import sys
import time
import pandas as pd
import boto3

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

CLASSIFICATION_PROMPT = """You are a bioinformatics expert. Classify the following bioinformatics tool into ONE of these categories:

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

Description:
{text}

Respond with ONLY the category name (e.g., "RNA-seq" or "Structural Biology"). Do not include any explanation or markdown formatting."""


def classify_tool(bedrock_client, tool_name: str, text: str, model_id: str) -> str:
    """Classify a single tool using Claude via Bedrock."""
    prompt = CLASSIFICATION_PROMPT.format(tool_name=tool_name, text=text[:4000])

    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        })

        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body
        )

        response_body = json.loads(response['body'].read())
        domain = response_body['content'][0]['text'].strip()

        if domain not in DOMAIN_CATEGORIES:
            domain_lower = domain.lower()
            for cat in DOMAIN_CATEGORIES:
                if cat.lower() in domain_lower or domain_lower in cat.lower():
                    return cat
            return "Other"
        return domain
    except Exception as e:
        print(f"  ERROR classifying {tool_name}: {e}", file=sys.stderr)
        return "Other"


def classify_batch(
    input_csv: str,
    output_csv: str,
    model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    delay: float = 0.1
):
    """Classify all tools in input CSV and write results."""
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')

    df = pd.read_csv(input_csv)
    print(f"Classifying {len(df)} tools from {input_csv}")
    print(f"Using model: {model_id}")

    results = []
    for i, row in df.iterrows():
        tool_name = row['tool_name']
        text = row['text']

        domain = classify_tool(bedrock_client, tool_name, text, model_id)
        results.append({'tool_name': tool_name, 'domain': domain})

        if (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(df)}] {tool_name}: {domain}")

        time.sleep(delay)

    out_df = pd.DataFrame(results)
    out_df.to_csv(output_csv, index=False)
    print(f"\nWrote {len(out_df)} classifications to {output_csv}")
    print(f"\nDomain distribution:")
    print(out_df['domain'].value_counts().to_string())


if __name__ == "__main__":
    if len(sys.argv) not in [3, 4]:
        print(f"Usage: {sys.argv[0]} <input_csv> <output_csv> [model_id]")
        print(f"Default model: us.anthropic.claude-sonnet-4-5-20250929-v1:0")
        sys.exit(1)

    model_id = sys.argv[3] if len(sys.argv) == 4 else "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    classify_batch(sys.argv[1], sys.argv[2], model_id)
