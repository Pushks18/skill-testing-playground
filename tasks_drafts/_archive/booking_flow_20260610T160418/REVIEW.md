# Review sheet — booking_flow

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain booking_flow`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | booking-flow-143 | baseline-fail | Can you please check if there are any flights from San Diego to Seattle on 2026-10-07? | search_flights |
| KEEP | booking-flow-144 | baseline-fail | I'd like to add an extra baggage service to my booking with reference BK4N2K5J. | add_ancillary |
| KEEP | booking-flow-145 | baseline-pass | Reserve a hotel in Tokyo for Amanda Lee from 2027-06-10 to 2027-06-15 after ensuring availability. | search_hotels, create_booking |
| DROP | booking-flow-146 | baseline-pass | I want to cancel my booking with reference BK3X9Z2A due to a personal emergency. | cancel_booking |
| KEEP | booking-flow-147 | baseline-fail | Can you book a flight from Munich to Vienna for tomorrow? I need the flight ID. |  |

## Near-duplicates auto-marked DROP

- booking-flow-146 ≈ booking-flow-125 (cos 0.906)
