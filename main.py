import argparse, logging, sys
import config
import state
from browser import SafetyStop, ensure_logged_in, launch_browser
from scanner import scan_all, scan_items, scan_topics

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


def main():
    ap = argparse.ArgumentParser(description="GFG Course Autopilot (Phase 1: scan only)")
    ap.add_argument("--scan", action="store_true", help="scan the course: open every chapter and sub-category, read all topics and their items, save data/state.json, print a summary")
    ap.add_argument("--topic", metavar="SLUG", help="with --scan: print items of one topic, e.g. recursion-siddhartha")
    args = ap.parse_args()
    if not args.scan:
        ap.print_help()
        return 0
    setup_logging()
    driver = None
    try:
        driver = launch_browser()
        ensure_logged_in(driver)
        if args.topic:
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
