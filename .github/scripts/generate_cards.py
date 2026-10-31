#!/usr/bin/env python3
"""Generate README cards (stats, streak, top languages, activity graph, quote)
directly from the GitHub API. No third-party card servers involved.

Env:
  GH_TOKEN  GitHub token (the Actions token is enough)
  GH_USER   GitHub username (default: Priyanshu-302)
"""
import datetime as dt
import json
import math
import os
import random
import urllib.request
from html import escape

USER = os.environ.get("GH_USER", "Priyanshu-302")
OUT = "assets"

BG, TITLE, ICON, TEXT, MUTED = "#0d1117", "#FF0055", "#FF6B00", "#ffffff", "#9aa4b2"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
FALLBACK_COLORS = ["#FF0055", "#FF6B00", "#FFD700", "#7C3AED", "#38B2AC",
                   "#3B82F6", "#22C55E", "#F472B6"]

QUOTES = [
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("Simplicity is the soul of efficiency.", "Austin Freeman"),
    ("Code is like humor. When you have to explain it, it's bad.", "Cory House"),
    ("Programs must be written for people to read.", "Harold Abelson"),
    ("Premature optimization is the root of all evil.", "Donald Knuth"),
    ("Any fool can write code that a computer can understand.", "Martin Fowler"),
    ("Before software can be reusable it first has to be usable.", "Ralph Johnson"),
    ("The best way to predict the future is to invent it.", "Alan Kay"),
]


# ----------------------------------------------------------------- GitHub API
def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": "bearer " + os.environ["GH_TOKEN"],
            "Content-Type": "application/json",
            "User-Agent": "readme-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


Q_PROFILE = """
query($login:String!){
  user(login:$login){
    name
    login
    followers{totalCount}
    pullRequests(first:1){totalCount}
    issues(first:1){totalCount}
    repositoriesContributedTo(first:1,contributionTypes:[COMMIT,ISSUE,PULL_REQUEST,REPOSITORY]){totalCount}
    contributionsCollection{
      totalCommitContributions
      restrictedContributionsCount
      contributionYears
      contributionCalendar{weeks{contributionDays{date contributionCount}}}
    }
    repositories(ownerAffiliations:OWNER,isFork:false,first:100){
      nodes{
        stargazerCount
        languages(first:10,orderBy:{field:SIZE,direction:DESC}){
          edges{size node{name color}}
        }
      }
    }
  }
}
"""

