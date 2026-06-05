# Review sheet — disruption

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain disruption`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | disruption-101 | baseline-fail | My flight from JFK to LAX just got canceled. Could you help me rebook the earliest available flight? | search_flights, modify_booking |
| KEEP | disruption-102 | baseline-pass | I need to find out if there's any compensation for my delayed flight AB1234. |  |
| KEEP | disruption-103 | baseline-fail | Something came up, and I can't make it to my London trip. Please cancel my hotel reservation. | cancel_booking |
| KEEP | disruption-104 | baseline-pass | Can you check which flights are available from Boston to Miami tomorrow morning after my flight got  | search_flights |
| KEEP | disruption-105 | baseline-fail | I missed my connection in Chicago. Could you rebook me on the next flight to San Francisco? | search_flights, modify_booking |
| KEEP | disruption-106 | baseline-fail | Is there any chance to add priority boarding to my flight to Los Angeles? | add_ancillary |
| KEEP | disruption-107 | baseline-fail | I'm not sure if my booking reference is BK3X9Z2A or BK4Y7A6B. Can you verify my passenger details? | validate_passenger |
| KEEP | disruption-108 | baseline-fail | What are my options for rebooking after my flight from Paris was canceled? |  |
| KEEP | disruption-109 | baseline-fail | My flight from Tokyo to Sydney has been delayed. Can I find out the compensation rules? |  |
| KEEP | disruption-110 | baseline-pass | Could you cancel my booking with reference GH8K4J2P? | cancel_booking |
| KEEP | disruption-111 | baseline-fail | I'm trying to travel from Seattle to Honolulu, but I need to check availability first. My booking re |  |
| KEEP | disruption-112 | baseline-fail | I've just learned my flight got canceled. Could you assist me with rebooking a similar flight to Den | search_flights, modify_booking |
