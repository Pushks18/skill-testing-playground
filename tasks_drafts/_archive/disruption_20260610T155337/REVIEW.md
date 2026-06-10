# Review sheet — disruption

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain disruption`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | disruption-121 | baseline-pass | My flight to Frankfurt got delayed. Can you check if there's compensation? Flight number is FR4567. | get_fare_rules |
| KEEP | disruption-122 | baseline-fail | The connecting flight from Houston to Miami was missed. Could you rebook the earliest possible fligh | search_flights, modify_booking |
| KEEP | disruption-123 | baseline-pass | I need to cancel my hotel reservation in Paris because my flight was canceled. The booking ID is PR5 | cancel_booking |
| KEEP | disruption-124 | baseline-fail | Could you help me find a new flight to Chicago after my original was canceled? It needs to be tomorr |  |
| KEEP | disruption-125 | baseline-fail | Will my flight from Sydney to Auckland, now delayed, be eligible for any sort of reimbursement? | get_fare_rules |
| KEEP | disruption-126 | baseline-pass | I can't make it to my booked flight to Tokyo and need to cancel it. Could you assist? |  |
| DROP | disruption-127 | broken | My family's flight from Orlando to Austin just got canceled. Could you assist in booking a morning f | search_flights, create_booking |
| KEEP | disruption-128 | baseline-fail | The airline overbooked my flight to Los Angeles. What alternatives do I have right now? |  |
| KEEP | disruption-129 | baseline-fail | I missed my connection in Dallas to San Diego. Can you find me a replacement flight? The booking ref | search_flights, modify_booking |
| KEEP | disruption-130 | baseline-fail | My flight from Hamburg to Zurich has been postponed. Could you tell me if I'm eligible for any sort  | get_fare_rules |
