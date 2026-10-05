# Requirements — TaskBoard

<!-- Sample for the ASDR reference app. Shortened: a real project fills every template section. -->

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

- NFR-01: Every control is reachable by keyboard and has an accessible name.
- NFR-02: The board renders 500 tasks in under 1 second on the reference laptop.

## 6. Edge cases

- EC-01: An empty or whitespace-only task title adds nothing.
- EC-02: An empty name blocks sign-in with the message "Please enter your name."
