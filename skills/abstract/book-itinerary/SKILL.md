# book-itinerary

## When to Use
When user wants to complete a full booking (flight + hotel) or plan a multi-step trip itinerary.

[reuse skill: flight-search | when: user needs flights as part of itinerary | provides: flight options]
[reuse skill: hotel-search | when: user needs hotels as part of itinerary | provides: hotel options]

## Workflow
1. Determine what components the trip needs (flight, hotel, or both)
2. Execute flight-search workflow if flights needed
3. Execute hotel-search workflow if hotels needed
4. Validate passenger details via validate_passenger
5. Call create_booking for each confirmed component
6. Present full itinerary summary

## When NOT to Use
- User only wants to search without booking
