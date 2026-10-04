"""The Kotoba note type: create it, or update an existing one, from cards/ (templates, styling and fonts).

Updating keeps the settings block at the top of your Styling (theme, dictionary order, sentence layout),
adds any fields and card types that are new since (at the end, so nothing moves) and any dictionaries new to
the default order, then renders a test card with Anki's template engine to check for errors.

Inside Anki: Tools → Kotoba: install or update note type. From a shell, with Anki closed and Anki's own
Python: python3 notetype.py path/to/collection.anki2
"""
import re
import sys
from pathlib import Path

NAME = "Kotoba"
FIELDS = ["Word", "Gloss", "Sentence", "SentenceTranslation", "SentenceAudio", "Picture", "Source",
          "Definitions", "PitchAccent", "WordAudio", "Notes", "Frequency", "Grammar"]
CARDS = Path(__file__).parent / "cards"
SETTINGS = re.compile(r"/\* ===== Settings:.*?\n}\n", re.S)
ORDER = re.compile(r'--dict-order: "([^"]*)";')


def files():
    """(front, back, listen, css) from cards/."""
    return tuple((CARDS / f).read_text(encoding="utf-8") for f in ("front.html", "back.html", "listen.html", "style.css"))


def merge_order(current, default):
    """The collection's settings block, with any dictionaries from the default order that it doesn't list yet
    added at the end (in default order). Your own order always stays as it is."""
    names = lambda block: [n.strip() for n in ORDER.search(block).group(1).split(",") if n.strip()]
    mine = names(current)
    extra = [n for n in names(default) if n.lower() not in {x.lower() for x in mine}]
    return ORDER.sub(lambda _: f'--dict-order: "{", ".join(mine + extra)}";', current, count=1) if extra else current


def updated_css(current_css, new_css):
    """The new styling with the current settings block kept (plus new default dictionaries)."""
    kept = SETTINGS.search(current_css or "")
    if not kept:
        return new_css
    block = merge_order(kept.group(0), SETTINGS.search(new_css).group(0))
    return SETTINGS.sub(lambda _: block, new_css, count=1)


def install(col):
    """Create or update the note type in an open collection; returns (what happened, [(check, ok)])."""
    front, back, listen, css = files()
    # Recognition: word → meaning. Listening (notes with scene audio only): hear a line → understand it.
    templates = {"Recognition": (front, back), "Listening": (listen, back)}
    # The leading _ keeps Check Media from removing them; names are lowercase, as Anki lowercases media names
    for font in sorted((CARDS / "fonts").glob("*.woff2")):
        col.media.add_file(str(font))
    mm = col.models
    m = mm.by_name(NAME)
    if m is None:
        m = mm.new(NAME)
        for name in FIELDS:
            mm.add_field(m, mm.new_field(name))
        for name, (q, a) in templates.items():
            t = mm.new_template(name)
            t["qfmt"], t["afmt"] = q, a
            mm.add_template(m, t)
        m["css"] = css
        mm.add_dict(m)
        done = f"Created the {NAME} note type."
    else:
        names = [f["name"] for f in m["flds"]]
        if names != FIELDS[:len(names)]:
            raise ValueError(f"The {NAME} note type's fields have been changed, so it can't be updated safely. "
                             f"Expected them to start: {', '.join(FIELDS[:len(names)])}")
        added = []
        for name in FIELDS[len(names):]:  # fields added since (at the end, so nothing moves)
            mm.add_field(m, mm.new_field(name))
            added.append(f"field {name}")
        m["css"] = updated_css(m["css"], css)
        for name, (q, a) in templates.items():
            t = next((t for t in m["tmpls"] if t["name"] == name), None)
            if t is None:
                t = mm.new_template(name)
                mm.add_template(m, t)
                added.append(f"card type {name}")
            t["qfmt"], t["afmt"] = q, a
        mm.update_dict(m)
        done = f"Updated the {NAME} note type (your settings kept)" + (f"; added {', '.join(added)}." if added else ".")
    return done, test_render(col)


def test_render(col):
    """Render a test note (not saved) with Anki's template engine: [(check, ok)]."""
    note = col.new_note(col.models.by_name(NAME))
    for k, v in {
        "Word": "電車[でんしゃ]", "Gloss": "train", "PitchAccent": "0,1",
        "Sentence": "今日[きょう]は<b>電車[でんしゃ]</b>が 遅[おく]れている。<hr><b>電車[でんしゃ]</b> 来[き]たよ。",
        "SentenceTranslation": "The train is running late today.<hr>Here comes the train.",
        "Definitions": '<ol><li data-dictionary="JMdict [2026-08-07]">train</li></ol>',
        "SentenceAudio": '<audio src="clip.mp3"></audio><hr>', "Grammar": '<div class="gp"><b>〜ている</b> <small>N5</small> ongoing</div><hr>',
        "Frequency": "1234",
    }.items():
        note[k] = v
    card = note.ephemeral_card()
    q, a = card.question(), card.answer()
    listening = note.ephemeral_card(ord=1).question()
    return [
        ("front: bare word", ">電車<" in q and "でんしゃ" not in q.split("<script>")[0].split("hint")[0]),
        ("front: sentence hint", "class=hint" in q and "今日は" in q),
        ("back: furigana", "<ruby>" in a),
        ("back: reading", ">でんしゃ<" in a),
        ("back: card id", re.search(r'data-card="\d*"', a) is not None),
        ("back: grammar notes", "〜ている" in a),
        ("listening front: audio, no word shown", "listen-play" in listening and "clip.mp3" in listening and 'id="word" hidden' in listening),
        ("no template errors", not any(s in q + a + listening for s in ("{{", "problem", "Unknown field"))),
    ]


if __name__ == "__main__":
    assert merge_order('--dict-order: "B, A";', '--dict-order: "A, B, C, D";') == '--dict-order: "B, A, C, D";'
    assert merge_order('--dict-order: "B, A";', '--dict-order: "A";') == '--dict-order: "B, A";'
    css = files()[3]
    mine = SETTINGS.sub(lambda m: m.group(0).replace('--theme: "ai"', '--theme: "sakura"'), css, count=1)
    assert '--theme: "sakura"' in updated_css(mine, css) and updated_css("", css) == css
    if len(sys.argv) < 2:
        sys.exit(print("selftest ok"))
    from anki.collection import Collection
    col = Collection(sys.argv[1])
    try:
        done, checks = install(col)
        print(done)
        for name, ok in checks:
            print("ok  " if ok else "FAIL", name)
        sys.exit(0 if all(ok for _, ok in checks) else 1)
    finally:
        col.close()
