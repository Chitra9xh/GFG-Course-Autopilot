"""Read-only scanner. Pure parse_* functions work on outerHTML so they can be tested offline."""
import logging, re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
import config
from browser import SafetyStop, check_safe_page, find, human_pause, wait_for

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
    
def normalize_href(href):
    """Keep only the path. A real sidebar link looked like 'https://www.geeksforgeeks.org/batch/...?_gl=..&gclid=..';
    host and tracking query are dropped so stored hrefs are stable. %3D stays as it is."""
    return urlsplit(href).path if href else href


def parse_item_html(outer_html):
    """Sidebar item (page 2) -> dict. done: True/False, or None if tick icon unrecognised (then 'icon' is stored)."""
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
    result = {
        "title": " ".join("".join(p.title).split()),
        "href": normalize_href(p.href),
        "type": classify(p.href, outer_html),
        "done": done,
        "active": "active" in (p.cls or "").split(),
    }
    if done is None:
        result["icon"] = next((s.rsplit("/", 1)[-1] for s in p.imgs if not s.startswith("data:")), None)
    return result


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


def _has_cls(cls, prefix):
    """True if any class token starts with prefix (class names carry build hashes, so match the prefix)."""
    return any(tok.startswith(prefix) for tok in (cls or "").split())


def _topics_in_meta(meta):
    """'12 Chapters · 33 Topics' -> 33, '3 Topics' -> 3, anything else -> None."""
    m = re.search(r"(\d+)\s*Topics", meta or "")
    return int(m.group(1)) if m else None


