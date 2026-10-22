"""Pure helpers for --run: topic order, per-topic notes, quiz counts, problems_todo.md lines, run summary.
No browser, no network."""
from pathlib import Path

STATUSES = ("done", "skipped", "stopped", "not reached")


def _items(topic):
    return topic.get("items") or []


def work_left(topic):
    """True if a video can still be watched (not done, tick not pending) or the quiz is not complete.
    Coding problems never count: the script does not do them."""
    for it in _items(topic):
        if it["type"] == "video" and it["done"] is False and not it.get("tick_pending"):
            return True
        if it["type"] == "quiz" and it["done"] is not True:
            return True
    return False


def started(topic):
    if topic.get("progress", 0) > 0:
        return True
    return any(it["done"] is True or it.get("tick_pending") or (it.get("correct") or 0) + (it.get("wrong") or 0) > 0
               for it in _items(topic))


def order_topics(topics, include):
    """-> (todo, completed), only topics of chapters in include, each list in page order.
    todo = partly done topics first, then not-started ones. A topic whose items were not read counts as not started."""
    partial, fresh, completed = [], [], []
    for t in sorted((t for t in topics if t.get("chapter") in include), key=lambda t: t["index"]):
        if "items" not in t:
            fresh.append(t)
        elif not work_left(t):
            completed.append(t)
        elif started(t):
            partial.append(t)
        else:
            fresh.append(t)
    return partial + fresh, completed


def leftovers(items):
    """Short note about things this run could not finish by itself (never fatal)."""
    vids = [it for it in items if it["type"] == "video"]
    parts = []
    n = sum(1 for v in vids if v["done"] is None)
    if n:
        parts.append(f"{n} video(s) with unknown tick")
    n = sum(1 for v in vids if v.get("tick_pending"))
    if n:
        parts.append(f"{n} video(s) tick pending")
    if not any(it["type"] == "quiz" for it in items):
        parts.append("no quiz")
    return "; ".join(parts)


def quiz_counts(rows):
    """Count this run's quiz rows (rows marked 'already submitted' belong to an earlier run)."""
    c = {"correct": 0, "wrong": 0, "unsupported": 0}
    for r in rows:
        note = r.get("note") or ""
        if note.startswith("unsupported"):
            c["unsupported"] += 1
        elif note == "already submitted":
            continue
        elif r.get("result") == "correct":
            c["correct"] += 1
        elif str(r.get("result")).startswith("WRONG"):
            c["wrong"] += 1
    return c


def new_record(topic, status, **extra):
    rec = {"index": topic["index"], "title": topic["title"], "status": status, "videos": 0, "correct": 0,
           "wrong": 0, "unsupported": 0, "models": [], "problems": 0, "note": ""}
    rec.update(extra)
    return rec


def summary_rows(records):
    """Rows for main.table: one per topic."""
    rows = []
    for r in records:
        quiz = "-" if not (r["correct"] or r["wrong"] or r["unsupported"]) else \
            f"{r['correct']} ok / {r['wrong']} wrong / {r['unsupported']} unsupported"
        rows.append({"n": r["index"], "topic": r["title"], "status": r["status"], "videos": r["videos"],
                     "quiz": quiz, "problems": r["problems"], "note": r["note"]})
    return rows


def totals(records):
    t = {s: sum(1 for r in records if r["status"] == s) for s in STATUSES}
    for k in ("videos", "correct", "wrong", "unsupported", "problems"):
        t[k] = sum(r[k] for r in records)
    t["models"] = list(dict.fromkeys(m for r in records for m in r["models"]))
    return t


def format_totals(t):
    return [f"Topics: {t['done']} done, {t['skipped']} skipped (already complete), {t['stopped']} stopped, "
            f"{t['not reached']} not reached",
            f"Videos watched: {t['videos']}",
            f"Quiz answers submitted: {t['correct']} correct, {t['wrong']} wrong; "
            f"{t['unsupported']} unsupported question(s) left unanswered",
            f"Models used: {', '.join(t['models']) or 'none'}",
            f"Coding problems newly logged: {t['problems']}"]


def problem_lines(topic, existing_text):
    """Lines to append to problems_todo.md: incomplete coding items (and unrecognised ones, which might be coding),
    skipping any whose href (last ' | ' field) is already in the file."""
    seen = {ln.rsplit(" | ", 1)[-1].strip() for ln in existing_text.splitlines() if ln.startswith("- [ ]")}
    lines = []
    for it in _items(topic):
        if it["type"] not in ("coding", "other") or it["done"] is True:
            continue
        key = it.get("href") or it["title"]
        if key in seen:
            continue
        seen.add(key)
        tag = "" if it["type"] == "coding" else "[unrecognised] "
        lines.append(f"- [ ] {tag}{it['title']} | {topic['title']} | {key}")
    return lines


def append_problems(topic, path):
    """Append the new lines to the file (created with a heading); returns how many were added. Never opens a problem."""
    path = Path(path)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = problem_lines(topic, existing)
    if not lines:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        if not existing:
            f.write("# Coding problems to do by hand (the script never opens them)\n\n")
        elif not existing.endswith("\n"):
            f.write("\n")
        f.write("\n".join(lines) + "\n")
    return len(lines)
    
def parse_chapters(tokens, unsupported=()):
    """['1', '2'] or ['1,2'] or ['1,', '2'] -> [1, 2]. Raises ValueError with a plain message for anything else."""
    parts = [p for tok in tokens for p in tok.replace(",", " ").split()]
    if not parts:
        raise ValueError("--chapters needs at least one chapter number, e.g. --chapters 1 2")
    nums = []
    for p in parts:
        if not (p.isascii() and p.isdigit()) or int(p) < 1:
            raise ValueError(f"--chapters: {p!r} is not a chapter number (use whole numbers such as 1 or 2)")
        n = int(p)
        if n in unsupported:
            raise ValueError(f"--chapters: chapter {n} (contests) is not supported yet")
        if n not in nums:
            nums.append(n)
    return sorted(nums)


def missing_chapters(chosen, topics):
    """Chosen chapter numbers that no scanned topic belongs to."""
    found = {t.get("chapter") for t in topics}
    return [c for c in chosen if c not in found]
