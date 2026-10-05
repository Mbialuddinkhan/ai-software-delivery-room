# Use-Case Catalogue — TaskBoard

### UC-01 · Sign in

- Primary actor: Team member or Team admin
- Goal: get onto the team board under my own name
- Main flow: 1. Opens TaskBoard 2. Enters name and role 3. Clicks Sign in 4. Sees the board
- Alternate / exception flows: E1: name empty → "Please enter your name."
- Linked requirements: FR-01
- Linked outcome: O-01

### UC-02 · Add a task

- Primary actor: Team member
- Goal: record something that needs doing
- Main flow: 1. Types a title (or presses N first) 2. Picks a category 3. Clicks Add task or presses Enter
- Alternate / exception flows: E1: empty title → nothing is added
- Linked requirements: FR-02, FR-06
- Linked outcome: O-01

### UC-03 · Complete a task

- Primary actor: Team member
- Goal: show the team a task is finished
- Main flow: 1. Ticks the task's box 2. The task is crossed out and the counter updates
- Linked requirements: FR-03, FR-05
- Linked outcome: O-01

### UC-04 · Find tasks by status

- Primary actor: Team member
- Goal: see only what is left, or only what is finished
- Main flow: 1. Clicks Active or Done 2. The list and counter reflect the filter
- Linked requirements: FR-04, FR-05
- Linked outcome: O-02

### UC-05 · Export tasks

- Primary actor: Team member
- Goal: take the task list into a spreadsheet
- Main flow: 1. Clicks Export CSV 2. tasks.csv downloads
- Linked requirements: FR-07
- Linked outcome: O-02

### UC-06 · Manage categories

- Primary actor: Team admin
- Goal: give the team categories that match how it works
- Main flow: 1. Opens Settings 2. Types a category name 3. Clicks Add category
- Alternate / exception flows: E1: a team member cannot see or open Settings
- Linked requirements: FR-08, FR-11
- Linked outcome: O-03

### UC-07 · Control who can delete tasks

- Primary actor: Team admin
- Goal: decide who may remove tasks, and tidy the board
- Main flow: 1. Ticks "Team members can delete tasks" 2. Sees "Settings saved." 3. Deletes a task
- Linked requirements: FR-09
- Linked outcome: O-03

### UC-08 · Sign out

- Primary actor: Team member or Team admin
- Goal: leave a shared computer safely without losing the board
- Main flow: 1. Clicks Sign out 2. Sees the sign-in page 3. Tasks are still there next time
- Linked requirements: FR-10
- Linked outcome: O-01
