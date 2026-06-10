# Review sheet — disruption

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain disruption`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| DROP | disruption-101 | baseline-fail | My flight from JFK to LAX just got canceled. Could you help me rebook the earliest available flight? | search_flights, modify_booking |
| DROP | disruption-102 | baseline-fail | I need to find out if there's any compensation for my delayed flight AB1234. |  |
| DROP | disruption-103 | baseline-fail | Something came up, and I can't make it to my London trip. Please cancel my hotel reservation. | cancel_booking |
| DROP | disruption-104 | baseline-pass | Can you check which flights are available from Boston to Miami tomorrow morning after my flight got  | search_flights |
| DROP | disruption-105 | baseline-fail | I missed my connection in Chicago. Could you rebook me on the next flight to San Francisco? | search_flights, modify_booking |
| DROP | disruption-106 | baseline-fail | Is there any chance to add priority boarding to my flight to Los Angeles? | add_ancillary |
| DROP | disruption-107 | baseline-fail | I'm not sure if my booking reference is BK3X9Z2A or BK4Y7A6B. Can you verify my passenger details? | validate_passenger |
| DROP | disruption-108 | baseline-fail | What are my options for rebooking after my flight from Paris was canceled? |  |
| DROP | disruption-109 | baseline-fail | My flight from Tokyo to Sydney has been delayed. Can I find out the compensation rules? |  |
| DROP | disruption-110 | baseline-pass | Could you cancel my booking with reference GH8K4J2P? | cancel_booking |
| DROP | disruption-111 | baseline-fail | I'm trying to travel from Seattle to Honolulu, but I need to check availability first. My booking re |  |
| DROP | disruption-112 | baseline-fail | I've just learned my flight got canceled. Could you assist me with rebooking a similar flight to Den | search_flights, modify_booking |
| KEEP | disruption-113 | baseline-pass | Due to a job obligation, I can no longer attend the Chicago conference. Can you cancel my reservatio | cancel_booking |
| KEEP | disruption-114 | baseline-fail | I just found out my flight from Rome got canceled. Could you assist me in finding the next available | search_flights, create_booking |
| KEEP | disruption-115 | baseline-pass | The hotel I'm supposed to stay at in Berlin has overbooked. What's the procedure for securing a comp |  |
| KEEP | disruption-116 | baseline-fail | I missed my flight from San Diego to New York. Can you help me book a different flight? My booking r | search_flights, modify_booking |
| KEEP | disruption-117 | baseline-pass | My flight from Madrid to Lisbon is delayed. Can you provide information on eligibility for compensat |  |
| KEEP | disruption-118 | baseline-fail | Hey, I need to switch my flight from Boston to New York. Could you assist me with the rebooking? The | search_flights, modify_booking |
| KEEP | disruption-119 | baseline-pass | I was supposed to travel from Miami, but my flight was canceled. I don't have the booking ID handy;  |  |
| KEEP | disruption-120 | baseline-fail | Unfortunately, my direct flight from Seattle to Dallas has been canceled. Can you book me a new itin | search_flights, create_booking |

## Near-duplicates auto-marked DROP

- disruption-101 ≈ disruption-101 (cos 0.955)
- disruption-102 ≈ disruption-102 (cos 1.0)
- disruption-103 ≈ disruption-103 (cos 0.953)
- disruption-104 ≈ disruption-104 (cos 1.0)
- disruption-105 ≈ disruption-105 (cos 0.92)
- disruption-106 ≈ disruption-106 (cos 0.955)
- disruption-107 ≈ disruption-107 (cos 1.0)
- disruption-108 ≈ disruption-108 (cos 1.0)
- disruption-109 ≈ disruption-109 (cos 1.0)
- disruption-110 ≈ disruption-110 (cos 1.0)
- disruption-111 ≈ disruption-111 (cos 1.0)
- disruption-112 ≈ disruption-112 (cos 0.951)
