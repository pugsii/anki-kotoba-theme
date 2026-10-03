"""Kotoba theme for Anki.

- Uses the active Kotoba card palette (theme + light/dark) for all of Anki: native windows, web screens.
- Replaces the Decks and deck overview screens with a redesign (screens.py / screens.css).
- Keeps the cards' "jp-*" localStorage (⚙ settings, chosen images) across sessions: desktop Anki's web
  storage is in-memory only, so it is saved in this add-on's config and restored on every page.

Install: copy this folder into Anki's addons21 folder (Flatpak: ~/.var/app/net.ankiweb.Anki/data/Anki2/addons21)
and restart Anki.
"""
import datetime
import json
from pathlib import Path

import aqt
from aqt import colors, gui_hooks, mw
from aqt.deckbrowser import DeckBrowser
from aqt.overview import Overview
from aqt.theme import theme_manager

from . import core, screens

SCREENS_CSS = (Path(__file__).parent / "screens.css").read_text(encoding="utf-8")
state = {"key": None, "vars": ""}


def stored():
    return (mw.addonManager.getConfig(__name__) or {}).get("storage", {})


def palette():
    model = mw.col.models.by_name("Kotoba")
    try:
        override = json.loads(stored().get("jp-settings") or "{}").get("theme")
    except ValueError:
        override = None
    name, p = core.pick_theme(model["css"] if model else "", override)
    mode = "dark" if theme_manager.night_mode else "light"
    return (name, mode), p[mode]


def apply_theme(*_args, force=False):
    """Point Anki's colours at the active palette and restyle the native widgets."""
    if not mw.col:
        return
    key, t = palette()
    if key == state["key"] and not force:
        return
    dark = theme_manager.night_mode
    for name, value in core.anki_colors(t, dark).items():
        getattr(colors, name)["dark" if dark else "light"] = value
    try:  # private in Anki; fall back to web-only theming if it changes
        theme_manager._apply_palette(mw.app)
        theme_manager._apply_style(mw.app)
    except AttributeError:
        pass
    state.update(key=key, vars=core.css_vars(t, dark))
    # Anki builds the top toolbar's HTML once and only patches it afterwards, so rebuild it to pick up the
    # new colours. Deferred, as this can run while another screen is being rendered.
    mw.progress.single_shot(0, mw.toolbar.draw)


def storage_script():
    """Restore saved jp-* entries, and report changes back to Python."""
    return f"""<script>(function () {{
  var saved = {json.dumps(stored()).replace("</", "<\\/")};
  try {{ for (var k in saved) localStorage.setItem(k, saved[k]); }} catch (e) {{}}
  var set = Storage.prototype.setItem, del = Storage.prototype.removeItem;
  function report(store, k, v) {{
    if (store === window.localStorage && /^jp-/.test(k) && window.pycmd) pycmd("kt-store:" + JSON.stringify([k, v]));
  }}
  Storage.prototype.setItem = function (k, v) {{ set.call(this, k, v); report(this, k, String(v)); }};
  Storage.prototype.removeItem = function (k) {{ del.call(this, k); report(this, k, null); }};
}})();</script>"""


def anki_today():
    """The date of the current Anki day (which starts at the rollover hour, not midnight)."""
    return datetime.date.fromtimestamp(mw.col.sched.day_cutoff - 86400)


def browse_day(kind, offset, deck_id):
    """Heatmap click: cards reviewed `offset` days ago (kt-day) or due in `offset` days (kt-due)."""
    search = f"prop:rated={offset}" if kind == "kt-day" else f"prop:due={offset}"
    if deck_id:  # by id: deck names can contain wildcards (_ *) and quotes
        search += " did:" + ",".join(map(str, mw.col.decks.deck_and_child_ids(deck_id)))
    aqt.dialogs.open("Browser", mw, search=(search,))


def home_html(browser):
    data = browser._render_data
    col = mw.col

    def node(n):
        return dict(id=n.deck_id, name=n.name, new=n.new_count, learn=n.learn_count, review=n.review_count, done=0,
                    collapsed=n.collapsed, current=n.deck_id == data.current_deck_id, children=[node(c) for c in n.children])

    decks = [node(c) for c in data.tree.children]
    cutoff = col.sched.day_cutoff
    due = sum(d["new"] + d["learn"] + d["review"] for d in decks)
    stats = core.review_stats(col.db.all, cutoff, due, anki_today(), col.sched.today)

    def rollup(d):
        d["done"] = stats["done_by_deck"].get(d["id"], 0) + sum(rollup(c) for c in d["children"])
        return d["done"]

    for d in decks:
        rollup(d)
    stats["studied"] = data.studied_today
    stats["today"] = anki_today()
    return screens.home(decks, stats)


def overview_html(overview):
    col = mw.col
    deck = col.decks.current()
    new, learn, review = col.sched.counts()
    ids = list(col.decks.deck_and_child_ids(deck["id"]))
    stats = core.review_stats(col.db.all, col.sched.day_cutoff, new + learn + review, anki_today(), col.sched.today, ids)
    try:
        description = overview._desc(deck)
    except Exception:
        description = ""
    return screens.overview(dict(id=deck["id"], name=deck["name"], new=new, learn=learn, review=review,
                                 minutes=stats["minutes"], description=description,
                                 done=sum(n for did, n in stats["done_by_deck"].items() if did in ids)),
                            stats, anki_today())


def on_set_content(web_content, context):
    if not mw.col:
        return
    apply_theme()  # cheap no-op unless the theme or night mode changed
    web_content.head += f"<style>{state['vars']}{SCREENS_CSS}</style>{storage_script()}"
    try:
        if isinstance(context, DeckBrowser):
            web_content.body = home_html(context)
        elif isinstance(context, Overview):
            web_content.body = overview_html(context)
    except Exception as e:  # never leave a blank screen: fall back to Anki's own page
        print("kotoba_theme:", repr(e))


def on_page_style(webview):
    """Pages Anki builds without stdHtml (deck options, stats, editor) only get the colours."""
    if state["vars"]:
        webview.eval("(function(){var s=document.createElement('style');s.textContent=%s;"
                     "document.head.appendChild(s);})();" % json.dumps(state["vars"]))


def on_message(handled, message, context):
    if message.startswith(("kt-day:", "kt-due:")):
        kind, offset, deck_id = message.split(":")
        browse_day(kind, int(offset), int(deck_id))
        return True, None
    if not message.startswith("kt-store:"):
        return handled
    key, value = json.loads(message[len("kt-store:"):])
    config = mw.addonManager.getConfig(__name__) or {}
    store = config.setdefault("storage", {})
    if value is None:
        store.pop(key, None)
    else:
        store[key] = value
    mw.addonManager.writeConfig(__name__, config)
    if key == "jp-settings":  # ⚙ theme change: recolour Anki too
        apply_theme()
    return True, None


def on_qt_style(css):
    """Anki's native stylesheet underlines the menu bar; with the flat toolbar that line looks stray."""
    return css + "QMenuBar { border-bottom: none; }"


gui_hooks.style_did_init.append(on_qt_style)
gui_hooks.profile_did_open.append(lambda: apply_theme(force=True))
gui_hooks.theme_did_change.append(lambda: apply_theme(force=True))
gui_hooks.webview_will_set_content.append(on_set_content)
gui_hooks.webview_did_inject_style_into_page.append(on_page_style)
gui_hooks.webview_did_receive_js_message.append(on_message)
