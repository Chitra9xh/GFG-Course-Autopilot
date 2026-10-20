"""Phase 2 video runner: pure decision logic (top, testable offline) and the Selenium part (bottom)."""
import logging, re, time
from datetime import datetime
from urllib.parse import unquote, urlsplit
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
import config
from browser import SafetyStop, check_safe_page, find, human_pause, wait_for
from scanner import _click, parse_item_html, scan_items

log = logging.getLogger("video")


def speed_label(speed):
    """2.0 -> '2x', 1.75 -> '1.75x' (the text of the site's speed-menu items)."""
    return f"{speed:g}x"


def hard_timeout(duration, speed):
    """Seconds after which a video is given up on: real playing time * factor + extra."""
    return duration / speed * config.VIDEO_TIMEOUT_FACTOR + config.VIDEO_TIMEOUT_EXTRA


def is_finished(ended, current, duration):
    """video.ended is the real signal; the 0.5 s tolerance covers a player that stops just short of the end."""
    return bool(ended) or (duration > 0 and current >= duration - 0.5)


def videos_todo(items, limit=None):
    """Videos still to watch, in sidebar order. Skips done ones, ones whose tick icon was not recognised
    (done is None) and ones already watched whose tick is still pending."""
    todo = [it for it in items if it["type"] == "video" and it["done"] is False and not it.get("tick_pending")]
    return todo[:limit] if limit else todo


def next_step(items, current_href):
    """After the current video: ('next', item) if the next sidebar item is a video, else ('stop', reason).
    Never answers 'next' for a problem/quiz/other, so the Next button is never clicked towards them."""
    pos = next((i for i, it in enumerate(items) if it["href"] == current_href), None)
    if pos is None:
        return "stop", f"current video not found in the sidebar list: {current_href}"
    if pos + 1 >= len(items):
        return "stop", "no next item (end of the list)"
    nxt = items[pos + 1]
    if nxt["type"] != "video":
        return "stop", f"next item is a {nxt['type']} ({nxt['title']!r}), Next not clicked"
    return "next", nxt


class StallTracker:
    """Feed it (currentTime, now). Returns True once currentTime has not moved for STALL_SECONDS."""

    def __init__(self, now, current=0.0):
        self.last_t, self.last_move = current, now

    def update(self, current, now):
        if current > self.last_t + 0.05:
            self.last_t, self.last_move = current, now
        return now - self.last_move >= config.STALL_SECONDS

    def reset(self, now):
        """Call after pressing play again, so the retry gets a fresh STALL_SECONDS."""
        self.last_move = now
        
        
        
# ---------------- more pure helpers (tested offline) ----------------

def same_path(a, b):
    """Compare two URLs/paths by path only: host, query string, %-encoding and a trailing slash are ignored."""
    return unquote(urlsplit(a).path).rstrip("/") == unquote(urlsplit(b).path).rstrip("/")


def parse_rate_text(text):
    """Text of a speed-menu item -> number. '2x' -> 2.0, '1.75x, selected' -> 1.75, anything else -> None."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)x", text or "")
    return float(m.group(1)) if m else None


def carry_over_pending(old_items, new_items, now=None):
    """scan_items rebuilds the item list, so copy tick_pending from the old items (matched by href).
    If a pending item is now done, drop the mark and report it. Returns [(title, seconds it was pending)]."""
    now = now or datetime.now()
    old = {it["href"]: it for it in old_items if it.get("href")}
    arrived = []
    for it in new_items:
        prev = old.get(it.get("href"))
        if not prev or not prev.get("tick_pending"):
            continue
        if it["done"] is True:
            arrived.append((it["title"], (now - datetime.fromisoformat(prev["tick_pending"])).total_seconds()))
        else:
            it["tick_pending"] = prev["tick_pending"]
    return arrived


# ---------------- Selenium part (needs a browser; not covered by the offline test) ----------------
_STATE_JS = "const v = arguments[0]; return [v.currentTime, v.duration, v.paused, v.ended, v.playbackRate];"


def _origin():
    u = urlsplit(config.COURSE_URL)
    return f"{u.scheme}://{u.netloc}"


def _mmss(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def dump_page(driver, name):
    """Save the current page's HTML to data/html (for debugging and for selectors we have not seen yet)."""
    try:
        config.HTML_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        (config.HTML_DUMP_DIR / name).write_text(driver.page_source, encoding="utf-8")
        log.info("Saved page HTML: data/html/%s", name)
    except (OSError, WebDriverException) as e:
        log.warning("Could not save %s: %s", name, e)


