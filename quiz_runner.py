"""Selenium side of the quiz runner. quiz.py stays pure; Gemini is reached only through make_ask()."""
import logging
import re
import time
from datetime import datetime

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

import config
import quiz
from browser import SafetyStop, check_safe_page, find, human_pause, wait_for
from scanner import _click, scan_items
from video import _origin, carry_over_pending, same_path

from scanner import _click, parse_quiz_html, scan_items

log = logging.getLogger("quiz_runner")


def make_ask():
    """Return ask(model, prompt) -> text, spaced by GEMINI_MIN_GAP. Only question text is ever sent."""
    key = config.GEMINI_API_KEY
    if not key or key == "your-key-here":
        raise SafetyStop("GEMINI_API_KEY is missing or still the placeholder: put your key in .env")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT * 1000))   # milliseconds
    last = [0.0]

    def ask(model, prompt):
        wait = config.GEMINI_MIN_GAP - (time.monotonic() - last[0])
        if wait > 0:
            time.sleep(wait)
        last[0] = time.monotonic()
        return client.models.generate_content(model=model, contents=prompt).text

    return ask


def _guard(driver):
    if "/quiz/" not in driver.current_url:
        raise SafetyStop(f"Not on a quiz page: {driver.current_url}")
    check_safe_page(driver)


def _wait_loader(driver):
    def gone(d):
        try:
            return not any(e.is_displayed() for e in find(d, "quiz_loader"))
        except StaleElementReferenceException:
            return False
    try:
        WebDriverWait(driver, config.QUIZ_NAV_WAIT).until(gone)
    except TimeoutException:
        raise SafetyStop("The quiz loader did not go away.")


def _safe_click(driver, el, label):
    text = (el.text or "").strip()
    if text in config.QUIZ_NEVER_CLICK:
        raise SafetyStop(f"Refusing to click {text!r} ({label})")
    _click(driver, el, label)


def _header_number(driver):
    try:
        els = find(driver, "quiz_question_current")
        m = re.search(r"\d+", els[0].text) if els else None
        return int(m.group()) if m else None
    except StaleElementReferenceException:
        return None


def _question(driver):
    for _ in range(3):
        try:
            els = find(driver, "quiz_contents")
            if len(els) != 1:
                raise SafetyStop(f"Expected one question block, found {len(els)}.")
            return quiz.parse_question_html(els[0].get_attribute("outerHTML"))
        except StaleElementReferenceException:
            human_pause()
    raise SafetyStop("The question block kept changing.")


def question_total(driver, expected):
    """Number of questions from the sidebar boxes; any mismatch is a SafetyStop."""
    box = find(driver, "sidebar_container")
    if not box:
        raise SafetyStop("Sidebar not found on the quiz page.")
    try:
        n = quiz.question_count(quiz.parse_quiz_boxes(box[0].get_attribute("outerHTML")))
    except quiz.QuizError as e:
        raise SafetyStop(f"Could not count quiz questions: {e}")
    live = len(find(driver, "quiz_boxes"))
    if live != n or (expected and n != expected):
        raise SafetyStop(f"Question count mismatch: sidebar html {n}, live boxes {live}, scan {expected}.")
    return n


def go_to(driver, k, n):
    """Open question k by clicking its sidebar number (the only way this runner navigates)."""
    _guard(driver)
    _wait_loader(driver)
    if _header_number(driver) == k:
        return
    boxes = find(driver, "quiz_boxes")
    if len(boxes) != n:
        raise SafetyStop(f"Expected {n} sidebar boxes, found {len(boxes)}.")
    if boxes[k - 1].text.strip() != str(k):
        raise SafetyStop(f"Sidebar box {k} shows {boxes[k - 1].text.strip()!r}.")
    _safe_click(driver, boxes[k - 1], f"quiz box {k}")
    try:
        WebDriverWait(driver, config.QUIZ_NAV_WAIT).until(lambda d: _header_number(d) == k)
    except TimeoutException:
        raise SafetyStop(f"'Question {k}' did not appear after clicking box {k}.")
    _wait_loader(driver)
    human_pause()


def read_question(driver, k, n):
    go_to(driver, k, n)
    q = _question(driver)
    if q["number"] != k:
        raise SafetyStop(f"Expected Question {k}, the page shows Question {q['number']}.")
    return q


def select_option(driver, q, idx, n):
    """Click one option (never Submit) and report whether the page shows it as selected."""
    letter = quiz.LETTERS[idx]
    go_to(driver, q["number"], n)
    fresh = _question(driver)
    if fresh["answered"]:
        raise SafetyStop(f"Question {q['number']} is already answered; not touching it.")
    options = find(driver, "quiz_options")
    if len(options) != len(q["options"]):
        raise SafetyStop(f"Question {q['number']}: expected {len(q['options'])} options, found {len(options)}.")
    el = options[idx]
    if config.MARKERS["quiz_radio_class"] not in (el.get_attribute("class") or ""):
        raise SafetyStop(f"Question {q['number']}: option {letter} is not a single-choice option.")
    _safe_click(driver, el, f"option {letter} of question {q['number']}")
    human_pause()

    def selected(d):
        try:
            return _question(d)["chosen"] == idx
        except StaleElementReferenceException:
            return False
    try:
        WebDriverWait(driver, config.QUIZ_NAV_WAIT).until(selected)
        return True
    except TimeoutException:
        return False


