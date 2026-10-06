# Requirements — TaskBoard

<!-- Sample for the ASDR reference app. Every id below is a testable item:
validate_product_map.py requires a test case for each one, and at the release
gate a passing test must have reached it. -->

## 1. Functional requirements

- FR-01: A person signs in with a name and a role (Team member or Admin); the name is required.
- FR-02: A signed-in person adds a task with a title and a category.
- FR-03: A person marks a task done, or not done again.
- FR-04: The board filters tasks by All, Active and Done.
- FR-05: The board shows a counter of open and done tasks that updates on every change.
- FR-06: Pressing N on the board puts the cursor in the new-task box.
- FR-07: A person exports every task to a CSV file named tasks.csv.
- FR-08: An admin adds task categories; new categories appear in everyone's category menu.
- FR-09: An admin decides whether team members may delete tasks; admins can always delete.
- FR-10: A person signs out; tasks stay on the board for the next sign-in on the same device.
- FR-11: The Settings page and its link are available to admins only.

## 2. Non-functional requirements

- NFR-01: Every control is reachable and usable by keyboard alone and has an accessible name (WCAG 2.1 A/AA, no serious or critical violations).
- NFR-02: The board renders 500 tasks in under 1 second on the reference laptop.

## 3. User stories

- US-01: As a team member, I want to sign in with my name, so that my work is attributed to me.
- US-02: As a team member, I want to add a task quickly, so that nothing gets lost.
- US-03: As a team member, I want to tick tasks off and untick them, so that the board shows what is really done.
- US-04: As a team member, I want to filter by status, so that I see only what matters now.
- US-05: As a team member, I want to export the board, so that I can build the weekly report.
- US-06: As an admin, I want to manage categories, so that tasks are grouped the way we work.
- US-07: As an admin, I want to decide who may delete tasks, so that the board stays tidy without accidents.
- US-08: As anyone, I want to sign out without losing tasks, so that a shared computer is safe to use.

## 4. Acceptance criteria

- AC-01.1: Signing in with a name and a role opens the board and shows the name and role in the top bar.
- AC-01.2: An empty name shows "Please enter your name." and the board does not open.
- AC-01.3: The top bar (Board, Sign out) is hidden until someone signs in.
- AC-02.1: Typing a title, picking a category and clicking Add task lists the task with that category.
- AC-02.2: Pressing Enter in the new-task box adds the task.
- AC-02.3: Pressing N on the board, outside a text box, puts the cursor in the new-task box.
- AC-02.4: An empty or whitespace-only title adds nothing and the counter does not change.
- AC-03.1: Ticking a task crosses it out and moves one from open to done in the counter.
- AC-03.2: Unticking a finished task makes it open again and moves the counter back.
- AC-04.1: Active shows only open tasks.
- AC-04.2: Done shows only finished tasks.
- AC-04.3: All shows every task.
- AC-05.1: Export CSV downloads tasks.csv with the header id, title, category, done and one row per task with its category and done status.
- AC-06.1: A category an admin adds appears in the category list and in a team member's category menu.
- AC-06.2: Team members see no Settings link, and opening the settings address directly does not show the settings page.
- AC-07.1: When "Team members can delete tasks" is on, a team member sees Delete on each task, and deleting removes the task and updates the counter.
- AC-07.2: When it is off, a team member sees no Delete button.
- AC-07.3: An admin always sees Delete, whether or not members may delete.
- AC-07.4: Changing the setting shows "Settings saved.".
- AC-08.1: Sign out returns to the sign-in page.
- AC-08.2: After signing in again on the same device, every task is still there with its status.
- AC-08.3: Reloading the page keeps the tasks.

## 5. Business rules

- BR-01: Only admins can change categories and permissions.
- BR-02: Team members can delete tasks only when an admin has allowed it; admins can always delete.

## 6. Edge cases

- EC-01: An empty or whitespace-only task title adds nothing.
- EC-02: An empty name blocks sign-in with the message "Please enter your name."
