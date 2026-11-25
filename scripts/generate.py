#!/usr/bin/env python3
# Authors: robotdory(Taehyeon Kim)
"""Generate the night delivery map from a GitHub contribution calendar."""

import argparse
from datetime import date
from heapq import heappop, heappush
from itertools import groupby
import json
import os
from pathlib import Path
from random import Random
from urllib.request import Request, urlopen

from art import render_missions


LEVELS = ("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
QUERY = """
query Calendar($user: String!) {
  user(login: $user) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionLevel } }
      }
    }
  }
}
"""


def fetch_calendar(user):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("Set GITHUB_TOKEN or supply --input with a saved calendar.")
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"user": user}}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_calendar(payload):
    if payload.get("errors"):
        raise ValueError("; ".join(error["message"] for error in payload["errors"]))
    calendar = payload
    if "data" in payload:
        user = payload["data"]["user"]
        if user is None:
            raise ValueError("GitHub returned no matching user.")
        calendar = user["contributionsCollection"]["contributionCalendar"]

    grid = []
    labels = []
    month = None
    for week in calendar["weeks"]:
        column = [-1] * 7
        for day in week["contributionDays"]:
            weekday = day["weekday"]
            if weekday not in range(7):
                raise ValueError(f"Invalid weekday: {weekday}")
            column[weekday] = LEVELS.index(day["contributionLevel"])
            if "date" in day:
                current = date.fromisoformat(day["date"]).month
                if current != month:
                    labels.append((len(grid), MONTHS[current - 1]))
                    month = current
        grid.append(column)
    if not grid:
        raise ValueError("GitHub returned an empty calendar.")
    if len(labels) > 1 and labels[1][0] - labels[0][0] < 3:
        labels.pop(0)
    if len(labels) > 1 and labels[-1][0] - labels[-2][0] < 3:
        labels.pop()
    return grid, calendar["totalContributions"], labels


def neighbors(point):
    x, y = point
    return ((x + 1, y), (x, y - 1), (x - 1, y), (x, y + 1))


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def connected_districts(roads):
    unseen = set(roads)
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        district = {start}
        stack = [start]
        while stack:
            for cell in neighbors(stack.pop()):
                if cell in unseen:
                    unseen.remove(cell)
                    district.add(cell)
                    stack.append(cell)
        yield district


def astar(grid, roads, start, goal, used=()):
    dx, dy = goal[0] - start[0], goal[1] - start[1]
    span = max(abs(dx), abs(dy), 1)
    queue = [(4 * distance(start, goal), 0, start)]
    previous = {}
    costs = {start: 0}
    while queue:
        _, cost, cell = heappop(queue)
        if cost != costs[cell]:
            continue
        if cell == goal:
            route = [goal]
            while route[-1] != start:
                route.append(previous[route[-1]])
            return route[::-1]
        for nxt in neighbors(cell):
            if nxt not in roads:
                continue
            x, y = nxt
            # Give cells near the direct approach a small advantage over distant streets.
            offset = abs(dx * (y - start[1]) - dy * (x - start[0])) // span
            candidate = cost + 4 + grid[x][y] + offset + 2 * (nxt in used)
            if candidate < costs.get(nxt, float("inf")):
                costs[nxt] = candidate
                previous[nxt] = cell
                heappush(queue, (candidate + 4 * distance(nxt, goal), candidate, nxt))
    raise RuntimeError("No route inside connected district.")


def approach(grid, roads, start, via, goal, used=()):
    return astar(grid, roads, start, via, used) + astar(grid, roads, via, goal, used)[1:]


def route_shape(path):
    steps = ((b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:]))
    runs = [sum(1 for _ in run) for _, run in groupby(steps)]
    rows = {y for _, y in path}
    return len(runs) - 1, max(runs), len(rows)


def plan_loop(grid, district, dock, goal):
    # Approach the same destination from opposite sides of the calendar when possible.
    middle = (dock[0] + goal[0]) // 2
    upper, lower = (min(district, key=lambda p: (distance(p, (middle, y)), p)) for y in (0, 6))
    candidates = []
    for out_via, home_via in ((upper, lower), (lower, upper)):
        out = approach(grid, district, dock, out_via, goal)
        home = approach(grid, district, goal, home_via, dock, set(out))
        if len(set(out)) != len(out) or len(set(home)) != len(home):
            continue
        turns, straight, rows = route_shape(out)
        back_turns, back_straight, back_rows = route_shape(home)
        score = (min(rows, back_rows, 5), min(turns, back_turns, 8),
                 -max(straight, back_straight, 5), len(set(home) - set(out)))
        candidates.append((score, out, home))
    if candidates:
        _, out, home = max(candidates)
        return out, home

    out = astar(grid, district, dock, goal)
    return out, astar(grid, district, goal, dock, set(out))


def plan_missions(grid, rng):
    roads = {(x, y) for x, week in enumerate(grid) for y, level in enumerate(week)
             if 0 <= level < 3}
    if not roads:
        dock = next(((x, y) for x, week in enumerate(grid) for y, level in enumerate(week)
                     if level >= 0), None)
        if dock is None:
            raise ValueError("Calendar has no dated cells.")
        return [([dock], [dock])]

    district = max(connected_districts(roads), key=len)
    # One common charger keeps consecutive missions continuous even when the SVG loops.
    streets = sorted(district)
    quarter = len(streets) // 4
    dock = rng.choice(streets[quarter:len(streets) - quarter])
    if len(streets) == 1:
        return [([dock], [dock])]

    goals = [cell for cell in streets if cell != dock]
    local_goals = [cell for cell in goals if 8 <= distance(dock, cell) <= 22]
    if len(local_goals) >= 8:
        goals = local_goals
    count = min(8, len(goals))
    missions = []
    for i in range(count):
        # Spread the stops across the district without selecting any destination twice.
        band = goals[i * len(goals) // count:(i + 1) * len(goals) // count]
        missions.append(plan_loop(grid, district, dock, rng.choice(band)))
    rng.shuffle(missions)
    return missions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    parser.add_argument("--input", type=Path, help="Use a saved GitHub GraphQL calendar.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path, help="Refresh the SVG in a marked HTML preview.")
    parser.add_argument("--seed", type=int, help="Repeat the same set of deliveries.")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text()) if args.input else fetch_calendar(args.user)
        grid, total, labels = parse_calendar(payload)
        missions = plan_missions(grid, Random(args.seed))
        svg = render_missions(grid, missions, total, month_labels=labels)
        if args.preview:
            start, end = "<!-- calendar:start -->", "<!-- calendar:end -->"
            preview = args.preview.read_text(encoding="utf-8")
            before, start_marker, middle = preview.partition(start)
            _, end_marker, after = middle.partition(end)
            if not start_marker or not end_marker or preview.count(start) != 1 or preview.count(end) != 1:
                raise ValueError("Preview must contain one ordered pair of calendar markers.")
            preview = before + start + "\n" + svg + end + after
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(svg, encoding="utf-8")
        if args.preview:
            args.preview.write_text(preview, encoding="utf-8")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(1, f"Could not generate night delivery map: {exc}\n")


if __name__ == "__main__":
    main()