def _short(text, width=40):
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 3] + "..."


def read_counters(driver):
    box = find(driver, "sidebar_container")
    c = parse_quiz_html(box[0].get_attribute("outerHTML")) if box else None
    if c is None:
        raise SafetyStop("Could not read the Correct/Wrong/Unanswered counters from the sidebar.")
    return c


def verify_counters(driver, before, result):
    """After a submit the counters must move by exactly one question; anything else is a SafetyStop."""
    want = quiz.expected_counters(before, result)
    got = {}

    def moved(d):
        try:
            got.update(read_counters(d))
        except StaleElementReferenceException:
            return False
        return all(got[k] == want[k] for k in want)
    try:
        WebDriverWait(driver, config.QUIZ_SUBMIT_WAIT).until(moved)
    except TimeoutException:
        raise SafetyStop(f"Counters did not move as expected: expected {want}, now "
                         f"{ {k: got.get(k) for k in want} }.")
    return got


def submit_answer(driver, q, idx, n, before, confirm):
    """Select option idx and submit ONE question, then check the page and the counters. Answers are final."""
    letter = quiz.LETTERS[idx]
    if confirm:
        print(f"\nQuestion {q['number']}: {q['text']}")
        for i, o in enumerate(q["options"]):
            print(f"  {quiz.LETTERS[i]}) {o['text']}")
        if input(f"Gemini chose {letter}. Submitting is FINAL. Type yes to submit: ").strip().lower() != "yes":
            raise SafetyStop("Submit declined at the prompt; nothing was submitted.")
    if not select_option(driver, q, idx, n):
        raise SafetyStop(f"Option {letter} did not show as selected on question {q['number']}; not submitting.")
    buttons = find(driver, "quiz_submit")
    if len(buttons) != 1:
        raise SafetyStop(f"Expected one 'Submit Response' button, found {len(buttons)}.")
    btn = buttons[0]
    if (btn.text or "").strip() != "Submit Response" or not btn.is_enabled():
        raise SafetyStop("The Submit Response button is missing its text or is disabled.")
    _guard(driver)
    log.info("Submitting option %s for question %d", letter, q["number"])
    _safe_click(driver, btn, f"Submit Response (question {q['number']})")
    try:
        WebDriverWait(driver, config.QUIZ_SUBMIT_WAIT).until(lambda d: bool(find(d, "quiz_response")))
    except TimeoutException:
        raise SafetyStop(f"No response message after submitting question {q['number']}; check the page by hand.")
    _wait_loader(driver)
    after = _question(driver)
    if (after["number"] != q["number"] or not after["answered"] or after["chosen"] != idx
            or after.get("result") not in ("correct", "incorrect")):
        raise SafetyStop(f"Question {q['number']} does not look submitted as {letter} "
                         f"(result {after.get('result')!r}, chosen {after.get('chosen')!r}).")
    counters = verify_counters(driver, before, after["result"])
    log.info("Question %d submitted: %s (counters %d correct, %d wrong, %d unanswered)", q["number"], after["result"],
             counters["correct"], counters["wrong"], counters["unanswered"])
    return after, counters


