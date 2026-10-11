"""Run: python test_scanner.py   (no browser needed). HTML trimmed from your pasted pages."""
from scanner import parse_item_html, parse_topic_html

IMG = '<span><img src="https://media.geeksforgeeks.org/img-practice/%s.svg"></span>'
YT = '<img src="https://media.geeksforgeeks.org/img-practice/youtube-1669791455.svg"><p class="sidebar_meta__9J4r4">Duration: 11 min</p>'

def item(href, title, icon, cls="sidebar_item__khyNp  ", extra=""):
    return (f'<a class="{cls}" href="{href}"><div><p>{title}</p>{extra}</div>'
            f'<div>{IMG % icon}</div><div>{YT}</div></a>')

def topic(href, title, pct, btn):
    ring = f'<div class="batch_circular_progress___lorQ"><svg><text class="CircularProgressbar-text">{pct}%</text></svg></div>' if pct else ""
    return (f'<a href="{href}"><div class="batch_item__ndA6j"><div class="batch_item_inner__ZdF6T">'
            f'<div class="batch_title_publish_container__MnHpt"><p class="batch_title__XImuz">{title}</p></div>'
            f'<p><span>9 Videos</span></p></div>{ring}<div><button class="ui button">{btn}</button></div></div></a>')

V = "/batch/dsa-juet/track/recursion-siddhartha/video/MTYxNw%3D%3D"

# --- sidebar items (page 2) ---
r = parse_item_html(item(V, "Recursion Introduction", "Group11(1)-1667280599"))
assert (r["title"], r["type"], r["done"], r["active"]) == ("Recursion Introduction", "video", True, False), r

r = parse_item_html(item(V, "Josephus Problem", "Group11-1667280519",
                         extra='<div class="sidebar_video_progress_bar_contents__Y9D7v"><div class="ui progress"></div></div>'))
assert (r["title"], r["type"], r["done"]) == ("Josephus Problem", "video", False), r  # 'Problem' in title must NOT make it coding

r = parse_item_html(item(V, "Palindrome Check using Recursion", "Group11-1667280519", cls="sidebar_item__khyNp active "))
assert r["active"] and r["done"] is False, r

r = parse_item_html(item("/batch/dsa-juet/track/recursion-siddhartha/quiz/NDM4OTY%3D", "Quiz", "Group11-1667280519"))
assert r["type"] == "quiz", r

# synthetic (no real coding HTML pasted yet): conservative rules
r = parse_item_html(item("/batch/dsa-juet/track/x/problem/abc", "Reverse array", "Group11-1667280519"))
assert r["type"] == "coding", r
r = parse_item_html(item("/batch/dsa-juet/track/x/weird/abc", "Something", "mystery-icon"))
assert (r["type"], r["done"]) == ("other", None), r

# --- topic cards (page 1) ---
t = parse_topic_html(topic("/batch/dsa-juet/track/mathematics-siddhartha", "Mathematics", 100, "Resume"))
assert t == {"title": "Mathematics", "slug": "mathematics-siddhartha", "progress": 100, "action": "Resume"}, t
t = parse_topic_html(topic("/batch/dsa-juet/track/recursion-siddhartha", "Recursion", 41, "Resume"))
assert t["progress"] == 41, t
t = parse_topic_html(topic("/batch/dsa-juet/track/bit-magic-siddhartha", "Bit Magic", 0, "Start"))
assert (t["progress"], t["action"]) == (0, "Start"), t
# 'Continue' card links to a video, not a topic -> ignored
assert parse_topic_html(topic("/batch/dsa-juet/track/recursion-siddhartha/video/MjMzMQ%3D%3D", "Recursion", 41, "Continue")) is None

print("all checks passed")