def _read(driver):
    """Player state as a dict, or None if the <video> is not on the page."""
    els = find(driver, "video_el")
    if not els:
        return None
    try:
        cur, dur, paused, ended, rate = driver.execute_script(_STATE_JS, els[0])
    except StaleElementReferenceException:
        return None
    num = lambda x: float(x) if isinstance(x, (int, float)) else 0.0   # NaN duration comes back as None
    return {"current": num(cur), "duration": num(dur), "paused": bool(paused), "ended": bool(ended), "rate": num(rate)}


def _playing(driver):
    s = _read(driver)
    return bool(s and not s["paused"] and s["current"] > 0)


def _wake(driver):
    """Real mouse move over the player so video.js shows its control bar again (it hides it when idle)."""
    els = find(driver, "video_el")
    if els:
        try:
            ActionChains(driver).move_to_element(els[0]).perform()
        except WebDriverException as e:
            log.warning("Could not move the mouse over the player: %s", (e.msg or str(e))[:100])


def _click_play(driver):
    """Real click on the big play button, else on the control-bar play button. True if a click was sent."""
    for key in ("big_play", "play_control"):
        for el in find(driver, key):
            try:
                if el.is_displayed():
                    el.click()
                    return True
            except WebDriverException as e:
                log.warning("Click on %s failed: %s", key, (e.msg or str(e))[:150])
    return False


def _wait_duration(driver):
    def ready(d):
        s = _read(d)
        return s if s and s["duration"] > 0 else False
    try:
        return WebDriverWait(driver, config.PAGE_TIMEOUT).until(ready)
    except TimeoutException:
        raise SafetyStop(f"Video length not available after {config.PAGE_TIMEOUT} s on {driver.current_url}")


def _start(driver, item):
    """Real click on play, then wait until the video is really playing. Only clicks while the player is paused
    (the play button toggles, so clicking a playing video would pause it)."""
    for attempt in range(1, config.MAX_PLAY_RETRIES + 1):
        s = _read(driver)
        if s and s["paused"]:
            _wake(driver)
            if not _click_play(driver):
                log.warning("Play attempt %d/%d: no clickable play control", attempt, config.MAX_PLAY_RETRIES)
            human_pause()
        try:
            WebDriverWait(driver, 10).until(_playing)
            return
        except TimeoutException:
            log.warning("Play attempt %d/%d: video not playing after 10 s", attempt, config.MAX_PLAY_RETRIES)
    dump_page(driver, f"video_noplay_{item['index']}.html")
    raise SafetyStop(f"Video {item['title']!r} would not start after {config.MAX_PLAY_RETRIES} attempts (overlay? see data/html)")


def _set_speed(driver, speed):
    """Pick the speed in the site's own menu. Fallback only if that did not work: video.playbackRate.
    Never touches currentTime. Returns 'already set', 'menu' or 'playbackRate'."""
    target = float(speed)

    def at_target():
        s = _read(driver)
        return bool(s) and abs(s["rate"] - target) < 0.01
        
    if at_target():
        log.info("Speed is already %s: the site's menu was not used", speed_label(speed))
        return "already set"

    try:
        _wake(driver)
        buttons = find(driver, "rate_menu_button")
        if buttons:
            ActionChains(driver).move_to_element(buttons[0]).perform()
            human_pause()
            for li in find(driver, "rate_items"):
                if parse_rate_text(li.get_attribute("textContent")) == target:
                    ActionChains(driver).move_to_element(li).click().perform()
                    break
            human_pause()
    except WebDriverException as e:
        log.warning("Speed menu failed: %s", (e.msg or str(e))[:150])
    if at_target():
        log.info("Speed is %s (set through the site's menu)", speed_label(speed))
        return "menu"
    els = find(driver, "video_el")
    if els:
        log.warning("Menu did not give %s: falling back to video.playbackRate", speed_label(speed))
        driver.execute_script("arguments[0].playbackRate = arguments[1];", els[0], target)
        if at_target():
            return "playbackRate"
    raise SafetyStop(f"Could not set the playback speed to {speed_label(speed)}")


