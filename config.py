"""All user-tunable settings + every selector. Edit here, nowhere else."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------- user-tunable settings ----------------
COURSE_URL = "https://www.geeksforgeeks.org/batch/dsa-juet"   # no trailing slash
PLAYBACK_SPEED = 2.0            # Phase 2 (site menu offers 0.25x .. 2x)
MAX_QUIZ_RETRIES = 2            # Phase 3
PASS_THRESHOLD = 0.9            # Phase 3 (fraction)
GEMINI_MODEL = "gemini-2.5-flash"   # Phase 3 - set to a model your key can use
DELAY_MIN = 1.0                 # human-like pause between actions (seconds)
DELAY_MAX = 3.0
CHROME_PROFILE_DIR = BASE_DIR / "chrome_profile"   # dedicated profile, login persists here
PAGE_TIMEOUT = 20               # seconds for Selenium waits

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")   # never hard-code

# ---------------- selectors ----------------
CSS, XPATH = "css selector", "xpath"   # == selenium By.CSS_SELECTOR / By.XPATH

# Built from the HTML you pasted. Class names carry build hashes
# (e.g. sidebar_item__khyNp) so we match the stable prefix only.
SELECTORS = {
    # header avatar shown when logged in (only the 'C' default avatar was pasted;
    # if you have a profile photo this may need changing)
    "logged_in": (CSS, "div.mainContainer div.defaultProfileImg"),
    "captcha": None,   # not seen yet - paste the HTML when one appears
    # course page (page 1): topic cards; filtered by href regex in scanner.py
    "topic_links": (CSS, 'a[href*="/track/"]'),
    # topic page (page 2) sidebar
    "sidebar_items": (CSS, 'a[class*="sidebar_item__"]'),
    "sidebar_tab_all": (XPATH, "//div[contains(@class,'sidebar_tabs__')][.//p[normalize-space()='all']]"),
}

# ---------------- parsing markers (not selectors; used on pasted/outerHTML) ----------------
MARKERS = {
    "topic_title_class": "batch_title__",          # <p class="batch_title__XImuz">
    "progress_class": "CircularProgressbar-text",  # <text ...>41%</text>
    "video_href": "/video/",
    "quiz_href": "/quiz/",
    # Tick icons. Inferred by counting: 13 files use the (1)-...599 icon and the
    # page says 13 of 16 watched, so (1)-...599 = filled/complete.
    "icon_done": "Group11(1)-1667280599",
    "icon_todo": "Group11-1667280519",
}
# UNCONFIRMED: no problem/coding item HTML pasted yet. Anything unclassified
# becomes "other" (skipped + logged) unless it matches these, then "coding".
CODING_HREF_PARTS = ("/problem",)
CODING_KEYWORDS = ("problem", "coding", "assessment")
