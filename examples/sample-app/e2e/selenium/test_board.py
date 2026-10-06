from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from asdr_a11y import check_a11y
from asdr_auth import sign_in_as
from asdr_cover import covers


def sign_in(driver, base_url, name, role="member"):
    driver.get(base_url + "/")
    driver.execute_script("localStorage.clear()")
    driver.get(base_url + "/")
    driver.find_element(By.ID, "name").send_keys(name)
    Select(driver.find_element(By.ID, "role")).select_by_value(role)
    driver.find_element(By.ID, "signin-submit").click()
    WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "board")))


def test_tc_15_add_task_updates_counter(driver, base_url):
    sign_in(driver, base_url, "Sara")
    driver.find_element(By.ID, "new-task").send_keys("Book venue")
    driver.find_element(By.ID, "add-task").click()
    assert "Book venue" in driver.find_element(By.ID, "tasks").text
    assert driver.find_element(By.ID, "counter").text == "1 open · 0 done"
    check_a11y(driver, "board")
    covers("FR-02", "FR-05")


def test_tc_16_complete_task_moves_to_done(driver, base_url):
    sign_in(driver, base_url, "Sara")
    driver.find_element(By.ID, "new-task").send_keys("Send invites")
    driver.find_element(By.ID, "add-task").click()
    driver.find_element(By.CSS_SELECTOR, '[aria-label="Mark Send invites done"]').click()
    driver.find_element(By.CSS_SELECTOR, '[data-filter="done"]').click()
    assert "Send invites" in driver.find_element(By.ID, "tasks").text
    assert driver.find_element(By.ID, "counter").text == "0 open · 1 done"
    covers("AC-03.1", "AC-04.2")


def test_tc_17_members_cannot_see_settings(driver, base_url):
    # Saved login: reuses the member state the Playwright auth setup saved, if any.
    how = sign_in_as(driver, base_url, "member")
    print(f"saved login: {how}")
    WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "board")))
    assert not driver.find_element(By.ID, "nav-settings").is_displayed()
    covers("AC-06.2", "BR-01")
