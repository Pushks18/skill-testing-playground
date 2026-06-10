# Review sheet — booking_flow

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain booking_flow`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | booking-flow-123 | baseline-fail | Book flight FL234 for passenger Kevin Hart (DOB 1978-07-06). Confirm once done. | validate_passenger, create_booking, get_itinerary |
| DROP | booking-flow-124 | baseline-pass | Please check if room availability is open for hotel HT213 on 2027-04-10. | check_availability |
| KEEP | booking-flow-125 | baseline-pass | I would like to cancel the booking with reference BK9X0Q2L. | cancel_booking |
| KEEP | booking-flow-126 | baseline-pass | List flights available to Boston from Chicago for 2026-10-14. I need to pick one. |  |
| KEEP | booking-flow-127 | baseline-pass | After verifying Ethan Moore (DOB 1983-11-20, passport F345678), book the hotel HT398 for him from 20 | validate_passenger, create_booking |
| KEEP | booking-flow-128 | baseline-fail | I need a room in Paris for Alice Green from 2027-05-22 to 2027-05-25. Please confirm availability be | search_hotels, create_booking |
| KEEP | booking-flow-129 | baseline-pass | Can you tell me the details of my itinerary for booking reference BK1P2A3Q? | get_itinerary |
| KEEP | booking-flow-130 | baseline-pass | Check the fare rules for flight FL888. | get_fare_rules |
| KEEP | booking-flow-131 | baseline-pass | Please assist in booking a hotel for Bryan Lee in Sydney. I forgot to mention the dates. |  |
| KEEP | booking-flow-132 | baseline-fail | I want to update booking reference BK4P5L7Y to include a late checkout service. | modify_booking |

## Near-duplicates auto-marked DROP

- booking-flow-124 ≈ booking-flow-103 (cos 0.901)
