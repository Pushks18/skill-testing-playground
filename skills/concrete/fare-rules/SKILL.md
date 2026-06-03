# fare-rules

## When to Use
When the user asks about the terms and conditions of a flight ticket. Triggers on: "cancellation policy", "can I cancel", "change fee", "is it refundable", "baggage allowance", "checked bag fee", "what happens if I miss my flight", "fare conditions", "ticket rules".

## Workflow
1. Identify the `flight_id` from the conversation context. If not available, ask the user: "What is your flight number or booking ID?"
2. Call `get_fare_rules` with the identified `flight_id`.
3. Summarize the response in plain language covering:
   - Cancellation: window and fee (e.g. "Free within 24h, $150 after")
   - Changes: fee to change date or route
   - Baggage: what's included and what costs extra
   - Refundable: yes/no with conditions
4. End with a clear recommendation if the user asked a yes/no question (e.g. "Yes, this ticket is refundable if cancelled within 24 hours of booking.")

## When NOT to Use
- User wants to search for new flights → use flight-search
- User wants to book or confirm a booking → use book-itinerary
- User wants to actually cancel or change a booking (not just ask about the policy) → use modify-booking
