# Review sheet — booking_flow

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain booking_flow`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | booking-flow-133 | baseline-pass | Can you confirm if there are flights available from Los Angeles to Miami on 2026-12-10? | search_flights |
| KEEP | booking-flow-134 | baseline-pass | Please reserve hotel HT678 for Mike Watson from 2027-04-01 to 2027-04-07 and add breakfast service. | create_booking, add_ancillary |
| DROP | booking-flow-135 | baseline-pass | Could you inform me of the itinerary details for booking reference BK3X9Z2A? | get_itinerary |
| KEEP | booking-flow-136 | baseline-fail | I need to book a flight for Robert Thompson from London to Rome. I don't have the flight ID. |  |
| KEEP | booking-flow-137 | baseline-fail | Add premium seating to the booking with reference BK7U3R4P. | modify_booking |
| KEEP | booking-flow-138 | baseline-fail | Reserve a hotel in Barcelona for Laura Kim from 2027-07-10 to 2027-07-15 after checking availability | search_hotels, create_booking |
| KEEP | booking-flow-139 | baseline-fail | Ensure a booking for David Wheeler on flight FL543 leaving on 2027-02-15. | create_booking |
| KEEP | booking-flow-140 | baseline-fail | I need to verify if flights are available from Paris to Tokyo on 2027-05-05 with no specific passeng |  |
| KEEP | booking-flow-141 | baseline-pass | Cancel the current booking with reference BK6L3Q5T due to a schedule change. | cancel_booking |
| KEEP | booking-flow-142 | baseline-pass | Please reserve a hotel in New York City for Sam Harris from 2026-11-20 to 2026-11-25 without a speci |  |

## Near-duplicates auto-marked DROP

- booking-flow-135 ≈ booking-flow-111 (cos 0.926)
