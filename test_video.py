"""Offline checks for video.py (no browser). Run: python3 test_video.py"""
import video

from datetime import datetime


def item(n, typ, done=False, **extra):
    return {"index": n, "title": f"{typ}{n}", "type": typ, "done": done, "href": f"/x/{typ}{n}", **extra}


# a Bit-Magic-like topic: 7 videos, then problems
items = [item(i, "video") for i in range(1, 8)] + [item(i, "coding") for i in range(8, 12)]

# speed label = text of the site's menu items
assert video.speed_label(2.0) == "2x" and video.speed_label(1.75) == "1.75x" and video.speed_label(1) == "1x"

# hard timeout = duration / speed * 1.5 + 60
assert abs(video.hard_timeout(600, 2) - 510) < 1e-9

# end detection
assert video.is_finished(True, 10, 620) and video.is_finished(False, 619.8, 620)
assert not video.is_finished(False, 300, 620) and not video.is_finished(False, 5, float("nan"))

# videos_todo: skips done, unknown tick, tick_pending, and non-videos
t = [item(1, "video", done=True), item(2, "video", tick_pending="2026-10-13T10:00:00"), item(3, "video"),
     item(4, "video", done=None), item(5, "video"), item(6, "coding"), item(7, "quiz"), item(8, "video")]
assert [i["index"] for i in video.videos_todo(t)] == [3, 5, 8]
assert [i["index"] for i in video.videos_todo(t, limit=2)] == [3, 5]

# next_step: click Next only when the next sidebar item is a video
assert video.next_step(items, "/x/video1")[0] == "next" and video.next_step(items, "/x/video1")[1]["index"] == 2
act, why = video.next_step(items, "/x/video7")
assert act == "stop" and "coding" in why
assert video.next_step(items, "/x/coding11")[0] == "stop"           # last item
assert video.next_step(items, "/x/nope")[0] == "stop"               # not in list
assert video.next_step([item(1, "video"), item(2, "quiz")], "/x/video1")[0] == "stop"

# stall tracker (STALL_SECONDS = 20)
s = video.StallTracker(now=0)
assert not s.update(10, 5)          # moved
assert not s.update(10, 24)         # 19 s without moving
assert s.update(10, 25)             # 20 s -> stalled
s.reset(25)
assert not s.update(10, 30)         # retry gets a fresh window
assert not s.update(11, 50)         # moving again

# same_path ignores host, query, %-encoding and a trailing slash
assert video.same_path("https://www.geeksforgeeks.org/batch/dsa-juet/track/a/video/QQ%3D%3D?_gl=1", "/batch/dsa-juet/track/a/video/QQ==")
assert not video.same_path("/a/video/1", "/a/video/2")

# speed-menu text
assert video.parse_rate_text("2x") == 2.0 and video.parse_rate_text("1.75x, selected") == 1.75
assert video.parse_rate_text("Auto") is None and video.parse_rate_text(None) is None

# carry_over_pending: still pending -> mark kept; tick arrived -> mark dropped and reported
old = [item(1, "video", tick_pending="2026-10-13T10:00:00"), item(2, "video", tick_pending="2026-10-13T10:00:00"), item(3, "video")]
new = [item(1, "video"), item(2, "video", done=True), item(3, "video")]
arrived = video.carry_over_pending(old, new, now=datetime(2026, 10, 13, 10, 30, 0))
assert new[0]["tick_pending"] == "2026-10-13T10:00:00"
assert "tick_pending" not in new[1] and arrived == [("video2", 1800.0)]
assert "tick_pending" not in new[2]


print("video checks passed")
