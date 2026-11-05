# CONTRACT · sprint-02 (ratified)
## Sprint goal
Staff can edit FAQ answers.
## Acceptance criteria
### Happy path
1. GET /admin/faq returns the clinic's FAQ as JSON for a signed-in staff user.
2. POST /admin/faq updates one answer and the change is visible on the next GET.
### Failure & error handling
3. POST /admin/faq without a session token returns HTTP 401.
