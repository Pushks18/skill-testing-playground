# book-itinerary

## When to Use
When the user wants to complete an actual booking, confirm a reservation, or plan a full trip end-to-end. Triggers on: "book a flight", "reserve a hotel", "complete my booking", "confirm my reservation", "book me into", "I want to book", "plan a trip to [destination]" (with intent to book).

[reuse skill: flight-search | when: user needs flights as part of itinerary | provides: flight options and flight_id]
[reuse skill: hotel-search | when: user needs hotels as part of itinerary | provides: hotel options and hotel_id]

## Workflow
1. Determine what the user wants to book: flight only, hotel only, or both.
2. **If flights needed:** run flight-search workflow to get flight options, confirm choice with user, note the `flight_id`.
3. **If hotel needed:** run hotel-search workflow to get hotel options, confirm choice with user, note the `hotel_id`.
4. Collect passenger details: full name and date of birth (DOB). Ask if not provided.
5. Call `validate_passenger` with `name` and `dob`. If validation fails, report the issue and stop.
6. Call `create_booking` with:
   - `flight_id` (if booking a flight)
   - `hotel_id` (if booking a hotel)
   - `passenger`: dict with name and dob
7. Confirm the booking to the user: show `booking_id`, status, and total price.

## Parameter rules
- Always validate passenger before creating booking
- If user provides a booking ID directly (e.g. "book flight FL123"), skip the search step and go straight to step 4
- For multi-leg trips: call `create_booking` once per leg

## When NOT to Use
- User only wants to search and compare options without booking → use flight-search or hotel-search
- User wants to check cancellation/change fees → use fare-rules
- User wants to cancel or modify an existing booking → use modify-booking