def _watch(driver, duration, speed):
    """Poll the player every 2 s (Selenium wait) until it ends. Returns (outcome, play_retries) where outcome is
    'ended' | 'timeout' | 'stalled' | 'lost' (the <video> disappeared from the page)."""
    timeout = hard_timeout(duration, speed)
    start = time.monotonic()
    s0 = _read(driver)
    tracker = StallTracker(start, s0["current"] if s0 else 0.0)
    out = {"outcome": None, "retries": 0, "warned": False, "last_log": start}

    def tick(d):
        s = _read(d)
        now = time.monotonic()
        if s is None:
            out["outcome"] = "lost"
            return True
        if is_finished(s["ended"], s["current"], s["duration"]):
            out["outcome"] = "ended"
            return True
        if now - start > timeout:
            out["outcome"] = "timeout"
            return True
        if now - out["last_log"] >= 60:
            out["last_log"] = now
            log.info("  %s / %s (rate %gx)", _mmss(s["current"]), _mmss(s["duration"]), s["rate"])
        if abs(s["rate"] - speed) > 0.01 and not out["warned"]:
            out["warned"] = True
            log.warning("Playback rate is %gx, not %gx: the site may have reset it; the timeout may be too short", s["rate"], speed)
        if tracker.update(s["current"], now):
            if out["retries"] >= config.MAX_PLAY_RETRIES:
                out["outcome"] = "stalled"
                return True
            out["retries"] += 1
            if s["paused"]:
                log.warning("Stalled at %s and paused: pressing play (retry %d/%d)", _mmss(s["current"]), out["retries"], config.MAX_PLAY_RETRIES)
                _wake(d)
                _click_play(d)
            else:
                log.warning("Stalled at %s but not paused (buffering?): waiting (retry %d/%d)", _mmss(s["current"]), out["retries"], config.MAX_PLAY_RETRIES)
            tracker.reset(now)
        return False

    try:
        WebDriverWait(driver, timeout + 30, poll_frequency=2).until(tick)
    except TimeoutException:
        out["outcome"] = out["outcome"] or "timeout"
    return out["outcome"], out["retries"]


def play_video(driver, item, speed, n):
    """Play ONE video in real time (the driver is already on its page). Returns a result dict.
    Any outcome other than 'ended' saves the page HTML and raises SafetyStop with the reason."""
    check_safe_page(driver)
    url = driver.current_url
    if any(p in url.lower() for p in config.CODING_HREF_PARTS):
        raise SafetyStop(f"Refusing to touch a coding page: {url}")
    wait_for(driver, "video_el")
    first = _wait_duration(driver)
    duration, start_pos = first["duration"], first["current"]
    titles = find(driver, "video_title")
    title = " ".join(titles[0].text.split()) if titles and titles[0].text.strip() else item["title"]
    log.info("Video %d: %r, length %s, starting at %s, speed %s, about %s to watch", n, title, _mmss(duration), _mmss(start_pos), speed_label(speed), _mmss(duration / speed))
    if n == 1:
        dump_page(driver, f"video_start_{item['index']}.html")
    _start(driver, item)
    how = _set_speed(driver, speed)
    t0 = time.monotonic()
    outcome, retries = _watch(driver, duration, speed)
    wall = time.monotonic() - t0
    if n == 1 or outcome != "ended":
        dump_page(driver, f"video_{outcome}_{item['index']}.html")
    if outcome != "ended":
        s = _read(driver)
        where = f"at {_mmss(s['current'])} of {_mmss(s['duration'])}" if s else f"(player gone, page is {driver.current_url})"
        raise SafetyStop(f"Video {title!r}: {outcome} {where}, {retries} play retries. Not marked as watched.")
    log.info("Video %d ended after %s (speed: %s, %d play retries)", n, _mmss(wall), how, retries)
    return {"n": n, "title": title, "length": _mmss(duration), "from": _mmss(start_pos), "wall": _mmss(wall), "outcome": outcome, "retries": retries, "tick": "?"}


