import argparse, logging, sys
import config
import state
from browser import SafetyStop, ensure_logged_in, launch_browser
from scanner import scan_all, scan_items, scan_topics
import plan
import video
import quiz_runner
from quiz import AllModelsFailed, FatalApiError

log = logging.getLogger("main")


def setup_logging():
    (config.BASE_DIR / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(config.BASE_DIR / "logs" / "run.log", encoding="utf-8")],
    )


def table(rows, cols):
    widths = [max(len(h), *(len(str(r[k])) for r in rows)) if rows else len(h) for h, k in cols]
    line = lambda vals: "  ".join(str(v).ljust(w) for v, w in zip(vals, widths))
    print(line([h for h, _ in cols]))
    print(line(["-" * w for w in widths]))
    for r in rows:
        print(line([r[k] for _, k in cols]))

def run_videos(driver, args):
    st = state.load_state()
    topic = next((t for t in st["topics"] if t["slug"] == args.topic), None)
    if topic is None:
        print(f"Topic {args.topic!r} is not in {config.STATE_FILE}. Run  python main.py --scan  first (slugs are in its last column).")
        return
    if topic.get("chapter") not in config.INCLUDE_CHAPTERS:
        print(f"Topic {args.topic!r} is in chapter {topic.get('chapter')}, not in INCLUDE_CHAPTERS {config.INCLUDE_CHAPTERS}. Not touching it.")
        return
    results, summary = [], None
    try:
        summary = video.run_topic(driver, topic, config.PLAYBACK_SPEED, args.limit, lambda: state.save_state(st), results)
    finally:
        if results:
            print()
            table(results, [("#", "n"), ("video", "title"), ("length", "length"), ("from", "from"), ("took", "wall"), ("outcome", "outcome"), ("play retries", "retries"), ("tick", "tick")])
    print(f"\n{summary}")
    
def run_quizzes(driver, args, ask):
    st = state.load_state()
    topic = next((t for t in st["topics"] if t["slug"] == args.topic), None)
    if topic is None:
        print(f"Topic {args.topic!r} is not in {config.STATE_FILE}. Run  python main.py --scan  first (slugs are in its last column).")
        return
    if topic.get("chapter") not in config.INCLUDE_CHAPTERS:
        print(f"Topic {args.topic!r} is in chapter {topic.get('chapter')}, not in INCLUDE_CHAPTERS {config.INCLUDE_CHAPTERS}. Not touching it.")
        return
    rows, summary = [], None
    try:
        if args.dry_run:
            summary = quiz_runner.dry_run(driver, topic, ask, lambda: state.save_state(st), rows)
        else:
            summary = quiz_runner.run_real(driver, topic, ask, lambda: state.save_state(st), rows, args.max_questions)
    finally:
        if rows:
            print()
            table(rows, [("Q", "n"), ("answer", "answer"), ("result", "result"), ("option text", "text"), ("note", "note")])
    print(f"\n{summary}")


def scan_course(driver):
    """Scan the course and save data/state.json; returns the state. Keeps tick_pending marks from the previous state."""
    old = {t["slug"]: t.get("items", []) for t in state.load_state()["topics"]}
    topics = scan_topics(driver)
    st = state.new_state(topics)   # shares the topic dicts, so each save below includes the topics read so far
    state.save_state(st)

    def after_topic(t):
        for title, secs in video.carry_over_pending(old.get(t["slug"], []), t["items"]):
            log.info("Tick for %r has appeared; it had been pending for %.0f s (%.1f min)", title, secs, secs / 60)
        state.save_state(st)

    scan_all(driver, topics, on_topic=after_topic)
    st["complete"] = True
    state.save_state(st)
    return st


