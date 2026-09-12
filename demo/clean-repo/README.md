# Clean Demo Repository

A deliberately clean repository used as the false-positive control for
CodeRisk Arcanum acceptance runs. Every file here is benign.

## Purpose

If the scanner reports any finding for this repository, that finding is a
false positive by construction, because nothing in this tree matches any
rule in the PITAX rulebook, static heuristics, taint-flow signatures, or
the known-vulnerable dependency list.
