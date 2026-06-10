# Review sheet — fare_rules

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain fare_rules`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | fare-rules-131 | baseline-pass | Check if booking XY7W9Y1 can be canceled and what the refund conditions are. | get_fare_rules |
| KEEP | fare-rules-132 | baseline-pass | I'm considering adding a pet to my booking with code HT35GL9. Are there any additional fees? |  |
| KEEP | fare-rules-133 | baseline-pass | For my flight AM123 on December 18th, what is the policy on meals and onboard purchases? | get_fare_rules |
| KEEP | fare-rules-134 | baseline-pass | Tell me if my reservation with booking PN7B4X5 includes flexibility to change travel dates without a | get_fare_rules |
| KEEP | fare-rules-135 | baseline-pass | Can you find out if flight DL456 allows cancellations and what the associated penalties might be? | get_fare_rules |
| KEEP | fare-rules-136 | baseline-fail | I'm planning to reschedule flight ZY987. What do I need to consider regarding fees and availability? |  |
| KEEP | fare-rules-137 | baseline-fail | What are the conditions for adding an extra passenger to my booking PL4B2N7? |  |
| KEEP | fare-rules-138 | baseline-pass | For flight MN345 from Berlin to Warsaw on October 21st, check if I get a complimentary upgrade to bu | get_fare_rules |
| KEEP | fare-rules-139 | baseline-pass | Check the terms under which I can change my seat from window to aisle on flight KL789. | get_fare_rules |
| KEEP | fare-rules-140 | baseline-pass | I need to know if there's a cost associated with a no-show for my journey on BA321 from Paris to Vie | get_fare_rules |
