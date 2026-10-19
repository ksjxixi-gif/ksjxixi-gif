#!/usr/bin/env python3
"""Render assets/stats.svg from live GitHub data, in the same Art Deco style.

Runs daily in .github/workflows/stats.yml. To include private repos it needs a
personal access token saved as the STATS_TOKEN repository secret; without one it
falls back to the workflow's own token, which only sees public work (the card
then says so).

Local run:
    STATS_TOKEN=ghp_... python3 design/stats.py
    python3 design/stats.py --placeholder     # card with no data, for a first commit
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as b  # noqa: E402  (shared palette, fonts and shapes)

LOGIN = os.environ.get("GITHUB_LOGIN", "ksjxixi-gif")
TOP_LANGUAGES = 6
WEEKS = 52
# Languages to leave out of the chart, e.g. {"HTML", "CSS"} if markup is drowning out code.
EXCLUDE_LANGUAGES: set[str] = set()

ACTIVITY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar { totalContributions weeks { contributionDays { contributionCount } } }
    }
  }
}"""

REPOS = """
query($login: String!, $after: String, $affiliations: [RepositoryAffiliation]) {
  user(login: $login) {
    repositories(first: 100, after: $after, isFork: false, ownerAffiliations: $affiliations) {
      pageInfo { hasNextPage endCursor }
      nodes {
        owner { login }
        stargazerCount
        languages(first: 25) { edges { size node { name } } }
      }
    }
  }
}"""


def gql(token: str, query: str, **variables) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": f"{LOGIN}-profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise SystemExit(f"GitHub API error: {body['errors']}")
    return body["data"]


