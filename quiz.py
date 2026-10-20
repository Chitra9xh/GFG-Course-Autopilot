"""Pure logic for the quiz runner. No browser, no network, no google-genai import.
Parsing works on outerHTML (stdlib html.parser); Gemini is reached only through a function
the caller passes in (ask), so everything here is testable offline: python test_quiz.py"""
import json
import re
import textwrap
import time
from collections import Counter
from html.parser import HTMLParser

import config

M = config.MARKERS
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}
IGNORE = {"gfg-tab", "script", "style", "svg"}          # hidden tab label, page chrome
BLOCK = {"p", "div", "li", "ul", "ol", "table", "tr", "td", "th", "blockquote", "section",
         "h1", "h2", "h3", "h4", "h5", "h6", "gfg-panel"}
RETRY, SKIP_MODEL, FATAL = "retry", "skip_model", "fatal"


class QuizError(Exception):
    pass


class ReplyError(QuizError):
    """Gemini's reply is unusable (wrong shape, missing or unknown answers)."""


class FatalApiError(QuizError):
    """Bad key / bad request: switching models cannot help, stop everything."""


class AllModelsFailed(QuizError):
    pass


class Node:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, [(k, v or "") for k, v in attrs])
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, [(k, v or "") for k, v in attrs]))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_tree(html):
    b = _Builder()
    b.feed(html)
    b.close()
    return b.root


def has_class(node, prefix):
    return isinstance(node, Node) and any(c.startswith(prefix) for c in node.classes)


def find_all(node, pred):
    out = []
    for c in node.children:
        if isinstance(c, Node):
            if pred(c):
                out.append(c)
            out.extend(find_all(c, pred))
    return out


def find_class(node, prefix):
    return find_all(node, lambda n: has_class(n, prefix))


def _script(node):
    """<sup>/<sub> -> ^x / _x, so O(n<sup>2</sup>) reaches Gemini as O(n^2), not O(n2)."""
    inner = re.sub(r"\s+", " ", _inline(node)).strip()
    if not inner:
        return ""
    mark = "^" if node.tag == "sup" else "_"
    if re.fullmatch(r"\w+", inner) or (inner.startswith("(") and inner.endswith(")")):
        return mark + inner
    return f"{mark}({inner})"


def _inline(node):
    """All descendant text, <sup>/<sub> converted, <br> as newline, whitespace untouched."""
    parts = []
    for c in node.children:
        if isinstance(c, str):
            parts.append(c)
        elif c.tag in ("sup", "sub"):
            parts.append(_script(c))
        elif c.tag == "br":
            parts.append("\n")
        elif c.tag not in IGNORE and c.tag != "img":
            parts.append(_inline(c))
    return "".join(parts)


class _Text:
    def __init__(self):
        self.out, self.cur, self.notes = [], [], []
        self.panels, self.lang = 0, None

    def flush(self):
        t = re.sub(r"\s+", " ", "".join(self.cur)).strip()
        self.cur = []
        if t:
            self.out.append(t)

    def code(self, node):
        raw = _inline(node).replace("\xa0", " ")
        text = textwrap.dedent("\n".join(l.rstrip() for l in raw.split("\n"))).strip("\n")
        return f"```{self.lang or ''}\n{text}\n```"

    def walk(self, node):
        if isinstance(node, str):
            self.cur.append(node)
            return
        tag = node.tag
        if tag in IGNORE:
            return
        if tag == "img":
            self.notes.append("image")
            return
        if tag == "br":
            self.flush()
            return
        if tag == "pre":
            self.flush()
            self.out.append(self.code(node))
            return
        if tag in ("sup", "sub"):
            self.cur.append(_script(node))
            return
        panel = tag == "gfg-panel"
        if panel:
            self.panels += 1
            if self.panels > 1:                       # only the first code panel is used
                self.notes.append("extra code panel")
                return
            self.lang = node.attrs.get("data-code-lang") or None
        block = tag in BLOCK
        if block:
            self.flush()
        for c in node.children:
            self.walk(c)
        if block:
            self.flush()
        if panel:
            self.lang = None


def render_text(node):
    """Node -> (plain text with ``` fences around code, notes like 'image')."""
    t = _Text()
    t.walk(node)
    t.flush()
    return "\n".join(t.out), t.notes


def _parse_option(el):
    kind = "radio" if has_class(el, M["quiz_radio_class"]) else "unknown"
    texts = find_class(el, M["quiz_option_text_class"])
    text, notes = render_text(texts[0] if texts else el)
    circle = find_class(el, M["quiz_inner_circle_class"])
    return {"kind": kind, "text": text, "notes": notes,
            "selected": kind == "radio" and bool(circle) and not has_class(circle[0], M["quiz_opt_unselected"]),
            "disabled": has_class(el, M["quiz_opt_disabled"]),
            "correct": has_class(el, M["quiz_opt_correct"]),
            "incorrect": has_class(el, M["quiz_opt_incorrect"])}


