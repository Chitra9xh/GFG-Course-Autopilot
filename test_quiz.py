"""Run: python test_quiz.py   (no browser, no network, no real key; Gemini is always a fake function)."""
import config
import quiz

# fixtures
R = "QuizRadioBtn_radio_container__aRD4F"


def opt(text_html, selected=False, state=None):
    """state: None (fresh) | 'locked' | 'correct' | 'incorrect' (as after a submit)."""
    cls = R + "   "
    if state:
        cls = R + (" QuizRadioBtn_is_correct__HP985 " if state == "correct" else
                   " QuizRadioBtn_is_incorrect__AYvn9" if state == "incorrect" else "  ") + " QuizRadioBtn_is_disabled__CMFLr"
    inner = "QuizRadioBtn_inner_circle__5N8Kq" if selected else "QuizRadioBtn_unselected_circle__FhFGl QuizRadioBtn_inner_circle__5N8Kq"
    return (f'<div class="{cls}"><div class="QuizRadioBtn_outer_circle__ldyUq"><div class="{inner}"></div></div>'
            f'<div class="QuizRadioBtn_helper_text__7SNt_ hide-codetabs-buttons">{text_html}</div></div>')


def question(num, body_html, options_html, response=None):
    resp = ""
    if response:
        resp = ('<div class="track_response_container__evS66"><p class="track_is_%s_response__x">Your submitted response '
                'was %s.</p></div>' % (response, response))
    return ('<div class="quiz_contents__inner "><div class="track_question_meta__pCS7l"><div><span class="track_question_current__87sy_">'
            f'Question {num}</span></div><div class="ui label">5 marks</div></div><div><div class="track_question_content__H0HtN">'
            f'<div class="track_question_body__h3bjS hide-codetabs-buttons">{body_html}</div></div></div>'
            f'<div class="track_question_choices__tzdro">{"".join(options_html)}</div>{resp}</div>')


# plain question: fresh, option selected, answered correctly
Q_AND = "<p>What is the result of the expression 5 &amp; 3?<br>&nbsp;</p>"
FRESH = question(1, Q_AND, [opt("<p>2</p>"), opt("<p>1</p>"), opt("<p>5</p>"), opt("<p>7</p>")])
SELECTED = question(1, Q_AND, [opt("<p>2</p>"), opt("<p>1</p>", selected=True), opt("<p>5</p>"), opt("<p>7</p>")])
RIGHT = question(1, Q_AND, [opt("<p>2</p>", state="locked"), opt("<p>1</p>", True, "correct"),
                            opt("<p>5</p>", state="locked"), opt("<p>7</p>", state="locked")], "correct")
# <pre> with <sup>, answered wrongly
PRE = ("<p>Which option gives the increasing order of complexity?</p><pre>  f1(n) = 2<sup>n</sup>\n"
       "  f2(n) = n<sup>(3/2)</sup>\n  f3(n) = n*log(n)\n  f4(n) = n<sup>log(n)</sup>\n</pre>")
WRONG = question(4, PRE, [opt("<p>f3, f2, f4, f1</p>", state="correct"), opt("<p>f3, f2, f1, f4</p>", True, "incorrect"),
                          opt("<p>f2, f3, f1, f4</p>", state="locked"), opt("<p>f2, f3, f4, f1</p>", state="locked")], "incorrect")
# options with <sup>
SUP = question(10, '<p dir="ltr"><span>What is the time complexity?&nbsp;</span></p>',
               [opt('<p dir="ltr"><span>O(n)</span></p>'),
                opt('<p dir="ltr"><span>O(n</span><sup><span>2</span></sup><span>)</span></p>'),
                opt('<p dir="ltr"><span>O(n*log(n)</span><sup><span>2</span></sup><span>)</span></p>')])
# code in gfg-tabs: highlighted spans, 4-space indent, a hidden tab label
CODE = ('<p dir="ltr"><span>What does this function return?</span></p><gfg-tabs data-run-ide="false" role="tablist">\n'
        '<gfg-tab slot="tab" hidden="" role="tab" selected="">C++</gfg-tab>\n'
        '<gfg-panel slot="panel" data-code-lang="cpp" role="tabpanel"><code class="language-cpp"><div class="highlight monokai"><pre>'
        '<span></span><span class="n">slow</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="n">head</span>\n'
        '<span class="k">while</span><span class="w"> </span><span class="n">fast</span><span class="p">:</span>\n'
        '<span class="w">    </span><span class="n">slow</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="n">slow</span><span class="p">.</span><span class="n">next</span>\n'
        '</pre></div></code></gfg-panel></gfg-tabs><p><br></p>')
