#!/usr/bin/env python3
"""Turn a repository's Almanack and JOSS results into an HTML recommendations report.

The report is advisory, so the calling process ignores failures: every error path still
writes an HTML file explaining what went wrong rather than leaving the output missing.

Which model produces the report is configuration, not a property of the pipeline. The
provider and model id are read from LLM_PROVIDER and LLM_MODEL, and each provider is one
function in PROVIDERS, so supporting another one means adding a function rather than
editing the report logic. Only the request and the response unwrapping differ between
providers; the prompt and the output do not.
"""

import json
import os
import sys

# Report length is bounded by the model's output limit, so this needs headroom: a truncated
# response is still valid-looking HTML and fails silently rather than raising.
MAX_TOKENS = 8192

DEFAULT_MODELS = {"anthropic": "claude-sonnet-4-6"}


def _call_anthropic(prompt: str, model: str) -> str:
    """Send one prompt to the Anthropic Messages API.

    Args:
        prompt: The full user turn.
        model: A model id the Messages API accepts.

    Returns:
        The concatenated text blocks of the response. Indexing the first block would drop
        text that follows a non-text block, and would raise if the first block is not text.

    Raises:
        KeyError: If ANTHROPIC_API_KEY is unset, which the caller turns into a report.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


# Every entry takes (prompt, model) and returns the response text, so the report logic never
# sees a provider-specific client, request shape or response object.
PROVIDERS = {"anthropic": _call_anthropic}


def call_model(prompt: str) -> str:
    """Send one prompt to the configured provider and return its text.

    Args:
        prompt: The full user turn.

    Returns:
        The response text.

    Raises:
        ValueError: If LLM_PROVIDER names a provider that has no entry in PROVIDERS. Failing
            beats falling back to the default, which would silently bill the wrong account
            and label the report with the wrong model. A plain exception rather than
            SystemExit, so the caller's handler still writes a report naming the cause.
    """
    # `or` rather than a get default: docker -e passes a set-but-empty variable through as an
    # empty string, which would otherwise be treated as a provider name and rejected.
    provider = os.environ.get("LLM_PROVIDER") or "anthropic"
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown LLM_PROVIDER {provider!r}; available: {', '.join(sorted(PROVIDERS))}"
        )
    return PROVIDERS[provider](prompt, os.environ.get("LLM_MODEL") or DEFAULT_MODELS[provider])


def build_prompt(repo_url: str, almanack_results: dict, joss_report: dict) -> str:
    """Assemble the analysis request for one repository.

    Args:
        repo_url: The repository the report is about.
        almanack_results: The parsed Almanack metrics.
        joss_report: The parsed JOSS criteria evaluation.

    Returns:
        The prompt, with both result sets embedded as indented JSON.
    """
    return f"""You are a scientific software sustainability expert. Analyze the following \
repository and provide actionable recommendations to improve its sustainability and \
community adoption.

Repository: {repo_url}

Almanack sustainability metrics:
{json.dumps(almanack_results, indent=2)}

JOSS criteria evaluation:
{json.dumps(joss_report, indent=2)}

Please provide your analysis as a well-structured HTML report that includes:
1. A summary of the repository's current sustainability status
2. Specific strengths to highlight
3. Prioritized, concrete improvement recommendations (focus on license, citability, \
documentation, and contribution infrastructure)
4. Estimated impact of each recommendation on community adoption

Return only valid HTML."""


def write_error_report(output_file: str, message: str, detail: str = "") -> None:
    """Write the failure report that stands in for the analysis.

    Args:
        output_file: Path to write.
        message: The one-line explanation shown to a reader.
        detail: Optional preformatted detail, such as a traceback.
    """
    body = f"<h1>Error in AI Analysis</h1><p>{message}</p>"
    if detail:
        body += f"<pre>{detail}</pre>"
    with open(output_file, "w") as f:
        f.write(f"<html><body>{body}</body></html>")


if __name__ == "__main__":
    repo_name = sys.argv[1]
    repo_url = sys.argv[2]
    almanack_results_file = sys.argv[3]
    joss_report_file = sys.argv[4]
    output_file = f"{repo_name}_ai_analysis.html"

    try:
        with open(almanack_results_file) as f:
            almanack_results = json.load(f)
        with open(joss_report_file) as f:
            joss_report = json.load(f)

        response_html = call_model(build_prompt(repo_url, almanack_results, joss_report))

        with open(output_file, "w") as f:
            f.write(response_html)
        print(f"[SUCCESS] AI analysis written to {output_file}")

    except KeyError as e:
        error_msg = f"Missing environment variable: {str(e)}"
        print(f"[ERROR] {error_msg}")
        write_error_report(output_file, error_msg)
        sys.exit(1)
    except Exception as e:
        import traceback

        error_msg = str(e)
        print(f"[ERROR] Analysis failed: {error_msg}")
        write_error_report(output_file, error_msg, traceback.format_exc())
        sys.exit(1)
