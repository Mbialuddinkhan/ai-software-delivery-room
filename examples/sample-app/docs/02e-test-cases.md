# Test Cases — TaskBoard

Written from the process flows before code. Each automated test's title starts with its id.

### TC-01 · New member signs in and adds a first task

- Type: journey
- Flow: PF-01
- Use cases: UC-01, UC-02, UC-03
- Requirements: FR-01, FR-02, FR-03
- Persona: Team member
- Priority: Must
- Preconditions: Empty board; nobody signed in
- Steps:
  1. Open TaskBoard
  2. Enter a name, keep Team member, click Sign in
  3. Type a task, pick a category, click Add task
  4. Tick the task
- Expected result: The task is listed, then crossed out; counter shows "0 open · 1 done"
- Automation: e2e/playwright/tours/member-basics.tour.spec.ts › [TC-01] Member basics: sign in, add and complete a task

### TC-02 · Sign-in without a name is refused

- Type: exception
- Flow: PF-01.E1
- Use cases: UC-01
- Requirements: FR-01
- Persona: Team member
- Priority: Must
- Preconditions: Sign-in page
- Steps:
  1. Leave the name empty
  2. Click Sign in
- Expected result: "Please enter your name." is shown and the board does not open
- Automation: e2e/playwright/board.spec.ts › [TC-02] sign in requires a name

### TC-03 · Member works through the day and comes back

- Type: journey
- Flow: PF-02
- Use cases: UC-02, UC-03, UC-04, UC-08
- Requirements: FR-02, FR-03, FR-04, FR-05, FR-06, FR-10
- Persona: Team member
- Priority: Must
- Preconditions: Signed in, empty board
- Steps:
  1. Press N, type a task, press Enter; add a second task
  2. Tick the first task
  3. Click Active
  4. Sign out, sign in again, click All
- Expected result: Counter goes 2 open → 1 open · 1 done; Active shows one task; after signing back in both tasks are still there
- Automation: e2e/playwright/journeys.spec.ts › [TC-03] member works through the day

### TC-04 · An empty task title adds nothing

- Type: exception
- Flow: PF-02.E1
- Use cases: UC-02
- Requirements: FR-02
- Persona: Team member
- Priority: Must
- Preconditions: Signed in, empty board
- Steps:
  1. Type only spaces in the new-task box
  2. Press Enter
- Expected result: No task is added; counter stays "0 open · 0 done"
- Automation: cypress/e2e/board.cy.js › [TC-04] an empty task title adds nothing

### TC-05 · Admin sets up categories and permissions

- Type: journey
- Flow: PF-03
- Use cases: UC-01, UC-06, UC-07
- Requirements: FR-01, FR-08, FR-09, FR-11
- Persona: Team admin
- Priority: Must
- Preconditions: Nobody signed in
- Steps:
  1. Sign in as Admin
  2. Open Settings
  3. Add the category Design
  4. Tick Team members can delete tasks
  5. Back on the board, add then delete a task
- Expected result: Design is listed; "Settings saved." shows; the deleted task is gone
- Automation: e2e/playwright/tours/admin-settings.tour.spec.ts › [TC-05] Admin: categories and permissions

### TC-06 · A team member cannot reach Settings

- Type: exception
- Flow: PF-03.E1
- Use cases: UC-06
- Requirements: FR-11
- Persona: Team member
- Priority: Must
- Preconditions: Signed in as Team member
- Steps:
  1. Look for a Settings link
  2. Go to #settings directly
- Expected result: No Settings link; the Team settings page is not shown. An admin who signs in does see it
- Automation: e2e/playwright/board.spec.ts › [TC-06] members cannot open settings; admins can

### TC-07 · Member reviews finished work and exports it

- Type: journey
- Flow: PF-04
- Use cases: UC-04, UC-05
- Requirements: FR-04, FR-05, FR-07
- Persona: Team member
- Priority: Should
- Preconditions: Signed in with open and finished tasks
- Steps:
  1. Click Active, then Done
  2. Click Export CSV
- Expected result: Done shows only finished tasks; tasks.csv downloads
- Automation: e2e/playwright/tours/member-advanced.tour.spec.ts › [TC-07] Member advanced: filters, keyboard shortcut and export

### TC-08 · Counter follows every new task

- Type: functional
- Flow: PF-01
- Use cases: UC-02
- Requirements: FR-02, FR-05
- Persona: Team member
- Priority: Must
- Preconditions: Signed in
- Steps:
  1. Add a task
- Expected result: Counter shows "1 open · 0 done"
- Automation: e2e/playwright/board.spec.ts › [TC-08] a member adds a task and the counter updates

### TC-09 · A finished task moves to the Done filter

- Type: functional
- Flow: PF-02
- Use cases: UC-03, UC-04
- Requirements: FR-03, FR-04
- Persona: Team member
- Priority: Must
- Preconditions: Signed in with one task
- Steps:
  1. Tick it
  2. Click Done
- Expected result: The task is listed under Done
- Automation: e2e/playwright/board.spec.ts › [TC-09] a completed task moves to the Done filter

### TC-10 · A new category reaches the task form