CODEQ = question(5, CODE, [opt('<p dir="ltr"><span>Last node</span></p>'), opt('<p dir="ltr"><span>Middle node</span></p>')])
# unsupported: checkbox options, image in the question
CHECKBOX = ('<div class="quiz_contents__inner "><span class="track_question_current__87sy_">Question 2</span>'
            '<div class="track_question_body__h3bjS"><p>Pick all that apply</p></div><div class="track_question_choices__tzdro">'
            '<div class="QuizCheckbox_box__abc"><div class="QuizCheckbox_text__x"><p>one</p></div></div>'
            '<div class="QuizCheckbox_box__abc"><div class="QuizCheckbox_text__x"><p>two</p></div></div></div></div>')
IMAGEQ = question(3, '<p>What does this show?</p><img src="x.png">', [opt("<p>a</p>"), opt("<p>b</p>")])


def sidebar(classes, label=None):
    boxes = "".join(f'<div class="{c} ">{i}</div>' for i, c in enumerate(classes, 1))
    lab = f"<div>quiz ({label})</div>" if label is not None else ""
    return (f'<div class="sidebar_quiz_questions__CdiiQ"><div class="sidebar_quiz_questions__flex__pZwwT">{boxes}</div></div>{lab}'
            '<p>0 Correct</p><p>0 Wrong</p><p>10 Unanswered</p>')


def q_of(html):
    return quiz.parse_question_html(html)


# text extraction
q = q_of(FRESH)
assert q["number"] == 1 and q["text"] == "What is the result of the expression 5 & 3?", q["text"]
assert [o["text"] for o in q["options"]] == ["2", "1", "5", "7"]
assert not q["answered"] and q["chosen"] is None and q["correct_index"] is None and q["unsupported"] == []

q = q_of(SUP)
assert [o["text"] for o in q["options"]] == ["O(n)", "O(n^2)", "O(n*log(n)^2)"], [o["text"] for o in q["options"]]
assert q["text"] == "What is the time complexity?"

q = q_of(WRONG)
assert q["text"].splitlines() == [
    "Which option gives the increasing order of complexity?", "```", "f1(n) = 2^n", "f2(n) = n^(3/2)",
    "f3(n) = n*log(n)", "f4(n) = n^(log(n))", "```"], q["text"]

q = q_of(CODEQ)
assert q["text"].splitlines() == ["What does this function return?", "```cpp", "slow = head", "while fast:",
                                  "    slow = slow.next", "```"], q["text"]
assert "C++" not in q["text"] and q["unsupported"] == []

# option and answer states
q = q_of(SELECTED)
assert q["chosen"] == 1 and not q["answered"]                      # selected but not submitted
q = q_of(RIGHT)
assert q["answered"] and q["result"] == "correct" and q["chosen"] == 1 and q["correct_index"] == 1
q = q_of(WRONG)
assert q["answered"] and q["result"] == "incorrect" and q["chosen"] == 1 and q["correct_index"] == 0
assert quiz.split_questions([q_of(FRESH), q_of(RIGHT), q_of(CHECKBOX), q_of(IMAGEQ)]) == (
    [q_of(FRESH)], [q_of(RIGHT)], [q_of(CHECKBOX), q_of(IMAGEQ)])

# unsupported questions are logged and left alone
c = q_of(CHECKBOX)
assert c["unsupported"] == ["not a single-choice question"], c["unsupported"]
assert q_of(IMAGEQ)["unsupported"] == ["contains an image"]
assert "empty question text" in q_of("<div></div>")["unsupported"]