def parse_question_html(html):
    """outerHTML of the quiz block (one question shown) -> dict:
    number, text, options (dicts with text/selected/...), answered, chosen (index or None),
    correct_index (shown only after a submit), result ('correct'|'incorrect'|None),
    unsupported (list of reasons, empty = we can answer it), notes."""
    root = parse_tree(html)
    cur = find_class(root, M["quiz_current_class"])
    m = re.search(r"\d+", _inline(cur[0])) if cur else None
    bodies = find_class(root, M["quiz_body_class"])
    text, notes = render_text(bodies[0]) if bodies else ("", [])
    choices = find_class(root, M["quiz_choices_class"])
    options = [_parse_option(el) for el in choices[0].children if isinstance(el, Node)] if choices else []
    for o in options:
        notes += o["notes"]
    result = ("correct" if find_class(root, M["quiz_resp_correct"])
              else "incorrect" if find_class(root, M["quiz_resp_incorrect"]) else None)
    answered = result is not None or any(o["disabled"] for o in options)
    reasons = []
    if not text:
        reasons.append("empty question text")
    if "image" in notes:
        reasons.append("contains an image")
    if len(options) < 2:
        reasons.append("fewer than 2 options")
    if any(o["kind"] != "radio" for o in options):
        reasons.append("not a single-choice question")
    idx = lambda key: next((i for i, o in enumerate(options) if o[key]), None)
    return {"number": int(m.group()) if m else None, "text": text, "options": options,
            "answered": answered, "chosen": idx("selected"), "correct_index": idx("correct"),
            "result": result, "unsupported": reasons, "notes": sorted(set(notes))}


def parse_quiz_boxes(html):
    """Sidebar HTML -> {'boxes': [{'n', 'active', 'state'}], 'label_total': N from 'quiz (N)' or None}.
    state is 'correct'/'incorrect'/None; the active box hides its real state, so do not trust it for that."""
    holders = find_class(parse_tree(html), M["quiz_box_container"])
    boxes = []
    for el in (holders[0].children if holders else []):
        if isinstance(el, Node):
            m = re.search(r"\d+", _inline(el))
            boxes.append({"n": int(m.group()) if m else None,
                          "active": M["quiz_box_active"] in el.classes,
                          "state": "correct" if M["quiz_box_correct"] in el.classes
                          else "incorrect" if M["quiz_box_incorrect"] in el.classes else None})
    m = re.search(r"quiz\s*\((\d+)\)", html, re.I)
    return {"boxes": boxes, "label_total": int(m.group(1)) if m else None}


def question_count(info):
    """Number of questions = number of sidebar boxes (never assume 10). Stop on anything odd."""
    nums = [b["n"] for b in info["boxes"]]
    n = len(nums)
    if n == 0:
        raise QuizError("no question boxes found in the sidebar")
    if nums != list(range(1, n + 1)):
        raise QuizError(f"question boxes are not numbered 1..{n}: {nums}")
    if info["label_total"] is not None and info["label_total"] != n:
        raise QuizError(f"sidebar label says {info['label_total']} questions but {n} boxes were found")
    return n


def split_questions(questions):
    """-> (to_answer, done, skipped). skipped = unsupported and unanswered: log each reason, leave it alone."""
    return ([q for q in questions if not q["answered"] and not q["unsupported"]],
            [q for q in questions if q["answered"]],
            [q for q in questions if not q["answered"] and q["unsupported"]])


def build_prompt(questions):
    head = ("You are answering a multiple-choice quiz on programming, data structures and algorithms.\n"
            "Every question has exactly one correct option. Read carefully: some ask which statement is NOT true. "
            "In the text, ^ means an exponent (n^2 is n squared) and _ means a subscript.\n"
            "Reply with ONLY a JSON object that maps each question number to the letter of the correct option, "
            'for example {"1": "B", "2": "A"}. No explanation, no markdown, no other keys. '
            "Answer every question below.")
    blocks = []
    for q in questions:
        opts = "\n".join(f"{LETTERS[i]}) {o['text']}" for i, o in enumerate(q["options"]))
        blocks.append(f"Question {q['number']}:\n{q['text']}\n{opts}")
    return head + "\n\n" + "\n\n".join(blocks) + "\n"


def parse_reply(text, questions):
    """Reply text -> {question number: option index}. Anything not exactly right raises ReplyError; never guesses."""
    s = (text or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S | re.I)
    if m:
        s = m.group(1)
    try:
        data = json.loads(s)
    except ValueError:
        raise ReplyError("reply is not JSON") from None
    if not isinstance(data, dict):
        raise ReplyError("reply is not a JSON object")
    want = {str(q["number"]): q for q in questions}
    if set(data) != set(want):
        raise ReplyError(f"reply keys {sorted(data)} do not match the questions {sorted(want)}")
    out = {}
    for key, q in want.items():
        v = data[key]
        v = v.strip().upper() if isinstance(v, str) else None
        if not v or len(v) != 1 or v not in LETTERS[:len(q["options"])]:
            raise ReplyError(f"question {key}: {data[key]!r} is not one of {LETTERS[:len(q['options'])]}")
        out[q["number"]] = LETTERS.index(v)
    return out