def fetch(token: str, private: bool) -> dict:
    activity = gql(token, ACTIVITY, login=LOGIN)["user"]["contributionsCollection"]
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"])
             for w in activity["contributionCalendar"]["weeks"]][-WEEKS:]

    # Org and collaborator repos count toward languages (that's where team work lives);
    # only repos the user owns count toward repositories and stars.
    affiliations = ["OWNER", "ORGANIZATION_MEMBER", "COLLABORATOR"] if private else ["OWNER"]
    owned = stars = 0
    sizes: Counter[str] = Counter()
    after = None
    while True:
        page = gql(token, REPOS, login=LOGIN, after=after, affiliations=affiliations)["user"]["repositories"]
        for repo in page["nodes"]:
            if repo["owner"]["login"].lower() == LOGIN.lower():
                owned += 1
                stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                if edge["node"]["name"] not in EXCLUDE_LANGUAGES:
                    sizes[edge["node"]["name"]] += edge["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]

    total = sum(sizes.values()) or 1
    return {
        "private": private,
        "contributions": activity["contributionCalendar"]["totalContributions"],
        "commits": activity["totalCommitContributions"],
        "pull_requests": activity["totalPullRequestContributions"],
        "reviews": activity["totalPullRequestReviewContributions"],
        "repositories": owned,
        "stars": stars,
        "languages": [(name, size / total * 100) for name, size in sizes.most_common(TOP_LANGUAGES)],
        "weeks": weeks,
    }


def compact(n: int) -> str:
    return f"{n:,}" if n < 10_000 else f"{n / 1000:.1f}K".replace(".0K", "K")


def safe(text: str, font: str) -> str:
    """Swap characters the embedded font lacks (e.g. unusual language names) for '?'."""
    cmap = b._font(font).getBestCmap()
    return "".join(c if c == " " or ord(c) in cmap else "?" for c in text)


def render(data: dict | None) -> b.Svg:
    w, h = b.W, 490
    if data:
        langs = ", ".join(f"{n} {p:.1f}%" for n, p in data["languages"])
        desc = (f"Last 12 months: {data['contributions']} contributions, {data['commits']} commits, "
                f"{data['pull_requests']} pull requests, {data['reviews']} code reviews. "
                f"{data['repositories']} repositories, {data['stars']} stars. Top languages by code size: {langs}.")
    else:
        desc = "GitHub stats will appear after the first scheduled run."
    svg = b.Svg(w, h, "GitHub stats", desc)
    b.panel(svg, glow=(0.15, 0.0))

    scope = "PUBLIC + PRIVATE REPOS" if (data or {}).get("private") else "PUBLIC REPOS ONLY"
    svg.text(78, 66, "BY THE NUMBERS", font="display", size=19, ls=0.12, fill=b.GOLD_LIGHT, anchor="start")
    svg.text(78, 88, "ACTIVITY OVER THE LAST 12 MONTHS", size=10.5, ls=0.32, fill=b.MUTED, anchor="start")
    if data:
        svg.text(w - 78, 88, scope, size=10.5, ls=0.32, fill=b.MUTED, anchor="end")

    # stat tiles, 2 x 3
    tiles = [("CONTRIBUTIONS", "contributions"), ("COMMITS", "commits"),
             ("PULL REQUESTS", "pull_requests"), ("CODE REVIEWS", "reviews"),
             ("REPOSITORIES", "repositories"), ("STARS EARNED", "stars")]
    tx, ty, tw, th, gap = 78, 112, 194, 72, 12
    for i, (label, key) in enumerate(tiles):
        x, y = tx + (i % 2) * (tw + gap), ty + (i // 2) * (th + gap)
        svg.add(f'<path d="{b.stepped_rect(x, y, tw, th, 4)}" fill="{b.PANEL}" stroke="{b.GOLD}" stroke-width="1"/>',
                f'<path d="{b.stepped_rect(x + 5, y + 5, tw - 10, th - 10, 3)}" fill="none" stroke="{b.GOLD}" stroke-width="0.5" opacity="0.3"/>')
        value = compact(data[key]) if data else "—"
        svg.text(x + tw / 2, y + 39, value, size=28, fill=b.GOLD_PALE)
        svg.text(x + tw / 2, y + 58, label, size=10, ls=0.24, fill=b.MUTED)

    # languages: one series, so one colour and no legend; value at each bar's tip
    lx, lw = 530, w - 78 - 530
    svg.text(lx, 122, "LANGUAGES · BY CODE SIZE", size=10.5, ls=0.32, fill=b.MUTED, anchor="start")
    if data and data["languages"]:
        top = data["languages"][0][1]
        bar_max = lw - 64
        for j, (name, pct) in enumerate(data["languages"]):
            y = 152 + j * 34
            svg.text(lx, y, safe(name, "label"), size=14, fill=b.CREAM, anchor="start")
            bw = max(4.0, bar_max * pct / top)
            by, bh, r = y + 7, 8, 4
            svg.add(f'<path d="M{lx},{by}H{lx + bw - r:.1f}A{r},{r} 0 0 1 {lx + bw:.1f},{by + r}'
                    f'A{r},{r} 0 0 1 {lx + bw - r:.1f},{by + bh}H{lx}Z" fill="{b.GOLD}"/>')
            svg.text(lx + bw + 10, by + 8, f"{pct:.1f}%", font="mono", size=12, fill=b.CREAM, anchor="start")
    else:
        svg.text(lx + lw / 2, 240, "Waiting for the first stats run", font="light", size=16, fill=b.MUTED)

    # weekly contributions: columns from one baseline, peak labelled, current week accented
    base, top_y, x0, x1 = 448, 404, 78, w - 78
    svg.text(x0, 386, f"CONTRIBUTIONS PER WEEK · LAST {WEEKS} WEEKS", size=10.5, ls=0.32, fill=b.MUTED, anchor="start")
    svg.add(f'<path d="M{x0},{base + 0.5}H{x1}" stroke="{b.MUTED}" stroke-width="1" opacity="0.45"/>')
    weeks = (data or {}).get("weeks") or []
    if weeks and max(weeks):
        n, cgap = len(weeks), 2
        cw = (x1 - x0 - cgap * (n - 1)) / n
        peak = max(weeks)
        peak_i = weeks.index(peak)
        for i, v in enumerate(weeks):
            if not v:
                continue
            ch = max(2.0, (base - top_y) * v / peak)
            x, y = x0 + i * (cw + cgap), base - ch
            r = min(4.0, cw / 2, ch)
            fill = b.GOLD_PALE if i == n - 1 else b.GOLD
            svg.add(f'<path d="M{x:.1f},{base}V{y + r:.1f}A{r:.1f},{r:.1f} 0 0 1 {x + r:.1f},{y:.1f}'
                    f'H{x + cw - r:.1f}A{r:.1f},{r:.1f} 0 0 1 {x + cw:.1f},{y + r:.1f}V{base}Z" '
                    f'fill="{fill}" opacity="{1 if i == n - 1 else 0.8}"/>')
        # Mark the peak column and name its value in the caption row, clear of the bars.
        px = x0 + peak_i * (cw + cgap) + cw / 2
        svg.add(b.diamond(px, top_y - 7, 3, fill=b.GOLD_PALE, stroke="none"))
        label = f"PEAK WEEK · {peak:,}"
        svg.text(x1, 386, label, size=10.5, ls=0.32, fill=b.CREAM, anchor="end")
        lw_ = b.text_width("label", label, 10.5, 0.32)
        svg.add(b.diamond(x1 - lw_ - 14, 382.5, 3, fill=b.GOLD_PALE, stroke="none"))
    return svg


def main() -> None:
    if "--placeholder" in sys.argv:
        render(None).save("stats.svg")
        return
    token = os.environ.get("STATS_TOKEN")
    private = bool(token)
    if not token:
        token = os.environ.get("GITHUB_TOKEN")
        print("::warning::STATS_TOKEN is not set, so the card only covers public repos. "
              "Add a personal access token as the STATS_TOKEN repository secret to include private work.")
    if not token:
        raise SystemExit("Set STATS_TOKEN (or GITHUB_TOKEN) to call the GitHub API.")
    render(fetch(token, private)).save("stats.svg")


if __name__ == "__main__":
    main()
