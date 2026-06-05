# Review sheet — booking_flow

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain booking_flow`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | booking-flow-101 | baseline-fail | Verify passenger Lisa Wong (DOB 1993-02-11, passport B9876543) and proceed to book flight FL876. | validate_passenger, create_booking |
| KEEP | booking-flow-102 | baseline-fail | Can you assist in booking hotel HT987 for John Doe? Arrival on 2026-10-05, departure on 2026-10-07. | create_booking |
| KEEP | booking-flow-103 | baseline-fail | Is room availability open for hotel HT342 on 2027-01-15? | check_availability |
| KEEP | booking-flow-104 | baseline-fail | Please add a meal plan to the booking ref BK1Y8Z5C. | add_ancillary |
| KEEP | booking-flow-105 | baseline-pass | Look for flights to Tokyo on 2026-12-01. | search_flights |
| KEEP | booking-flow-106 | baseline-fail | Cancel the booking for reference BK5D9F3Q due to unexpected circumstances. | cancel_booking |
| KEEP | booking-flow-107 | baseline-fail | I need a list of rules associated with fare code FC302. | get_fare_rules |
| KEEP | booking-flow-108 | baseline-fail | After verifying Mia Cheng (DOB 1995-09-25, passport C3456789), book hotel HT654 for 2026-10-02 to 20 | validate_passenger, create_booking |
| KEEP | booking-flow-109 | baseline-fail | I want to reserve flight FL101 for Jane Roe, with her birth date 1987-04-17. |  |
| KEEP | booking-flow-110 | baseline-fail | Check if any double rooms are open for hotel HT123 on 2026-11-05 and confirm for Mark Twain (DOB 196 | check_availability, create_booking |
| KEEP | booking-flow-111 | baseline-fail | Get the details of the itinerary for booking reference BK7X6Z5R. | get_itinerary |
| KEEP | booking-flow-112 | baseline-pass | Reserve a flight for Emily Carter to Paris without specifying a date. |  |