# question count from the sidebar
info = quiz.parse_quiz_boxes(sidebar(["is_active"] + [""] * 9, 10))
assert quiz.question_count(info) == 10 and info["boxes"][0]["active"]
partly = ["is_correct", "is_correct", "is_correct", "is_active", "is_incorrect"] + [""] * 7
info = quiz.parse_quiz_boxes(sidebar(partly, 12))
assert quiz.question_count(info) == 12
assert [b["state"] for b in info["boxes"]][:5] == ["correct", "correct", "correct", None, "incorrect"]   # active box hides its state
assert quiz.question_count(quiz.parse_quiz_boxes(sidebar(["is_active", ""], 2))) == 2
assert quiz.question_count(quiz.parse_quiz_boxes(sidebar([""] * 25, None))) == 25
for bad in (sidebar([], 10), sidebar([""] * 9, 10), "<div></div>"):
    try:
        quiz.question_count(quiz.parse_quiz_boxes(bad))
        raise AssertionError("should have stopped")
    except quiz.QuizError:
        pass

# prompt
qs = [q_of(FRESH), q_of(SUP)]
p = quiz.build_prompt(qs)
assert 'Question 1:\nWhat is the result of the expression 5 & 3?\nA) 2\nB) 1\nC) 5\nD) 7' in p
assert "Question 10:" in p and "C) O(n*log(n)^2)" in p and '{"1": "B", "2": "A"}' in p

# reply validation (never guess)
assert quiz.parse_reply('{"1": "B", "10": "c"}', qs) == {1: 1, 10: 2}
assert quiz.parse_reply('```json\n{"1": "B", "10": "A"}\n```', qs) == {1: 1, 10: 0}
for bad in ("not json", "[1, 2]", '{"1": "B"}', '{"1": "B", "10": "A", "2": "A"}', '{"1": "B", "11": "A"}',
            '{"1": "E", "10": "A"}', '{"1": "B", "10": "D"}', '{"1": ["A", "B"], "10": "A"}',
            '{"1": "AB", "10": "A"}', '{"1": 2, "10": "A"}', '{"1": "", "10": "A"}', "", None):
    try:
        quiz.parse_reply(bad, qs)
        raise AssertionError(f"accepted {bad!r}")
    except quiz.ReplyError:
        pass

# double-check
assert quiz.disputed([{1: 0, 2: 1}, {1: 0, 2: 2}]) == [2]
final, notes = quiz.resolve([{1: 0, 2: 1}, {1: 0, 2: 1}])
assert final == {1: 0, 2: 1} and notes == {}
final, notes = quiz.resolve([{1: 0, 2: 1}, {1: 0, 2: 2}], {2: 2})                  # third agrees with pass 2
assert final == {1: 0, 2: 2} and "majority" in notes[2]
final, notes = quiz.resolve([{1: 0, 2: 1}, {1: 0, 2: 2}], {2: 3})                  # all different: strongest model wins
assert final[2] == 3 and "strongest model" in notes[2]
try:
    quiz.resolve([{1: 0}, {1: 1}])
    raise AssertionError("needs a tiebreak")
except quiz.QuizError:
    pass
try:
    quiz.disputed([{1: 0}, {2: 0}])
    raise AssertionError("different questions")
except quiz.QuizError:
    pass

# error classes, model order, backoff
class Err(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg or f"HTTP {code}")
        self.code = code

assert [quiz.classify_error(Err(c)) for c in (503, 429, 500, 408)] == [quiz.RETRY] * 4
assert quiz.classify_error(Err(404)) == quiz.SKIP_MODEL
assert [quiz.classify_error(Err(c)) for c in (400, 401, 403, 418)] == [quiz.FATAL] * 4
assert quiz.classify_error(ConnectionError("reset")) == quiz.RETRY
assert quiz.classify_error(quiz.ReplyError("x")) == quiz.RETRY
assert quiz.classify_error(TypeError("bug")) == quiz.FATAL
assert quiz.model_order(["a", "b", "c"], 0) == ["a", "b", "c"] and quiz.model_order(["a", "b", "c"], 1) == ["b", "c", "a"]
assert quiz.model_order(["a", "b"], 4) == ["a", "b"] and quiz.model_order([], 1) == []
assert [quiz.backoff_seconds(a, 5) for a in (1, 2, 3, 6)] == [5, 10, 20, 60]

# model fallback with a fake Gemini
good = lambda t: t
sleeps, logs = [], []
def run(script, models=("m1", "m2", "m3"), tries=2):
    calls = []
    def ask(model):
        calls.append(model)
        step = script[model].pop(0)
        if isinstance(step, Exception):
            raise step
        return step
    out = quiz.ask_with_fallback(ask, list(models), good, tries, 5, sleeps.append, logs.append)
    return out, calls

