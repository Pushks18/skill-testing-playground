# Review sheet — itinerary_build

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain itinerary_build`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | itinerary-101 | baseline-fail | Organize a 5-day holiday in Paris, including flights from Boston and a hotel in the Montmartre distr | search_flights, search_hotels, create_booking |
| KEEP | itinerary-102 | baseline-pass | Get the details for what has been planned under booking BK6XZ8V1. | get_itinerary |
| KEEP | itinerary-103 | baseline-pass | Plan a 2-week family vacation in Tokyo; find flights departing from Sydney and a family-friendly hot | search_flights, search_hotels |
| KEEP | itinerary-104 | baseline-pass | Tell me what you have for booking reference BK9T3F0Z. | get_itinerary |
| KEEP | itinerary-105 | baseline-fail | Could you arrange a 3-day romantic getaway in Venice with flights from London and a hotel near the G | search_flights, search_hotels, create_booking |
| KEEP | itinerary-106 | baseline-pass | Please plan a trip from New Orleans to Denver with flights and a downtown hotel stay. Departure is t |  |
| KEEP | itinerary-107 | baseline-pass | Find flights to Cancun but I need hotels with the best ocean view options. |  |
| KEEP | itinerary-108 | baseline-fail | I'm planning a 3-day conference trip to Berlin, flying from Toronto. Could you sort out the flights  | search_flights, search_hotels, create_booking |
| KEEP | itinerary-109 | baseline-fail | Please prepare a detailed itinerary for an educational tour in Rome for 12 nights, departing from Da | search_flights, search_hotels, create_booking |
| KEEP | itinerary-110 | baseline-pass | I need to know the itinerary for booking reference BK4P7C9X. | get_itinerary |

## Batch 2 — 2026-06-10 (itinerary-111..122)

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | itinerary-111 | baseline-fail | Can you put together a week-long trip to Sydney? I need flights from Vancouver and a beachfront hote | search_flights, search_hotels |
| DROP | itinerary-112 | baseline-pass | What's the current itinerary for booking reference BK7W1P4X? | get_itinerary |
| KEEP | itinerary-113 | baseline-fail | I'd like to have a romantic weekend in Kyoto. Can you find flights departing from Seoul and a ryokan | search_flights, search_hotels |
| KEEP | itinerary-114 | baseline-fail | Make arrangements for a business trip to Bangkok for 3 days, originating from Kuala Lumpur. Book som | search_flights, search_hotels, create_booking |
| KEEP | itinerary-115 | baseline-pass | Can you please provide a detailed itinerary for my trip under booking reference number BK5T9D1K? | get_itinerary |
| KEEP | itinerary-116 | baseline-fail | I'm considering a quick getaway to Reykjavik. Check flights from Montreal and suggest a centrally lo |  |
| KEEP | itinerary-117 | baseline-fail | I'd like to visit Cape Town from Johannesburg over Christmas. Can you help with flights and a luxury |  |
| KEEP | itinerary-118 | baseline-fail | Can you assist me with a travel itinerary? I need flights to Auckland from Los Angeles and a stay at | search_flights, search_hotels |
| KEEP | itinerary-119 | baseline-fail | Make a booking for a 10-day family vacation to the Maldives, departing from Zurich. We want an all-i | search_flights, search_hotels, create_booking |
| KEEP | itinerary-120 | baseline-pass | Plan a solo adventure to Machu Picchu. I'll be flying from Miami, and I need convenient lodging. |  |
| KEEP | itinerary-121 | baseline-pass | What are the details of my current booking, BK8E2Q0R? | get_itinerary |
| KEEP | itinerary-122 | baseline-fail | Organize a 2-week workation in Lisbon. Flights should be from Frankfurt and the accommodation should | search_flights, search_hotels, create_booking |

### Decisions

- itinerary-111: KEEP - multi-component week trip, baseline-fail (agent skipped hotel search)
- itinerary-112: DROP - near-duplicate of promoted itinerary-110 (cos 0.91)
- itinerary-113: KEEP - weekend trip paraphrase family, baseline-fail
- itinerary-114: KEEP - 3-day business trip multi-step incl. create_booking, baseline-fail
- itinerary-115: KEEP - get_itinerary lookup, baseline-pass anchor
- itinerary-116: KEEP - llm_judge missing-dates clarification case, baseline-fail (agent fabricated dates)
- itinerary-117: KEEP - llm_judge ambiguous 'Christmas' dates clarification case, baseline-fail
- itinerary-118: KEEP - flight+hotel paraphrase family, baseline-fail
- itinerary-119: KEEP - 10-day family vacation multi-step booking, baseline-fail
- itinerary-120: KEEP - llm_judge solo trip planning, baseline-pass
- itinerary-121: KEEP - booking-details paraphrase of 115, baseline-pass
- itinerary-122: KEEP - 2-week workation budget/amenity constraint, baseline-fail

### Near-duplicates auto-marked DROP

- itinerary-112 ≈ itinerary-110 (cos 0.91)
