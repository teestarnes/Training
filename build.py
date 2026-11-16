"""Step 6: build dashboard.html from the files in data/.

    python3 build.py

Makes ONE self-contained file (no internet needed to view it). Charts are
drawn as SVG here in Python, so they show up even in the Files app preview;
a tiny script adds tap/hover tooltips when the viewer allows scripts.
"""
import datetime as dt
import html
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "dashboard.html")
TODAY = dt.date.today()

# ---- your goals (from Step 4) ----
GOAL = "Get faster: sharp under 90 minutes, strong for 3-4 hours"
LONG_RIDE_NOW = 2.5        # hours available per ride for the next few weeks
LONG_RIDE_GOAL = (3, 4)    # hours to ramp toward
STRENGTH_TARGET = 2        # sessions per week

M_PER_MI = 1609.344
FT_PER_M = 3.28084

SPORTS = ["Road", "Gravel", "MTB", "Indoor", "Strength", "Other"]
COLOR = {s: f"var(--s{i + 1})" for i, s in enumerate(SPORTS[:5])}
COLOR["Other"] = "var(--muted)"
BIKE = {"Road", "Gravel", "MTB", "Indoor"}


# ---------------------------------------------------------------- loading

def load(name, default):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    try:
        with open(p) as f:
            return json.load(f)
    except (ValueError, OSError):
        return default


def dig(o, path):
    for k in path.split("."):
        if not isinstance(o, dict):
            return None
        o = o.get(k)
    return o


def sport_of(a):
    k = ((a.get("activityType") or {}).get("typeKey") or "").lower()
    if "gravel" in k or "cyclocross" in k:
        return "Gravel"
    if "mountain" in k or "mtb" in k or "downhill" in k or "enduro" in k:
        return "MTB"
    if "indoor" in k or "virtual" in k or "trainer" in k:
        return "Indoor"
    if "cycl" in k or "bik" in k or "ride" in k:
        return "Road"
    if "strength" in k:
        return "Strength"
    return "Other"


def week_of(d):
    return d - dt.timedelta(days=d.weekday())


def parse_acts():
    out = []
    for a in load("activities.json", []):
        try:
            day = dt.date.fromisoformat(a["startTimeLocal"][:10])
        except (KeyError, ValueError, TypeError):
            continue
        dur = a.get("movingDuration") or a.get("duration") or 0
        out.append({
            "date": day,
            "name": a.get("activityName") or "",
            "sport": sport_of(a),
            "mi": (a.get("distance") or 0) / M_PER_MI,
            "hrs": (a.get("duration") or 0) / 3600,
            "moving_hrs": dur / 3600,
            "ft": (a.get("elevationGain") or 0) * FT_PER_M,
            "load": a.get("activityTrainingLoad") or 0,
            "p20": a.get("maxAvgPower_1200") or a.get("max20MinPower"),
            "p60": a.get("maxAvgPower_3600"),
            "np": a.get("normPower"),
        })
    out.sort(key=lambda x: x["date"])
    return out


# ---------------------------------------------------------------- formatting

def esc(s):
    return html.escape(str(s), quote=True)


def fdate(d, year=True):
    return d.strftime("%b %-d, %Y" if year else "%b %-d")


def fh(h):
    m = int(round(h * 60))
    return f"{m // 60}:{m % 60:02d}"


def nice_max(v):
    if v <= 0:
        return 1
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * e >= v:
            return m * e
    return 10 * e


def nice_step(span, n=4):
    raw = span / n if span > 0 else 1
    e = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * e >= raw:
            return m * e
    return 10 * e


def nice_scale(lo, hi, n=4):
    step = nice_step(hi - lo, n)
    lo = math.floor(lo / step) * step
    hi = math.ceil(hi / step) * step
    if hi <= lo:
        hi = lo + step
    return lo, hi, step


def ticks(lo, hi, step):
    out, v = [], lo
    while v <= hi + step * 1e-6:
        out.append(round(v, 6))
        v += step
    return out


def tnum(v):
    if abs(v) >= 100 or v == int(v):
        return f"{v:,.0f}"
    return f"{v:.1f}"


# ---------------------------------------------------------------- SVG charts
W, H = 520, 230
ML, MR, MT, MB = 44, 12, 14, 30


def frame(ymin, ymax, labels, unit="", step=None):
    """Grid, y ticks and x labels. labels: list of (x, text)."""
    pw, ph = W - ML - MR, H - MT - MB
    g = []
    for v in ticks(ymin, ymax, step or nice_step(ymax - ymin)):
        y = MT + ph - (v - ymin) / (ymax - ymin) * ph
        g.append(f'<line class="gl" x1="{ML}" x2="{W - MR}" y1="{y:.1f}" y2="{y:.1f}"/>')
        g.append(f'<text class="tick" x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end">'
                 f'{tnum(v)}{unit}</text>')
    for x, t in labels:
        g.append(f'<text class="tick" x="{x:.1f}" y="{H - 8}" text-anchor="middle">{esc(t)}</text>')
    return "".join(g)


def svg(body, label):
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{body}</svg>')


def xlabels(n, text_at, every=None):
    pw = W - ML - MR
    every = every or max(1, math.ceil(n / 6))
    out = []
    for i in range(n):
        if (n - 1 - i) % every == 0:
            out.append((ML + (i + 0.5) * pw / n, text_at(i)))
    return out


