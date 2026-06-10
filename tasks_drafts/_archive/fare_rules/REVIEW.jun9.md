# Review sheet — fare_rules

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain fare_rules`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | fare-rules-101 | baseline-pass | Find out if the flight FL999 allows seat upgrades and if there are extra charges. | get_fare_rules |
| KEEP | fare-rules-102 | baseline-pass | Tell me about the rules for changing travel dates on flight FL123. | get_fare_rules |
| KEEP | fare-rules-103 | baseline-pass | Can I get a refund for my ticket on flight FL789? Under what conditions? | get_fare_rules |
| KEEP | fare-rules-104 | baseline-pass | I have a booking with reference BK3X9Z2A. Are seat selections free or is there a charge? | get_fare_rules |
| KEEP | fare-rules-105 | baseline-fail | I need to know if there's a fee for changing flights from New York to London on July 10th. |  |
| KEEP | fare-rules-106 | baseline-pass | Is there any restriction on baggage for flight FL890 scheduled on May 5? | get_fare_rules |
| KEEP | fare-rules-107 | baseline-fail | Please check if I can get a partial refund for canceling my booking with reference LC6V5R0. | get_fare_rules |
| KEEP | fare-rules-108 | baseline-pass | What are the terms for upgrading my seat on flight FL550 to first class? | get_fare_rules |
| KEEP | fare-rules-109 | baseline-pass | On flight FL700, are meals included in the fare or do they cost extra? | get_fare_rules |
| KEEP | fare-rules-110 | baseline-fail | My flight from San Francisco to Tokyo was delayed. Can I change it without additional cost? |  |
