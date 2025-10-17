---- MODULE CanaryFSM ----
EXTENDS Naturals

VARIABLES state

States == {"Baseline", "Shadow", "Canary", "Rollback", "Promote"}

Init == state = "Baseline"

Shadow == /\ state = "Baseline"
          /\ state' = "Shadow"

Promote == /\ state = "Canary"
           /\ state' = "Promote"

Rollback == /\ state \in {"Shadow", "Canary"}
            /\ state' = "Rollback"

Advance == /\ state = "Shadow"
           /\ state' = "Canary"

Next == Shadow \/ Advance \/ Promote \/ Rollback

Safe == state \in States

Spec == Init /\ [][Next]_state

THEOREM Spec => []Safe
----

