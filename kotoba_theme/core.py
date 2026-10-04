"""Theme palettes and colour mapping. Pure Python (no Anki imports), so it can be tested and previewed.

The palettes come from the Kotoba note type's Styling (the `.t-<name> { --bg: ... }` rules), so cards
and the Anki UI always share one source of truth.
"""
import datetime
import re
import time

TOKENS = ("bg", "fg", "muted", "line", "panel", "accent")
FALLBACK = {"light": dict(bg="#faf8f4", fg="#1f1d1a", muted="#77716a", line="#e4dfd6", panel="#f1ede5", accent="#b4441e"),
            "dark": dict(bg="#1c1b19", fg="#ece8e1", muted="#9a948b", line="#3a3732", panel="#262420", accent="#f08a5d")}


def palettes(css):
    """{theme: {"light": tokens, "dark": tokens}} in Styling order (which is also the weekly rotation order)."""
    out = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*--bg:[^{}]*)\}", css or ""):
        values = dict(re.findall(r"--(\w+):\s*(#[0-9a-fA-F]{6})", body))
        if not all(t in values for t in TOKENS):
            continue
        tokens = {t: values[t] for t in TOKENS}
        for name, night in re.findall(r"\.t-([\w-]+)(:is\([^)]*\))?", selectors):
            out.setdefault(name, {})["dark" if night else "light"] = tokens
    for p in out.values():  # a theme defined for one mode only uses it for both
        p.setdefault("light", p.get("dark"))
        p.setdefault("dark", p.get("light"))
    return out


def setting(css, name, default=""):
    m = re.search(rf"--{name}:\s*\"([^\"]*)\"", css or "")
    return m.group(1).strip() if m else default


