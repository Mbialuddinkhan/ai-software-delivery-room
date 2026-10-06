# Feature List — TaskBoard

## Summary

| ID | Feature | Persona(s) | Priority | Release | Flows | Use cases | Requirements | Affects |
|---|---|---|---|---|---|---|---|---|
| F-01 | Sign-in with roles | Team member, Team admin | Must | MVP | PF-01, PF-03 | UC-01 | FR-01, FR-11 | — |
| F-02 | Task capture | Team member | Must | MVP | PF-01, PF-02 | UC-02 | FR-02, FR-06 | — |
| F-03 | Completion and counter | Team member | Must | MVP | PF-02 | UC-03 | FR-03, FR-05 | — |
| F-04 | Status filters | Team member | Should | MVP | PF-02, PF-04 | UC-04 | FR-04, FR-05 | — |
| F-05 | CSV export | Team member | Should | MVP | PF-04 | UC-05 | FR-07 | — |
| F-06 | Category management | Team admin, Team member | Must | MVP | PF-03, PF-01 | UC-06 | FR-08, FR-11 | Team member |
| F-07 | Delete permission | Team admin, Team member | Should | MVP | PF-03, PF-05 | UC-07 | FR-09 | Team member (on/off) |
| F-08 | Sign-out with saved board | Team member, Team admin | Must | MVP | PF-02 | UC-08 | FR-10 | — |

## Feature detail

### F-01 · Sign-in with roles

- Problem it solves: the team needs to know who added or finished each task, and only some people should change settings
- Who uses it: everyone, once per session
- Value: work on the board is attributed, and settings are protected
- In scope: name + role; admin-only Settings
- Out of scope: passwords and accounts (a later release)
- Where it sits in the journey: PF-01.1–PF-01.2, PF-03.1
- Success measure: 95% of first visits reach the board within 30 seconds
- Dependencies: none
- Open questions: none

### F-02 · Task capture

- Problem it solves: tasks live in chat threads and get lost
- Who uses it: team members, several times a day
- Value: a task is on the shared board within seconds of thinking of it
- In scope: title, category, N shortcut, Enter to add
- Out of scope: due dates, assignees
- Where it sits in the journey: PF-01.3, PF-02.1–PF-02.2
- Success measure: median time from pressing N to task added under 5 seconds
- Dependencies: F-01
- Open questions: none

### F-03 · Completion and counter

- Problem it solves: nobody knows what is finished
- Who uses it: team members, daily
- Value: one glance shows open versus done
- In scope: tick and untick, live counter
- Out of scope: completion history
- Where it sits in the journey: PF-02.3
- Success measure: counter matches the list in 100% of automated checks
- Dependencies: F-02
- Open questions: none

### F-04 · Status filters

- Problem it solves: long boards hide what is left to do
- Who uses it: team members, daily; weekly for round-ups
- Value: focus on open work, or review finished work
- In scope: All, Active, Done
- Out of scope: search, filter by category
- Where it sits in the journey: PF-02.4, PF-04.1
- Success measure: filter switch under 100 ms with 500 tasks
- Dependencies: F-03
- Open questions: none

### F-05 · CSV export

- Problem it solves: the weekly report is built by hand
- Who uses it: team members, weekly
- Value: the round-up starts from a spreadsheet, not a blank page
- In scope: all tasks with title, category and status
- Out of scope: scheduled exports
- Where it sits in the journey: PF-04.2
- Success measure: tasks.csv opens in Excel, Numbers and Google Sheets without edits
- Dependencies: F-02
- Open questions: none

### F-06 · Category management

- Problem it solves: one "General" bucket does not match how the team works
- Who uses it: the team admin, at set-up and occasionally after
- Value: tasks are grouped the way the team thinks
- In scope: add categories
- Out of scope: rename and delete categories
- Where it sits in the journey: PF-03.2–PF-03.3 (admin), PF-01.3 (a team member picks the category)
- Success measure: a new category appears in members' menu with no reload
- Dependencies: F-01
- Open questions: none

### F-07 · Delete permission

- Problem it solves: stale and duplicate tasks clutter the board, but not every team wants everyone deleting
- Who uses it: the team admin
- Value: the admin chooses tidiness or safety
- In scope: one switch; admins can always delete
- Out of scope: undo
- Where it sits in the journey: PF-03.4–PF-03.5 (admin), PF-05.1–PF-05.2 (team member)
- Success measure: "Settings saved." shown within 1 second of the change
- Dependencies: F-06
- Open questions: none

### F-08 · Sign-out with saved board

- Problem it solves: shared computers, and fear of losing the list
- Who uses it: everyone, at the end of a session
- Value: safe to sign out; the board is still there tomorrow
- In scope: sign out; tasks kept on the device
- Out of scope: sync between devices
- Where it sits in the journey: PF-02.5
- Success measure: 100% of tasks present after sign-out and sign-in in automated checks
- Dependencies: F-01
- Open questions: none