(out, calls) = run({"m1": [Err(503), Err(503)], "m2": ["ok"]})                       # busy twice: next model
assert out == ("m2", "ok") and calls == ["m1", "m1", "m2"] and sleeps == [5]
sleeps.clear()
(out, calls) = run({"m1": [Err(503), "ok"]})                                         # busy once: retry same model
assert out == ("m1", "ok") and calls == ["m1", "m1"] and sleeps == [5]
sleeps.clear()
(out, calls) = run({"m1": [Err(404)], "m2": ["ok"]})                                 # model gone: no wait, no retry
assert out == ("m2", "ok") and calls == ["m1", "m2"] and sleeps == []
try:
    run({"m1": [Err(403, "denied")]})                                                # bad key: stop everything
    raise AssertionError("should be fatal")
except quiz.FatalApiError:
    assert calls is not None
try:
    run({"m1": [Err(503)] * 2, "m2": [Err(429)] * 2, "m3": [Err(503)] * 2})
    raise AssertionError("all down")
except quiz.AllModelsFailed as e:
    assert "m3" in str(e)
assert any("switching to m2" in l for l in logs)

config.GEMINI_API_KEY = "fake-key-123"                                               # the key must never leak into messages
try:
    run({"m1": [Err(403, "key fake-key-123 rejected")]})
except quiz.FatalApiError as e:
    assert "fake-key-123" not in str(e) and "***" in str(e)
config.GEMINI_API_KEY = None

# whole decision flow with a fake Gemini
qs = [q_of(FRESH), q_of(SUP)]                      # question 1 (4 options) and question 10 (3 options)
def make_ask(answers):                             # answers: model -> reply texts, used in order
    seen = []
    def ask(model, prompt):
        seen.append((model, prompt))
        return answers[model].pop(0)
    return ask, seen

ask, seen = make_ask({"m1": ['{"1": "B", "10": "B"}'], "m2": ['{"1": "B", "10": "B"}']})   # both agree
final, notes, used = quiz.solve(qs, ask, ["m1", "m2"], 2, 2, 5, sleeps.append)
assert final == {1: 1, 10: 1} and notes == {} and used == ["m1", "m2"] and [s[0] for s in seen] == ["m1", "m2"]

ask, seen = make_ask({"m1": ['{"1": "B", "10": "B"}', '{"10": "B"}'], "m2": ['{"1": "B", "10": "C"}']})
final, notes, used = quiz.solve(qs, ask, ["m1", "m2"], 2, 2, 5, sleeps.append)      # pass 2 differs on question 10
assert final == {1: 1, 10: 1} and 10 in notes and used == ["m1", "m2", "m1"]
assert seen[2][1].count("Question ") == 1 and "Question 10:" in seen[2][1]         # tiebreak asks only the disputed one

ask, seen = make_ask({"m1": ['{"1": "B", "10": "B"}', '{"10": "A"}'], "m2": ['{"1": "B", "10": "C"}']})
final, notes, used = quiz.solve(qs, ask, ["m1", "m2"], 2, 2, 5, sleeps.append)      # all three differ: strongest (m1) wins
assert final[10] == 0 and "strongest model" in notes[10]

ask, seen = make_ask({"m1": ['{"1": "B", "10": "B"}']})                              # passes=1: no double-check
final, notes, used = quiz.solve(qs, ask, ["m1"], 1, 2, 5, sleeps.append)
assert final == {1: 1, 10: 1} and used == ["m1"]

ask, seen = make_ask({"m1": ["sorry, I cannot", '{"1": "B", "10": "B"}']})           # bad reply: retried, not guessed
final, notes, used = quiz.solve(qs, ask, ["m1"], 1, 2, 5, sleeps.append)
assert final == {1: 1, 10: 1} and len(seen) == 2

# expected counters after one submit
b = {"correct": 3, "wrong": 1, "unanswered": 6}
assert quiz.expected_counters(b, "correct") == {"correct": 4, "wrong": 1, "unanswered": 5}
assert quiz.expected_counters(b, "incorrect") == {"correct": 3, "wrong": 2, "unanswered": 5}
for bad_before, bad_result in ((b, "maybe"), ({"correct": 9, "wrong": 1, "unanswered": 0}, "correct")):
    try:
        quiz.expected_counters(bad_before, bad_result)
        raise AssertionError("should have stopped")
    except quiz.QuizError:
        pass

print("test_quiz: all passed")