class _Course(HTMLParser):
    """Walks the chapters section of the course page and remembers which chapter / sub-category each topic card is in."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, src):
        super().__init__()
        self.src = src
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", src)]
        self.stack = []                # (tag, kind) for every open non-void tag
        self.chapters = []
        self.field = None              # (dict, key) that text is currently being added to
        self.card_start = self.card_sub = None

    def _index(self):
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        kind = None
        if tag == "div" and M["chapter_tab_class"] in cls:
            kind = "chapter"
            self.chapters.append({"number": None, "title": "", "meta": "", "open": _has_cls(cls, M["open_class"]),
                                  "subcategories": [], "topics": []})
        elif self.chapters:
            ch = self.chapters[-1]
            if tag == "div" and M["sub_item_class"] in cls:
                kind = "sub"
                ch["subcategories"].append({"name": "", "meta": "", "open": _has_cls(cls, M["sub_open_class"])})
            elif tag == "a" and self.card_start is None and SLUG_RE.search(a.get("href") or ""):
                kind = "card"
                self.card_start = self._index()
                self.card_sub = ch["subcategories"][-1] if any(k == "sub" for _, k in self.stack) else None
            elif tag == "span" and M["chapter_number_class"] in cls:
                self.field = (ch, "number")
            elif tag == "span" and M["chapter_meta_class"] in cls:
                self.field = (ch, "meta")
            elif tag == "h3" and not ch["title"]:
                self.field = (ch, "title")
            elif tag == "span" and ch["subcategories"] and M["sub_name_class"] in cls:
                self.field = (ch["subcategories"][-1], "name")
            elif tag == "span" and ch["subcategories"] and M["sub_meta_class"] in cls:
                self.field = (ch["subcategories"][-1], "meta")
        if self.field and self.field[0].get(self.field[1]) is None:
            self.field[0][self.field[1]] = ""
        if tag not in self.VOID:
            self.stack.append((tag, kind))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                kind = self.stack[i][1]
                del self.stack[i:]
                break
        else:
            return
        if tag in ("span", "h3"):
            self.field = None
        if kind == "card":
            end = self.src.index(">", self._index()) + 1
            t = parse_topic_html(self.src[self.card_start:end])
            if t:
                sub = " ".join(self.card_sub["name"].split()) if self.card_sub else None
                self.chapters[-1]["topics"].append({**t, "sub_category": sub})
            self.card_start = self.card_sub = None

    def handle_data(self, data):
        if self.field:
            d, k = self.field
            d[k] = (d.get(k) or "") + data


def parse_course_html(outer_html):
    """Chapters section (course page) -> list of chapters:
    {number, title, meta, open, subcategories: [{name, meta, open}], topics: [{...topic card..., sub_category}]}.
    Only what is open is in the page: a closed chapter has no sub-categories or topics yet, a closed sub-category no topics."""
    p = _Course(outer_html)
    p.feed(outer_html)
    p.close()
    for ch in p.chapters:
        num = re.search(r"\d+", ch["number"] or "")
        ch["number"] = int(num.group()) if num else None
        ch["title"] = " ".join(ch["title"].split())
        ch["meta"] = " ".join(ch["meta"].split())
        for s in ch["subcategories"]:
            s["name"] = " ".join(s["name"].split())
            s["meta"] = " ".join(s["meta"].split())
    return p.chapters


def _click(driver, el, label):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        el.click()
    except WebDriverException as e:
        raise SafetyStop(f"Could not click {label!r}: {(e.msg or str(e))[:150]}")


def _open(driver, get_target, is_open, label):
    """Click the header if its section is closed, then wait until it reports open. get_target() re-finds the
    header each time so a re-rendered page does not leave us with a stale element. Returns True if it clicked."""
    if is_open(get_target()):
        return False
    _click(driver, get_target(), label)

    def now_open(_):
        try:
            return is_open(get_target())
        except (StaleElementReferenceException, IndexError):
            return False
    try:
        WebDriverWait(driver, config.PAGE_TIMEOUT).until(now_open)
    except TimeoutException:
        raise SafetyStop(f"{label!r} did not open after the click (page changed?)")
    human_pause()
    check_safe_page(driver)
    return True


def _wait_body(driver, get_container, key, label):
    """After opening, wait until the section has something besides its header. Only a warning if not:
    the count check at the end of scan_topics reports what is missing."""
    def has_body(_):
        try:
            return bool(find(get_container(), key))
        except (StaleElementReferenceException, IndexError):
            return False
    try:
        WebDriverWait(driver, config.PAGE_TIMEOUT).until(has_body)
    except TimeoutException:
        log.warning("%s: nothing appeared after opening it", label)


def _dump_html(name, html):
    try:
        config.HTML_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        (config.HTML_DUMP_DIR / name).write_text(html, encoding="utf-8")
    except OSError as e:
        log.warning("Could not save %s: %s", name, e)


def scan_topics(driver):
    """Open every chapter and every sub-category one at a time and read what is on the page after each open,
    so it works whether or not the page closes the others. Topics come back in page order, tagged with
    chapter and sub-category. Only the dropdown headers are clicked; no topic or item is opened."""
    driver.get(config.COURSE_URL)
    check_safe_page(driver)
    wait_for(driver, "chapter_blocks")
    topics, seen, chapter_info, sub_expected, sub_rank = [], set(), {}, {}, {}

    def read(dump_name=None):
        html = find(driver, "chapters_section")[0].get_attribute("outerHTML")
        if dump_name:
            _dump_html(dump_name, html)
        for ch in parse_course_html(html):
            chapter_info.setdefault(ch["number"], {"title": ch["title"], "expected": _topics_in_meta(ch["meta"])})
            for i, s in enumerate(ch["subcategories"]):
                sub_expected.setdefault((ch["number"], s["name"]), _topics_in_meta(s["meta"]))
                sub_rank.setdefault((ch["number"], s["name"]), i)   # position of the sub-category on the page
            for t in ch["topics"]:
                if t["slug"] not in seen:
                    seen.add(t["slug"])
                    topics.append({"index": 0, "chapter": ch["number"], "chapter_title": ch["title"], **t})

    n_chapters = len(find(driver, "chapter_blocks"))
    log.info("Course page has %d chapters", n_chapters)
    for ci in range(n_chapters):
        blocks = lambda: find(driver, "chapter_blocks")[ci]
        label = f"chapter {ci + 1}"
        if _open(driver, lambda: find(blocks(), "chapter_header")[0],
                 lambda h: _has_cls(h.get_attribute("class"), M["open_class"]), label):
            log.info("Opened %s", label)
            _wait_body(driver, blocks, "chapter_body", label)
        read(f"chapter_{ci + 1}.html")
        for si in range(len(find(blocks(), "subcat_headers"))):
            head = lambda: find(blocks(), "subcat_headers")[si]
            sub_label = f"{label} / sub-category {si + 1} ({' '.join(head().text.split())})"
            if _open(driver, head, lambda h: _has_cls(find(h, "subcat_item")[0].get_attribute("class"), M["sub_open_class"]), sub_label):
                log.info("Opened %s", sub_label)
                _wait_body(driver, lambda: find(head(), "subcat_item")[0], "subcat_body", sub_label)
            read()

    # Topics were read in the order the sections were opened (the one already open comes first), so put them
    # back in page order. The sort is stable, so the card order inside each sub-category is kept.
    topics.sort(key=lambda t: (t["chapter"] or 0, sub_rank.get((t["chapter"], t["sub_category"]), -1)))
    for i, t in enumerate(topics, 1):
        t["index"] = i

    # Compare with the counts the page itself announces ('12 Chapters · 33 Topics', '3 Topics').
    for num, info in chapter_info.items():
        found = sum(1 for t in topics if t["chapter"] == num)
        if info["expected"] is not None and info["expected"] != found:
            log.warning("Chapter %s %r: page says %d topics, found %d", num, info["title"], info["expected"], found)
    for (num, name), expected in sub_expected.items():
        found = sum(1 for t in topics if t["chapter"] == num and t["sub_category"] == name)
        if expected is not None and expected != found:
            log.warning("Chapter %s / %r: page says %d topics, found %d", num, name, expected, found)
    log.info("Found %d topics in %d chapters", len(topics), len(chapter_info))
    return topics


def _wait_all_tab_active(driver):
    def active(d):
        t = find(d, "sidebar_tab_all")
        return bool(t) and "active" in (t[0].get_attribute("class") or "").split()
    try:
        WebDriverWait(driver, config.PAGE_TIMEOUT).until(active)
    except TimeoutException:
        raise SafetyStop(f"Sidebar 'all' tab did not become active after the click on {driver.current_url} (page changed?)")
        
        
def parse_quiz_html(outer_html):
    """Sidebar with the 'quiz' tab open -> dict, or None if there is no quiz block."""
    counts = {k.lower(): int(n) for n, k in re.findall(r"(\d+)\s*(Correct|Wrong|Unanswered)", outer_html)}
    m = re.search(r"quiz\s*\((\d+)\)", outer_html, re.I)
    total = int(m.group(1)) if m else (sum(counts.values()) or None)
    if not total:
        return None
    unanswered = counts.get("unanswered", total)
    return {"questions": total, "correct": counts.get("correct", 0), "wrong": counts.get("wrong", 0),
            "unanswered": unanswered, "done": unanswered == 0}


def scan_quiz(driver):
    """Click the sidebar 'quiz' tab (read-only; nothing is answered) and read the question counts.
    Returns a quiz item dict, or None if the topic has no quiz tab or no quiz."""
    tabs = find(driver, "sidebar_tab_quiz")
    if not tabs:
        return None
    if "active" not in (tabs[0].get_attribute("class") or "").split():
        tabs[0].click()

    def ready(d):
        try:
            t, box = find(d, "sidebar_tab_quiz"), find(d, "sidebar_container")
            return (bool(t) and "active" in (t[0].get_attribute("class") or "").split()
                    and bool(box) and parse_quiz_html(box[0].get_attribute("outerHTML")) is not None)
        except StaleElementReferenceException:
            return False

    try:
        WebDriverWait(driver, config.QUIZ_WAIT).until(ready)
    except TimeoutException:
        return None
    human_pause()
    check_safe_page(driver)
    q = parse_quiz_html(find(driver, "sidebar_container")[0].get_attribute("outerHTML"))
    href = normalize_href(driver.current_url) if "/quiz/" in driver.current_url else None
    return {"title": "Quiz", "href": href, "type": "quiz", "done": q["done"], "active": False,
            "questions": q["questions"], "correct": q["correct"], "wrong": q["wrong"], "unanswered": q["unanswered"]}
            
def unknown_ticks(items):
    """0-based positions of the items whose tick icon is not recognised."""
    return [i for i, it in enumerate(items) if it["done"] is None]


def _show_item(driver, i):
    """Scroll sidebar item i into view (the last one if i is too big). Lazy-loaded icons load once visible."""
    els = find(driver, "sidebar_items")
    if els:
        driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", els[min(i, len(els) - 1)])


def read_sidebar(driver):
    """Parse every sidebar item. Icons of items below the visible part may not be loaded yet, so scroll the
    list to the bottom and wait until every tick is recognised. Items still unknown are scrolled into view one by
    one and re-read (TICK_RELOAD_ROUNDS times). What stays unknown is returned with done=None (skipped later)."""
    seen = []

    def parse(_):
        try:
            seen[:] = [parse_item_html(el.get_attribute("outerHTML")) for el in find(driver, "sidebar_items")]
        except StaleElementReferenceException:
            return False
        return bool(seen) and not unknown_ticks(seen)

    _show_item(driver, 10 ** 6)
    for rnd in range(config.TICK_RELOAD_ROUNDS + 1):
        try:
            WebDriverWait(driver, config.TICK_LOAD_WAIT).until(parse)
            break
        except TimeoutException:
            if rnd < config.TICK_RELOAD_ROUNDS:
                bad = unknown_ticks(seen)
                log.info("%d tick icon(s) not loaded yet (item #%s): scrolling them into view (round %d)",
                         len(bad), ", #".join(str(i + 1) for i in bad), rnd + 1)
                for i in bad:
                    _show_item(driver, i)
    return seen            


def scan_items(driver, slug):
    driver.get(f"{config.COURSE_URL}/track/{slug}")
    check_safe_page(driver)
    wait_for(driver, "sidebar_items")
    tabs = find(driver, "sidebar_tab_all")
    # Switching to the 'all' tab only changes the sidebar filter; it opens nothing.
    # (The Recursion page was saved with the 'videos' tab active, so this click is needed.)
    if not tabs:
        log.warning("No 'all' tab found on %s: only the tab currently shown is scanned", driver.current_url)
    elif "active" not in (tabs[0].get_attribute("class") or "").split():
        tabs[0].click()
        _wait_all_tab_active(driver)
        human_pause()
        check_safe_page(driver)
    items = []
    wait_for(driver, "sidebar_items")
    for it in read_sidebar(driver):
        it["index"] = len(items) + 1
        if it["type"] == "other":
            log.warning("Unclassified item #%d %r href=%s -> 'other' (will be skipped)", it["index"], it["title"], it["href"])
        if it["done"] is None:
            log.warning("Unrecognised tick icon on #%d %r (icon=%s)", it["index"], it["title"], it.get("icon"))
        items.append(it)
    quiz = scan_quiz(driver)
    if quiz:
        quiz["index"] = len(items) + 1
        log.info("Quiz found: %d questions, %d unanswered, href=%s", quiz["questions"], quiz["unanswered"], quiz["href"])
        items.append(quiz)
    return items


def scan_all(driver, topics, on_topic=None):
    """Read the items of every topic in config.INCLUDE_CHAPTERS (read-only). Topics of other chapters stay listed
    but their pages are not opened. on_topic(topic) runs after each topic, e.g. to save state.
    A SafetyStop propagates; whatever on_topic already saved stays."""
    todo = [t for t in topics if t.get("chapter") in config.INCLUDE_CHAPTERS]
    if len(todo) < len(topics):
        log.info("Reading items only for chapters %s; %d topics in other chapters are listed but not opened",
                 sorted(config.INCLUDE_CHAPTERS), len(topics) - len(todo))
    for n, t in enumerate(todo, 1):
        log.info("Scanning topic %d/%d: %s", n, len(todo), t["title"])
        t["items"] = scan_items(driver, t["slug"])
        t["scanned_at"] = datetime.now().isoformat(timespec="seconds")
        if on_topic:
            on_topic(t)
        human_pause()
    return topics
