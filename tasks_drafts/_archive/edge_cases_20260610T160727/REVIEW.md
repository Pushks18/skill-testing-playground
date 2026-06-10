# Review sheet — edge_cases

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain edge_cases`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | edge-mixed-101 | baseline-fail | Is there availability on flight DL456 on August 10, 2026? | check_availability |
| KEEP | edge-mixed-102 | baseline-pass | Cancel my booking with reference number BK65432109. | cancel_booking |
| KEEP | edge-mixed-103 | baseline-pass | I want to change my flight on BK89345678 to September 30, 2026. | modify_booking |
| KEEP | edge-mixed-104 | baseline-pass | Book me a flight from Miami to Houston on September 1 and then from Houston to San Francisco on Sept | search_flights |
| KEEP | edge-mixed-105 | baseline-fail | I need more details to check the refund for my reservation BK998877. Can you help? |  |
| KEEP | edge-mixed-106 | baseline-pass | Find flights from LAX to SFO on November 15th, and from SFO to LAS on November 18th. Are there any o | search_flights |