def make_confirm(auto_yes):
    """ONE 'type yes' per run, asked before the first quiz submit; --yes skips it."""
    asked = [auto_yes]

    def confirm(count):
        if asked[0]:
            return
        print(f"\nAbout to submit {count} quiz answer(s) for real. Every answer is FINAL (no retake), and the rest of "
              "this run submits answers without asking again.")
        if input("Type yes to start: ").strip().lower() != "yes":
            raise SafetyStop("Start declined at the prompt; nothing was submitted.")
        asked[0] = True
    return confirm


def run_all(driver, args, ask):
    """Scan, then per topic: videos, quiz, log coding problems. Returns the exit code: 0 finished, 2 safety stop or fatal
    API error, 3 unexpected error, 130 Ctrl+C. State is saved after every step, so re-running resumes."""
    st = scan_course(driver)
    todo, completed = plan.order_topics(st["topics"], config.INCLUDE_CHAPTERS)
    later = []
    if args.max_topics:
        todo, later = todo[:args.max_topics], todo[args.max_topics:]
    records = [plan.new_record(t, "skipped", note="already complete") for t in completed]
    log.info("Run plan: %d topic(s) to work on, %d already complete, %d left for later (chapters %s)",
             len(todo), len(completed), len(later), sorted(config.INCLUDE_CHAPTERS))
    confirm, save = make_confirm(args.yes), (lambda: state.save_state(st))
    code, reason, rest = 0, None, later
    for n, t in enumerate(todo, 1):
        print(f"\n=== Topic {n}/{len(todo)}: {t['title']} (chapter {t['chapter']}) ===")
        rec = plan.new_record(t, "stopped")
        records.append(rec)
        results, rows, stats = [], [], {}
        try:
            log.info("Videos: %s", video.run_topic(driver, t, config.PLAYBACK_SPEED, None, save, results))
            log.info("Quiz: %s", quiz_runner.run_real(driver, t, ask, save, rows, None, confirm, stats))
            rec["problems"] = plan.append_problems(t, config.PROBLEMS_LOG)
            rec["status"] = "done"
            notes = ["work left, re-run to continue" if plan.work_left(t) else "", plan.leftovers(t.get("items") or [])]
            rec["note"] = "; ".join(x for x in notes if x)
        except (SafetyStop, FatalApiError, AllModelsFailed) as e:
            code, reason = 2, str(e)
        except KeyboardInterrupt:
            code, reason = 130, "interrupted with Ctrl+C"
        except Exception as e:   # unattended: end cleanly with a summary; state is already saved
            log.exception("Unexpected error in topic %r", t["title"])
            code, reason = 3, f"unexpected {type(e).__name__}: {e}"
        finally:
            rec["videos"] = len(results)
            rec.update(plan.quiz_counts(rows))
            rec["models"] = stats.get("models", [])
        if code:
            rec["note"] = reason[:100]
            rest = todo[n:] + later
            break
    records += [plan.new_record(t, "not reached") for t in rest]
    records.sort(key=lambda r: r["index"])
    print()
    table(plan.summary_rows(records), [("#", "n"), ("topic", "topic"), ("status", "status"), ("videos", "videos"),
                                       ("quiz", "quiz"), ("problems logged", "problems"), ("note", "note")])
    print()
    for line in plan.format_totals(plan.totals(records)):
        print(line)
    if code:
        log.error("STOPPED: %s", reason)
        print(f"\nSTOPPED: {reason}\nFinished work is saved. Run  python3 main.py --run  again to resume.")
    else:
        print(f"\nRun finished. Coding problems are listed in {config.PROBLEMS_LOG}")
    return code
    
    
