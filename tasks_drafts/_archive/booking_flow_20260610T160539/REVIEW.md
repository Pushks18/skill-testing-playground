# Review sheet — booking_flow

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain booking_flow`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | booking-flow-148 | baseline-fail | Check if there are available flights from Miami to San Francisco on 2026-10-20 and inform me of the  | search_flights |
| KEEP | booking-flow-149 | baseline-fail | I'd like to book the hotel HT202 for Jessica Ray (DOB 1972-05-10) from 2027-03-01 to 2027-03-05. Ver | validate_passenger, create_booking |
| KEEP | booking-flow-150 | baseline-pass | I need to cancel my reservation with reference BK5T4N2Q. | cancel_booking |
| KEEP | booking-flow-151 | baseline-pass | See if there's room availability at hotel HT560 from 2027-02-25 to 2027-03-01, and if it’s open, con | check_availability, create_booking |
| KEEP | booking-flow-152 | baseline-fail | Could you tell me if flights are accessible from New York City to Toronto on 2026-08-15? Include fli | search_flights |
| KEEP | booking-flow-153 | baseline-fail | Please update my booking to include airport transfer service for reference BK8X3Y6P. | modify_booking |
| KEEP | booking-flow-154 | baseline-pass | Book flight FL654 for passenger Mia Williams. What's her date of birth? |  |
| KEEP | booking-flow-155 | baseline-fail | Reserve a flight to New Orleans for Andrew Clark on 2026-12-24. Let me know if we need more details. |  |
