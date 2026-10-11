"""Run: python test_state.py   (no browser needed)."""
import json, tempfile
from pathlib import Path
import state


def it(i, ty, href, done):
    return {"index": i, "title": f"item {i}", "href": href, "type": ty, "done": done, "active": False}


topics = [
    {"index": 1, "chapter": 1, "title": "Recursion", "sub_category": "Maths, Recursion and Bits", "slug": "recursion-siddhartha",
     "progress": 41, "action": "Resume", "items": [
        it(1, "video", "/x/video/1", True), it(2, "video", "/x/video/2", False), it(3, "quiz", "/x/quiz/3", False),
        it(4, "coding", "/x/problem/4", False), it(5, "other", "/x/weird/5", None)]},
    {"index": 2, "chapter": 1, "title": "Bit Magic", "sub_category": "Maths, Recursion and Bits", "slug": "bit-magic-siddhartha",
     "progress": 0, "action": "Start"},                                            # items not read (yet)
    {"index": 3, "chapter": 2, "title": "SQL Basics", "sub_category": None, "slug": "sql-basics-siddhartha",
     "progress": 0, "action": "Start"},
]

r1, r2, r3, tot = state.summarize(topics)
assert (r1["videos"], r1["quizzes"], r1["problems"], r1["other"], r1["unknown"]) == ("1/2", "0/1", "0/1", 1, 1), r1
assert (r1["chapter"], r1["sub_category"]) == (1, "Maths, Recursion and Bits"), r1
assert (r2["videos"], r2["other"], r2["unknown"]) == ("-", "-", "-"), r2             # not read -> '-'
assert (r3["sub_category"], r3["videos"]) == ("", "-"), r3
assert (tot["title"], tot["videos"], tot["quizzes"], tot["problems"], tot["other"], tot["unknown"]) == ("TOTAL", "1/2", "0/1", "0/1", 1, 1), tot

with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "sub" / "state.json"
    assert state.load_state(p)["topics"] == []            # missing file -> empty state
    st = state.new_state(topics)
    state.save_state(st, p)
    back = state.load_state(p)
    assert back["topics"] == topics and back["complete"] is False, back
    assert not list(p.parent.glob("*.tmp"))               # temp file cleaned up
    p.write_text(json.dumps({"version": 999}))
    try:
        state.load_state(p)
        raise AssertionError("expected ValueError for a wrong version")
    except ValueError:
        pass

print("state checks passed")
