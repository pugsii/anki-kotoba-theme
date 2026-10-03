"""HTML for the redesigned Decks (home) and deck overview screens.

Pure functions over plain data, so the preview renders exactly what Anki shows. Links use Anki's own
commands: open:<deck id>, opts:<deck id>, collapse:<deck id> (Decks screen) and study (overview).
"""
import datetime
from html import escape

try:
    from .core import FORECAST_WEEKS, YEAR_WEEKS
except ImportError:  # imported directly, as the preview does
    from core import FORECAST_WEEKS, YEAR_WEEKS

GEAR = ('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 '
        '.33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 '
        '2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 '
        '1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 '
        '0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 '
        '1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 '
        '1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 '
        '2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>')
CHEVRON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>'
WEEKDAYS = "月火水木金土日"


def greeting(hour):
    return "おはよう" if 5 <= hour < 11 else "こんにちは" if 11 <= hour < 18 else "こんばんは"


def counts(new, learn, review):
    chip = lambda n, kind: f'<span class="kt-{kind}{" kt-zero" if not n else ""}">{n}</span>'
    return f'<span class="kt-counts">{chip(new, "new")}{chip(learn, "learn")}{chip(review, "review")}</span>'


def progress(done, due):
    if not done + due:
        return ""
    return f'<div class="kt-bar" title="{done} done today, {due} to go"><span style="width:{100 * done / (done + due):.0f}%"></span></div>'


def deck_row(d, level):
    fold = (f'<button class="kt-fold{" kt-open" if not d["collapsed"] else ""}" title="Expand/collapse" '
            f'onclick="event.stopPropagation();return pycmd(\'collapse:{d["id"]}\')">{CHEVRON}</button>'
            if d["children"] else '<span class="kt-fold"></span>')
    row = (f'<div class="kt-row kt-level{min(level, 3)}{" kt-current" if d["current"] else ""}" '
           f'onclick="return pycmd(\'open:{d["id"]}\')">{fold}<span class="kt-name">{escape(d["name"])}</span>'
           f'{counts(d["new"], d["learn"], d["review"])}'
           f'<button class="kt-gear" title="Options" onclick="event.stopPropagation();return pycmd(\'opts:{d["id"]}\')">{GEAR}</button></div>')
    if not d["collapsed"]:
        row += "".join(deck_row(c, level + 1) for c in d["children"])
    return row


def _level(n, top):
    return 0 if not n else min(4, 1 + int(4 * n / (top + 1)))


def heatmap(stats, today, deck_id=0):
    """A year of reviews plus the coming weeks' due forecast. Columns are weeks, Monday on top.
    Clicking a day opens Browse with the cards reviewed (past) or due (future) that day."""
    day = datetime.timedelta(days=1)
    start = today - day * (7 * YEAR_WEEKS + today.weekday())
    end = today + day * (7 * FORECAST_WEEKS + 6 - today.weekday())
    top_past = max(stats["heat"].values(), default=0)
    top_due = max(stats["forecast"].values(), default=0)
    cells, months, d, col = [], [], start, 0
    while d <= end:
        if d.weekday() == 0:
            col += 1
            if d.day <= 7:  # first week of a month
                months.append(f'<span style="grid-column:{col}">{d.month}月</span>')
        offset = (d - today).days
        if offset <= 0:
            n = stats["heat"].get(d, 0)
            cls, tip = f"l{_level(n, top_past)}", f"{n} review{'s' * (n != 1)}"
            click = f"kt-day:{offset}:{deck_id}" if n else ""
        else:
            n = stats["forecast"].get(d, 0)
            cls, tip = f"f f{_level(n, top_due)}", f"{n} due"
            click = f"kt-due:{offset}:{deck_id}" if n else ""
        cls += " today" if offset == 0 else ""
        handler = f' onclick="pycmd(\'{click}\')"' if click else ""
        cells.append(f'<i class="{cls}" title="{d.day} {d:%b}: {tip}"{handler}></i>')
        d += day
    facts = [(stats["average"], "daily average"), (f'{stats["studied_pct"]}%', "of days studied"),
             (stats["longest"], "longest streak"), (stats["streak"], "current streak")]
    return f"""<section class="kt-heatcard">
  <div class="kt-heatwrap">
    <div class="kt-months">{"".join(months)}</div>
    <div class="kt-wdays"><span>月</span><span></span><span>水</span><span></span><span>金</span></div>
    <div class="kt-heat">{"".join(cells)}</div>
  </div>
  <div class="kt-heatstats">{"".join(f"<span><b>{v}</b> {label}</span>" for v, label in facts)}
    <span class="kt-legend"><i class="l2"></i> reviewed <i class="f f2"></i> due</span></div>
</section>"""


def home(decks, stats, now=None):
    """decks: [{id, name, new, learn, review, done, collapsed, current, children}];
    stats: core.review_stats plus "studied" (Anki's summary line) and "today" (the Anki day's date)."""
    now = now or datetime.datetime.now()
    tiles = [(stats["due"], "due today"), (stats["done"], "done today"),
             (stats["streak"], "day streak"), (f'~{stats["minutes"]}', "minutes left")]
    deck_cards = "".join(
        f'<section class="kt-deck">{deck_row(d, 0)}{progress(d["done"], d["new"] + d["learn"] + d["review"])}</section>'
        for d in decks)
    return f"""
<div class="kt kt-home">
  <header class="kt-hero">
    <div class="kt-date">{now.month}月{now.day}日（{WEEKDAYS[now.weekday()]}）</div>
    <h1>{greeting(now.hour)}</h1>
  </header>
  <div class="kt-tiles">{"".join(f'<div class="kt-tile"><b>{v}</b><span>{label}</span></div>' for v, label in tiles)}</div>
  {heatmap(stats, stats.get("today", now.date()))}
  <div class="kt-decks">{deck_cards}</div>
  <footer class="kt-foot">{stats["studied"]}</footer>
</div>"""


def overview(deck, stats=None, today=None):
    """deck: {id, name (full path), new, learn, review, done, minutes, description}; stats: review_stats for this deck."""
    *parents, name = deck["name"].split("::")
    total = deck["new"] + deck["learn"] + deck["review"]
    tiles = [(deck["new"], "new", "New"), (deck["learn"], "learn", "Learning"), (deck["review"], "review", "To review")]
    study = (f'<button id="study" class="kt-study" autofocus onclick="return pycmd(\'study\')">Study now'
             f'<small>{total} cards · ~{deck["minutes"]} min</small></button>' if total else
             '<div class="kt-done">Done for today. お疲れ様でした！</div>')
    return f"""
<div class="kt kt-overview">
  <div class="kt-crumb">{escape(" › ".join(parents))}</div>
  <h1>{escape(name)}</h1>
  <div class="kt-tiles kt-tiles3">{"".join(
        f'<div class="kt-tile kt-{k}{" kt-zero" if not v else ""}"><b>{v}</b><span>{label}</span></div>' for v, k, label in tiles)}</div>
  {study}
  {progress(deck["done"], total)}
  {heatmap(stats, today or datetime.date.today(), deck["id"]) if stats else ""}
  <div class="kt-desc">{deck["description"]}</div>
</div>"""
