# Review sheet — itinerary_build

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain itinerary_build`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | itinerary-123 | baseline-fail | I'd like a short break in Amsterdam. Can you arrange flights from Berlin and suggest a hotel by the  | search_flights, search_hotels |
| KEEP | itinerary-124 | baseline-fail | Plan a long weekend trip to Barcelona from Madrid with accommodation near La Sagrada Familia. | search_flights, search_hotels |
| KEEP | itinerary-125 | baseline-pass | What's my itinerary under booking reference BK3X9Z2A? | get_itinerary |
| KEEP | itinerary-126 | baseline-pass | I'd like to plan a 7-day tour of Iceland. Could you find flights from Boston? I haven't decided on a | search_flights |
| KEEP | itinerary-127 | baseline-fail | Could you book a luxury honeymoon in the Maldives? We'll be flying from New York, and we want an ove | create_booking, search_flights, search_hotels |
| KEEP | itinerary-128 | baseline-fail | Please find flights to Moscow for March 15th. I need help with the hotel booking later. | search_flights |
| KEEP | itinerary-129 | baseline-fail | Can you arrange a trip to Singapore with flights from Sydney and a hotel near Marina Bay? | search_flights, search_hotels |
| KEEP | itinerary-130 | baseline-fail | Could you organize a 10-day adventure in New Zealand? I need flights, but I'm not sure about the acc | search_flights |
| KEEP | itinerary-131 | baseline-pass | Prepare a detailed itinerary for my trip under reference BK7Q8P5Z. | get_itinerary |
| KEEP | itinerary-132 | baseline-fail | I want to visit Athens for a week. Can you arrange flights from Rome and a boutique hotel in Plaka? | search_flights, search_hotels |
