import logging, random, time
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
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


def launch_browser():
    config.CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    opts = webdriver.ChromeOptions()
    opts.add_argument(f"--user-data-dir={config.CHROME_PROFILE_DIR}")
    opts.add_argument("--start-maximized")
    try:
        return webdriver.Chrome(options=opts)   # Selenium Manager fetches the driver
    except WebDriverException as e:
        raise SafetyStop(f"Chrome failed to start (close any Chrome using {config.CHROME_PROFILE_DIR}): {e.msg[:200]}")


def _logged_in(driver, timeout):
    try:
        WebDriverWait(driver, timeout).until(lambda d: find(d, "logged_in") or False)
        return True
    except TimeoutException:
        return False


def ensure_logged_in(driver):
    driver.get(config.COURSE_URL)
    if _logged_in(driver, 10):
        log.info("Logged in (profile: %s)", config.CHROME_PROFILE_DIR)
        return
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
