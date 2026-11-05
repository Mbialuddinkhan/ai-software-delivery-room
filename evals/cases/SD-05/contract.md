# CONTRACT · sprint-01
Status: in-negotiation
## Sprint goal
Ship the webhook.
## Acceptance criteria
### Failure & error handling
1. The webhook payload must contain the value 3600000 for the hold window.
2. The response body must not match /\d{7,}/ anywhere in the payload.
