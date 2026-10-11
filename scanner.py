"""Read-only scanner. Pure parse_* functions work on outerHTML so they can be tested offline."""
import logging, re
from html.parser import HTMLParser
from urllib.parse import unquote
import config
from browser import check_safe_page, find, human_pause, wait_for

log = logging.getLogger("scanner")
M = config.MARKERS
SLUG_RE = re.compile(r"/track/([^/?#]+)/?(?:[?#].*)?$")   # topic link, NOT /track/x/video/y


class _Item(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = self.cls = None
        self.title, self.imgs, self._in_p, self._p_done = [], [], False, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and self.href is None:
            self.href, self.cls = a.get("href"), a.get("class", "")
        elif tag == "img" and a.get("src"):
            self.imgs.append(unquote(a["src"]))
        elif tag == "p" and not self._p_done:
            self._in_p = True

    def handle_endtag(self, tag):
        if tag == "p" and self._in_p:
            self._in_p, self._p_done = False, True

    def handle_data(self, data):
        if self._in_p:
            self.title.append(data)


def classify(href, raw_html):
    h, raw = (href or "").lower(), raw_html.lower()
    if M["video_href"] in h:
        return "video"
    if M["quiz_href"] in h:
        return "quiz"
    # conservative: doubt -> coding (never touched)
    if any(p in h for p in config.CODING_HREF_PARTS) or any(k in raw for k in config.CODING_KEYWORDS):
        return "coding"
    return "other"


def parse_item_html(outer_html):
    """Sidebar item (page 2) -> dict. done: True/False, or None if tick icon unrecognised."""
    p = _Item()
    p.feed(outer_html)
    done = None
    for src in p.imgs:
        if M["icon_done"] in src:
            done = True
            break
        if M["icon_todo"] in src:
            done = False
            break
    return {
        "title": " ".join("".join(p.title).split()),
        "href": p.href,
        "type": classify(p.href, outer_html),
        "done": done,
        "active": "active" in (p.cls or "").split(),
    }


class _Topic(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href, self.v, self._f = None, {}, None   # v: field -> collected text

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "a" and self.href is None:
            self.href = a.get("href")
        elif tag == "p" and M["topic_title_class"] in cls and "title" not in self.v:
            self._f = "title"
        elif tag == "text" and M["progress_class"] in cls:
            self._f = "progress"
        elif tag == "button" and "action" not in self.v:
            self._f = "action"
        if self._f:
            self.v.setdefault(self._f, "")

    def handle_endtag(self, tag):
        if tag in ("p", "text", "button"):
            self._f = None

    def handle_data(self, data):
        if self._f:
            self.v[self._f] += data


def parse_topic_html(outer_html):
    """Topic card (page 1) -> dict, or None if the link isn't a topic (e.g. 'Continue' card)."""
    p = _Topic()
    p.feed(outer_html)
    m = SLUG_RE.search(p.href or "")
    if not m:
        return None
    pct = re.search(r"(\d+)\s*%", p.v.get("progress", ""))
    return {
        "title": " ".join(p.v.get("title", "").split()),
        "slug": m.group(1),
        "progress": int(pct.group(1)) if pct else 0,   # no ring shown = not started
        "action": " ".join(p.v.get("action", "").split()),
    }


def scan_topics(driver):
    driver.get(config.COURSE_URL)
    check_safe_page(driver)
    els = wait_for(driver, "topic_links")
    topics, seen = [], set()
    for el in els:
        t = parse_topic_html(el.get_attribute("outerHTML"))
        if t and t["slug"] not in seen:
            seen.add(t["slug"])
            topics.append({"index": len(topics) + 1, **t})
    log.info("Found %d topics (only expanded sections exist in the page; collapsed ones are not scanned)", len(topics))
    return topics


def scan_items(driver, slug):
    driver.get(f"{config.COURSE_URL}/track/{slug}")
    check_safe_page(driver)
    wait_for(driver, "sidebar_items")
    tabs = find(driver, "sidebar_tab_all")
    # Switching to the 'all' tab only changes the sidebar filter; it opens nothing.
    if tabs and "active" not in (tabs[0].get_attribute("class") or "").split():
        tabs[0].click()
        human_pause()
        check_safe_page(driver)
    items = []
    for el in wait_for(driver, "sidebar_items"):
        it = parse_item_html(el.get_attribute("outerHTML"))
        it["index"] = len(items) + 1
        if it["type"] == "other":
            log.warning("Unclassified item #%d %r href=%s -> 'other' (will be skipped)", it["index"], it["title"], it["href"])
        if it["done"] is None:
            log.warning("Unrecognised tick icon on #%d %r", it["index"], it["title"])
        items.append(it)
    return items
