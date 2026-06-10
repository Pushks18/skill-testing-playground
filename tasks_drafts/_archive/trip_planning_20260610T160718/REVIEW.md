# Review sheet — trip_planning

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain trip_planning`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | planning-132 | baseline-fail | I'd love to experience the vibrant city life in Tokyo for a week. I'll be departing from Vancouver a | search_flights, search_hotels |
| KEEP | planning-133 | baseline-fail | Can you plan a cultural and historical tour for me in Egypt, starting from Cairo in January 2027? |  |
| KEEP | planning-134 | baseline-fail | I need to travel from Zurich to Geneva for a business meeting on January 18, 2027, and return the ne | search_flights, search_hotels, create_booking |
| KEEP | planning-135 | baseline-fail | I'm planning a romantic weekend trip with my partner to Venice at the end of February 2027. Departin | search_flights, search_hotels |
| KEEP | planning-136 | baseline-pass | I want to book a family trip to Cape Town for a wildlife safari, but I haven't decided on a specific |  |
| KEEP | planning-137 | baseline-fail | I'm attending a wedding in Cape Cod, flying from Chicago, arriving by August 10 and returning by Aug | search_flights, search_hotels, create_booking |
| KEEP | planning-138 | baseline-pass | I'd like to organize a birthday weekend getaway to Nashville for four people. We're leaving from Cha | search_flights, search_hotels |
| KEEP | planning-139 | baseline-pass | I am thinking about embarking on an adventure trip to New Zealand, starting from Sydney. It will be  |  |
| KEEP | planning-140 | baseline-fail | Could you help me with a booking? ID: BK3X9Z2A. I need to add a car rental to this reservation. | add_ancillary |
| KEEP | planning-141 | baseline-fail | Plan a week-long skiing trip in the Canadian Rockies next February. Departing from Edmonton, what ar |  |