def bar_chart(cols, stacks, tips, label, unit="", refs=(), xl=None, ymax=None, bands=()):
    """cols: number of columns. stacks: list of (color, values[]) bottom-up."""
    pw, ph = W - ML - MR, H - MT - MB
    tot = [sum(s[1][i] for s in stacks) for i in range(cols)]
    peak = max(tot + [r[0] for r in refs] + [b[1] for b in bands] + [0.01]) * 1.04
    _, top, step = nice_scale(0, ymax or peak)
    y = lambda v: MT + ph - v / top * ph
    bw = pw / cols
    body = [frame(0, top, xl or [], unit, step)]
    for b_lo, b_hi, b_text in bands:
        body.append(f'<rect class="band" x="{ML}" width="{pw}" y="{y(b_hi):.1f}" '
                    f'height="{y(b_lo) - y(b_hi):.1f}"/>'
                    f'<text class="reflabel" x="{ML + 4}" y="{y(b_hi) + 14:.1f}">{esc(b_text)}</text>')
    for r_val, r_text in refs:
        yy = y(r_val)
        body.append(f'<line class="ref" x1="{ML}" x2="{W - MR}" y1="{yy:.1f}" y2="{yy:.1f}"/>'
                    f'<text class="reflabel" x="{W - MR - 2}" y="{yy - 4:.1f}" '
                    f'text-anchor="end">{esc(r_text)}</text>')
    for i in range(cols):
        x0 = ML + i * bw + bw * 0.16
        w = bw * 0.68
        base = 0
        segs = [(c, v[i]) for c, v in stacks if v[i] > 0]
        for j, (c, v) in enumerate(segs):
            y1, y0 = y(base + v), y(base)
            h = max(0.0, y0 - y1 - (2 if j < len(segs) - 1 else 0))
            r = min(4, w / 2, h / 2) if j == len(segs) - 1 else 0
            if r:
                body.append(f'<path fill="{c}" d="M{x0:.1f},{y0:.1f}V{y1 + r:.1f}'
                            f'Q{x0:.1f},{y1:.1f} {x0 + r:.1f},{y1:.1f}H{x0 + w - r:.1f}'
                            f'Q{x0 + w:.1f},{y1:.1f} {x0 + w:.1f},{y1 + r:.1f}V{y0:.1f}Z"/>')
            else:
                body.append(f'<rect fill="{c}" x="{x0:.1f}" y="{y1:.1f}" width="{w:.1f}" '
                            f'height="{h:.1f}"/>')
            base += v
        body.append(f'<rect class="hit" x="{ML + i * bw:.1f}" y="{MT}" width="{bw:.1f}" '
                    f'height="{ph}" data-tip="{esc(tips[i])}"/>')
    return svg("".join(body), label)


