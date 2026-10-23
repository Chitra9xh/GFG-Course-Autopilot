import os
import logging
import random
import re
import shutil
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

import config
log = logging.getLogger("browser")


class SafetyStop(Exception):
    """Raised when the script must stop instead of continuing blindly."""


def human_pause():
    time.sleep(random.uniform(config.DELAY_MIN, config.DELAY_MAX))


def find(driver, key):
    return driver.find_elements(*config.SELECTORS[key])


def wait_for(driver, key, timeout=None):
    """Wait until at least one element for SELECTORS[key] exists; return the list."""
    try:
        return WebDriverWait(driver, timeout or config.PAGE_TIMEOUT).until(lambda d: find(d, key) or False)
    except TimeoutException:
        raise SafetyStop(f"Timed out waiting for '{key}' on {driver.current_url} (page changed?)")


def _find_installed_browser():
    """Find an installed Chromium first, then Google Chrome."""


    candidates = [
        (
            "Chromium",
            [
                "chromium",
                "chromium-browser",
            ],
            [
                "/usr/bin/chromium",
                "/snap/bin/chromium",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium-browser",
            ],
        ),
        (
            "Google Chrome",
            [
                "google-chrome",
                "google-chrome-stable",
            ],
            [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/opt/google/chrome/chrome",
            ],
        ),
    ]

    for browser_name, commands, paths in candidates:

        for command in commands:
            executable = shutil.which(command)
            if executable:
                log.info(
                    "Found installed %s: %s",
                    browser_name,
                    executable,
                )
                return Path(executable)


        for candidate in paths:
            path = Path(candidate)
            if path.is_file() and path.stat().st_mode & 0o111:
                log.info(
                    "Found installed %s: %s",
                    browser_name,
                    path,
                )
                return path

    return None


def _find_cached_browser_and_driver():
    """Find a cached Chrome and its matching ChromeDriver."""

    cache = Path.home() / ".cache" / "selenium"
    browser_root = cache / "chrome" / "linux64"
    driver_root = cache / "chromedriver" / "linux64"

    if not browser_root.is_dir() or not driver_root.is_dir():
        return None, None

    def version_key(path):

        return tuple(
            int(part)
            for part in re.findall(r"\d+", path.name)
        )

    browser_versions = sorted(
        (
            path for path in browser_root.iterdir()
            if path.is_dir()
        ),
        key=version_key,
        reverse=True,
    )

    for version_dir in browser_versions:
        browser = version_dir / "chrome"
        driver = driver_root / version_dir.name / "chromedriver"

        if (
            browser.is_file()
            and browser.stat().st_mode & 0o111
            and driver.is_file()
            and driver.stat().st_mode & 0o111
        ):
            log.info(
                "Found cached Chrome and matching ChromeDriver: %s",
                version_dir.name,
            )
            return browser, driver

    return None, None

def build_options(opts, browser_path=None, background=False):
    """Fill a Chrome options object. background=True adds Chrome's new headless mode with an explicit window size.
    Nothing else changes: no user-agent or other disguises."""
    if browser_path is not None:
        opts.binary_location = str(browser_path)

    opts.add_argument(
        f"--user-data-dir={config.CHROME_PROFILE_DIR}"
    )
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")

    if background:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=%d,%d" % tuple(config.BACKGROUND_WINDOW_SIZE))

    return opts


def profile_in_use(profile_dir):
    """True if another Chrome seems to be using this profile (Chrome's SingletonLock link names its process id).
    A lock left behind by a crashed Chrome (process gone) does not count. Linux/macOS only; elsewhere False."""
    lock = Path(profile_dir) / "SingletonLock"
    if not os.path.lexists(lock):
        return False
    try:
        pid = os.readlink(lock).rsplit("-", 1)[-1]
    except OSError:
        return True
    if not pid.isdigit():
        return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def launch_browser(background=False):
    """Launch Chromium first, then Chrome, with a cached Chrome fallback. background=True: no visible window."""

    config.CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    def make_options(browser_path=None):
        return build_options(webdriver.ChromeOptions(), browser_path, background)

    errors = []


    installed_browser = _find_installed_browser()

    if installed_browser is not None:
        try:
            log.info(
                "Launching installed browser: %s",
                installed_browser,
            )
            return webdriver.Chrome(
                options=make_options(installed_browser)
            )
        except WebDriverException as e:
            message = (
                f"Installed browser {installed_browser} failed: {e.msg}"
            )
            errors.append(message)
            log.warning("%s", message)


    cached_browser, cached_driver = (
        _find_cached_browser_and_driver()
    )

    if cached_browser is not None and cached_driver is not None:
        try:
            log.info("Launching cached Chrome: %s", cached_browser)

            service = Service(executable_path=str(cached_driver))

            return webdriver.Chrome(
                service=service,
                options=make_options(cached_browser),
            )
        except WebDriverException as e:
            message = f"Cached Chrome failed: {e.msg}"
            errors.append(message)
            log.warning("%s", message)


    try:
        log.info("Trying Selenium Manager as a final fallback.")
        return webdriver.Chrome(options=make_options())
    except WebDriverException as e:
        errors.append(f"Selenium Manager failed: {e.msg}")

    details = "\n".join(errors)

    raise SafetyStop(
        "Could not start Chromium or Chrome. "
        f"Close any browser using {config.CHROME_PROFILE_DIR}. "
        f"Attempts:\n{details[:1500]}"
    )


def _logged_in(driver, timeout):
    try:
        WebDriverWait(driver, timeout).until(lambda d: find(d, "logged_in") or False)
        return True
    except TimeoutException:
        return False


def ensure_logged_in(driver, background=False):
    driver.get(config.COURSE_URL)
    if _logged_in(driver, 10):
        log.info("Logged in (profile: %s)", config.CHROME_PROFILE_DIR)
        return
    if background:
        raise SafetyStop("Not logged in. Log in once without --background, then run again.")
    log.warning("Not logged in. Log in by hand in the Chrome window.")
    input(">>> Finish logging in, then press Enter here to continue... ")
    driver.get(config.COURSE_URL)
    if not _logged_in(driver, 15):
        raise SafetyStop("Still logged out after manual login pause.")
    log.info("Login confirmed.")


def check_safe_page(driver):
    """Call before every major action. Raises SafetyStop on CAPTCHA / logged-out / wrong page."""
    url = driver.current_url
    if not url.startswith(config.COURSE_URL):
        raise SafetyStop(f"Unexpected page: {url}")
    captcha = config.SELECTORS.get("captcha")
    if captcha and any(e.is_displayed() for e in driver.find_elements(*captcha)):
        raise SafetyStop("CAPTCHA detected - solve it by hand, then re-run.")
    if not _logged_in(driver, 10):
        raise SafetyStop("Logged-out state detected.")
