"""Run: python test_plan.py   (no browser, no network)."""
import tempfile
from pathlib import Path
import plan


def it(i, ty, done, **kw):
    return {"index": i, "title": f"item {i}", "href": f"/x/{ty}/{i}", "type": ty, "done": done, **kw}


def topic(index, chapter, items=None, progress=0, title=None):
    t = {"index": index, "chapter": chapter, "title": title or f"T{index}", "slug": f"t{index}", "progress": progress}
    if items is not None:
        t["items"] = items
    return t


# ---- order: partial first, then not started, completed skipped, page order, only chosen chapters
topics = [
    topic(5, 1, [it(1, "video", False)]),                                              # not started
    topic(2, 1, [it(1, "video", True), it(2, "video", True), it(3, "quiz", True)], 100),  # completed
    topic(4, 1, [it(1, "video", True), it(2, "video", False)], 50),                    # partial
    topic(1, 1, [it(1, "video", True), it(2, "quiz", False)]),                         # partial (a video is done)
    topic(7, 2, [it(1, "video", False)]),                                              # other chapter
    topic(3, 1),                                                                       # items not read -> not started
    topic(6, 1, [it(1, "video", True), it(2, "coding", False), it(3, "quiz", True)], 90),  # only coding left -> completed
    topic(8, 1, [it(1, "video", False, tick_pending="2026-10-22T10:00:00")], 20),      # pending tick only, quiz none
    topic(9, 1, [it(1, "quiz", False, correct=3, wrong=0)]),                           # quiz started -> partial
]
todo, completed = plan.order_topics(topics, [1])
assert [t["index"] for t in todo] == [1, 4, 9, 3, 5], [t["index"] for t in todo]
assert [t["index"] for t in completed] == [2, 6, 8], [t["index"] for t in completed]
assert all(t["chapter"] == 1 for t in todo + completed)
todo2, _ = plan.order_topics(topics, [2])
assert [t["index"] for t in todo2] == [7]

# ---- leftovers
assert plan.leftovers([it(1, "video", None), it(2, "video", False, tick_pending="x")]) == \
    "1 video(s) with unknown tick; 1 video(s) tick pending; no quiz"
assert plan.leftovers([it(1, "video", True), it(2, "quiz", True)]) == ""

# ---- quiz counts (earlier-run rows are not counted)
rows = [{"n": 1, "result": "correct", "note": ""}, {"n": 2, "result": "WRONG (right: C)", "note": "disputed"},
        {"n": 3, "result": "correct", "note": "already submitted"}, {"n": 4, "result": "-", "note": "unsupported: image"},
        {"n": 5, "result": "-", "note": ""}]
assert plan.quiz_counts(rows) == {"correct": 1, "wrong": 1, "unsupported": 1}

# ---- summary
recs = [plan.new_record(topics[1], "skipped"),
        plan.new_record(topics[2], "done", videos=3, correct=8, wrong=1, unsupported=1, models=["m1", "m2"], problems=2),
        plan.new_record(topics[0], "stopped", videos=1, models=["m2", "m3"], note="Gemini stopped the run"),
        plan.new_record(topics[5], "not reached")]
t = plan.totals(recs)
assert (t["done"], t["skipped"], t["stopped"], t["not reached"]) == (1, 1, 1, 1), t
assert (t["videos"], t["correct"], t["wrong"], t["unsupported"], t["problems"]) == (4, 8, 1, 1, 2), t
assert t["models"] == ["m1", "m2", "m3"], t
rows_out = plan.summary_rows(recs)
assert rows_out[1]["quiz"] == "8 ok / 1 wrong / 1 unsupported" and rows_out[0]["quiz"] == "-", rows_out
assert len(plan.format_totals(t)) == 5

# ---- problems_todo.md: no duplicates, done ones and videos ignored, file created with a heading
tp = topic(1, 1, [it(1, "video", False), it(2, "coding", False), it(3, "coding", True), it(4, "other", None), it(5, "coding", None)],
           title="Recursion")
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "data" / "problems_todo.md"
    assert plan.append_problems(tp, p) == 3
    first = p.read_text(encoding="utf-8")
    assert first.startswith("# Coding problems") and first.count("- [ ]") == 3, first
    assert "- [ ] [unrecognised] item 4 | Recursion | /x/other/4" in first
    assert plan.append_problems(tp, p) == 0                       # run again: nothing new
    tp["items"].append(it(6, "coding", False))
    assert plan.append_problems(tp, p) == 1                       # only the new one
    assert p.read_text(encoding="utf-8").count("- [ ]") == 4
    assert plan.append_problems(topic(2, 1, [it(1, "video", False)]), p) == 0


# ---- --chapters parsing and validation
assert plan.parse_chapters(["1"], (3, 4)) == [1]
assert plan.parse_chapters(["1", "2"], (3, 4)) == [1, 2]
assert plan.parse_chapters(["1,2"], (3, 4)) == [1, 2]
assert plan.parse_chapters(["2,", "1", "2"], (3, 4)) == [1, 2]          # sorted, no duplicates
for bad, word in ((["3"], "contests"), (["1", "4"], "contests"), (["x"], "not a chapter"), (["1.5"], "not a chapter"),
                  (["0"], "not a chapter"), (["-1"], "not a chapter"), ([], "at least one"), ([","], "at least one")):
    try:
        plan.parse_chapters(bad, (3, 4))
    except ValueError as e:
        assert word in str(e), (bad, str(e))
    else:
        raise AssertionError(f"{bad} should be refused")
assert plan.missing_chapters([1, 2], topics) == []                       # topics 1 and 2 exist in the sample list
assert plan.missing_chapters([1, 2, 7], topics) == [7]
print("test_plan OK")