- Type: functional
- Flow: PF-03
- Use cases: UC-06
- Requirements: FR-08
- Persona: Team admin
- Priority: Must
- Preconditions: Signed in as Admin
- Steps:
  1. Add the category Design in Settings
  2. Open the board's category menu
- Expected result: Design is an option
- Automation: e2e/playwright/board.spec.ts › [TC-10] a new category appears when adding tasks

### TC-11 · Export contains every task

- Type: functional
- Flow: PF-04
- Use cases: UC-05
- Requirements: FR-07
- Persona: Team member
- Priority: Should
- Preconditions: Signed in with tasks
- Steps:
  1. Click Export CSV
- Expected result: tasks.csv has a header row and one row per task
- Automation: e2e/playwright/board.spec.ts › [TC-11] export downloads a CSV with the tasks

### TC-12 · Tasks survive a page reload

- Type: functional
- Flow: PF-02
- Use cases: UC-08
- Requirements: FR-10
- Persona: Team member
- Priority: Must
- Preconditions: Signed in
- Steps:
  1. Add a task
  2. Reload the page
- Expected result: The task is still listed
- Automation: cypress/e2e/board.cy.js › [TC-12] keeps tasks after a page reload

### TC-13 · The top bar stays hidden until someone signs in

- Type: functional
- Flow: PF-01
- Use cases: UC-01
- Requirements: FR-01
- Persona: Team member
- Priority: Must
- Preconditions: Nobody signed in
- Steps:
  1. Open TaskBoard
  2. Sign in
- Expected result: No Sign out button before sign-in; it appears after
- Automation: e2e/playwright/board.spec.ts › [TC-13] the top bar stays hidden until someone signs in

### TC-14 · N then Enter adds a task without the mouse

- Type: functional
- Flow: PF-02
- Use cases: UC-02
- Requirements: FR-06
- Persona: Team member
- Priority: Should
- Preconditions: Signed in
- Steps:
  1. Press N
  2. Type a task and press Enter
- Expected result: The cursor jumps to the new-task box and the task is listed
- Automation: e2e/selenium/test_tour_quick_add.py › test_tc_14_tour_quick_add_with_keyboard

### TC-15 · Adding a task updates the counter (Selenium)

- Type: functional
- Flow: PF-01
- Use cases: UC-02
- Requirements: FR-02, FR-05
- Persona: Team member
- Priority: Should
- Preconditions: Signed in
- Steps:
  1. Add a task
- Expected result: Counter shows "1 open · 0 done"
- Automation: e2e/selenium/test_board.py › test_tc_15_add_task_updates_counter

### TC-16 · Completing a task moves it to Done (Selenium)

- Type: functional
- Flow: PF-02
- Use cases: UC-03
- Requirements: FR-03
- Persona: Team member
- Priority: Should
- Preconditions: Signed in
- Steps:
  1. Add and tick a task
  2. Click Done
- Expected result: Listed under Done; counter "0 open · 1 done"
- Automation: e2e/selenium/test_board.py › test_tc_16_complete_task_moves_to_done

### TC-17 · Members see no Settings link (Selenium)

- Type: functional
- Flow: PF-03.E1
- Use cases: UC-06
- Requirements: FR-11
- Persona: Team member
- Priority: Should
- Preconditions: Signed in as Team member
- Steps:
  1. Look at the top bar
- Expected result: No Settings link
- Automation: e2e/selenium/test_board.py › test_tc_17_members_cannot_see_settings

### TC-18 · Adding a task updates the counter (Cypress)

- Type: functional
- Flow: PF-01
- Use cases: UC-02
- Requirements: FR-02, FR-05
- Persona: Team member
- Priority: Should
- Preconditions: Signed in
- Steps:
  1. Add a task
- Expected result: Counter shows "1 open · 0 done"
- Automation: cypress/e2e/board.cy.js › [TC-18] adds a task and updates the counter

### TC-19 · Members see no Settings link (Cypress)

- Type: functional
- Flow: PF-03.E1
- Use cases: UC-06
- Requirements: FR-11
- Persona: Team member
- Priority: Should
- Preconditions: Signed in as Team member
- Steps:
  1. Look at the top bar
- Expected result: No Settings link
- Automation: cypress/e2e/board.cy.js › [TC-19] hides settings from members

### TC-20 · Signing out returns to sign-in

- Type: functional
- Flow: PF-02
- Use cases: UC-08
- Requirements: FR-10
- Persona: Team member
- Priority: Must
- Preconditions: Signed in
- Steps:
  1. Check the name in the top bar
  2. Click Sign out
- Expected result: The sign-in form is shown
- Automation: cypress/e2e/account.tour.cy.js › [TC-20] shows who is signed in and signs out

### TC-21 · Key screens meet WCAG 2.1 A/AA

- Type: nfr
- Flow: PF-02
- Use cases: UC-01, UC-02, UC-06
- Requirements: FR-01
- Persona: Team member
- Priority: Must
- Preconditions: Saved logins for member and admin
- Steps:
  1. Open the sign-in page, the board with a finished task, and the settings page
  2. Run the axe-core WCAG 2.1 A/AA rules on each
- Expected result: No critical or serious accessibility violations on any of the three screens (NFR-01)
- Automation: e2e/playwright/a11y.spec.ts › [TC-21] … is accessible

