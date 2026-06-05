# Review sheet — itinerary_build

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain itinerary_build`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | itinerary-101 | baseline-fail | Organize a 5-day holiday in Paris, including flights from Boston and a hotel in the Montmartre distr | search_flights, search_hotels, create_booking |
| KEEP | itinerary-102 | baseline-fail | Get the details for what has been planned under booking BK6XZ8V1. | get_itinerary |
| KEEP | itinerary-103 | baseline-pass | Plan a 2-week family vacation in Tokyo; find flights departing from Sydney and a family-friendly hot | search_flights, search_hotels |
| KEEP | itinerary-104 | baseline-fail | Tell me what you have for booking reference BK9T3F0Z. | get_itinerary |
| KEEP | itinerary-105 | baseline-fail | Could you arrange a 3-day romantic getaway in Venice with flights from London and a hotel near the G | search_flights, search_hotels, create_booking |
| KEEP | itinerary-106 | baseline-pass | Please plan a trip from New Orleans to Denver with flights and a downtown hotel stay. Departure is t |  |
| KEEP | itinerary-107 | baseline-pass | Find flights to Cancun but I need hotels with the best ocean view options. |  |
| KEEP | itinerary-108 | baseline-fail | I'm planning a 3-day conference trip to Berlin, flying from Toronto. Could you sort out the flights  | search_flights, search_hotels, create_booking |
| KEEP | itinerary-109 | baseline-fail | Please prepare a detailed itinerary for an educational tour in Rome for 12 nights, departing from Da | search_flights, search_hotels, create_booking |
| KEEP | itinerary-110 | baseline-fail | I need to know the itinerary for booking reference BK4P7C9X. | get_itinerary |
