"""Render a top-down delivery route on a GitHub contribution calendar."""
# Authors: robotdory(Taehyeon Kim)

from html import escape


PITCH = 18
CELL = 14
LEFT = 51
TOP = 73
MISSION_SECONDS = 24
LEVEL_COLORS = ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353")
GLYPHS = {
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "V": ("10001", "10001", "10001", "10001", "01010", "01010", "00100"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
}


def _title():
    x = 0
    pixels = []
    for char in "GAEMI DELIVERY":
        if char == " ":
            x += 3
            continue
        glyph = GLYPHS[char]
        for y, row in enumerate(glyph):
            for col, bit in enumerate(row):
                if bit == "1":
                    pixels.append(f"M{x + col} {y}h1v1h-1z")
        x += len(glyph[0]) + 1
    return '<path fill="#ffda54" transform="translate(18 13) scale(3)" d="' + "".join(pixels) + '"/>'


def _point(cell):
    x, y = cell
    return LEFT + PITCH * x + CELL // 2, TOP + PITCH * y + CELL // 2


def _heading(start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    return {(1, 0): 0, (0, 1): 90, (-1, 0): 180, (0, -1): 270}[(dx, dy)]


def _motion(index, outbound, inbound, grid):
    positions, headings = {}, {}

    def move(cells, start, finish, reverse=False):
        if len(cells) < 2:
            return
        weights = [4 + grid[x][y] for x, y in cells[1:]]
        total = sum(weights)
        elapsed = 0
        for origin, target, weight in zip(cells, cells[1:], weights):
            start_time = start + (finish - start) * elapsed / total
            angle = _heading(origin, target)
            positions[start_time] = origin
            headings[start_time] = (angle + 180) % 360 if reverse else angle
            elapsed += weight
        positions[finish] = cells[-1]

    dock = outbound[0]
    parked_angle = _heading(inbound[-1], inbound[-2])
    positions[0] = dock
    headings[0] = parked_angle
    move(outbound, 6, 43)
    positions[55] = outbound[-1]
    move(inbound[:-1], 55, 88)
    move(inbound[-2:], 90, 94, reverse=True)
    positions[100] = dock
    headings[100] = parked_angle
    translation = []
    for time, cell in sorted(positions.items()):
        x, y = _point(cell)
        translation.append(f'{time:.4f}%{{transform:translate({x}px,{y}px)}}')
    rotation = [f'{time:.4f}%{{transform:rotate({angle}deg)}}'
                for time, angle in sorted(headings.items())]
    return (f'@keyframes drive-{index}{{' + ''.join(translation) + '}'
            + f'@keyframes face-{index}{{' + ''.join(rotation) + '}')


def _style(missions, grid):
    css = """
      text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#9198a1;font-size:12px}
      .mono{font-family:ui-monospace,Consolas,"Liberation Mono",monospace}
      .route{fill:none;stroke-linejoin:round;stroke-linecap:round;stroke-dasharray:2 4;stroke-width:1.8}
      .loop{animation-duration:var(--delivery-duration);animation-iteration-count:infinite;animation-timing-function:step-end}
      .mission{opacity:0}.mission-0{opacity:1}
      .back,.status,.delivered{opacity:0}.charging{opacity:1}
    """
    active_rules = []
    for index, (outbound, inbound) in enumerate(missions):
        selector = f'.mission-{index}'
        if len(outbound) > 1 and len(inbound) > 1:
            css += _motion(index, outbound, inbound, grid)
            active_rules.append(f'{selector} .robot{{animation-name:drive-{index};'
                                'animation-timing-function:linear}')
            active_rules.append(f'{selector} .heading{{animation-name:face-{index}}}')
        if len(missions) > 1:
            active_rules.append(f'{selector}{{animation:mission-slot {MISSION_SECONDS*len(missions)}s '
                                f'step-end {MISSION_SECONDS*index}s infinite}}')
    if len(missions) > 1:
        css += (f'@keyframes mission-slot{{0%{{opacity:1}}'
                f'{100/len(missions):.9f}%,100%{{opacity:0}}}}')
    intervals = {
        "go": (6, 43), "handoff": (43, 55), "returning": (55, 88),
        "docking": (88, 94), "back": (55, 94), "delivered": (43, 100),
    }
    for name, (start, end) in intervals.items():
        css += f'@keyframes {name}{{0%,100%{{opacity:0}}{start}%{{opacity:1}}{end}%{{opacity:0}}}}'
    css += """
      @keyframes charging{0%,94%,100%{opacity:1}6%{opacity:0}}
      @keyframes forward{0%,94%,100%{opacity:1}55%{opacity:0}}
      @keyframes cargo{0%,100%{opacity:1}43%{opacity:0}}
      @media(prefers-reduced-motion:no-preference){
        .moving .charging{animation-name:charging}.moving .cargo{animation-name:cargo}
        .forward{animation-name:forward}
    """
    active_rules.extend(f'.moving .{name}{{animation-name:{name}}}' for name in intervals)
    return css + ''.join(active_rules) + '}'


def _robot():
    # The nose points along +x. Keep the flag and roof lidar clear of the cargo indicator.
    return """
      <g shape-rendering="crispEdges">
        <g fill="#101319" stroke="#080c10" stroke-width="1">
          <rect x="-9" y="-10" width="6" height="5" rx="1"/>
          <rect x="4" y="-10" width="6" height="5" rx="1"/>
          <rect x="-9" y="5" width="6" height="5" rx="1"/>
          <rect x="4" y="5" width="6" height="5" rx="1"/>
        </g>
        <path fill="#677077" d="M-8-10h4v1h-4zm13 0h4v1H5zM-8 9h4v1h-4zm13 0h4v1H5z"/>
        <path fill="#171a20" d="M-12-5h2v-3h3v-1H7v1h3v2h2v2h1v8h-1v2h-2v2H7v1H-7V8h-3V6h-2z"/>
        <path fill="#d5900e" d="M-11-5h2v-2H6v1h2v12H6v2H-8V7h-2V5h-1z"/>
        <path fill="#ffcf27" d="M-10-5h2v-2H5v1h2v12H5v1H-8V5h-2z"/>
        <path fill="#ffe564" d="M-9-5h2v-1H4v1H-6v1h-3z"/>
        <path fill="#3b4146" d="M-1-6h5v1h1v1H1v-1h-2zM1 4h4v1H4v1h-5V5h2z"/>
        <path fill="#30353a" d="M7-6h2v1h2v2h1v6h-1v2H9v1H7z"/>
        <path fill="#14181c" d="M8-2h3v4H8z"/>
        <path fill="#20efef" d="M8-5h2v3H8zm0 7h2v3H8z"/>
        <path fill="#b5ffff" d="M9-5h1v2H9zm0 7h1v2H9z"/>
        <path fill="#ffdf49" d="M12-3h1v6h-1z"/>
        <path fill="#d44325" d="M0-2h4v4H0z"/>
        <path fill="#161b20" d="M1-3h2v1h1v3H0v-3h1z"/>
        <path fill="#7f888c" d="M1-2h2v1H1z"/>
        <g class="loop cargo">
          <path fill="#bd8115" d="M-8-2h5v5h-5z"/>
          <path fill="#f6ab37" d="M-8-2h5v4h-5z"/>
          <path fill="#ffeb9c" d="M-6-2h1v3h-1z"/>
        </g>
        <path fill="#6a757b" d="M-10-13h2v10h-2z"/>
        <path fill="#d5dddb" d="M-10-13h1v9h-1z"/>
        <path fill="#ffde35" d="M-8-14h3v1h2v1h2v1h-2v1h-2v1h-3z"/>
        <path fill="#383a2d" d="M-7-12h2v1h-2z"/>
        <path fill="#f45146" d="M-11-15h3v2h-3z"/>
      </g>
    """


def _route(cells, name, color):
    points = ' '.join(f'{x},{y}' for x, y in map(_point, cells))
    return f'<polyline class="route loop {name}" points="{points}" stroke="{color}"/>'


def _overlay(index, outbound, inbound, footer):
    parked = len(outbound) < 2 or len(inbound) < 2
    dx, dy = _point(outbound[0])
    gx, gy = _point(outbound[-1])
    state = 'parked' if parked else 'moving'
    parts = [f'<g class="mission mission-{index} {state}" data-mission="{index}">']
    if not parked:
        parts += [_route(outbound, 'forward', '#e5f4cb'), _route(inbound, 'back', '#ffca83')]
    parts.append(f'<g class="dock" transform="translate({dx} {dy})">'
                 '<rect x="-7" y="-7" width="14" height="14" rx="2" fill="#142e32" stroke="#82c9c5"/>'
                 '<path fill="#abf6e9" d="M0-5h4L1-1h3l-6 7 1-5h-3z"/></g>')
    if not parked:
        parts.append(f'<g class="dropoff" transform="translate({gx} {gy})">'
                     '<rect x="-7" y="-7" width="14" height="14" rx="2" fill="#352820" stroke="#efb37e"/>'
                     '<path fill="#ffbd7c" d="M0-5l5 5-5 5-5-5z"/>'
                     '<g class="loop delivered"><rect x="-7" y="-7" width="14" height="14" rx="2" fill="#f3b470"/>'
                     '<path d="m-4 0 3 3 5-6" fill="none" stroke="#291e18" stroke-width="2"/></g></g>')
    angle = 0 if parked else _heading(inbound[-1], inbound[-2])
    parts += [f'<g class="loop robot" transform="translate({dx} {dy})">'
              f'<g class="loop heading" transform="rotate({angle})">{_robot()}</g></g>']
    for phase, label, color in (('charging', 'Charging', '#8edbc6'), ('go', 'Out for delivery', '#f3b470'),
                                ('handoff', 'Parcel delivered', '#a7e49c'),
                                ('returning', 'Returning to dock', '#f3b470'),
                                ('docking', 'Reverse docking', '#8edbc6')):
        parts.append(f'<g class="loop status {phase}"><circle cx="21" cy="{footer-4}" r="3" fill="{color}"/>'
                     f'<text class="mono" x="32" y="{footer}" style="fill:#c9d1d9">{label}</text></g>')
    parts.append('</g>')
    return '\n'.join(parts)


def _terrain_tiles():
    tiles = ['<defs>']
    for level, color in enumerate(LEVEL_COLORS):
        tiles.append(f'<g id="terrain-{level}">')
        if level < 3:
            tiles.append(f'<rect width="{CELL}" height="{CELL}" rx="2" fill="{color}"/>')
            # Keep the middle clear for the route. Tread marks encode ground resistance.
            for mark in range(level):
                tiles.append(f'<path d="m{2 + 4*mark} 11 2-2" stroke="#87c8a0" '
                             'stroke-opacity=".48" stroke-width="1.3"/>')
        else:
            # The base stays inside its calendar cell; only the raised face projects upward.
            lift = 3 if level == 3 else 6
            tiles.append(f'<path fill="#16522e" d="M0 2l2-{lift}v11l-2 {lift}z"/>'
                         f'<path fill="#21753c" d="M0 13l2-{lift}h12l-2 {lift}z"/>'
                         f'<rect x="2" y="{2-lift}" width="12" height="11" rx="1" fill="{color}"/>'
                         f'<path d="M3 {3-lift}h9" stroke="#b8eea6" stroke-opacity=".58"/>')
            if level == 4:
                tiles.append('<path d="M2 10h10" stroke="#65bf68" stroke-opacity=".7"/>')
        tiles.append('</g>')
    return ''.join(tiles) + '</defs>'


def _tile(level, x, y):
    return f'<use xlink:href="#terrain-{level}" x="{x}" y="{y}"/>'


def _terrain_legend(width, baseline):
    # Repeat the actual map glyphs, with costs adjacent to the surfaces they describe.
    x = width - 300
    parts = [f'<g transform="translate({x} {baseline})" role="group" '
             'aria-label="Traversable terrain with base step costs 4, 5, 6, and blocked terrain">',
             '<text x="0" y="0">Base cost</text>']
    for level in range(3):
        offset = 63 + level * 38
        parts.extend((_tile(level, offset, -11),
                      f'<text x="{offset + 17}" y="0" style="fill:#c9d1d9">{4 + level}</text>'))
    parts += ['<path d="M177 -12v14" stroke="#30363d"/>',
              '<text x="191" y="0">Blocked</text>', _tile(3, 244, -10), _tile(4, 263, -10), '</g>']
    return ''.join(parts)


def render(grid, outbound, inbound, total, month_labels=()):
    """Return an animated SVG for a column-major contribution calendar and two cell paths."""
    return render_missions(grid, [(outbound, inbound)], total, month_labels)


def render_missions(grid, missions, total, month_labels=()):
    """Render the calendar once and cycle through a sequence of 24-second deliveries."""
    if not missions:
        raise ValueError("At least one delivery mission is required.")
    width = max(365, LEFT + len(grid) * PITCH + 13)
    footer = TOP + 7 * PITCH + 22
    height = footer + 17 + (28 if width < 500 else 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" style="--delivery-duration:{MISSION_SECONDS}s" '
        'role="img" aria-labelledby="title description">',
        '<title id="title">GAEMI DELIVERY</title>',
        f'<desc id="description">A top-down view of {total:,} GitHub contributions. A delivery '
        'robot follows a planned route across flat cells with base costs 4, 5 and 6. Raised blocks are impassable. The robot returns to charge.</desc>',
        '<style>' + _style(missions, grid) + '</style>',
        f'<rect width="{width}" height="{height}" rx="6" fill="#0d1117"/>', _terrain_tiles(), _title(),
        f'<text x="{width - 18}" y="31" text-anchor="end">robotdory’s {total:,} contributions</text>',
    ]
    for column, month in month_labels:
        parts.append(f'<text x="{LEFT + PITCH * column}" y="{TOP - 8}">{escape(month)}</text>')
    for y, day in ((1, 'Mon'), (3, 'Wed'), (5, 'Fri')):
        parts.append(f'<text x="{LEFT - 9}" y="{_point((0, y))[1] + 4}" text-anchor="end">{day}</text>')
    parts.append('<g class="terrain">')
    for x, week in enumerate(grid):
        for y, level in enumerate(week):
            if level >= 0:
                parts.append(_tile(level, LEFT + PITCH * x, TOP + PITCH * y))
    parts.append('</g>')
    for index, (outbound, inbound) in enumerate(missions):
        parts.append(_overlay(index, outbound, inbound, footer))
    parts.extend((_terrain_legend(width, height - 17), '</svg>'))
    return '\n'.join(parts) + '\n'
