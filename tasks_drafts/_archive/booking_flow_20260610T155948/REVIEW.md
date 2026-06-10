# Review sheet — booking_flow

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain booking_flow`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | booking-flow-113 | baseline-pass | Can you cancel the booking with reference BK2P6N4R for me? | cancel_booking |
| KEEP | booking-flow-114 | baseline-fail | Check if there are flights available to Madrid from New York for 2026-11-20. | search_flights |
| KEEP | booking-flow-115 | baseline-pass | I need to validate passenger Robert Green (DOB 1980-07-23, passport D2345678) and book the flight FL | validate_passenger, create_booking |
| KEEP | booking-flow-116 | baseline-fail | Reserve a hotel in Berlin for Anna Lee but make sure it's available first for the dates 2026-06-01 t | search_hotels, create_booking |
| DROP | booking-flow-117 | baseline-pass | Look up the itinerary for booking reference BK4Y7Z6B. | get_itinerary |
| KEEP | booking-flow-118 | baseline-pass | Can you book a flight to Dubai for Sandra Boehm? I forgot to provide the date. |  |
| KEEP | booking-flow-119 | baseline-fail | Ensure a flight booking for Martin Woods. I need to know which flight ID to use. |  |
| KEEP | booking-flow-120 | baseline-pass | Please fetch the fare rules for flight FL111. | get_fare_rules |
| KEEP | booking-flow-121 | baseline-pass | Look up hotels in San Francisco from 2027-03-15 to 2027-03-20 for 2 guests. | search_hotels |
| KEEP | booking-flow-122 | baseline-fail | Update booking reference BK8M5R9A to include a gym access service. | add_ancillary |

## Near-duplicates auto-marked DROP

- booking-flow-117 ≈ booking-flow-111 (cos 0.922)
