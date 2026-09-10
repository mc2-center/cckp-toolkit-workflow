#!/usr/bin/env python3

import json
import os
import sys

import anthropic


def call_claude(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=4096, messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


if __name__ == "__main__":
    repo_name = sys.argv[1]
    repo_url = sys.argv[2]
    almanack_results_file = sys.argv[3]
    joss_report_file = sys.argv[4]

    try:
        with open(almanack_results_file) as f:
            almanack_results = json.load(f)
        with open(joss_report_file) as f:
            joss_report = json.load(f)

        prompt = f"""You are a scientific software sustainability expert. Analyze the following repository and provide actionable recommendations to improve its sustainability and community adoption.

Repository: {repo_url}

Almanack sustainability metrics:
{json.dumps(almanack_results, indent=2)}

JOSS criteria evaluation:
{json.dumps(joss_report, indent=2)}

Please provide your analysis as a well-structured HTML report that includes:
1. A summary of the repository's current sustainability status
2. Specific strengths to highlight
3. Prioritized, concrete improvement recommendations (focus on license, citability, documentation, and contribution infrastructure)
4. Estimated impact of each recommendation on community adoption

Return only valid HTML."""

        response_html = call_claude(prompt)

        output_file = f"{repo_name}_ai_analysis.html"
        with open(output_file, "w") as f:
            f.write(response_html)
        print(f"[SUCCESS] AI analysis written to {output_file}")

    except KeyError as e:
        error_msg = f"Missing environment variable: {str(e)}"
        print(f"[ERROR] {error_msg}")
        output_file = f"{repo_name}_ai_analysis.html"
        with open(output_file, "w") as f:
            f.write(f"<html><body><h1>Error in AI Analysis</h1><p>{error_msg}</p></body></html>")
        sys.exit(1)
    except Exception as e:
        import traceback

        error_msg = str(e)
        print(f"[ERROR] Analysis failed: {error_msg}")
        output_file = f"{repo_name}_ai_analysis.html"
        with open(output_file, "w") as f:
            f.write(
                f"<html><body><h1>Error in AI Analysis</h1><p>{error_msg}</p><pre>{traceback.format_exc()}</pre></body></html>"
            )
        sys.exit(1)