Q_YEAR = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    contributionsCollection(from:$from,to:$to){
      contributionCalendar{weeks{contributionDays{date contributionCount}}}
    }
  }
}
"""


def days_from_calendar(cal):
    out = {}
    for w in cal["weeks"]:
        for d in w["contributionDays"]:
            out[d["date"]] = d["contributionCount"]
    return out


def fetch_data():
    u = gql(Q_PROFILE, {"login": USER})["user"]
    coll = u["contributionsCollection"]
    days = days_from_calendar(coll["contributionCalendar"])
    for y in coll["contributionYears"]:
        d = gql(Q_YEAR, {
            "login": USER,
            "from": "%d-01-01T00:00:00Z" % y,
            "to": "%d-12-31T23:59:59Z" % y,
        })["user"]["contributionsCollection"]["contributionCalendar"]
        days.update(days_from_calendar(d))

    stars = 0
    langs = {}
    for repo in u["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            cur = langs.get(n, {"size": 0, "color": e["node"]["color"]})
            cur["size"] += e["size"]
            langs[n] = cur

    return {
        "name": u["name"] or u["login"],
        "followers": u["followers"]["totalCount"],
        "stars": stars,
        "commits": coll["totalCommitContributions"] + coll["restrictedContributionsCount"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "contributed_to": u["repositoriesContributedTo"]["totalCount"],
        "langs": langs,
        "days": days,
    }


# ------------------------------------------------------------------- helpers
def svg(w, h, body, label):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" aria-label="%s">'
        '<rect width="%d" height="%d" rx="4.5" fill="%s"/>%s</svg>\n'
        % (w, h, w, h, escape(label), w, h, BG, body)
    )


def text(x, y, s, size=14, fill=TEXT, weight=400, anchor="start"):
    return (
        '<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="%s" '
        'fill="%s" text-anchor="%s">%s</text>'
        % (x, y, FONT.replace('"', "'"), size, weight, fill, anchor, escape(str(s)))
    )


def fmt_date(d, year=False):
    s = d.strftime("%b ") + str(d.day)
    return s + (d.strftime(", %Y") if year else "")


# --------------------------------------------------------------------- cards
def card_stats(d):
    rows = [
        ("Total Stars Earned", d["stars"]),
        ("Commits (last year)", d["commits"]),
        ("Total PRs", d["prs"]),
        ("Total Issues", d["issues"]),
        ("Contributed to (last year)", d["contributed_to"]),
    ]
    b = text(25, 35, "%s's GitHub Stats" % d["name"], 18, TITLE, 700)
    for i, (label, val) in enumerate(rows):
        y = 70 + i * 25
        b += '<circle cx="32" cy="%d" r="5" fill="%s"/>' % (y - 5, ICON)
        b += text(50, y, label + ":", 14, TEXT, 600)
        b += text(455, y, "{:,}".format(val), 14, TEXT, 700, "end")
    return svg(495, 195, b, "GitHub stats")


def compute_streaks(days):
    items = sorted((dt.date.fromisoformat(k), v) for k, v in days.items())
    total = sum(v for _, v in items)
    longest, run, run_start = (0, None, None), 0, None
    for date, v in items:
        if v > 0:
            if run == 0:
                run_start = date
            run += 1
            if run > longest[0]:
                longest = (run, run_start, date)
        else:
            run = 0
    cur = (0, None, None)
    idx = len(items) - 1
    if idx >= 0 and items[idx][1] == 0:
        idx -= 1  # today not counted yet; streak may still be alive
    end = items[idx][0] if idx >= 0 else None
    n = 0
    while idx >= 0 and items[idx][1] > 0:
        n += 1
        start = items[idx][0]
        idx -= 1
    if n:
        cur = (n, start, end)
    first = items[0][0] if items else None
    last = items[-1][0] if items else None
    return total, first, last, cur, longest


def card_streak(d):
    total, first, last, cur, longest = compute_streaks(d["days"])
    b = ""
    cols = [82, 247, 412]
    b += '<line x1="165" y1="30" x2="165" y2="165" stroke="%s" stroke-opacity=".35"/>' % TITLE
    b += '<line x1="330" y1="30" x2="330" y2="165" stroke="%s" stroke-opacity=".35"/>' % TITLE
    # total
    b += text(cols[0], 85, "{:,}".format(total), 28, TEXT, 700, "middle")
    b += text(cols[0], 117, "Total Contributions", 14, TEXT, 400, "middle")
    if first:
        b += text(cols[0], 140, "%s - Present" % fmt_date(first, True), 11, MUTED, 400, "middle")
    # current
    b += '<circle cx="%d" cy="82" r="38" fill="none" stroke="%s" stroke-width="5"/>' % (cols[1], TITLE)
    b += text(cols[1], 91, cur[0], 28, TEXT, 700, "middle")
    b += text(cols[1], 140, "Current Streak", 14, ICON, 700, "middle")
    if cur[1]:
        b += text(cols[1], 160, "%s - %s" % (fmt_date(cur[1]), fmt_date(cur[2])), 11, MUTED, 400, "middle")
    # longest
    b += text(cols[2], 85, longest[0], 28, TEXT, 700, "middle")
    b += text(cols[2], 117, "Longest Streak", 14, TEXT, 400, "middle")
    if longest[1]:
        b += text(cols[2], 140, "%s - %s" % (fmt_date(longest[1], True), fmt_date(longest[2], True)), 11, MUTED, 400, "middle")
    return svg(495, 195, b, "Contribution streak")


def card_langs(d):
    items = sorted(d["langs"].items(), key=lambda kv: kv[1]["size"], reverse=True)[:8]
    total = sum(v["size"] for _, v in items) or 1
    b = text(25, 35, "Most Used Languages", 18, TITLE, 700)
    cx, cy, r, sw = 125, 150, 62, 28
    circ = 2 * math.pi * r
    off = 0.0
    for i, (name, v) in enumerate(items):
        color = v["color"] or FALLBACK_COLORS[i % len(FALLBACK_COLORS)]
        seg = v["size"] / total * circ
        b += (
            '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d" '
            'stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f" transform="rotate(-90 %d %d)"/>'
            % (cx, cy, r, color, sw, seg, circ - seg, -off, cx, cy)
        )
        off += seg
        y = 70 + i * 24
        b += '<circle cx="258" cy="%d" r="6" fill="%s"/>' % (y - 5, color)
        b += text(272, y, name, 14, TEXT, 600)
        b += text(470, y, "%.1f%%" % (v["size"] / total * 100), 13, MUTED, 400, "end")
    return svg(495, 270, b, "Most used languages")


def card_activity(d):
    today = dt.date.today()
    series = []
    for i in range(30, -1, -1):
        day = today - dt.timedelta(days=i)
        series.append((day, d["days"].get(day.isoformat(), 0)))
    w, h = 900, 300
    left, right, top, bottom = 70, 870, 70, 240
    vmax = max(4, max(v for _, v in series))
    step = max(1, math.ceil(vmax / 4))
    vmax = step * 4

    def X(i):
        return left + i * (right - left) / (len(series) - 1)

    def Y(v):
        return bottom - v / vmax * (bottom - top)

    b = text(450, 35, "%s's Contribution Graph" % USER, 20, TITLE, 700, "middle")
    for k in range(5):
        v = k * step
        y = Y(v)
        b += '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#ffffff" stroke-opacity=".12"/>' % (left, y, right, y)
        b += text(left - 10, y + 4, v, 12, ICON, 400, "end")
    pts = " ".join("%.1f,%.1f" % (X(i), Y(v)) for i, (_, v) in enumerate(series))
    area = "%d,%d %s %d,%d" % (left, bottom, pts, right, bottom)
    b += '<polygon points="%s" fill="%s" fill-opacity=".2"/>' % (area, TITLE)
    b += '<polyline points="%s" fill="none" stroke="%s" stroke-width="3" stroke-linejoin="round"/>' % (pts, TITLE)
    for i, (day, v) in enumerate(series):
        b += '<circle cx="%.1f" cy="%.1f" r="3.5" fill="#ffffff" stroke="%s" stroke-width="1.5"/>' % (X(i), Y(v), TITLE)
        if i % 3 == 0 or i == len(series) - 1:
            b += text("%.1f" % X(i), bottom + 20, day.day, 12, ICON, 400, "middle")
    b += text(450, 285, "Days (last 31)", 12, ICON, 400, "middle")
    return svg(w, h, b, "Contribution graph")


def card_quote(_d):
    q, a = random.choice(QUOTES)
    b = text(450, 45, "“" + q + "”", 20, TEXT, 600, "middle")
    b += text(450, 80, "— " + a, 15, ICON, 400, "middle")
    return svg(900, 110, b, "Random dev quote")


# ---------------------------------------------------------------------- main
def build(d, out=OUT):
    os.makedirs(out, exist_ok=True)
    files = {
        "stats.svg": card_stats(d),
        "streak.svg": card_streak(d),
        "top-langs.svg": card_langs(d),
        "activity-graph.svg": card_activity(d),
        "quote.svg": card_quote(d),
    }
    for name, content in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(content)
        print("wrote", name)
    with open(os.path.join(out, "stars.json"), "w", encoding="utf-8") as f:
        json.dump({"schemaVersion": 1, "label": "TOTAL STARS",
                   "message": str(d["stars"]), "color": "FFD700"}, f)
        f.write("\n")
    print("wrote stars.json")


if __name__ == "__main__":
    build(fetch_data())
