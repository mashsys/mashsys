#!/usr/bin/env python3
"""Update the aggregate profile statistics block in README.md."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


START_MARKER = "<!-- PROFILE_STATS:START -->"
END_MARKER = "<!-- PROFILE_STATS:END -->"
README_PATH = Path(__file__).resolve().parents[1] / "README.md"


def github_get(url: str, token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mashsys-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def paginated_repositories(url: str, token: str | None) -> list[dict]:
    repositories: list[dict] = []
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        page_url = f"{url}{separator}per_page=100&page={page}"
        payload = github_get(page_url, token)
        if not isinstance(payload, list):
            raise RuntimeError("GitHub returned an unexpected repository response.")
        repositories.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return repositories
        page += 1


def public_repositories(username: str) -> list[dict]:
    url = f"https://api.github.com/users/{urllib.parse.quote(username)}/repos?type=all"
    return paginated_repositories(url, None)


def authenticated_repositories(token: str) -> list[dict]:
    url = (
        "https://api.github.com/user/repos"
        "?visibility=all&affiliation=owner,organization_member,collaborator"
    )
    return paginated_repositories(url, token)


def format_stats(repositories: list[dict], private_count: int | None) -> str:
    public_count = sum(1 for repo in repositories if not repo.get("private", False))
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repositories)
    forks = sum(int(repo.get("forks_count", 0)) for repo in repositories)
    languages = Counter(
        repo["language"]
        for repo in repositories
        if isinstance(repo.get("language"), str) and repo["language"]
    )
    language_total = sum(languages.values())

    private_display = str(private_count) if private_count is not None else "Unavailable"
    language_rows = []
    for language, count in languages.most_common(5):
        share = round(count / language_total * 100) if language_total else 0
        language_rows.append(f"| {language} | {share}% |")
    if not language_rows:
        language_rows.append("| Not available yet | - |")

    return "\n".join(
        [
            "| Public repos | Private repos | Stars | Forks |",
            "| ---: | ---: | ---: | ---: |",
            f"| {public_count} | {private_display} | {stars} | {forks} |",
            "",
            "**Primary language mix**",
            "",
            "| Language | Share |",
            "| --- | ---: |",
            *language_rows,
            "",
            "_Private repository count: available via `PROFILE_README_TOKEN`._"
            if private_count is None
            else "_Language share is calculated from each repository's primary language._",
        ]
    )


def update_readme(content: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    start = readme.find(START_MARKER)
    end = readme.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("README stats markers are missing or out of order.")
    end += len(END_MARKER)
    replacement = f"{START_MARKER}\n{content}\n{END_MARKER}"
    README_PATH.write_text(readme[:start] + replacement + readme[end:], encoding="utf-8")


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "mashsys/mashsys")
    username = repository.split("/", 1)[0]
    token = os.environ.get("PROFILE_README_TOKEN")

    try:
        repositories = public_repositories(username)
        private_count = None
        if token:
            accessible_repositories = authenticated_repositories(token)
            known_repositories = {
                repo.get("full_name") for repo in repositories if repo.get("full_name")
            }
            repositories.extend(
                repo
                for repo in accessible_repositories
                if repo.get("full_name") not in known_repositories
            )
            private_count = sum(1 for repo in repositories if repo.get("private", False))
        update_readme(format_stats(repositories, private_count))
    except (OSError, RuntimeError, urllib.error.HTTPError, urllib.error.URLError) as error:
        print(f"Unable to update profile stats: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