def main():
    ap = argparse.ArgumentParser(description="GFG Course Autopilot (scan, watch videos, solve quizzes, full run)")
    ap.add_argument("--scan", action="store_true", help="scan the course: open every chapter and sub-category, read all topics and their items, save data/state.json, print a summary")
    ap.add_argument("--topic", metavar="SLUG", help="with --scan: print items of one topic; with --videos: the topic to work on, e.g. recursion-siddhartha")
    ap.add_argument("--videos", action="store_true", help="watch the incomplete videos of --topic in real time at PLAYBACK_SPEED (needs data/state.json from --scan)")
    ap.add_argument("--limit", type=int, metavar="N", help="with --videos: stop after N videos")
    ap.add_argument("--quizzes", action="store_true", help="solve and submit the quiz of --topic (needs data/state.json from --scan); add --dry-run or --max-questions N to submit less")
    ap.add_argument("--dry-run", action="store_true", help="with --quizzes: read and solve, select ONE option, never click Submit")
    ap.add_argument("--max-questions", type=int, metavar="N", help="with --quizzes: submit at most N questions for real, asking you to type yes before each")
    ap.add_argument("--run", action="store_true", help="scan, then work through every topic of INCLUDE_CHAPTERS: videos, then quiz, then log coding problems; partly done topics first, completed ones skipped")
    ap.add_argument("--yes", action="store_true", help="with --run: skip the one 'type yes' before the first quiz submit (answers are FINAL)")
    ap.add_argument("--max-topics", type=int, metavar="N", help="with --run: work on at most N topics, then stop")
    args = ap.parse_args()
    if args.run and (args.scan or args.videos or args.quizzes):
        ap.error("--run cannot be combined with --scan, --videos or --quizzes")
    if args.run and (args.topic or args.limit is not None):
        ap.error("--run works on the whole course; --topic and --limit do not apply")
    if (args.yes or args.max_topics is not None) and not args.run:
        ap.error("--yes and --max-topics only work with --run")
    if args.max_topics is not None and args.max_topics < 1:
        ap.error("--max-topics must be 1 or more")
    if sum([args.scan, args.videos, args.quizzes]) > 1:
        ap.error("use only one of --scan, --videos, --quizzes")
    if (args.videos or args.quizzes) and not args.topic:
        ap.error("--videos and --quizzes need --topic SLUG")
    if (args.dry_run or args.max_questions is not None) and not args.quizzes:
        ap.error("--dry-run and --max-questions only work with --quizzes")
    if args.dry_run and args.max_questions is not None:
        ap.error("use either --dry-run or --max-questions, not both")
    if args.quizzes and args.limit is not None:
        ap.error("--limit applies to --videos only; --quizzes works on one topic")

    if args.max_questions is not None and args.max_questions < 1:
        ap.error("--max-questions must be 1 or more")
    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be 1 or more")
    if not (args.scan or args.videos or args.quizzes or args.run):
        ap.print_help()
        return 0
    setup_logging()
    driver = None
    try:
        ask = quiz_runner.make_ask() if (args.quizzes or args.run) else None
        driver = launch_browser()
        ensure_logged_in(driver)
        if args.run:
            return run_all(driver, args, ask)
        if args.videos:
            run_videos(driver, args)
        elif args.quizzes:
            run_quizzes(driver, args, ask)
        elif args.topic:
            items = scan_items(driver, args.topic)
            for it in items:
                it["done_s"] = {True: "yes", False: "no", None: "?"}[it["done"]]
                it["active_s"] = "<- active" if it["active"] else ""
            table(items, [("#", "index"), ("title", "title"), ("type", "type"), ("done", "done_s"), ("", "active_s")])
        else:
            topics = scan_course(driver)["topics"]
            table(state.summarize(topics), [("#", "index"), ("ch", "chapter"), ("topic", "title"), ("sub-category", "sub_category"),
                                            ("videos", "videos"), ("quizzes", "quizzes"), ("problems", "problems"),
                                            ("other", "other"), ("?tick", "unknown"), ("slug", "slug")])
            print(f"\nItems were read for chapters {sorted(config.INCLUDE_CHAPTERS)} only ('-' = not read). Saved to {config.STATE_FILE}")
        input("\nCompare with the browser window, then press Enter to close... ")
        return 0
    except SafetyStop as e:
        log.error("STOPPED: %s", e)
        print(f"\nSTOPPED: {e}")
        return 2
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    sys.exit(main())