def disputed(passes):
    """Question numbers on which the passes do not all agree."""
    keys = set(passes[0])
    if any(set(p) != keys for p in passes):
        raise QuizError("passes answered different sets of questions")
    return [n for n in passes[0] if len({p[n] for p in passes}) > 1]


def resolve(passes, tiebreak=None):
    """-> (final {number: index}, notes {number: text} for disputed questions only).
    All passes agree = final. Otherwise the clear winner among passes + tiebreak; if the top is tied,
    the tiebreak (strongest model) answer wins."""
    final, notes = {}, {}
    dis = set(disputed(passes))
    for n in passes[0]:
        votes = [p[n] for p in passes]
        if n not in dis:
            final[n] = votes[0]
            continue
        if not tiebreak or n not in tiebreak:
            raise QuizError(f"question {n}: passes disagree {votes} and there is no tiebreak answer")
        votes.append(tiebreak[n])
        ranked = Counter(votes).most_common()
        if ranked[0][1] > ranked[1][1]:
            final[n], how = ranked[0][0], "majority"
        else:
            final[n], how = tiebreak[n], "strongest model"
        notes[n] = f"votes {[LETTERS[v] for v in votes]} -> {LETTERS[final[n]]} ({how})"
    return final, notes


def classify_error(exc):
    """retry (busy, rate limit, network, bad reply) | skip_model (model gone) | fatal (bad key/request, or a bug)."""
    if isinstance(exc, ReplyError):
        return RETRY
    if isinstance(exc, (TypeError, AttributeError, NameError, ImportError, KeyError)):
        return FATAL
    code = getattr(exc, "code", None)
    if code == 404:
        return SKIP_MODEL
    if code in (400, 401, 403):
        return FATAL
    if code is None or code in (408, 429) or (isinstance(code, int) and code >= 500):
        return RETRY
    return FATAL


def backoff_seconds(attempt, base):
    return min(base * 2 ** (attempt - 1), 60)


def model_order(models, k):
    """Order to try for pass k: pass 0 starts at the strongest, pass 1 at the second, ...; the rest follow."""
    if not models:
        return []
    k %= len(models)
    return list(models[k:]) + list(models[:k])


def _scrub(text):
    key = config.GEMINI_API_KEY
    return text.replace(key, "***") if key else text


def ask_with_fallback(ask, models, validate, tries, backoff, sleep=time.sleep, log=None):
    """ask(model) -> reply text; validate(text) -> result or raises ReplyError.
    Tries each model up to `tries` times (waiting between attempts), then the next model.
    Returns (model, result). Raises FatalApiError (stop everything) or AllModelsFailed."""
    log = log or (lambda msg: None)
    last = "no models configured"
    for i, model in enumerate(models):
        for attempt in range(1, tries + 1):
            try:
                return model, validate(ask(model))
            except Exception as exc:
                kind = classify_error(exc)
                last = _scrub(f"{model}: {type(exc).__name__}: {str(exc)[:200]}")
                log(f"{last} -> {kind} (attempt {attempt}/{tries})")
                if kind == FATAL:
                    raise FatalApiError(last) from None
                if kind == SKIP_MODEL:
                    break
                if attempt < tries:
                    sleep(backoff_seconds(attempt, backoff))
        if i + 1 < len(models):
            log(f"{model} unavailable, switching to {models[i + 1]}")
    raise AllModelsFailed(last)


def solve(questions, ask, models, passes, tries, backoff, sleep=time.sleep, log=None):
    """Decide the answers for `questions` (supported, unanswered ones) BEFORE anything is submitted.
    ask(model, prompt) -> reply text. Returns (final {number: index}, notes, models_used)."""
    prompt = build_prompt(questions)
    results, used = [], []
    for k in range(max(1, passes)):
        model, answers = ask_with_fallback(lambda m: ask(m, prompt), model_order(models, k),
                                           lambda t: parse_reply(t, questions), tries, backoff, sleep, log)
        results.append(answers)
        used.append(model)
    dis = disputed(results) if len(results) > 1 else []
    tiebreak = None
    if dis:
        sub = [q for q in questions if q["number"] in dis]
        sub_prompt = build_prompt(sub)
        model, tiebreak = ask_with_fallback(lambda m: ask(m, sub_prompt), model_order(models, 0),
                                            lambda t: parse_reply(t, sub), tries, backoff, sleep, log)
        used.append(model)
    final, notes = resolve(results, tiebreak)
    return final, notes, used
    
    
    
def expected_counters(before, result):
    """Counters after one submit: unanswered -1, and correct or wrong +1."""
    if result not in ("correct", "incorrect"):
        raise QuizError(f"unknown result {result!r}")
    if before["unanswered"] < 1:
        raise QuizError("no unanswered question left to submit")
    after = {k: before[k] for k in ("correct", "wrong", "unanswered")}
    after["unanswered"] -= 1
    after["correct" if result == "correct" else "wrong"] += 1
    return after
