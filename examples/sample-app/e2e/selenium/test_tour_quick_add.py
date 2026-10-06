import pytest
from selenium.webdriver.common.by import By

from asdr_cover import covers
from asdr_manual import manual_step
from test_board import sign_in

T = "quick-add"


@pytest.mark.tour
def test_tc_14_tour_quick_add_with_keyboard(driver, base_url):
    sign_in(driver, base_url, "Sara")
    manual_step(driver, T, "board", "Your board after signing in", "#board")
    driver.find_element(By.TAG_NAME, "body").send_keys("n")
    assert driver.switch_to.active_element.get_attribute("id") == "new-task"
    manual_step(driver, T, "press-n", "Press N to jump to the new-task box", "#new-task")
    driver.find_element(By.ID, "new-task").send_keys("Call the caterer\n")
    assert "Call the caterer" in driver.find_element(By.ID, "tasks").text
    covers("AC-02.2", "AC-02.3")
    manual_step(driver, T, "added", "Press Enter to add it", "#tasks")
