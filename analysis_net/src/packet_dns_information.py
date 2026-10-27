import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

URL = "https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/domains/pro.txt"
FALLBACKS = [
    "https://gitlab.com/hagezi/mirror/-/raw/main/dns-blocklists/domains/pro.txt",
    "https://codeberg.org/hagezi/mirror2/raw/branch/main/dns-blocklists/domains/pro.txt",
]


FMT_STR = "%d %b %Y %H:%M"


def download_block_list() -> set[str] | None:
    response = requests.get(URL)

    if response.status_code != 200:
        for fallback in FALLBACKS:
            response = requests.get(fallback)
            if response.status_code == 200:
                break

    if response.status_code != 200:
        print("[ERROR] Could not download block list")
        return

    lines = response.text.splitlines()
    domains = set()

    for line in lines:
        if line.startswith("# Last modified:"):
            line = line.replace("# Last modified:", "").strip()
            last_updated = datetime.strptime(line, "%d %b %Y %H:%M %Z")

            if datetime.now(tz=last_updated.tzinfo) - last_updated > timedelta(days=2):
                print("[WARN ] Block list is outdated")

        elif line.startswith("#") or not line.strip():
            continue

        else:
            domains.add(line.strip().lower())

    return domains


def load_block_list(path: Path) -> set[str]:
    if not os.path.exists(path):
        print("[INFO ] Block list does not exist, downloading...")

        blocklist = download_block_list()
        if blocklist is None:
            return set()

        with open(path, "w", encoding="utf-8") as f:
            now = datetime.now().strftime(FMT_STR)

            f.write(now + "\n")
            for domain in blocklist:
                f.write(domain + "\n")

        return blocklist

    else:
        print("[INFO ] Block list exists, checking if update is needed...")

        need_update = False

        lines = []
        with open(path, "r", encoding="utf-8") as f:
            last_updated = datetime.strptime(f.readline().strip(), FMT_STR)
            now = datetime.now()

            if now - last_updated > timedelta(days=2):
                print("[INFO ] Block list is outdated, downloading...")
                need_update = True

            else:
                lines = f.readlines()

        if need_update:
            assert len(lines) == 0
            print("[INFO ] Downloading new block list...")

            lines = download_block_list()
            if lines is None:
                return set()

            with open(path, "w", encoding="utf-8") as f:
                f.write(datetime.now().strftime(FMT_STR) + "\n")

                for domain in lines:
                    f.write(domain + "\n")
        else:
            print("[INFO ] Block list is up to date")

        return {line.strip().lower() for line in lines}


def search_block_list(domain: str, blocklist: set[str]) -> bool:
    domain = domain.lower().strip()

    if domain in blocklist:
        return True

    parts = domain.split(".")

    stripped_last_part = ".".join(parts[1:])

    if stripped_last_part in blocklist:
        return True

    return False
