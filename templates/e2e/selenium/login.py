"""PROJECT-SPECIFIC (devops fills this in): how a person in each test role signs
in, for when no saved Playwright state exists. Credentials come from
ASDR_USER_<ROLE> / ASDR_PASS_<ROLE> — test users the seed step creates."""
import os

from selenium.webdriver.common.by import By


def login(driver, base_url: str, role: str) -> None:
    key = role.upper()
    user, pw = os.environ.get(f"ASDR_USER_{key}"), os.environ.get(f"ASDR_PASS_{key}")
    if not user or not pw:
        raise RuntimeError(f"Set ASDR_USER_{key} and ASDR_PASS_{key}: the seed step creates these test users")
    driver.get(base_url + "/login")                                  # <- your sign-in page
    driver.find_element(By.NAME, "email").send_keys(user)            # <- your fields
    driver.find_element(By.NAME, "password").send_keys(pw)
    driver.find_element(By.XPATH, "//button[normalize-space()='Sign in']").click()
