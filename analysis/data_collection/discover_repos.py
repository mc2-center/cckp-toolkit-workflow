#!/usr/bin/env python3
"""Discover bioinformatics repositories from GitHub; writes a repo_url CSV."""

import argparse
import csv
import os
import sys
import requests
import time
from typing import List, Set
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()  # pull GITHUB_TOKEN from a .env file if present


def search_github_repos(query: str, token: str, max_results: int = 1000) -> List[dict]:
    repos = []
    page = 1
    per_page = 100

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    while len(repos) < max_results:
        url = f"https://api.github.com/search/repositories?q={quote(query)}&per_page={per_page}&page={page}&sort=stars"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if not data.get('items'):
                break

            for item in data['items']:
                repos.append({
                    'full_name': item['full_name'],
                    'html_url': item['html_url'],
                    'stars': item['stargazers_count'],
                    'language': item.get('language', 'Unknown'),
                    'description': item.get('description', ''),
                    'created_at': item['created_at'],
                    'updated_at': item['updated_at']
                })

            remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
            if remaining < 10:
                print(f"Rate limit low: {remaining} requests remaining")
                time.sleep(60)

            if len(data['items']) < per_page:
                break

            page += 1
            time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page}: {e}")
            break
    
    return repos[:max_results]


def discover_bioinformatics_repos(token: str, min_stars: int = 10) -> Set[str]:
    """Run several GitHub searches and return a set of repo URLs (owner/repo.git)."""
    repos = set()

    queries = [
        'topic:bioinformatics',
        'topic:computational-biology',
        'topic:genomics',
        'topic:rna-seq',
        'topic:differential-expression',
        'topic:single-cell',
        'bioinformatics language:python',
        'bioinformatics language:r',
        'genomics analysis language:python',
        'rna-seq analysis language:python',
    ]

    print(f"Discovering repositories with minimum {min_stars} stars...")

    for query in queries:
        print(f"Searching: {query}")
        search_query = f"{query} stars:>={min_stars}"
        results = search_github_repos(search_query, token, max_results=100)

        for repo in results:
            if repo['stars'] >= min_stars:
                repo_url = f"{repo['html_url']}.git"
                repos.add(repo_url)
                print(f"  Found: {repo['full_name']} ({repo['stars']} stars)")

        time.sleep(1)

    print(f"\nTotal unique repositories found: {len(repos)}")
    return repos


def save_to_csv(repos: Set[str], output_file: str):
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['repo_url'])
        for repo_url in sorted(repos):
            writer.writerow([repo_url])

    print(f"Saved {len(repos)} repositories to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Discover bioinformatics repositories from GitHub')
    parser.add_argument('--token', 
                       default=None,
                       help='GitHub personal access token (or set GITHUB_PAT/GH_PATH environment variable)')
    parser.add_argument('--output', default='discovered_repos.csv', help='Output CSV file')
    parser.add_argument('--min-stars', type=int, default=10, help='Minimum stars (default: 10)')
    
    args = parser.parse_args()

    token = args.token or os.getenv('GITHUB_TOKEN') or os.getenv('GITHUB_PAT') or os.getenv('GH_PATH')

    if not token:
        print("ERROR: GitHub token required!")
        print("  Set environment variable: export GITHUB_PAT=your_token")
        print("  Or use --token argument: --token your_token")
        sys.exit(1)

    repos = discover_bioinformatics_repos(token, min_stars=args.min_stars)
    save_to_csv(repos, args.output)

    print(f"\nDone! Next steps:")
    print(f"1. Review {args.output}")
    print(f"2. Validate repositories: python scripts/validate_repos.py --input {args.output}")
    print(f"3. Generate sample sheets: python scripts/generate_sample_sheets.py --input {args.output}")
    print(f"\nNote: Token was read from environment variable or command line argument")


if __name__ == '__main__':
    main()

