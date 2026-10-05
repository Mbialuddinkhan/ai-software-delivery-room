"""TaskBoard's sign-in, used by asdr_auth.sign_in_as when no saved
Playwright state exists. No passwords in the sample."""
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

NAMES = {"member": "Sara", "admin": "Omar"}


def login(driver, base_url: str, role: str) -> None:
    driver.get(base_url + "/")
    driver.find_element(By.ID, "name").send_keys(NAMES[role])
    Select(driver.find_element(By.ID, "role")).select_by_value(role)
    driver.find_element(By.ID, "signin-submit").click()
    WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "board")))
