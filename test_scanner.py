"""Run: python test_scanner.py   (no browser needed). HTML trimmed from your pasted pages."""
from scanner import _topics_in_meta, normalize_href, parse_course_html, parse_item_html, parse_topic_html

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

# --- href seen on the real Recursion page: absolute URL + tracking query (fake values here), '&' arrives as &amp; ---
P = "/batch/dsa-juet/track/recursion-siddhartha/video/MTYyOQ%3D%3D"
RAW = "https://www.geeksforgeeks.org" + P + "?_gl=1*abc*_up*MQ..&gclid=XYZ"
assert normalize_href(RAW) == P and normalize_href(V) == V and normalize_href(None) is None
r = parse_item_html(item(RAW.replace("&", "&amp;"), "Some video", "Group11(1)-1667280599"))
assert (r["href"], r["type"], r["done"]) == (P, "video", True), r

# --- course page (page 1): chapters, sub-categories, topic cards. Markup shaped like the real page (class prefixes + hashes). ---
def card(*a):   # the real cards are <a target="_self" href=...>
    return topic(*a).replace("<a href=", '<a target="_self" href=', 1)

def chapter_block(n, title, meta, open_, body=""):
    o = " batch_open__FkoHN" if open_ else ""
    return (f'<div class="batch_individual_tab__type___wbkY batch_chapters_individual_tab__aYS9a {o}">'
            f'<div class="batch_category_header___igBF  {o}"><span class="batch_category_number__2Aaag">{n}</span><h3>{title}</h3>'
            f'<span class="batch_category_meta__OnTVd">{meta}</span><div class="batch_arrow_icon__0ipKc"></div></div>{body}</div>')

def sub_item(name, meta, cards=None):   # cards=None -> closed: no body in the page
    o = " batch_subcategory_open__J4ONM" if cards is not None else ""
    body = f'<div class="batch_items__RzVSg"><div class="batch_content__HAEMJ">{cards}</div></div>' if cards is not None else ""
    return (f'<div class="batch_subcategory_item__95s0o {o}"><div class="batch_subcategory_header__l8FWZ">'
            f'<span class="batch_subcategory_name__YnkaH">{name}</span><span class="batch_subcategory_meta__aFkyw">{meta}</span>'
            f'<i aria-hidden="true" class="chevron down icon batch_subcategory_chevron___gB9o"></i></div>{body}</div>')

PAGE = ('<section class="batch_chapters_container__txdTP">'
        + card("/batch/dsa-juet/track/recursion-siddhartha/video/MjMzMQ%3D%3D", "Recursion", 41, "Continue")   # 'Continue' card sits before the chapters
        + chapter_block(1, "DSA Basics", "2 Chapters · 3 Topics", True, '<div class="batch_subcategory_accordion__1Kk_W">'
            + sub_item("Fundamentals", "1 Topics")
            + sub_item("Maths, Recursion &amp; Bits", "2 Topics",
                       card("/batch/dsa-juet/track/mathematics-siddhartha", "Mathematics", 100, "Resume")
                       + card("/batch/dsa-juet/track/recursion-siddhartha", "Recursion", 41, "Resume"))
            + '</div>')
        + chapter_block(2, "SQL", "5 Topics", True, '<div class="batch_items__RzVSg">' + card("/batch/dsa-juet/track/sql-basics-siddhartha", "SQL Basics", 0, "Start") + '</div>')
        + chapter_block(3, "Product Based Test Series", "5 Topics", False)
        + '</section>')
chs = parse_course_html(PAGE)
assert [(c["number"], c["title"], c["meta"], c["open"], len(c["subcategories"]), len(c["topics"])) for c in chs] == [
    (1, "DSA Basics", "2 Chapters · 3 Topics", True, 2, 2), (2, "SQL", "5 Topics", True, 0, 1),
    (3, "Product Based Test Series", "5 Topics", False, 0, 0)], chs
assert [(s["name"], s["meta"], s["open"]) for s in chs[0]["subcategories"]] == [
    ("Fundamentals", "1 Topics", False), ("Maths, Recursion & Bits", "2 Topics", True)], chs[0]["subcategories"]
assert [(t["slug"], t["progress"], t["action"], t["sub_category"]) for t in chs[0]["topics"]] == [
    ("mathematics-siddhartha", 100, "Resume", "Maths, Recursion & Bits"), ("recursion-siddhartha", 41, "Resume", "Maths, Recursion & Bits")]
assert [(t["slug"], t["sub_category"]) for t in chs[1]["topics"]] == [("sql-basics-siddhartha", None)]   # chapter with no sub-categories
assert (_topics_in_meta("12 Chapters · 33 Topics"), _topics_in_meta("3 Topics"), _topics_in_meta("")) == (33, 3, None)

# --- lazy-loaded tick icons: scroll, wait, re-read (fake driver: an icon "loads" once its item was scrolled into view) ---
import scanner, config
from scanner import read_sidebar, unknown_ticks

assert unknown_ticks([{"done": True}, {"done": None}, {"done": False}, {"done": None}]) == [1, 3]

class FakeEl:
    def __init__(self, n, loads_on):
        self.n, self.loads_on, self.visible = n, loads_on, False   # loads_on: "bottom", "own" or "never"
    def get_attribute(self, name):
        icon = "Group11(1)-1667280599" if self.visible else "Problems_1752210994"
        return item(f"/batch/dsa-juet/track/x/video/V{self.n}", f"Video {self.n}", icon)

class FakeDriver:
    def __init__(self, loads):
        self.els = [FakeEl(n, w) for n, w in enumerate(loads)]
        self.scrolled = []
    def execute_script(self, script, el):
        self.scrolled.append(el.n)
        for e in self.els:   # scrolling to the bottom loads the 'bottom' icons; scrolling to an item loads its own
            if (e is el) or (e.loads_on == "bottom" and el is self.els[-1]):
                e.visible = e.visible or e.loads_on != "never"

scanner.find = lambda d, key: d.els
config.TICK_LOAD_WAIT, config.TICK_RELOAD_ROUNDS = 1, 2

d = FakeDriver(["bottom", "bottom", "bottom"])           # scrolling to the bottom is enough
r = read_sidebar(d)
assert [i["done"] for i in r] == [True, True, True] and d.scrolled == [2], (r, d.scrolled)

d = FakeDriver(["bottom", "own", "own", "bottom"])        # items 2 and 3 need their own scroll (round 1)
r = read_sidebar(d)
assert [i["done"] for i in r] == [True, True, True, True] and d.scrolled == [3, 1, 2], (r, d.scrolled)

d = FakeDriver(["bottom", "never"])                       # never loads: stays unknown, never marked done, no hang
r = read_sidebar(d)
assert [i["done"] for i in r] == [True, None] and r[1]["icon"] == "Problems_1752210994.svg", r
assert unknown_ticks(r) == [1]

print("all checks passed")
