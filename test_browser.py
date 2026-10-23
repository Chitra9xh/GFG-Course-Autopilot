"""Run: python test_browser.py   (no browser, no network)."""
import os, subprocess, sys, tempfile
from pathlib import Path
import browser
import config


class FakeOptions:
    def __init__(self):
        self.arguments, self.binary_location = [], None

    def add_argument(self, arg):
        self.arguments.append(arg)


# ---- launch options: the headless flag only with --background
plain = browser.build_options(FakeOptions(), None, False)
bg = browser.build_options(FakeOptions(), "/x/chrome", True)
for o in (plain, bg):
    for flag in ("--start-maximized", "--no-first-run", "--no-default-browser-check", "--profile-directory=Default"):
        assert flag in o.arguments, (flag, o.arguments)
    assert any(a.startswith("--user-data-dir=") for a in o.arguments)
    assert not any("user-agent" in a.lower() or "automation" in a.lower() for a in o.arguments), o.arguments   # no disguises
assert "--headless=new" not in plain.arguments and not any(a.startswith("--window-size") for a in plain.arguments)
assert "--headless=new" in bg.arguments
assert "--window-size=%d,%d" % tuple(config.BACKGROUND_WINDOW_SIZE) in bg.arguments
assert plain.binary_location is None and bg.binary_location == "/x/chrome"

# ---- login pre-flight: in background mode a logged-out profile stops instead of asking for a manual login
class FakeDriver:
    def get(self, url):
        pass

real = browser._logged_in
try:
    browser._logged_in = lambda d, t: False
    try:
        browser.ensure_logged_in(FakeDriver(), background=True)
    except browser.SafetyStop as e:
        assert "Log in once without --background" in str(e), e
    else:
        raise AssertionError("background mode must not wait for a manual login")
    browser._logged_in = lambda d, t: True
    browser.ensure_logged_in(FakeDriver(), background=True)     # logged in: no error
finally:
    browser._logged_in = real

# ---- profile in use (Linux/macOS: Chrome's SingletonLock link "host-pid")
if hasattr(os, "symlink") and os.name != "nt":
    with tempfile.TemporaryDirectory() as d:
        lock = Path(d) / "SingletonLock"
        assert browser.profile_in_use(d) is False                              # no lock
        os.symlink(f"host-{os.getpid()}", lock)
        assert browser.profile_in_use(d) is True                               # a live process
        os.unlink(lock)
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        os.symlink(f"host-{p.pid}", lock)
        assert browser.profile_in_use(d) is False                              # stale lock of a finished process
        os.unlink(lock)
        os.symlink("garbage", lock)
        assert browser.profile_in_use(d) is True                               # unreadable lock: be careful
print("test_browser OK")
