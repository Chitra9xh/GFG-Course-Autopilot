"""Local state file (data/state.json). Standard library only; no browser needed."""
import json, os, tempfile
from datetime import datetime
from pathlib import Path
import config

VERSION = 1


def _now():
    return datetime.now().isoformat(timespec="seconds")


def new_state(topics=None):
    """'complete' stays False until a scan has finished, so a partial file can be told apart."""
    return {"version": VERSION, "updated_at": _now(), "complete": False, "topics": topics if topics is not None else []}


def load_state(path=None):
    path = Path(path or config.STATE_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return new_state()
    if data.get("version") != VERSION:
        raise ValueError(f"{path} has state version {data.get('version')!r}, expected {VERSION}")
    return data


def save_state(state, path=None):
    """Write atomically (temp file, then replace) so a crash never leaves a half-written state.json."""
    path = Path(path or config.STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def summarize(topics):
    """One row per topic plus a TOTAL row. Counts are 'done/total'. A topic whose items were not read (its chapter is
    not in INCLUDE_CHAPTERS, or the scan stopped before it) shows '-'. 'unknown' = items whose tick icon was not
    recognised (counted as not done). The TOTAL row only adds up the topics that were read."""
    def fmt(p):
        return f"{p[0]}/{p[1]}"

    def count(items):
        c = {"video": [0, 0], "quiz": [0, 0], "coding": [0, 0], "other": 0, "unknown": 0}
        for it in items:
            if it["type"] in ("video", "quiz", "coding"):
                c[it["type"]][1] += 1
                c[it["type"]][0] += 1 if it["done"] else 0
            else:
                c["other"] += 1
            if it["done"] is None:
                c["unknown"] += 1
        return c

    def row(index, chapter, title, sub, slug, c):
        if c is None:
            c = {"video": "-", "quiz": "-", "coding": "-", "other": "-", "unknown": "-"}
        else:
            c = {**c, "video": fmt(c["video"]), "quiz": fmt(c["quiz"]), "coding": fmt(c["coding"])}
        return {"index": index, "chapter": chapter, "title": title, "sub_category": sub or "", "videos": c["video"],
                "quizzes": c["quiz"], "problems": c["coding"], "other": c["other"], "unknown": c["unknown"], "slug": slug}

    rows, total = [], count([])
    for t in topics:
        c = count(t["items"]) if "items" in t else None
        rows.append(row(t["index"], t.get("chapter", ""), t["title"], t.get("sub_category"), t["slug"], c))
        if c:
            for k in ("video", "quiz", "coding"):
                total[k][0] += c[k][0]
                total[k][1] += c[k][1]
            total["other"] += c["other"]
            total["unknown"] += c["unknown"]
    rows.append(row("", "", "TOTAL", "", "", total))
    return rows
