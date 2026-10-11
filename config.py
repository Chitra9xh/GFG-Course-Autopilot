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
QUIZ_WAIT = 6   # seconds to wait for the quiz block after clicking the quiz tab (short: many topics have no quiz)

MAX_TABS = 5                    # Phase 5 (parallel tabs)
INCLUDE_CHAPTERS = [1]          # chapters whose topic items are read/worked on (1 = DSA Basics to Advanced). 2 (SQL), 3 and 4 (test series) not confirmed yet.
STATE_FILE = BASE_DIR / "data" / "state.json"
PROBLEMS_LOG = BASE_DIR / "data" / "problems_todo.md"   # Phase 4
HTML_DUMP_DIR = BASE_DIR / "data" / "html"              # course-page HTML saved by --scan, for debugging

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
    
    # course page (page 1): chapter blocks, each with a header and, when open, sub-category dropdowns
    "chapters_section": (CSS, 'section[class*="batch_chapters_container__"]'),
    "chapter_blocks": (XPATH, "//div[contains(@class,'batch_chapters_individual_tab__')]"),
    "chapter_header": (XPATH, "./div[contains(@class,'batch_category_header__')]"),          # relative to a chapter block
    "chapter_body": (XPATH, "./*[not(contains(@class,'batch_category_header__'))]"),         # relative to a chapter block
    "subcat_headers": (XPATH, ".//div[contains(@class,'batch_subcategory_header__')]"),      # relative to a chapter block
    "subcat_item": (XPATH, ".."),                                                            # relative to a sub-category header
    "subcat_body": (XPATH, "./*[not(contains(@class,'batch_subcategory_header__'))]"),       # relative to a sub-category item
    
    
    # topic page (page 2) sidebar
    "sidebar_items": (CSS, 'a[class*="sidebar_item__"]'),
    "sidebar_tab_all": (XPATH, "//div[contains(@class,'sidebar_tabs__')][.//p[normalize-space()='all']]"),
    
    "sidebar_tab_quiz": (XPATH, "//div[contains(@class,'sidebar_tabs__')][.//p[normalize-space()='quiz']]"),
    "sidebar_container": (CSS, "#scrollableContainer"),
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
    
        # course page structure (stable prefixes; the part after '__' is a build hash)
    "chapter_tab_class": "batch_chapters_individual_tab__",
    "chapter_number_class": "batch_category_number__",
    "chapter_meta_class": "batch_category_meta__",
    "open_class": "batch_open__",                        # on an open chapter block and its header
    "sub_item_class": "batch_subcategory_item__",
    "sub_open_class": "batch_subcategory_open__",        # on an open sub-category item
    "sub_name_class": "batch_subcategory_name__",
    "sub_meta_class": "batch_subcategory_meta__",
}
# Confirmed: coding items have /problem/ in their href. Anything unclassified
# becomes "other" (skipped + logged) unless it matches these, then "coding".
CODING_HREF_PARTS = ("/problem",)
CODING_KEYWORDS = ("problem", "coding", "assessment")