def _open_and_solve(driver, topic, ask, on_save, rows):
    """Rescan the topic, open its quiz, read every question, get Gemini's answers (double-checked). Submits nothing.
    Returns (message, None) when there is nothing to do, else (None, context)."""
    items = scan_items(driver, topic["slug"])
    for title, secs in carry_over_pending(topic.get("items", []), items):
        log.info("Tick for %r has appeared; it had been pending for %.0f s (%.1f min)", title, secs, secs / 60)
    topic["items"] = items
    topic["scanned_at"] = datetime.now().isoformat(timespec="seconds")
    on_save()
    qz = next((it for it in items if it["type"] == "quiz"), None)
    if qz is None:
        return "This topic has no quiz.", None
    if qz["done"]:
        return "The quiz is already complete (nothing unanswered).", None
    if not qz["href"]:
        raise SafetyStop("The quiz URL was not recorded by the scan; send the sidebar outerHTML with the quiz tab open.")
    if not same_path(driver.current_url, qz["href"]):
        driver.get(_origin() + qz["href"])
        human_pause()
    wait_for(driver, "quiz_boxes")
    _guard(driver)
    _wait_loader(driver)
    n = question_total(driver, qz["questions"])

    questions = [read_question(driver, k, n) for k in range(1, n + 1)]
    todo, answered, unsupported = quiz.split_questions(questions)
    log.info("Quiz read: %d questions, %d to answer, %d already answered, %d unsupported",
             n, len(todo), len(answered), len(unsupported))
    for u in unsupported:
        log.warning("Question %s left unanswered: %s", u["number"], "; ".join(u["unsupported"]))
        rows.append({"n": u["number"], "answer": "-", "result": "-", "text": "",
                     "note": "unsupported: " + "; ".join(u["unsupported"])})
    for a in answered:
        letter = quiz.LETTERS[a["chosen"]] if a["chosen"] is not None else "?"
        rows.append({"n": a["number"], "answer": letter, "result": a.get("result") or "?", "text": "",
                     "note": "already submitted"})
    ctx = {"qz": qz, "n": n, "todo": todo, "final": {}, "notes": {}, "used": [],
           "unsupported": [u["number"] for u in unsupported]}
    if not todo:
        rows.sort(key=lambda r: r["n"])
        return "Nothing for Gemini to answer in this quiz.", None

    try:
        final, notes, used = quiz.solve(todo, ask, config.GEMINI_MODELS, config.GEMINI_PASSES,
                                        config.GEMINI_TRIES, config.GEMINI_BACKOFF, log=log.info)
    except (quiz.FatalApiError, quiz.AllModelsFailed) as e:
        raise SafetyStop(f"Gemini stopped the run: {e}")
    log.info("Gemini answered %d question(s); calls went to: %s", len(final), ", ".join(used))
    for q in todo:
        idx = final[q["number"]]
        rows.append({"n": q["number"], "answer": quiz.LETTERS[idx], "result": "-",
                     "text": _short(q["options"][idx]["text"]), "note": notes.get(q["number"], "")})
    rows.sort(key=lambda r: r["n"])
    ctx.update(final=final, notes=notes, used=used)
    return None, ctx


def dry_run(driver, topic, ask, on_save, rows):
    """Read every question, ask Gemini, select ONE option, never submit."""
    msg, ctx = _open_and_solve(driver, topic, ask, on_save, rows)
    if msg:
        return msg
    first = ctx["todo"][0]
    idx = ctx["final"][first["number"]]
    shown = select_option(driver, first, idx, ctx["n"])
    log.info("Dry run: option %s selected on question %d, selected state %s; Submit NOT clicked",
             quiz.LETTERS[idx], first["number"], "shown" if shown else "NOT shown")
    return (f"Dry run: {len(ctx['todo'])} question(s) answered by Gemini; option {quiz.LETTERS[idx]} selected on "
            f"question {first['number']} (selected state {'shown' if shown else 'NOT shown'}). Nothing was submitted.")


def _ask_start(count):
    print(f"\nAbout to submit {count} answer(s) for real. Every answer is FINAL (no retake).")
    if input("Type yes to start: ").strip().lower() != "yes":
        raise SafetyStop("Start declined at the prompt; nothing was submitted.")


def run_real(driver, topic, ask, on_save, rows, max_questions, confirm_start=None, stats=None):
    """Submit the unanswered questions one at a time. With max_questions: stop after N and confirm each one.
    Without it: one confirmation, then the whole quiz."""
    msg, ctx = _open_and_solve(driver, topic, ask, on_save, rows)
    if msg:
        return msg
    qz, n, final, notes = ctx["qz"], ctx["n"], ctx["final"], ctx["notes"]
    if stats is not None:
        stats["models"] = list(dict.fromkeys(ctx["used"]))
    batch = ctx["todo"][:max_questions] if max_questions else ctx["todo"]
    if max_questions is None:
        (confirm_start or _ask_start)(len(batch))
    before = read_counters(driver)
    submitted = 0
    for q in batch:
        after, counters = submit_answer(driver, q, final[q["number"]], n, before, confirm=max_questions is not None)
        before = counters
        row = next(r for r in rows if r["n"] == q["number"])
        if after["result"] == "correct":
            row["result"] = "correct"
        else:
            ci = after.get("correct_index")
            row["result"] = "WRONG" + (f" (right: {quiz.LETTERS[ci]})" if ci is not None else "")
        qz.update({k: counters[k] for k in ("correct", "wrong", "unanswered", "done")})
        on_save()
        submitted += 1
        human_pause()
    disputed = sorted(notes)
    ties = sorted(k for k, v in notes.items() if "strongest model" in v)
    log.info("Quiz finished: %d submitted | models used: %s | disputed: %s | tie-breaks: %s | unsupported: %s",
             submitted, ", ".join(ctx["used"]), disputed or "none", ties or "none", ctx["unsupported"] or "none")
    return (f"Submitted {submitted} question(s). Counters now: {before['correct']} correct, "
            f"{before['wrong']} wrong, {before['unanswered']} unanswered.\n"
            f"Models used: {', '.join(ctx['used'])}. Disputed questions: {disputed or 'none'}. "
            f"Tie-breaks by the strongest model: {ties or 'none'}. Unsupported (left unanswered): {ctx['unsupported'] or 'none'}.")
