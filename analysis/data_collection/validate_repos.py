#!/usr/bin/env python3
"""Validate repo_url entries in a CSV; optionally write valid URLs to an output CSV."""

import argparse
import csv
import re
import sys
from urllib.parse import urlparse


def validate_repo_url(url: str) -> tuple[bool, str]:
    """Return (is_valid, message) for a GitHub owner/repo.git URL."""
    if not url or not url.strip():
        return False, "Empty URL"

    url = url.strip()

    if not url.startswith('https://github.com/') and not url.startswith('http://github.com/'):
        return False, "Not a GitHub URL (must start with https://github.com/ or http://github.com/)"

    pattern = r'^https?://github\.com/[^/]+/[^/]+\.git$'
    if not re.match(pattern, url):
        return False, f"Invalid format (expected: https://github.com/owner/repo.git or http://..., got: {url})"

    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) != 2:
        return False, f"Invalid path (expected owner/repo, got: {parsed.path})"

    owner, repo = path_parts
    repo = repo.replace('.git', '')
    if not owner or not repo:
        return False, "Missing owner or repository name"

    return True, "Valid"


def validate_csv(input_file: str, output_file: str = None) -> dict:
    valid_urls = []
    invalid_urls = []
    stats = {
        'total': 0,
        'valid': 0,
        'invalid': 0,
        'errors': []
    }

    print(f"Validating {input_file}...")
    print("=" * 80)

    try:
        with open(input_file, 'r') as f:
            reader = csv.DictReader(f)

            if not reader.fieldnames:
                print("ERROR: CSV file is empty or missing header")
                sys.exit(1)
            if 'repo_url' not in reader.fieldnames:
                print(f"ERROR: CSV missing 'repo_url' column. Found columns: {reader.fieldnames}")
                sys.exit(1)

            for row_num, row in enumerate(reader, start=2):
                stats['total'] += 1
                url = row.get('repo_url', '').strip()

                is_valid, error_msg = validate_repo_url(url)
                if is_valid:
                    stats['valid'] += 1
                    valid_urls.append(url)
                    print(f"OK   Row {row_num}: {url}")
                else:
                    stats['invalid'] += 1
                    invalid_urls.append((row_num, url, error_msg))
                    print(f"FAIL Row {row_num}: {url} - {error_msg}")
                    stats['errors'].append({
                        'row': row_num,
                        'url': url,
                        'error': error_msg
                    })

        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        print(f"Total URLs:     {stats['total']}")
        print(f"Valid URLs:    {stats['valid']} ({stats['valid']/stats['total']*100:.1f}%)")
        print(f"Invalid URLs:   {stats['invalid']} ({stats['invalid']/stats['total']*100:.1f}%)")

        if invalid_urls:
            print("\nInvalid URLs:")
            for row_num, url, error in invalid_urls[:10]:
                print(f"  Row {row_num}: {url}")
                print(f"    Error: {error}")
            if len(invalid_urls) > 10:
                print(f"  ... and {len(invalid_urls) - 10} more")

        if output_file:
            with open(output_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['repo_url'])
                for url in valid_urls:
                    writer.writerow([url])
            print(f"\nValidated URLs saved to: {output_file}")
            print(f"  ({len(valid_urls)} valid URLs)")

        return stats

    except FileNotFoundError:
        print(f"ERROR: File not found: {input_file}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Validate repository URLs in CSV file for CCKP Toolkit workflow'
    )
    parser.add_argument('--input', 
                       required=True,
                       help='Input CSV file with repo_url column')
    parser.add_argument('--output',
                       default=None,
                       help='Output CSV file with only valid URLs (optional)')
    parser.add_argument('--fix',
                       action='store_true',
                       help='Attempt to fix common URL format issues')
    
    args = parser.parse_args()

    stats = validate_csv(args.input, args.output)

    if stats['invalid'] > 0:
        print(f"\nWarning: {stats['invalid']} invalid URLs found")
        sys.exit(1)
    else:
        print("\nAll URLs are valid")
        sys.exit(0)


if __name__ == '__main__':
    main()