def pick_theme(css, override=None, now=None):
    """The active theme's palette: the ⚙ override if any, else the Styling setting; "weekly" rotates."""
    themes = palettes(css)
    name = override or setting(css, "theme", "ai")
    if name == "weekly" and themes:
        week = int((now if now is not None else time.time()) * 1000 // 604800000)
        name = list(themes)[week % len(themes)]
    return name, themes.get(name, FALLBACK)


# ----- colour helpers -----
def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def mix(a, b, w):
    """Blend colour a toward b by w (0..1)."""
    return "#" + "".join(f"{round(x + (y - x) * w):02x}" for x, y in zip(_rgb(a), _rgb(b)))


def rgba(h, alpha):
    return "rgba({}, {}, {}, {})".format(*_rgb(h), alpha)


def luminance(h):
    c = [x / 255 for x in _rgb(h)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def on(color):
    """Text colour that reads well on a filled `color` (for primary buttons and chips)."""
    return "#ffffff" if luminance(color) < 0.35 else "#111111"


def anki_colors(t, dark):
    """Anki's colour names -> values for one palette. Names not listed keep Anki's defaults."""
    elevated = mix(t["bg"], t["fg"], 0.06) if dark else mix(t["bg"], "#ffffff", 0.6)
    return {
        "FG": t["fg"], "FG_SUBTLE": t["muted"], "FG_DISABLED": mix(t["muted"], t["bg"], 0.4),
        "FG_FAINT": mix(t["muted"], t["bg"], 0.55), "FG_LINK": t["accent"],
        "CANVAS": t["bg"], "CANVAS_ELEVATED": elevated, "CANVAS_INSET": t["panel"], "CANVAS_OVERLAY": elevated,
        "CANVAS_CODE": elevated, "CANVAS_GLASS": rgba(t["bg"], 0.45),
        "BORDER": t["line"], "BORDER_SUBTLE": mix(t["line"], t["bg"], 0.5), "BORDER_STRONG": t["muted"],
        "BORDER_FOCUS": t["accent"],
        "BUTTON_BG": elevated, "BUTTON_GRADIENT_START": elevated, "BUTTON_GRADIENT_END": t["panel"],
        "BUTTON_HOVER_BORDER": t["accent"], "BUTTON_DISABLED": t["panel"],
        "BUTTON_PRIMARY_BG": t["accent"], "BUTTON_PRIMARY_GRADIENT_START": t["accent"],
        "BUTTON_PRIMARY_GRADIENT_END": mix(t["accent"], t["fg"], 0.12), "BUTTON_PRIMARY_DISABLED": mix(t["accent"], t["bg"], 0.5),
        "SCROLLBAR_BG": mix(t["line"], t["muted"], 0.3), "SCROLLBAR_BG_HOVER": t["muted"], "SCROLLBAR_BG_ACTIVE": t["fg"],
        "SHADOW": rgba("#000000", 0.35 if dark else 0.12), "SHADOW_SUBTLE": rgba("#000000", 0.2 if dark else 0.06),
        "SHADOW_FOCUS": rgba(t["accent"], 0.4),
        "ACCENT_CARD": t["accent"], "ACCENT_NOTE": mix(t["accent"], t["fg"], 0.3),
        "HIGHLIGHT_BG": rgba(t["accent"], 0.3), "HIGHLIGHT_FG": t["fg"],
        "SELECTED_BG": rgba(t["accent"], 0.22), "SELECTED_FG": t["fg"],
    }


def css_vars(t, dark):
    """CSS overriding Anki's web variables, plus the Kotoba tokens for the redesigned screens."""
    names = {k: "--" + k.lower().replace("_", "-") for k in anki_colors(t, dark)}
    decls = "".join(f"{names[k]}:{v}!important;" for k, v in anki_colors(t, dark).items())
    decls += "".join(f"--kt-{k}:{v};" for k, v in t.items()) + f"--kt-on-accent:{on(t['accent'])};"
    return f":root,:root.night-mode,.night-mode{{{decls}}}"


# ----- review stats for the heatmaps -----
YEAR_WEEKS, FORECAST_WEEKS = 52, 4


def review_stats(query, cutoff, due, today, day_num, deck_ids=None):
    """History, forecast, streaks and pace from the review log.

    query(sql, *args) -> rows (Anki's col.db.all, or sqlite in the preview); cutoff = end of today (seconds);
    due = cards left today; today = date of the current Anki day; day_num = Anki's day number for today
    (what card due dates count in); deck_ids = limit to these decks (None = whole collection).
    """
    day = datetime.timedelta(days=1)
    ids = ",".join(map(str, deck_ids)) if deck_ids else ""
    in_decks = f" and cid in (select id from cards where did in ({ids}))" if ids else ""
    span = 7 * (YEAR_WEEKS + 1)
    base = cutoff - 86400 * span
    rows = query(f"select (id/1000 - ?)/86400, count() from revlog where id > ? and ease > 0{in_decks} group by 1",
                 base, base * 1000)
    heat = {today - day * (span - 1 - i): n for i, n in rows if 0 <= i < span}
    rows = query(f"select due - ?, count() from cards where queue in (2, 3) and due > ? and due <= ?"
                 f"{' and did in (' + ids + ')' if ids else ''} group by 1", day_num, day_num, day_num + 7 * FORECAST_WEEKS)
    forecast = {today + day * d: n for d, n in rows}

    current, d = 0, today if heat.get(today) else today - day
    while heat.get(d):
        current, d = current + 1, d - day
    longest = run = 0
    first = min(heat) if heat else today
    d = first
    while d <= today:
        run = run + 1 if heat.get(d) else 0
        longest = max(longest, run)
        d += day
    studied = sum(1 for n in heat.values() if n)
    avg_ms = query(f"select avg(time) from revlog where id > ? and ease > 0{in_decks}", (cutoff - 14 * 86400) * 1000)[0][0] or 8000
    done_by_deck = dict(query("select c.did, count() from revlog r join cards c on c.id = r.cid "
                              "where r.id > ? and r.ease > 0 group by c.did", (cutoff - 86400) * 1000))
    return {"heat": heat, "forecast": forecast, "streak": current, "longest": longest,
            "average": round(sum(heat.values()) / studied) if studied else 0,
            "studied_pct": round(100 * studied / ((today - first).days + 1)) if heat else 0,
            "done": heat.get(today, 0), "due": due, "minutes": round(due * avg_ms / 60000), "done_by_deck": done_by_deck}


if __name__ == "__main__":  # self-check
    css = (".card, .t-washi { --bg: #faf8f4; --fg: #1f1d1a; --muted: #77716a; --line: #e4dfd6; --panel: #f1ede5; --accent: #b4441e; }\n"
           ".card:is(.nightMode, .night_mode), .t-washi:is(.nightMode, .night_mode) { --bg: #1c1b19; --fg: #ece8e1; --muted: #9a948b; --line: #3a3732; --panel: #262420; --accent: #f08a5d; }\n"
           ".t-neon, .t-neon:is(.nightMode, .night_mode) { --bg: #0a0e17; --fg: #e6f7ff; --muted: #7f9bb3; --line: #1c2a3d; --panel: #101a28; --accent: #00e5ff; }\n"
           '.card { --theme: "neon"; }')
    p = palettes(css)
    assert list(p) == ["washi", "neon"] and p["washi"]["dark"]["bg"] == "#1c1b19" and p["neon"]["light"] == p["neon"]["dark"]
    assert pick_theme(css)[0] == "neon" and pick_theme(css, override="washi")[0] == "washi"
    assert pick_theme(css.replace('"neon"', '"weekly"'), now=0)[0] == "washi"
    assert mix("#000000", "#ffffff", 0.5) == "#808080" and on("#00e5ff") == "#111111" and on("#b4441e") == "#ffffff"
    assert "--canvas:#faf8f4!important" in css_vars(p["washi"]["light"], False)
    today = datetime.date(2026, 10, 4)

    def fake(sql, *args):
        if "from revlog where id >" in sql and "group by 1" in sql:   # daily review counts (index 370 = today)
            return [(370, 5), (369, 3), (368, 2), (360, 9), (359, 9), (358, 9), (357, 9)]
        if "from cards where queue" in sql:
            return [(1, 34), (3, 12)]
        if "avg(time)" in sql:
            return [(6000,)]
        return []

    st = review_stats(fake, 0, 100, today, 900)
    assert st["streak"] == 3 and st["longest"] == 4 and st["done"] == 5, st
    assert st["forecast"][today + datetime.timedelta(days=1)] == 34 and st["minutes"] == 10
    assert st["average"] == round(46 / 7) and st["studied_pct"] == round(100 * 7 / 14), st
    print("selftest ok")
