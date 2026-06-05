# Disruption Handling

## Workflow

1. **Confirm required inputs.** Ask for any missing required fields before proceeding. Many of the failed tasks are missing booking references (`BK3X9Z2A` or `BK4Y7A6B`), desired destination/origin, or the specific nature of the disruption (e.g., "flight got canceled" is clear, but "I need to check availability" is not specific enough to a disruption).
2. **Identify the type of disruption.** Determine if the disruption is a cancellation, delay, missed connection, or other event impacting a travel itinerary. This will inform the appropriate tools and information to retrieve (e.g., compensation rules are only applicable for certain disruptions).

Once the type of disruption and required details are confirmed, immediately use the appropriate tools to retrieve rebooking options, alternative flights, or compensation information based on the situation.
3. **Retrieve booking details.** Use the provided booking reference or passenger details to look up the affected itinerary. If multiple booking references are provided, attempt to verify each one to find the correct booking.
4. **Evaluate rebooking options or alternative solutions.** Based on the disruption type and the traveler's stated needs (e.g., "rebooking a similar flight to Denver"), investigate available tools or knowledge bases to find appropriate solutions (e.g., alternative flights, compensation policies). This step was entirely missed in the `NO_TOOL_CALL` failures, as the agent didn't attempt to search for solutions.

Ensure to use the 'search_flights' tool when checking for flight availability after a cancellation, and always use the 'modify_booking' tool if a rebooking is being requested by the user. Never respond verbally if these tool calls are required; instead, use the tools to retrieve and present the structured options. Use relevant tools or resources to provide explicit compensation rules if a user inquires about it.

If a user inquires about adding services such as priority boarding, utilize the 'add_ancillary' tool to fulfill the request.
5. **Present options to the user.** Clearly communicate the available rebooking options, compensation information, or other relevant details obtained in the previous step.

## Required Inputs

| Input          | Notes                                                                                                                              |
| :------------- | :--------------------------------------------------------------------------------------------------------------------------------- |
| `disruption_type`    | The specific type of travel disruption (e.g., "flight cancellation", "flight delay", "missed connection"). Cannot be generic. |
| `passenger_name` | The full name of the passenger associated with the booking.                                                                        |
| `contact_email_or_phone` | An email address or phone number associated with the booking. Essential for verification if booking reference is ambiguous or missing. |

## Optional Inputs

| Input             | Default                          |
| :---------------- | :------------------------------- |
| `booking_reference` | None                             |
| `origin_airport`  | None                             |
| `destination_airport` | None                             |
| `desired_rebooking_date` | Original departure date if available |

## Output

```json
{
  "outcome_summary": "string", // A concise summary of the disruption handling process and resolution.
  "proposed_solutions": [
    {
      "solution_type": "string", // e.g., "rebooking_option", "compensation_info", "alternative_transport"
      "details": "object" // Structured details specific to the solution type (e.g., new flight details for rebooking)
    }
  ],
  "agent_actions_taken": [
    {
      "tool_name": "string",
      "parameters_used": "object",
      "result_summary": "string"
    }
  ]
}
```

## Edge Cases and Quality Checks

*   **Ambiguous Booking References:** If multiple booking references are provided or the provided reference is invalid, the agent must ask for clarification or additional identifying information (e.g., full passenger name, contact details, flight number) before attempting any tool calls.
*   **Missing Disruption Type:** If the user's initial instruction does not clearly state the disruption (e.g., "I need to check availability"), the agent must prompt the user for more specific information to determine the `disruption_type`. The agent should not assume a disruption has occurred without explicit confirmation.
*   **Incomplete Rebooking Requests:** If a user requests rebooking but does not specify a desired destination or date, the agent must prompt for these details.
*   **Verification of Passenger Details:** Even if a booking reference is provided, if there's any ambiguity, the agent should attempt to verify `passenger_name` against the booking to prevent incorrect actions.
* **Tool Usage for Communication:** Do not respond with text explanations where a tool can provide structured or authoritative answers. Ensure compensation policies and rebooking options are retrieved and presented using the correct tools.

Always retrieve and present the compensation policies using the appropriate tool or resource when a disruption involves flight delays or cancellations and the user inquires about potential compensation.