def line_chart(n, series, tips, label, unit="", band=None, xl=None, ymin=None,
               ymax=None, refs=()):
    """series: list of (color, values[] with None gaps, dots?, width)."""
    pw, ph = W - ML - MR, H - MT - MB
    vals = [v for s in series for v in s[1] if v is not None]
    if band:
        vals += [v for b in band[1:] for v in b if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi, step = nice_scale(ymin if ymin is not None else lo - pad,
                              ymax if ymax is not None else hi + pad)
    xs = lambda i: ML + (i + 0.5) * pw / n
    y = lambda v: MT + ph - (v - lo) / (hi - lo) * ph
    body = [frame(lo, hi, xl or [], unit, step)]
    for r_val, r_text in refs:
        if lo <= r_val <= hi:
            yy = y(r_val)
            body.append(f'<line class="ref" x1="{ML}" x2="{W - MR}" y1="{yy:.1f}" y2="{yy:.1f}"/>'
                        f'<text class="reflabel" x="{W - MR - 2}" y="{yy - 4:.1f}" '
                        f'text-anchor="end">{esc(r_text)}</text>')
    if band:
        color, low, high = band
        pts_hi = [(xs(i), y(high[i])) for i in range(n) if high[i] is not None and low[i] is not None]
        pts_lo = [(xs(i), y(low[i])) for i in range(n) if high[i] is not None and low[i] is not None]
        if pts_hi:
            d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts_hi + pts_lo[::-1]) + "Z"
            body.append(f'<path d="{d}" fill="{color}" opacity="0.14"/>')
    for color, values, dots, width in series:
        path, pen = [], False
        for i, v in enumerate(values):
            if v is None:
                pen = False
                continue
            path.append(("L" if pen else "M") + f"{xs(i):.1f},{y(v):.1f}")
            pen = True
        if dots:
            for i, v in enumerate(values):
                if v is not None:
                    body.append(f'<circle cx="{xs(i):.1f}" cy="{y(v):.1f}" r="{dots}" '
                                f'fill="{color}" class="dot"/>')
        if path and width:
            body.append(f'<path d="{"".join(path)}" fill="none" stroke="{color}" '
                        f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')
    bw = pw / n
    for i in range(n):
        if tips[i]:
            body.append(f'<rect class="hit" x="{ML + i * bw:.1f}" y="{MT}" width="{bw:.2f}" '
                        f'height="{ph}" data-tip="{esc(tips[i])}"/>')
    return svg("".join(body), label)


def legend(items):
    return '<div class="legend">' + "".join(
        f'<span><i style="background:{c}"></i>{esc(t)}</span>' for t, c in items) + "</div>"


def card(title, question, chart, note="", wide=False):
    if not chart:
        return ""
    return (f'<section class="card{" wide" if wide else ""}"><h3>{esc(title)}</h3>'
            f'<p class="q">{esc(question)}</p>{chart}'
            f'{f"<p class=note>{note}</p>" if note else ""}</section>')


def rolling(values, k):
    out, win = [], []
    for v in values:
        win.append(v)
        if len(win) > k:
            win.pop(0)
        got = [x for x in win if x is not None]
        out.append(sum(got) / len(got) if len(got) >= max(1, k // 2) else None)
    return out


# ---------------------------------------------------------------- build

def main():
    acts = parse_acts()
    if not acts:
        print("No activities in data/ yet. Run: python3 pull.py")
        return
    apple = load("apple.json", {})
    gdaily = load("daily.json", {})
    gsleep = load("sleep.json", {})
    ghrv = load("hrv.json", {})

    # ---------- weekly rollups
    this_week = week_of(TODAY)
    weeks = defaultdict(lambda: defaultdict(lambda: {"hrs": 0, "mi": 0, "n": 0}))
    wload = defaultdict(float)
    longest = defaultdict(float)
    for a in acts:
        w = week_of(a["date"])
        s = weeks[w][a["sport"]]
        s["hrs"] += a["hrs"]
        s["mi"] += a["mi"]
        s["n"] += 1
        wload[w] += a["load"]
        if a["sport"] in BIKE:
            longest[w] = max(longest[w], a["hrs"])

    def wk(w, key, sports=BIKE):
        return sum(weeks[w][s][key] for s in sports if s in weeks[w])

    prev8 = [this_week - dt.timedelta(weeks=i) for i in range(1, 9)]
    avg = lambda f: sum(f(w) for w in prev8) / 8
    last7 = [a for a in acts if a["date"] > TODAY - dt.timedelta(days=7)]
    l7 = lambda key, sports=BIKE: sum(a[key] for a in last7 if a["sport"] in sports)

    tiles = []

    def tile(label, now, base, fmt):
        delta = ""
        if base:
            pct = (now - base) / base * 100
            arrow = "&#9650;" if pct >= 0 else "&#9660;"
            delta = f' &middot; <span class="delta">{arrow} {abs(pct):.0f}%</span>'
        tiles.append(f'<div class="tile"><div class="tl">{label}</div>'
                     f'<div class="tv">{fmt(now)}</div>'
                     f'<div class="ts">8-week avg {fmt(base)}{delta}</div></div>')

    tile("Bike miles, last 7 days", l7("mi"), avg(lambda w: wk(w, "mi")),
         lambda v: f"{v:,.0f}")
    tile("Bike hours, last 7 days", l7("hrs"), avg(lambda w: wk(w, "hrs")), fh)
    tile("Training load, last 7 days", sum(a["load"] for a in last7), avg(lambda w: wload[w]),
         lambda v: f"{v:,.0f}")
    st_now = sum(1 for a in last7 if a["sport"] == "Strength")
    st_avg = avg(lambda w: weeks[w]["Strength"]["n"] if "Strength" in weeks[w] else 0)
    tiles.append(f'<div class="tile"><div class="tl">Strength, last 7 days</div>'
                 f'<div class="tv">{st_now} <small>of {STRENGTH_TARGET}</small></div>'
                 f'<div class="ts">{"Target met" if st_now >= STRENGTH_TARGET else f"{STRENGTH_TARGET - st_now} to go"}'
                 f' &middot; 8-week avg {st_avg:.1f}/wk</div></div>')

    # year to date
    ytd = sum(a["mi"] for a in acts if a["sport"] in BIKE and a["date"].year == TODAY.year)
    try:
        same_day_ly = TODAY.replace(year=TODAY.year - 1)
    except ValueError:
        same_day_ly = TODAY - dt.timedelta(days=365)
    ly = sum(a["mi"] for a in acts if a["sport"] in BIKE and a["date"].year == TODAY.year - 1
             and a["date"] <= same_day_ly)

    # ---------- fitness / fatigue from Garmin training load
    start = max(acts[0]["date"], TODAY - dt.timedelta(days=3 * 365))
    daily_load = defaultdict(float)
    for a in acts:
        daily_load[a["date"]] += a["load"]
    ctl = atl = 0.0
    fit_days, ctl_s, atl_s = [], [], []
    d = start
    while d <= TODAY:
        L = daily_load.get(d, 0)
        ctl += (L - ctl) / 42
        atl += (L - atl) / 7
        if d > TODAY - dt.timedelta(days=182):
            fit_days.append(d)
            ctl_s.append(ctl)
            atl_s.append(atl)
        d += dt.timedelta(days=1)
    form = ctl - atl
    ctl_4wk = ctl_s[-29] if len(ctl_s) > 29 else ctl_s[0]
    trend = ctl - ctl_4wk
    fit_tips = [f"{fdate(day)}\nFitness (42-day) {c:.0f}\nFatigue (7-day) {f:.0f}\n"
                f"Form {c - f:+.0f}\nLoad that day {daily_load.get(day, 0):.0f}"
                for day, c, f in zip(fit_days, ctl_s, atl_s)]
    month_lab = lambda days: lambda i: days[i].strftime("%b")
    fit_xl = [(ML + (i + 0.5) * (W - ML - MR) / len(fit_days), fit_days[i].strftime("%b"))
              for i in range(len(fit_days)) if fit_days[i].day == 1]
    fitness_chart = line_chart(
        len(fit_days),
        [("var(--s1)", ctl_s, 0, 2.5), ("var(--s2)", atl_s, 0, 1.5)],
        fit_tips, "Fitness and fatigue, last 6 months", xl=fit_xl, ymin=0)
    fitness_chart = legend([("Fitness: 42-day load", "var(--s1)"),
                            ("Fatigue: 7-day load", "var(--s2)")]) + fitness_chart
    form_word = ("fresh" if form > 5 else "balanced" if form > -10 else
                 "building (tired)" if form > -30 else "very fatigued")

    # ---------- weekly volume by sport (16 weeks)
    W16 = [this_week - dt.timedelta(weeks=i) for i in range(15, -1, -1)]
    stack_sports = ["Road", "Gravel", "MTB", "Indoor", "Strength"]
    stacks = [(COLOR[s], [weeks[w][s]["hrs"] if s in weeks[w] else 0 for w in W16])
              for s in stack_sports]
    vol_tips = []
    for w in W16:
        lines = [f"Week of {fdate(w, False)}{' (so far)' if w == this_week else ''}"]
        for s in stack_sports + ["Other"]:
            if s in weeks[w] and weeks[w][s]["n"]:
                x = weeks[w][s]
                lines.append(f"{s}: {fh(x['hrs'])} h" +
                             (f", {x['mi']:.0f} mi" if s in BIKE and x['mi'] else "") +
                             f" ({x['n']}x)")
        lines.append(f"Bike total: {wk(w, 'mi'):.0f} mi, {fh(wk(w, 'hrs'))} h")
        lines.append(f"Training load: {wload[w]:.0f}")
        vol_tips.append("\n".join(lines))
    wk_lab = lambda i: W16[i].strftime("%-m/%-d")
    vol_chart = legend([(s, COLOR[s]) for s in stack_sports]) + bar_chart(
        16, stacks, vol_tips, "Weekly hours by sport", unit="h", xl=xlabels(16, wk_lab, 3))

    # weekly miles + load small chart
    miles_chart = bar_chart(16, [("var(--s1)", [wk(w, "mi") for w in W16])],
                            [f"Week of {fdate(w, False)}\n{wk(w, 'mi'):.0f} bike miles\n"
                             f"{fh(wk(w, 'hrs'))} h on the bike" for w in W16],
                            "Weekly bike miles", xl=xlabels(16, wk_lab, 3))

    # ---------- longest ride each week (26 weeks)
    W26 = [this_week - dt.timedelta(weeks=i) for i in range(25, -1, -1)]
    long_vals = [longest[w] for w in W26]
    long_chart = bar_chart(
        26, [("var(--s1)", long_vals)],
        [f"Week of {fdate(w, False)}\nLongest ride {fh(longest[w])} h" for w in W26],
        "Longest ride each week", unit="h",
        refs=[(LONG_RIDE_NOW, f"{LONG_RIDE_NOW:g} h: current max")],
        bands=[(LONG_RIDE_GOAL[0], LONG_RIDE_GOAL[1], f"Goal {LONG_RIDE_GOAL[0]}-{LONG_RIDE_GOAL[1]} h")],
        xl=xlabels(26, lambda i: W26[i].strftime("%-m/%-d"), 5))

    # ---------- speed and power by month (24 months)
    months = []
    m = dt.date(TODAY.year, TODAY.month, 1)
    for _ in range(24):
        months.append(m)
        m = (m - dt.timedelta(days=1)).replace(day=1)
    months.reverse()
    mkey = lambda d: (d.year, d.month)
    spd = defaultdict(lambda: {"s": [0, 0, 0], "l": [0, 0, 0]})
    p20 = defaultdict(float)
    p60 = defaultdict(float)
    for a in acts:
        k = mkey(a["date"])
        if a["sport"] == "Road" and a["mi"] > 3 and a["moving_hrs"] > 0.25:
            b = "s" if a["hrs"] < 1.5 else "l" if a["hrs"] >= 2 else None
            if b:
                spd[k][b][0] += a["mi"]
                spd[k][b][1] += a["moving_hrs"]
                spd[k][b][2] += 1
        if a["sport"] in BIKE:
            if a["p20"]:
                p20[k] = max(p20[k], a["p20"])
            if a["p60"]:
                p60[k] = max(p60[k], a["p60"])

    def mph(k, b):
        x = spd[k][b]
        return x[0] / x[1] if x[2] >= 2 else None

    sp_s = [mph(mkey(m), "s") for m in months]
    sp_l = [mph(mkey(m), "l") for m in months]
    def sp_line(label, v, n):
        return f"{label}: {v:.1f} mph ({n} rides)" if v else f"{label}: not enough rides"

    sp_tips = ["\n".join([m.strftime("%B %Y"),
                           sp_line("Under 90 min", sp_s[i], spd[mkey(m)]["s"][2]),
                           sp_line("2 h and longer", sp_l[i], spd[mkey(m)]["l"][2])])
               for i, m in enumerate(months)]
    mon_xl = xlabels(24, lambda i: months[i].strftime("%b %y"), 4)
    speed_chart = ""
    if any(sp_s) or any(sp_l):
        speed_chart = legend([("Rides under 90 min", "var(--s1)"),
                              ("Rides 2 h and longer", "var(--s2)")]) + line_chart(
            24, [("var(--s1)", sp_s, 4, 2), ("var(--s2)", sp_l, 4, 2)], sp_tips,
            "Average road speed by month", unit="", xl=mon_xl)

    n_power = sum(1 for a in acts if a["p20"])
    power_chart = ""
    if n_power >= 5:
        v20 = [p20[mkey(m)] or None for m in months]
        v60 = [p60[mkey(m)] or None for m in months]
        if any(v20):
            power_chart = legend([("Best 20 min", "var(--s1)"), ("Best 60 min", "var(--s2)")]) + \
                line_chart(24, [("var(--s1)", v20, 4, 2), ("var(--s2)", v60, 4, 2)],
                           [f"{m.strftime('%B %Y')}\nBest 20 min: {f'{v20[i]:.0f} W' if v20[i] else '-'}\n"
                            f"Best 60 min: {f'{v60[i]:.0f} W' if v60[i] else '-'}"
                            for i, m in enumerate(months)],
                           "Best power by month", unit="", xl=mon_xl)

    # ---------- VO2 max (Apple)
    vo2 = apple.get("vo2max") or {}
    vo2_chart = ""
    if len(vo2) >= 5:
        vd = sorted(vo2.items())[-60:]
        vo2_chart = line_chart(
            len(vd), [("var(--s1)", [v for _, v in vd], 4, 2)],
            [f"{fdate(dt.date.fromisoformat(k))}\nVO2 max {v:.1f}" for k, v in vd],
            "VO2 max from Apple Watch",
            xl=xlabels(len(vd), lambda i: dt.date.fromisoformat(vd[i][0]).strftime("%b %y"),
                       max(1, len(vd) // 4)))

    # ---------- strength + mix
    st_vals = [weeks[w]["Strength"]["n"] if "Strength" in weeks[w] else 0 for w in W16]
    strength_chart = bar_chart(
        16, [(COLOR["Strength"], st_vals)],
        [f"Week of {fdate(w, False)}\n{v} strength session{'s' if v != 1 else ''}"
         for w, v in zip(W16, st_vals)],
        "Strength sessions per week", refs=[(STRENGTH_TARGET, f"target {STRENGTH_TARGET}/wk")],
        xl=xlabels(16, wk_lab, 3), ymax=max(4, max(st_vals) + 1))

    def mix(days):
        cut = TODAY - dt.timedelta(days=days)
        h = defaultdict(float)
        for a in acts:
            if a["date"] > cut:
                h[a["sport"]] += a["hrs"]
        return h

    def mixbar(h, title):
        tot = sum(h.values()) or 1
        segs, x = [], 0
        for s in SPORTS:
            if h.get(s):
                pct = h[s] / tot * 100
                tip = title + "\n" + f"{s}: {pct:.0f}% ({fh(h[s])} h)"
                segs.append(f'<span style="width:{pct:.2f}%;background:{COLOR[s]}" '
                            f'data-tip="{esc(tip)}">{s if pct >= 9 else ""}</span>')
        return (f'<div class="mixrow"><div class="mixl">{esc(title)}</div>'
                f'<div class="mix">{"".join(segs)}</div></div>')

    mix_html = (legend([(s, COLOR[s]) for s in SPORTS]) + mixbar(mix(90), "Last 90 days") +
                mixbar(mix(365), "Last 12 months") + mixbar(
                    defaultdict(float, {k: v for k, v in mix(365 * 3).items()}), "Last 3 years"))

    # ---------- recovery: choose Garmin or Apple per metric
    def series_from_garmin_daily(path):
        return {k: dig(v, path) for k, v in gdaily.items() if dig(v, path)}

    def pick(garmin_vals, apple_vals):
        cut = (TODAY - dt.timedelta(days=90)).isoformat()
        g = sum(1 for k in garmin_vals if k >= cut)
        a = sum(1 for k in (apple_vals or {}) if k >= cut)
        return (garmin_vals, "Garmin") if g > a else (apple_vals or {}, "Apple Watch")

    hrv, hrv_src = pick({k: v.get("lastNightAvg") for k, v in ghrv.items()
                         if v.get("lastNightAvg")}, apple.get("hrv"))
    rhr, rhr_src = pick(series_from_garmin_daily("heartRate.restingValue"), apple.get("rhr"))
    a_sleep = {k: v["total"] / 60 for k, v in (apple.get("sleep") or {}).items()}
    g_sleep = {k: v["sleepTimeSeconds"] / 3600 for k, v in gsleep.items()
               if v.get("sleepTimeSeconds")}
    sleep, sleep_src = pick(g_sleep, a_sleep)
    stages = apple.get("sleep") or {} if sleep_src == "Apple Watch" else {}

    days180 = [TODAY - dt.timedelta(days=i) for i in range(179, -1, -1)]
    d_xl = [(ML + (i + 0.5) * (W - ML - MR) / 180, days180[i].strftime("%b"))
            for i in range(180) if days180[i].day == 1]

    def daily_chart(data, name, unit, k=7, fmt="{:.0f}", extra=None, lower_better=False):
        raw = [data.get(d.isoformat()) for d in days180]
        if sum(1 for v in raw if v) < 20:
            return "", None
        # look back further so the first points of the rolling average are real
        pre = [data.get((days180[0] - dt.timedelta(days=i)).isoformat()) for i in range(60, 0, -1)]
        full = pre + raw
        sm = rolling(full, k)[60:]
        base = rolling(full, 60)[60:]
        sd = []
        for i in range(180):
            win = [v for v in full[i: i + 61] if v is not None]
            if len(win) >= 10:
                mu = sum(win) / len(win)
                sd.append((sum((v - mu) ** 2 for v in win) / len(win)) ** 0.5)
            else:
                sd.append(None)
        lo = [b - s if b is not None and s is not None else None for b, s in zip(base, sd)]
        hi = [b + s if b is not None and s is not None else None for b, s in zip(base, sd)]
        tips = []
        for i, d in enumerate(days180):
            t = [fdate(d)]
            t.append(f"That day: {fmt.format(raw[i])} {unit}" if raw[i] else "That day: no reading")
            if sm[i] is not None:
                t.append(f"{k}-day average: {fmt.format(sm[i])} {unit}")
            if lo[i] is not None:
                t.append(f"Your normal: {fmt.format(lo[i])}-{fmt.format(hi[i])} {unit}")
            if extra:
                t += extra(d)
            tips.append("\n".join(t))
        chart = legend([(f"{k}-day average", "var(--s1)"), ("Daily", "var(--dot)"),
                        ("Your normal range (60 days)", "var(--band)")]) + line_chart(
            180, [("var(--dot)", raw, 1.6, 0), ("var(--s1)", sm, 0, 2.5)], tips, name,
            band=("var(--s1)", lo, hi), xl=d_xl)
        last = next((v for v in reversed(sm) if v is not None), None)
        return chart, last

    hrv_chart, hrv_now = daily_chart(hrv, "HRV", "ms")
    rhr_chart, rhr_now = daily_chart(rhr, "Resting heart rate", "bpm")

    def sleep_extra(d):
        s = stages.get(d.isoformat())
        if not s:
            return []
        out = [f"Deep {fh(s['deep'] / 60)}, REM {fh(s['rem'] / 60)}, Core {fh(s['core'] / 60)}"]
        if s.get("awake"):
            out.append(f"Awake {s['awake']} min")
        return out

    sleep_chart, sleep_now = daily_chart(sleep, "Sleep", "h", fmt="{:.1f}", extra=sleep_extra)

    # ---------- blood pressure
    bp = apple.get("bp") or []
    bp_chart, bp_tile = "", ""
    if len(bp) >= 5:
        bym = defaultdict(list)
        for r in bp:
            bym[r["when"][:7]].append(r)
        st_month = defaultdict(int)
        for a in acts:
            if a["sport"] == "Strength":
                st_month[a["date"].strftime("%Y-%m")] += 1
        keys = [m.strftime("%Y-%m") for m in months]
        sys_v = [sum(r["sys"] for r in bym[k]) / len(bym[k]) if bym.get(k) else None for k in keys]
        dia_v = [sum(r["dia"] for r in bym[k]) / len(bym[k]) if bym.get(k) else None for k in keys]
        tips = [f"{m.strftime('%B %Y')}\n" +
                (f"Average {sys_v[i]:.0f}/{dia_v[i]:.0f} ({len(bym[keys[i]])} readings)"
                 if sys_v[i] else "No readings") +
                f"\nStrength sessions: {st_month.get(keys[i], 0)}"
                for i, m in enumerate(months)]
        if any(sys_v):
            bp_chart = legend([("Systolic (top)", "var(--s1)"), ("Diastolic (bottom)", "var(--s2)")]) + \
                line_chart(24, [("var(--s1)", sys_v, 4, 2), ("var(--s2)", dia_v, 4, 2)], tips,
                           "Blood pressure, monthly average", xl=mon_xl,
                           refs=[(120, "120"), (80, "80")])
        recent = sorted(bp, key=lambda r: r["when"])[-7:]
        s_avg = sum(r["sys"] for r in recent) / len(recent)
        d_avg = sum(r["dia"] for r in recent) / len(recent)
        cat = ("Normal" if s_avg < 120 and d_avg < 80 else
               "Elevated" if s_avg < 130 and d_avg < 80 else
               "Stage 1 range" if s_avg < 140 and d_avg < 90 else "Stage 2 range")
        bp_tile = (f'<div class="tile"><div class="tl">Blood pressure</div>'
                   f'<div class="tv">{s_avg:.0f}/{d_avg:.0f}</div>'
                   f'<div class="ts">avg of last {len(recent)} readings &middot; {cat} (AHA)</div></div>')

    # ---------- records
    bikes = [a for a in acts if a["sport"] in BIKE]
    outdoor = [a for a in bikes if a["sport"] != "Indoor"]

    def best(items, key, fmt, this_year=False):
        pool = [a for a in items if key(a)]
        if this_year:
            pool = [a for a in pool if a["date"].year == TODAY.year]
        if not pool:
            return "-"
        b = max(pool, key=key)
        return f'{fmt(key(b))}<small>{fdate(b["date"])}</small>'

    week_mi = defaultdict(float)
    month_mi = defaultdict(float)
    for a in bikes:
        week_mi[week_of(a["date"])] += a["mi"]
        month_mi[(a["date"].year, a["date"].month)] += a["mi"]

    def best_period(dct, fmt, label, this_year=False):
        items = [(k, v) for k, v in dct.items()
                 if not this_year or (k.year if isinstance(k, dt.date) else k[0]) == TODAY.year]
        if not items:
            return "-"
        k, v = max(items, key=lambda kv: kv[1])
        when = (f"week of {fdate(k)}" if isinstance(k, dt.date)
                else dt.date(k[0], k[1], 1).strftime("%B %Y"))
        return f"{fmt(v)}<small>{when}</small>"

    fast = lambda a: a["mi"] / a["moving_hrs"] if a["sport"] == "Road" and a["mi"] >= 20 and a["moving_hrs"] else 0
    recs = [
        ("Longest ride", lambda ty: best(outdoor, lambda a: a["mi"], lambda v: f"{v:.1f} mi", ty)),
        ("Longest time on the bike", lambda ty: best(bikes, lambda a: a["hrs"], lambda v: f"{fh(v)} h", ty)),
        ("Most climbing in a ride", lambda ty: best(outdoor, lambda a: a["ft"], lambda v: f"{v:,.0f} ft", ty)),
        ("Fastest road ride (20+ mi)", lambda ty: best(bikes, fast, lambda v: f"{v:.1f} mph", ty)),
        ("Best 20-min power", lambda ty: best(bikes, lambda a: a["p20"] or 0, lambda v: f"{v:.0f} W", ty)),
        ("Best 60-min power", lambda ty: best(bikes, lambda a: a["p60"] or 0, lambda v: f"{v:.0f} W", ty)),
        ("Biggest training load (one ride)", lambda ty: best(bikes, lambda a: a["load"], lambda v: f"{v:.0f}", ty)),
        ("Biggest week", lambda ty: best_period(week_mi, lambda v: f"{v:.0f} mi", "week", ty)),
        ("Biggest month", lambda ty: best_period(month_mi, lambda v: f"{v:,.0f} mi", "month", ty)),
    ]
    rec_rows = "".join(
        f"<tr><th>{esc(n)}</th><td>{f(False)}</td><td>{f(True)}</td></tr>"
        for n, f in recs if f(False) != "-")
    top5 = sorted(outdoor, key=lambda a: a["mi"], reverse=True)[:5]
    top_rows = "".join(
        f'<tr><td>{fdate(a["date"])}</td><td>{esc(a["name"][:40])}</td><td>{a["sport"]}</td>'
        f'<td class="r">{a["mi"]:.1f}</td><td class="r">{fh(a["hrs"])}</td>'
        f'<td class="r">{a["ft"]:,.0f}</td></tr>' for a in top5)

    # ---------- headline tiles row 2
    tiles2 = []
    ytd_delta = f"{(ytd - ly) / ly * 100:+.0f}% vs same date last year" if ly else ""
    tiles2.append(f'<div class="tile"><div class="tl">Bike miles in {TODAY.year}</div>'
                  f'<div class="tv">{ytd:,.0f}</div><div class="ts">{ytd_delta}</div></div>')
    tiles2.append(f'<div class="tile"><div class="tl">Fitness (42-day load)</div>'
                  f'<div class="tv">{ctl:.0f}</div><div class="ts">'
                  f'{"&#9650;" if trend >= 0 else "&#9660;"} {abs(trend):.0f} in 4 weeks &middot; '
                  f'form {form:+.0f}, {form_word}</div></div>')
    if hrv_now:
        tiles2.append(f'<div class="tile"><div class="tl">HRV, 7-day avg</div>'
                      f'<div class="tv">{hrv_now:.0f} <small>ms</small></div>'
                      f'<div class="ts">{hrv_src}</div></div>')
    if rhr_now:
        tiles2.append(f'<div class="tile"><div class="tl">Resting HR, 7-day avg</div>'
                      f'<div class="tv">{rhr_now:.0f} <small>bpm</small></div>'
                      f'<div class="ts">{rhr_src}</div></div>')
    if bp_tile:
        tiles2.append(bp_tile)

    last_long = max((a["hrs"] for a in bikes if a["date"] >= this_week - dt.timedelta(weeks=4)),
                    default=0)

    # ---------- page
    meta = load("meta.json", {})
    updated = meta.get("last_pull", "")[:16].replace("T", " ")
    since = acts[0]["date"]
    sections = [
        ("This week and recent weeks", [
            card("Weekly hours by sport", "Am I putting in the time, and where is it going?",
                 vol_chart),
            card("Weekly bike miles", "How does my mileage compare with recent weeks?", miles_chart),
            card("Fitness and fatigue", "Am I building fitness or just getting tired?",
                 fitness_chart,
                 "Fitness is your 42-day average of Garmin's training load; fatigue is the "
                 "7-day average. Form = fitness &minus; fatigue. When fatigue sits well above "
                 "fitness for weeks, plan an easier week."),
        ]),
        ("Getting faster", [
            card("Longest ride each week", f"Am I ramping toward {LONG_RIDE_GOAL[0]}-{LONG_RIDE_GOAL[1]} hour rides?",
                 long_chart, f"Longest in the last 4 weeks: {fh(last_long)} h."),
            card("Road speed, short vs long rides",
                 "Am I getting faster in sub-90-minute rides and in longer ones?", speed_chart,
                 "Average moving speed in mph, outdoor road rides only, months with 2+ rides. "
                 "Wind, route and group rides move this around, so watch the trend."),
            card("Best power by month", "Is my power going up?", power_chart),
            card("VO2 max", "Is my aerobic engine improving?", vo2_chart,
                 "Apple Watch estimate."),
        ]),
        ("Well-rounded", [
            card("Strength sessions per week",
                 "Am I getting my strength work in (bike, golf, blood pressure)?", strength_chart),
            card("Training mix by time", "Am I less cycling-only than I used to be?", mix_html),
            card("Blood pressure", "Is my blood pressure moving the right way as strength work goes up?",
                 bp_chart, "Tap a month to see how many strength sessions you did. Reference lines at 120 "
                 "and 80. This is a training log, not medical advice."),
        ]),
        ("Recovery", [
            card("HRV", "Am I recovered, compared with my own normal?", hrv_chart,
                 f"From {hrv_src}. Apple measures HRV differently from Garmin and Whoop, so "
                 "compare against your own range, not other devices."),
            card("Resting heart rate", "Is my resting heart rate trending down?", rhr_chart,
                 f"From {rhr_src}. A few beats above your normal often means fatigue, "
                 "illness or poor sleep."),
            card("Sleep", "Am I sleeping enough to absorb the training?", sleep_chart,
                 f"From {sleep_src}. Tap a day to see sleep stages."),
        ]),
    ]
    body_sections = ""
    for title, cards in sections:
        inner = "".join(c for c in cards if c)
        if inner:
            body_sections += f'<h2>{esc(title)}</h2><div class="grid">{inner}</div>'

    page = TEMPLATE.format(
        goal=esc(GOAL), updated=esc(updated or TODAY.isoformat()),
        since=fdate(since), n=f"{len(acts):,}",
        tiles="".join(tiles), tiles2="".join(tiles2), sections=body_sections,
        rec_rows=rec_rows, top_rows=top_rows, year=TODAY.year)
    with open(OUT, "w") as f:
        f.write(page)
    print(f"Built dashboard.html from {len(acts):,} activities"
          f"{' + Apple Health' if apple else ''}.")
    print("Open it: Files app > On My iPad > a-Shell > garmin-dashboard > dashboard.html")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Training Dashboard</title>
<style>
:root {{
  color-scheme: light;
  --bg:#f4f3ef; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#8a8984;
  --grid:#e6e5e0; --line:#d9d8d2; --dot:#9ec5f4; --band:#b7d3f6;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4;
  --up:#006300; --down:#b42318;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --bg:#111110; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#8f8e86;
    --grid:#2c2c2a; --line:#3a3a37; --dot:#1c5cab; --band:#184f95;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --bg:#111110; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#8f8e86;
  --grid:#2c2c2a; --line:#3a3a37; --dot:#1c5cab; --band:#184f95;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  -webkit-text-size-adjust:100%; }}
main {{ max-width:1180px; margin:0 auto; padding:24px 16px 48px; }}
header {{ display:flex; flex-wrap:wrap; align-items:flex-end; justify-content:space-between;
  gap:8px 24px; margin-bottom:18px; }}
header h1 {{ font-size:28px; margin:0; letter-spacing:-0.02em; }}
.goal {{ color:var(--ink2); margin:4px 0 0; font-size:16px; }}
.meta {{ color:var(--muted); font-size:13px; text-align:right; }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--ink2);
  margin:30px 0 10px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px;
  margin-bottom:12px; }}
.tile {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }}
.tl {{ font-size:13px; color:var(--ink2); }}
.tv {{ font-size:34px; font-weight:650; letter-spacing:-0.02em; font-variant-numeric:tabular-nums;
  line-height:1.15; margin:2px 0; }}
.tv small {{ font-size:15px; font-weight:500; color:var(--ink2); }}
.ts {{ font-size:12.5px; color:var(--ink2); }}
.delta {{ white-space:nowrap; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:12px; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:14px;
  padding:16px 16px 12px; min-width:0; }}
.card.wide {{ grid-column:1 / -1; }}
.card h3 {{ margin:0; font-size:16px; }}
.q {{ margin:2px 0 8px; color:var(--ink2); font-size:13.5px; }}
.note {{ margin:8px 0 0; color:var(--muted); font-size:12.5px; }}
.legend {{ display:flex; flex-wrap:wrap; gap:4px 14px; font-size:12.5px; color:var(--ink2); margin-bottom:4px; }}
.legend i {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:5px;
  vertical-align:-1px; }}
svg {{ width:100%; height:auto; display:block; overflow:visible; }}
svg line.gl {{ stroke:var(--grid); stroke-width:1; }}
svg .tick {{ fill:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }}
svg .ref {{ stroke:var(--ink2); stroke-width:1.2; stroke-dasharray:4 4; }}
svg .reflabel {{ fill:var(--ink2); font-size:11.5px; paint-order:stroke; stroke:var(--surface);
  stroke-width:3px; }}
svg .dot {{ stroke:var(--surface); stroke-width:1; }}
svg .band {{ fill:var(--s3); fill-opacity:.12; }}
svg .hit {{ fill:transparent; cursor:pointer; }}
svg .hit.on {{ fill:var(--ink); fill-opacity:.07; }}
.mixrow {{ display:flex; align-items:center; gap:10px; margin:10px 0; }}
.mixl {{ width:100px; font-size:13px; color:var(--ink2); flex:none; }}
.mix {{ flex:1; display:flex; gap:2px; height:30px; border-radius:6px; overflow:hidden; }}
.mix span {{ display:flex; align-items:center; justify-content:center; color:#fff; font-size:12px;
  font-weight:600; overflow:hidden; white-space:nowrap; cursor:pointer; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; font-variant-numeric:tabular-nums; }}
th, td {{ text-align:left; padding:8px 6px; border-bottom:1px solid var(--line); vertical-align:top; }}
thead th {{ font-size:12px; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:.05em; }}
tbody th {{ font-weight:500; color:var(--ink2); }}
td small {{ display:block; color:var(--muted); font-size:12px; }}
td.r {{ text-align:right; }}
.scroll {{ overflow-x:auto; }}
#tip {{ position:fixed; z-index:9; pointer-events:none; background:var(--ink); color:var(--surface);
  font-size:13px; line-height:1.4; padding:8px 10px; border-radius:8px; max-width:260px;
  white-space:pre-line; opacity:0; transition:opacity .08s; box-shadow:0 4px 18px rgba(0,0,0,.18); }}
#tip b {{ font-weight:650; }}
footer {{ margin-top:28px; color:var(--muted); font-size:12.5px; }}
@media (max-width:520px) {{
  main {{ padding:16px 12px 40px; }}
  header h1 {{ font-size:23px; }}
  .meta {{ text-align:left; }}
  .grid {{ grid-template-columns:1fr; }}
  .tiles {{ grid-template-columns:1fr 1fr; gap:8px; }}
  .tv {{ font-size:27px; }}
  svg .tick {{ font-size:15px; }}
  svg .reflabel {{ font-size:14px; }}
}}
</style></head>
<body><main>
<header>
  <div><h1>Training Dashboard</h1><p class="goal">{goal}</p></div>
  <div class="meta">Updated {updated}<br>{n} activities since {since}</div>
</header>
<div class="tiles">{tiles}</div>
<div class="tiles">{tiles2}</div>
{sections}
<h2>Records and biggest days</h2>
<div class="grid">
  <section class="card"><h3>Personal records</h3>
    <p class="q">What are my bests, all time and this year?</p>
    <div class="scroll"><table><thead><tr><th></th><th>All time</th><th>{year}</th></tr></thead>
    <tbody>{rec_rows}</tbody></table></div></section>
  <section class="card"><h3>Longest rides ever</h3>
    <p class="q">What are my biggest days on the bike?</p>
    <div class="scroll"><table><thead><tr><th>Date</th><th>Ride</th><th>Type</th>
    <th class="r">mi</th><th class="r">h</th><th class="r">ft</th></tr></thead>
    <tbody>{top_rows}</tbody></table></div></section>
</div>
<footer>Built from your Garmin Connect data (read-only Personal API) and your Apple Health
export. Everything stays on this device. Tap or hover on any chart for exact numbers.</footer>
</main>
<div id="tip" role="status"></div>
<script>
(function () {{
  var tip = document.getElementById('tip'), on = null;
  function show(el, x, y) {{
    if (on && on !== el) on.classList.remove('on');
    on = el; el.classList.add('on');
    var t = el.getAttribute('data-tip').split('\\n');
    tip.innerHTML = '';
    var b = document.createElement('b'); b.textContent = t[0]; tip.appendChild(b);
    if (t.length > 1) tip.appendChild(document.createTextNode('\\n' + t.slice(1).join('\\n')));
    tip.style.opacity = 1;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14));
    var top = y - h - 14; if (top < 8) top = y + 18;
    tip.style.left = left + 'px'; tip.style.top = top + 'px';
  }}
  function hide() {{ if (on) on.classList.remove('on'); on = null; tip.style.opacity = 0; }}
  function find(e) {{ var t = e.target; return t && t.closest ? t.closest('[data-tip]') : null; }}
  document.addEventListener('pointermove', function (e) {{
    var el = find(e); if (el) show(el, e.clientX, e.clientY); else if (e.pointerType === 'mouse') hide();
  }});
  document.addEventListener('pointerdown', function (e) {{
    var el = find(e); if (el) show(el, e.clientX, e.clientY); else hide();
  }});
  window.addEventListener('scroll', hide, {{ passive: true }});
}})();
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
