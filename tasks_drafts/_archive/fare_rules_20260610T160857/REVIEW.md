# Review sheet — fare_rules

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain fare_rules`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | fare-rules-111 | baseline-pass | What are the specific restrictions on changing my reservation for flight FL322? | get_fare_rules |
| KEEP | fare-rules-112 | baseline-fail | If I cancel my booking with code RT56YU8, am I eligible for any form of reimbursement? | get_itinerary |
| KEEP | fare-rules-113 | baseline-pass | Can you tell me if I can carry extra baggage on flight FL310 without additional charges? | get_fare_rules |
| KEEP | fare-rules-114 | baseline-fail | What are the cancellation policies for my travel from Los Angeles to Paris on March 15th? |  |
| KEEP | fare-rules-115 | baseline-pass | For flight FL765, what are the terms for making a change to my seat class? | get_fare_rules |
| KEEP | fare-rules-116 | baseline-pass | I need to know if there is a penalty for no-showing my flight from Miami to New York on September 1s |  |
| KEEP | fare-rules-117 | baseline-pass | If I decide to reschedule my flight FL220 to a later date, what will it cost me? | get_fare_rules |
| KEEP | fare-rules-118 | baseline-pass | Can you confirm if passengers are allowed to upgrade classes on flight FL453? Is there an associated | get_fare_rules |
| KEEP | fare-rules-119 | baseline-fail | For my booking with reference MN8J2K4, what are the charges for modifying the flight dates? | get_itinerary |
| KEEP | fare-rules-120 | baseline-pass | I plan to cancel my flight reservation. Could you check if all bookings with reference ZX45PLQ refun | get_itinerary |
