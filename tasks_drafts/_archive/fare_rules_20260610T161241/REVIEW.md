# Review sheet — fare_rules

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain fare_rules`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | fare-rules-141 | baseline-pass | I'm considering changing my booking for flight FR340 on February 14th. Could you check the fees invo | get_fare_rules |
| KEEP | fare-rules-142 | baseline-pass | Will I be charged for bringing a bicycle on my flight CM123 from Boston to Chicago next week? |  |
| KEEP | fare-rules-143 | baseline-pass | I want to cancel my flight reservation with code GL89TY7. Can you let me know if there's a refund an | get_fare_rules |
| KEEP | fare-rules-144 | baseline-pass | Is seat selection included in my booking ID DF182Y4 for flight BH456? If not, what's the extra charg |  |
