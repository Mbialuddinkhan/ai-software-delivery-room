# CONTRACT · sprint-01
Status: in-negotiation
## Sprint goal
Ship the booking seam.
## Acceptance criteria
### Happy path
1. Booking a valid slot returns HTTP 200 with a booking id in the body.
2. Substantive size stays in budget: facts:diff.src/booking.ts.net_nonblank <= 120.
### Failure & error handling
1. Booking a taken slot returns HTTP 409 and writes no booking row.
2. The suite reports no failures: facts:tests.failed == 0.
