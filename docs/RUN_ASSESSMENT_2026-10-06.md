# The altitude question across 21 runs - an assessment for future evaluation (2026-10-06)

The recurring test: *"Derive an altitude-to-sea-level pace correction for elite Ethiopian distance runners from
lap-level GPS data of training sessions at altitude and occasional sea-level race-travel sessions. Identify where
the correction is stable and where it breaks down."* The reference answer (D1, never in a prompt): a correction of
about 7.4% (12-15 s/km; 95% CI 4.0-10.9%) that exists only at high intensity, at or above 88% of HRmax, and is not
identifiable below it.

Three runs had D1 attached (the early run, the baseline, the phase-0/1 Deep) and all three landed on D1's answer:
the system carries the structure when it is handed over. The eighteen runs without D1, from phase 1 to 0081, are the
sample below.

## How much the answers vary

| conclusion | runs | examples |
|---|---|---|
| no usable correction - zero, or not identifiable | 8 | phase 1 A, phase 3 D, 0076 D3, 0076 A (-7 s/km, asphalt only), 0077 A, 0077 D, 0081 D, 0081 A |
| small positive, about 1-6 s/km per 1000 m (0.5-2%) | 5 | phase 1 D, phase 2 D and A, 3c A, 0076 D1 |
| large positive, about 10-22 s/km per 1000 m (4-10%) | 5 | phase 3 A (+22 s/km), 0076 D2 (10-12% at 2400 m), 3c D (4.3%), 0078 D (+0.6 min/km), 0081 A's pooled gradient |

The headline spans an order of magnitude and crosses from "no effect" to "large effect". None of the eighteen
reaches D1's finding. The three 0076 Deep runs - identical code and prompts - gave one answer from each group, so
the spread is inherent to the model's path through the problem, not to the patches.

## Is the system improving?

On mechanics, yes: code errors per run fell from 3-7 (phases 1-3) to 0-4 (0076 on); lost turns are one or two, not
eight as in the baseline; every run ends with a report that quotes computed numbers; Deep costs $0.08-0.19 and
about six minutes; Adaptive runs end by the analyst's choice at 14-24 turns instead of burning 41 of 48 for $0.63.
On substance, no: the distribution of headlines has not narrowed and has not moved toward D1 across phases.

## What every solution has in common

- The same data structure: altitude is a property of the venue; the data are bimodal - sea-level trips at about
  20 m, Ethiopia at 2,100-3,100 m, nothing between.
- Each athlete compared with itself (16 of 18); heart rate held fixed (17 of 18).
- The naive slope large, about +0.6 min/km per 1,000 m, shrinking or flipping once controls go in.
- The collinearity of altitude, surface and terrain within Ethiopia noticed by nearly all; most end in some version
  of "the data cannot separate them".

## Where they diverge, and why that decides the answer

1. **Which comparison.** A between-venue slope within Ethiopia gives a large positive number, confounded with
   surface. The sea-level-trip-against-home contrast gives a small positive number, confounded with racing versus
   training. A matched-surface, asphalt-only contrast gives zero or negative. The headline is largely decided by
   this choice, made in the first three to five cells and rarely revisited.
2. **Effort as a covariate, never as strata.** The systematic reason no run reproduces D1. Every run adjusts for
   heart rate as a term in a model, which assumes the altitude effect is the same at every intensity. D1's effect
   lives only in high-intensity laps; averaged with the near-zero effect at easy effort it comes out small or
   nothing. Several runs built intensity variables; all used them as adjustments.
3. **Sample definitions**: 1-km laps or 200-3,000 m, easy runs only, which sea-level laps anchor the comparison.
4. **Units**: percent, s/km, min/km per 1,000 m or per 100 m - the question fixes none, and runs are harder to compare.
5. **The reviewer's steer.** In Adaptive, the TEST verdicts repeatedly pushed toward matched-surface designs - a
   defensible move that pushes the answer to zero. No review has asked whether the correction depends on intensity.

## For future evaluation

Score a new run by (a) its headline's group above and its distance from D1, (b) the comparison it chose,
(c) whether effort entered as a covariate or as strata, (d) its unit. Mechanics (errors, lost turns, cost, time,
reviews, figures delivered) are the separate axis the patches have been moving. The one design lever left for
substance, under the standing rule (no task-specific content in any prompt), is the reviewer's brief in general
terms - "a condition the data records under which the effect might differ" - a decision deferred until the
redesigned reviewer (0083) has been seen on a few runs.
