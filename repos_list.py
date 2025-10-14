"""
repos_list.py

Description: Lets the use of a txt file in cli for detecting and parsing the repos by url 

"""
from pathlib import Path
import argparse


def load_urls_from_file(path: str) -> list[str]:
    urls: list[str] = []
    path = Path(path)
    if not path.exists():
        print(f"URL list file not found: {path}")
        return urls
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls

def collect_urls(argv=None) -> list[str]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("repos", nargs="*", help="repo url(s) or local path(s) or @file")
    parser.add_argument("--list-file", "-f", help="Text file with one repo per line")
    known, _ = parser.parse_known_args(argv)

    seen, out = set(), []

    #positional arguments (allow @file shorthand)
    for item in known.repos:
        if item.startswith("@"):
            for url in load_urls_from_file(item[1:]):
                if url not in seen:
                    seen.add(url); out.append(url)
        else:
            if item not in seen:
                seen.add(item); out.append(item)

    #explicit --list-file
    if known.list_file:
        for url in load_urls_from_file(known.list_file):
            if url not in seen:
                seen.add(url); out.append(url)

    return out
