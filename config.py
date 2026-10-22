"""All user-tunable settings and every selector. Edit here, nowhere else."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------- settings ----------------
COURSE_URL = "https://www.geeksforgeeks.org/batch/dsa-juet"
PLAYBACK_SPEED = 2.0            # must be one of the site's menu values: 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2

GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]  # strongest first
GEMINI_PASSES = 2               # independent answers per question (2 = double check, 1 = off)
GEMINI_TRIES = 2
GEMINI_BACKOFF = 5

DELAY_MIN = 1.0                 # human-like pause between actions, seconds
DELAY_MAX = 3.0
CHROME_PROFILE_DIR = BASE_DIR / "chrome_profile"   # dedicated profile; the login persists here
PAGE_TIMEOUT = 20               # Selenium wait, seconds
QUIZ_WAIT = 6                   # wait for the quiz block (short: many topics have no quiz)
QUIZ_NAV_WAIT = 10              # wait for "Question N" after clicking a sidebar number
QUIZ_SUBMIT_WAIT = 10           # wait for the right/wrong message after Submit Response
GEMINI_TIMEOUT = 240            # seconds before ONE Gemini call is given up (then retried / next model); the slowest pass seen took 143 s
GEMINI_MIN_GAP = 12              # minimum seconds between Gemini calls; set from the free-tier limits page

TICK_LOAD_WAIT = 6              # after scrolling a sidebar, seconds to wait for lazy-loaded tick icons
TICK_RELOAD_ROUNDS = 2          # extra rounds that scroll each still-unknown item into view and re-read
VERIFY_TICK_WAIT = 60           # after a video ends, how long to re-read the sidebar for its tick
VERIFY_POLL = 5                 # seconds between those re-reads
STALL_SECONDS = 20              # currentTime not advancing this long = stalled
MAX_PLAY_RETRIES = 3            # press play again this many times after a stall, then stop
VIDEO_TIMEOUT_FACTOR = 1.5      # hard timeout = duration / speed * FACTOR + EXTRA
VIDEO_TIMEOUT_EXTRA = 60

INCLUDE_CHAPTERS = [1]          # 1 = DSA; 2 (SQL), 3 and 4 (test series) are not supported yet
STATE_FILE = BASE_DIR / "data" / "state.json"
PROBLEMS_LOG = BASE_DIR / "data" / "problems_todo.md"
HTML_DUMP_DIR = BASE_DIR / "data" / "html"              # course-page HTML saved by --scan


def load_env_file(path):
    """Load KEY=VALUE lines from a .env file into os.environ; real environment variables win."""
    path = Path(path)
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():   # utf-8-sig: Notepad adds a BOM
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")   # never hard-code

# ---------------- selectors ----------------
CSS, XPATH = "css selector", "xpath"   # same values as selenium By.CSS_SELECTOR / By.XPATH

# Class names carry build hashes (e.g. sidebar_item__khyNp), so only the stable prefix is matched.
# Chapter and sub-category selectors marked "relative" are searched inside their parent element.
SELECTORS = {
    # header avatar when logged in; may need changing if the profile has a photo
    "logged_in": (CSS, "div.mainContainer div.defaultProfileImg"),
    "captcha": None,   # not seen yet

    # course page
    "topic_links": (CSS, 'a[href*="/track/"]'),
    "chapters_section": (CSS, 'section[class*="batch_chapters_container__"]'),
    "chapter_blocks": (XPATH, "//div[contains(@class,'batch_chapters_individual_tab__')]"),
    "chapter_header": (XPATH, "./div[contains(@class,'batch_category_header__')]"),          # relative
    "chapter_body": (XPATH, "./*[not(contains(@class,'batch_category_header__'))]"),         # relative
    "subcat_headers": (XPATH, ".//div[contains(@class,'batch_subcategory_header__')]"),      # relative
    "subcat_item": (XPATH, ".."),                                                            # relative
    "subcat_body": (XPATH, "./*[not(contains(@class,'batch_subcategory_header__'))]"),       # relative

    # topic page sidebar
    "sidebar_items": (CSS, 'a[class*="sidebar_item__"]'),
    "sidebar_tab_all": (XPATH, "//div[contains(@class,'sidebar_tabs__')][.//p[normalize-space()='all']]"),
    "sidebar_tab_quiz": (XPATH, "//div[contains(@class,'sidebar_tabs__')][.//p[normalize-space()='quiz']]"),
    "sidebar_container": (CSS, "#scrollableContainer"),

    # video page ('vjs-*' are video.js classes)
    "video_el": (CSS, "div.video-js video.vjs-tech"),
    "big_play": (CSS, "div.video-js button.vjs-big-play-button"),
    "play_control": (CSS, "div.video-js button.vjs-play-control"),
    "rate_menu_button": (CSS, "div.video-js div.vjs-playback-rate"),      # hover to open the speed menu
    "rate_items": (CSS, "div.video-js div.vjs-playback-rate li.vjs-menu-item"),
    "video_title": (CSS, 'span[class*="track_title__"]'),
    "next_button": (XPATH, "//div[contains(@class,'track_action_sec__')]//button[normalize-space()='Next']"),

    # quiz page: one question at a time. Buttons are matched by text, never by position.
    "quiz_boxes": (CSS, 'div[class*="sidebar_quiz_questions__flex__"] > div'),     # count = number of questions
    "quiz_contents": (CSS, 'div[class*="quiz_contents__inner"]'),                   # whole question block (prefix from the test fixtures)
    "quiz_question_current": (CSS, 'span[class*="track_question_current__"]'),      # text like "Question 5"
    "quiz_question_body": (CSS, 'div[class*="track_question_body__"]'),
    "quiz_options": (CSS, 'div[class*="track_question_choices__"] > div'),          # type is checked with MARKERS
    "quiz_option_text": (CSS, 'div[class*="QuizRadioBtn_helper_text__"]'),          # relative to an option
    "quiz_submit": (XPATH, "//button[normalize-space()='Submit Response']"),
    "quiz_response": (CSS, 'div[class*="track_response_container__"] p'),           # exists only after a submit
    "quiz_loader": (CSS, 'div.ui.dimmer[class*="track_loader__"]'),
}

# ---------------- parsing markers (used on outerHTML, not as selectors) ----------------
MARKERS = {
    "topic_title_class": "batch_title__",
    "progress_class": "CircularProgressbar-text",
    "video_href": "/video/",
    "quiz_href": "/quiz/",
    # Tick icons, inferred by counting: 13 items with the "(1)" icon matched "13 of 16 watched".
    "icon_done": "Group11(1)-1667280599",
    "icon_todo": "Group11-1667280519",

    # course page structure
    "chapter_tab_class": "batch_chapters_individual_tab__",
    "chapter_number_class": "batch_category_number__",
    "chapter_meta_class": "batch_category_meta__",
    "open_class": "batch_open__",                        # on an open chapter block and its header
    "sub_item_class": "batch_subcategory_item__",
    "sub_open_class": "batch_subcategory_open__",
    "sub_name_class": "batch_subcategory_name__",
    "sub_meta_class": "batch_subcategory_meta__",

    # quiz page
    "quiz_radio_class": "QuizRadioBtn_radio_container__",      # single-choice option; anything else is only logged
    "quiz_opt_unselected": "QuizRadioBtn_unselected_circle__", # inner circle has this class when NOT chosen
    "quiz_opt_disabled": "QuizRadioBtn_is_disabled__",         # question already submitted
    "quiz_opt_correct": "QuizRadioBtn_is_correct__",           # right option, shown after submit
    "quiz_opt_incorrect": "QuizRadioBtn_is_incorrect__",       # the wrong option that was chosen
    "quiz_resp_correct": "track_is_correct_response__",
    "quiz_resp_incorrect": "track_is_incorrect_response__",

    "quiz_box_container": "sidebar_quiz_questions__flex__",
    "quiz_current_class": "track_question_current__",
    "quiz_body_class": "track_question_body__",
    "quiz_choices_class": "track_question_choices__",
    "quiz_option_text_class": "QuizRadioBtn_helper_text__",
    "quiz_inner_circle_class": "QuizRadioBtn_inner_circle__",
    "quiz_box_active": "is_active",
    "quiz_box_correct": "is_correct",
    "quiz_box_incorrect": "is_incorrect",
}

# Coding items have /problem/ in their href. Anything unclassified becomes "other" (skipped and logged).
CODING_HREF_PARTS = ("/problem",)
CODING_KEYWORDS = ("problem", "coding", "assessment")

# Quiz-page buttons the script must never click (matched by exact text).
QUIZ_NEVER_CLICK = ("Go to Problems", "Next Track", "Next", "Previous", "Report Issue")
