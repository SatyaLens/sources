#!/usr/bin/env python3
import os
import sys
from firecrawl import Firecrawl


def main():
    if len(sys.argv) < 2:
        print("Usage: scrape_firecrawl.py URL", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        print("Error: FIRECRAWL_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Initialize Firecrawl client
    fc = Firecrawl(api_key=api_key)

    # Scrape page as markdown
    # Firecrawl's Python SDK returns a dict with a "markdown" field when formats includes "markdown".[web:992][web:995]
    try:
        doc = fc.scrape(url, formats=["markdown"])
    except Exception as e:
        print(f"Error scraping URL {url}: {e}", file=sys.stderr)
        sys.exit(1)

    markdown = doc.markdown
    if not markdown:
        print("Error: No markdown content found in Firecrawl response.", file=sys.stderr)
        sys.exit(1)

    # Print clean markdown to stdout
    print(markdown)


if __name__ == "__main__":
    main()