def verify_tick(driver, item):
    """Re-read the sidebar every VERIFY_POLL s for up to VERIFY_TICK_WAIT s. Returns the seconds until the tick
    was seen (about 0 = immediately), or None. Reads the live sidebar only; the page is not reloaded."""
    t0 = time.monotonic()
    seen = {"item": False}

    def shown(d):
        for el in find(d, "sidebar_items"):
            try:
                it = parse_item_html(el.get_attribute("outerHTML"))
            except StaleElementReferenceException:
                return False
            if it["href"] and same_path(it["href"], item["href"]):
                seen["item"] = True
                return it["done"] is True
        return False

    try:
        WebDriverWait(driver, config.VERIFY_TICK_WAIT, poll_frequency=config.VERIFY_POLL).until(shown)
        return time.monotonic() - t0
    except TimeoutException:
        if not seen["item"]:
            log.warning("Video %r was not found in the sidebar of its own page, so its tick could not be checked", item["title"])
        return None


def click_next(driver, expected_href):
    """Click the site's Next button and check that it led to the video we expected. Nothing else on that page is touched."""
    btns = find(driver, "next_button")
    if not btns:
        raise SafetyStop("Next button not found on the video page")
    check_safe_page(driver)
    _click(driver, btns[0], "Next")
    try:
        WebDriverWait(driver, config.PAGE_TIMEOUT).until(lambda d: same_path(d.current_url, expected_href))
    except TimeoutException:
        raise SafetyStop(f"After Next the page is {driver.current_url}, expected {expected_href}. Stopped, nothing done there.")
    human_pause()


def run_topic(driver, topic, speed, limit, on_save, results):
    """Watch the incomplete videos of one topic, one tab. Rescans the topic first (resume), keeps tick_pending marks,
    saves state after every video. Returns a one-line summary; SafetyStop propagates (state already saved)."""
    items = scan_items(driver, topic["slug"])
    for title, secs in carry_over_pending(topic.get("items", []), items):
        log.info("Tick for %r has appeared; it had been pending for %.0f s (%.1f min)", title, secs, secs / 60)
    topic["items"] = items
    topic["scanned_at"] = datetime.now().isoformat(timespec="seconds")
    on_save()
    vids = [it for it in items if it["type"] == "video"]
    todo = videos_todo(items, limit)
    log.info("Topic %r: %d videos, %d done, %d watched with tick pending, %d unknown tick; %d to watch now (limit %s)",
             topic["title"], len(vids), sum(1 for v in vids if v["done"]), sum(1 for v in vids if v.get("tick_pending")),
             sum(1 for v in vids if v["done"] is None), len(todo), limit or "none")
    if not todo:
        return "Nothing to watch: no incomplete videos left in this topic."
    watched = 0
    for n, it in enumerate(todo, 1):
        if not same_path(driver.current_url, it["href"]):
            driver.get(_origin() + it["href"])
            human_pause()
        res = play_video(driver, it, speed, n)
        secs = verify_tick(driver, it)
        now = datetime.now().isoformat(timespec="seconds")
        if secs is None:
            it["tick_pending"] = now
            res["tick"] = f"pending (not seen in {config.VERIFY_TICK_WAIT} s)"
            log.warning("Tick for %r not seen within %d s: marked tick_pending, moving on", it["title"], config.VERIFY_TICK_WAIT)
        else:
            it["done"] = True
            it.pop("tick_pending", None)
            it["watched_at"] = now
            res["tick"] = "immediate" if secs < 2 else f"after {secs:.0f} s"
            log.info("Tick for %r seen: %s", it["title"], res["tick"])
        results.append(res)
        on_save()
        watched += 1
        if n == len(todo):
            break
        act, info = next_step(items, it["href"])
        if act == "stop":
            log.info("Video loop stopped: %s", info)
            return f"Stopped after {watched} video(s): {info}"
        human_pause()
        if same_path(info["href"], todo[n]["href"]):
            click_next(driver, todo[n]["href"])
        else:
            log.info("The next sidebar video %r is already done: opening %r directly instead of Next", info["title"], todo[n]["title"])
    return f"Done: {watched} video(s) watched."
