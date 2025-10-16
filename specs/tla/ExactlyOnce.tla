---- MODULE ExactlyOnce ----
EXTENDS Naturals, Sequences

CONSTANTS Events

VARIABLES queue, processed

Init == /\ queue = << >>
        /\ processed = {}

Enqueue(e) == queue' = Append(queue, e)
Process == /\ queue # << >>
           /\ LET head == Head(queue) IN
              queue' = Tail(queue)
           /\ processed' = processed \cup {Head(queue)}

Next == \E e \in Events : Enqueue(e) \/ Process

Inv == \A e \in processed : Cardinality({x \in processed : x = e}) = 1

Spec == Init /\ [][Next]_<<queue, processed>>

THEOREM Spec => []Inv
----

