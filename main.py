import argparse, logging, sys
import config
import state
from browser import SafetyStop, ensure_logged_in, launch_browser
from scanner import scan_all, scan_items, scan_topics
import video
import quiz_runner

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

def main():
    ap = argparse.ArgumentParser(description="GFG Course Autopilot (scan, watch videos)")
    ap.add_argument("--scan", action="store_true", help="scan the course: open every chapter and sub-category, read all topics and their items, save data/state.json, print a summary")
    ap.add_argument("--topic", metavar="SLUG", help="with --scan: print items of one topic; with --videos: the topic to work on, e.g. recursion-siddhartha")
    ap.add_argument("--videos", action="store_true", help="watch the incomplete videos of --topic in real time at PLAYBACK_SPEED (needs data/state.json from --scan)")
    ap.add_argument("--limit", type=int, metavar="N", help="with --videos: stop after N videos")
    ap.add_argument("--quizzes", action="store_true", help="solve and submit the quiz of --topic (needs data/state.json from --scan); add --dry-run or --max-questions N to submit less")
    ap.add_argument("--dry-run", action="store_true", help="with --quizzes: read and solve, select ONE option, never click Submit")
    ap.add_argument("--max-questions", type=int, metavar="N", help="with --quizzes: submit at most N questions for real, asking you to type yes before each")
    args = ap.parse_args()
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
    if not (args.scan or args.videos or args.quizzes):
        ap.print_help()
        return 0
    setup_logging()
    driver = None
    try:
        ask = quiz_runner.make_ask() if args.quizzes else None
        driver = launch_browser()
        ensure_logged_in(driver)
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
            topics = scan_topics(driver)
            st = state.new_state(topics)   # shares the topic dicts, so each save below includes the topics read so far
            state.save_state(st)
            scan_all(driver, topics, on_topic=lambda t: state.save_state(st))
            st["complete"] = True
            state.save_state(st)
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
