# Review sheet — fare_rules

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain fare_rules`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | fare-rules-121 | baseline-pass | I'm thinking of switching my flight FL456 to a later date. What are the fees involved for this chang | get_fare_rules |
| KEEP | fare-rules-122 | baseline-pass | Can you tell me if booking PL56TY3 allows cancellations and what the associated penalties might be? | get_fare_rules |
| KEEP | fare-rules-123 | baseline-fail | I've booked a flight from London to Rome on June 20th. Will I need to pay for checked luggage? | get_fare_rules, search_flights |
| KEEP | fare-rules-124 | baseline-pass | What's the upgrade policy for my seat on flight AL320 from New York to Los Angeles? | get_fare_rules |
| KEEP | fare-rules-125 | baseline-fail | I need to understand the conditions for changing my itinerary with reference KO9L5J8. What steps sho |  |
| KEEP | fare-rules-126 | baseline-pass | Let me know if there is any fee for carrying extra hand luggage on flight FL222. | get_fare_rules |
| KEEP | fare-rules-127 | baseline-pass | If I don't show up for flight CA123 from Chicago to Boston on August 15th, will I be charged a no-sh | get_fare_rules |
| KEEP | fare-rules-128 | baseline-fail | What are the baggage restrictions for my upcoming trip with booking code GH54HY7? Please check for a |  |
| KEEP | fare-rules-129 | baseline-pass | My flight JE890 from Toronto to Paris was rescheduled. Can I request a refund if the new date doesn' | get_fare_rules |
| KEEP | fare-rules-130 | baseline-pass | Please find out if flight KT777 includes complimentary meals or if they come at an additional expens | get_fare_rules |
