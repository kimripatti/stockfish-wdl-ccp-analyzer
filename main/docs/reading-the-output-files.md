CONTENTS:

CHESS ANALYTICS 00.3: Methods, Part 3: How to Read the Output Files

From Numbers to Interpretation
1. The Main File Categories
2. First Rule: Know Whether the Number Is a Mean or a Sum
3. Second Rule: Separate Faced Difficulty from Caused Difficulty
4. Third Rule: Higher Does Not Always Mean Better
5. Fourth Rule: Raw CCP-v2 and Log CCP-v2 Are Different
6. Reading article_report.md
7. Reading all_metrics_3source.csv
8. Reading metric_ratios.csv
9. Reading player_summary.csv
10. Reading game_summary_readable.csv
11. Reading critical_moves.csv
12. Reading volatility_swings.csv
13. Reading hardest_positions.csv
14. Reading difficulty_critical_moves.csv
15. Reading ccp_hardest_positions.csv
16. Reading ccp_v2_log_hardest_positions.csv
17. Reading ccp_v2_log_critical_moves.csv
18. Reading ccp_v2_root_branch_summary.csv
19. Reading ccp_v2_root_branch_ply_summary.csv
20. Reading ccp_v2_root_branch_top_moves.csv
21. Reading ccp_v2_root_branch_payoff_moves.csv
22. Reading ccp_v2_root_branch_workload_rows.csv
23. Difficulty Share
24. Difficulty Pressure Quality, DPQ
25. Pressure Yield
26. Combining the Metrics: Common Interpretation Patterns
27. Style Profiles the Files Can Reveal
28. How to Compare Two Matches
29. A Simple Expert Reading Formula
30. Final Reading Checklist
31. The Main Lesson


# CHESS ANALYTICS 00.2: Methods, Part 3 — How to Read the Output Files

## From Numbers to Interpretation

The first methods article explained the WDL foundation: expected score, expected-score loss, WDL Accuracy, and the main performance metrics.

The second methods article introduced the post-WDL difficulty layer: all-legal difficulty, CCP Search Difficulty, CCP-v2 recursive forcing burden, probe/confirm search, root-branch diagnostics, Difficulty Pressure Quality, and Pressure Yield.

This third part explains how to read the actual output files.

The purpose is practical:

> When the analyzer and reporter produce many CSV files, which ones should you open first, what do the numbers mean, and how can they be turned into chess interpretation?

A single number rarely explains a chess match. The useful interpretation usually comes from reading several files together.

The basic reading method is:

1. Start with the match-level report.
2. Check the player summaries.
3. Check the game summaries.
4. Identify the largest losses and swings.
5. Study difficulty-weighted and pressure-weighted results.
6. Read the log-critical move files.
7. Use root-branch diagnostics to understand why a position was search-heavy.
8. Compare “faced,” “caused,” “yield,” and “share” metrics to describe style.

The final goal is not only to say:

> Player A was more accurate than Player B.

The richer goal is:

> Player A created this kind of pressure, Player B faced that kind of difficulty, and the match was decided because one player converted pressure better, defended pressure better, or failed under specific types of difficulty.

---

# 1. The Main File Categories

The output files can be divided into six families.

## A. Match-level summary files

These give the broadest view.

Important files:

* `article_report.md`
* `all_metrics_3source.csv`
* `metric_ratios.csv`
* `player_summary.csv`
* `game_summary_readable.csv`

Use these first.

They answer:

> What happened in the match overall?

> Which player was more accurate?

> Which player caused more difficulty?

> Which player suffered more under pressure?

> Was the match balanced or one-sided?

---

## B. Move-level critical files

These list the most important individual moves.

Important files:

* `critical_moves.csv`
* `volatility_swings.csv`
* `difficulty_critical_moves.csv`
* `ccp_v2_log_critical_moves.csv`

Use these when you want concrete chess examples.

They answer:

> Which moves lost the most expected score?

> Which moves changed the game most?

> Which mistakes occurred in difficult positions?

> Which mistakes occurred in high CCP-v2 search-burden positions?

---

## C. Hardest-position files

These list difficult positions whether or not the player made a mistake.

Important files:

* `hardest_positions.csv`
* `ccp_hardest_positions.csv`
* `ccp_v2_log_hardest_positions.csv`

Use these when you want to study the hardest tasks players faced.

They answer:

> Which positions were narrowest?

> Which positions had the highest immediate forcing pressure?

> Which positions had the highest recursive forcing-search burden?

A hard position is not automatically a bad move. Sometimes the player solved it perfectly.

That is why hardest-position files and critical-move files should be read together.

---

## D. Root-branch diagnostic files

These explain the internal shape of the CCP-v2 search.

Important files:

* `ccp_v2_root_branch_summary.csv`
* `ccp_v2_root_branch_ply_summary.csv`
* `ccp_v2_root_branch_top_moves.csv`
* `ccp_v2_root_branch_payoff_moves.csv`
* `ccp_v2_root_branch_workload_rows.csv`

Use these when you want to understand why the recursive search was difficult.

They answer:

> Which candidate root moves were probed?

> Which candidate root moves were confirmed?

> Was the played move included?

> Did the difficulty come from checks/captures/promotions or quiet moves?

> Did the branch have delayed payoff?

> Was the position search-heavy because of one main line or many branches?

---

## E. Analyzer metadata files

These tell you how the analysis was run.

Important files:

* `analysis_metadata.csv`
* `analysis_metadata_wide.csv`

Use these before comparing different analyses.

They answer:

> Which Stockfish settings were used?

> How many nodes were used?

> Was CCP-v2 enabled?

> What were the probe and confirm parameters?

> Was the same analyzer version used?

This matters because raw CCP-v2 values are parameter-sensitive. Comparisons are best when the same analyzer and similar parameters are used.

---

## F. Combined run files

When several match reports are combined into a larger run, the combiner produces files such as:

* `run_all_metrics.csv`
* `run_metric_ratios.csv`
* `run_summary_by_match.csv`
* `run_summary_overall.csv`
* `run_game_summary.csv`
* `run_game_metric_ratios.csv`
* `run_ccp_v2_root_branch_by_match.csv`
* `run_ccp_v2_root_branch_top_moves.csv`
* `run_ccp_v2_root_branch_payoff_moves.csv`
* `run_article_report.md`

Use these when one player’s whole run is being studied across multiple matches.

They answer:

> Did the player’s style change from match to match?

> Was one opponent harder to convert than another?

> Did the player cause more pressure in one match than in another?

> Did the player’s accuracy remain stable across different opponents?

---

# 2. First Rule: Know Whether the Number Is a Mean or a Sum

The most common mistake is comparing totals when the match lengths differ.

For example, a 24-game match naturally has more total moves than a 6-game match. So total difficulty, total volatility, total pressure, and total branch count will usually be larger in the longer match.

For fair comparison between matches of different length, prefer mean/per-move metrics.

## Mean metrics

Mean metrics ask:

> How intense was this on average?

Examples:

* WDL Accuracy
* Mean ES Loss
* WDL Volatility
* Pure Position Difficulty Faced
* CCP Search Difficulty Caused
* CCP-v2 Log Soft Search Difficulty Faced
* Pressure Yield Suffered
* Pressure Yield Caused
* DPQ if calculated from mean caused difficulty

Use mean metrics for style comparison between matches of different length.

## Sum metrics

Sum metrics ask:

> How much total exposure accumulated over the match?

Examples:

* Score
* Expected Score
* Conversion
* Total WDL Volatility
* Total Difficulty Faced
* Total Difficulty Caused
* Total CCP-v2 Log Difficulty Faced

Use sum metrics for match burden, endurance, and total historical workload.

But do not use raw sums alone to say that one match was “more difficult” than another if the match lengths differ.

A 24-game match can have more total difficulty while being less intense per move.

---

# 3. Second Rule: Separate Faced Difficulty from Caused Difficulty

Many post-WDL metrics come in two versions:

* Faced
* Caused

This distinction is essential.

## Faced difficulty

Faced difficulty is measured before the player’s own move.

It answers:

> How hard were the positions this player had to solve?

High faced difficulty means the player repeatedly had to make decisions in narrow, dangerous, tactically complicated, or search-heavy positions.

## Caused difficulty

Caused difficulty is attributed one ply backward to the previous mover.

It answers:

> How hard were the positions this player gave the opponent to solve?

High caused difficulty means the player repeatedly created positions where the opponent had to solve difficult problems.

This is not absolute strategic causation. It is immediate practical causation.

In plain language:

> Faced = what you had to solve.
> Caused = what you made your opponent solve.

A player can be high in one and low in the other.

For example:

* High faced, low caused: the player was under pressure but did not create much pressure back.
* Low faced, high caused: the player forced the opponent to solve problems while remaining relatively comfortable.
* High faced, high caused: both sides were in a sharp or tense mutual fight.
* Low faced, low caused: the game was broad, quiet, or low-pressure by that metric.

---

# 4. Third Rule: Higher Does Not Always Mean Better

Some metrics are performance metrics.

For these, higher is better.

Examples:

* WDL Accuracy
* Performance Quality
* Difficulty-weighted accuracy
* CCP-weighted accuracy
* CCP-v2 log-weighted accuracy
* Score
* Expected Score

Some metrics are loss metrics.

For these, lower is better.

Examples:

* Mean ES Loss
* RMS ES Loss
* Volatility, if interpreted as instability suffered
* Pressure Yield Suffered
* Difficulty-weighted ES Loss

Some metrics are difficulty or exposure metrics.

For these, higher means more difficult, not better by itself.

Examples:

* Pure Position Difficulty Faced
* CCP Search Difficulty Caused
* CCP-v2 Log Soft Difficulty Caused
* Narrowness
* Legal RMS Loss
* Quiet-Pause Burden
* Confirmed root branches
* Leaf count

A player who causes more difficulty may be more aggressive, more pressuring, more tactical, or more strategically demanding. But “more difficulty caused” becomes truly valuable only if it also produces opponent errors, conversion, or persistent practical problems.

That is why Pressure Yield and DPQ are useful.

---

# 5. Fourth Rule: Raw CCP-v2 and Log CCP-v2 Are Different

CCP-v2 raw values can become enormous because they measure recursive tree mass.

Raw CCP-v2 is useful for diagnostics, but it can be dominated by extreme outliers.

For public interpretation, log-scaled CCP-v2 is usually better.

## Raw CCP-v2

Useful for:

> Seeing the full magnitude of the recursive tree.

But it can be unstable across parameter changes and extreme positions.

## Log CCP-v2

Useful for:

> Comparing search burden on a compressed, readable scale.

The log scale preserves the basic ordering inside a metric but prevents one giant tree from overwhelming everything else.

For most article writing, prefer:

* `ccp_v2_log_search_difficulty_pure`
* `ccp_v2_log_search_difficulty_soft`
* `ccp_v2_log_critical_moves.csv`
* `ccp_v2_log_hardest_positions.csv`

---

# 6. Reading `article_report.md`

This is the easiest first file to open.

It contains:

* all metrics,
* player summary,
* game summary,
* largest WDL losses,
* volatility swings,
* hardest positions,
* difficulty-weighted loss proxies,
* CCP hardest positions,
* CCP-v2 log-critical moves,
* root-branch summaries if available,
* reading notes.

Use it as the first overview.

A good reading order is:

1. Read the interpretation notes.
2. Check Score and Expected Score.
3. Check WDL Accuracy and Mean/RMS ES Loss.
4. Check Conversion.
5. Check all-legal difficulty faced/caused.
6. Check CCP difficulty faced/caused.
7. Check CCP-v2 log difficulty faced/caused.
8. Check difficulty-weighted accuracy.
9. Check Pressure Yield and DPQ if present.
10. Look at log-critical moves.
11. Look at root-branch diagnostic summaries.

The markdown report is not always the best file for detailed spreadsheet work, but it is the best first reading experience.

---

# 7. Reading `all_metrics_3source.csv`

This is the main metric file.

It usually has rows such as:

* metric key,
* metric name,
* definition,
* aggregation,
* direction,
* Player A value,
* Player A SD,
* Player B value,
* Player B SD,
* both players value,
* both players SD.

This file is useful because it places all major metrics in one table.

## Useful for

Comparing the players across every metric.

## Reveals

Overall match profile, performance gap, style gap, pressure gap, difficulty asymmetry, and match-wide tendency.

## If a value is high

Interpret according to metric direction.

For performance metrics, high is usually good.

For difficulty metrics, high means more exposure or more pressure.

For yield/loss metrics, high means more expected-score loss.

## If a value is low

Low can mean accurate, low-pressure, low-complexity, or low conversion depending on the metric.

Always read the `direction` column.

## If both players are even

The metric was shared symmetrically.

This can mean:

* balanced accuracy,
* balanced difficulty,
* mutual pressure,
* similar style,
* or an evenly contested match.

## If uneven

Ask whether the unevenness is good, bad, or merely stylistic.

For example:

* Higher WDL Accuracy is good.
* Higher Mean ES Loss is bad.
* Higher Difficulty Caused may be pressure.
* Higher Difficulty Faced may be suffering or a difficult opponent.
* Higher Pressure Yield Caused is good for the player who caused the pressure, because the opponent lost more expected score under it.
* Higher Pressure Yield Suffered is bad for the player who suffered it.

---

# 8. Reading `metric_ratios.csv`

This file compares Player A and Player B by ratios and differences.

It is useful, but it must be read carefully.

Ratios are good when values are positive and stable.

Differences are better when the metric can be zero, negative, or signed.

## Useful for

Quickly seeing how much larger one player’s value was.

## Reveals

Relative advantage, relative instability, pressure imbalance, and ratio-scale asymmetry.

## If ratio is high

One player’s value is much larger.

But ask whether larger is good.

For WDL Accuracy, larger is good.

For Mean ES Loss, larger is worse.

For Difficulty Caused, larger means more pressure created.

For Difficulty Faced, larger means more pressure faced.

## If ratio is near 1

The players are close.

This may mean balance, equality, or mutual pressure.

## If the metric is signed

Prefer differences over ratios.

Examples:

* Conversion
* Dominance
* score minus expected score

A ratio between signed values can be misleading.

---

# 9. Reading `player_summary.csv`

This file is often the best compact player-style file.

It gives one row per player.

It usually contains:

* games,
* moves,
* score,
* expected score,
* conversion,
* accuracy,
* mean ES loss,
* RMS ES loss,
* volatility,
* difficulty faced/caused,
* difficulty-weighted accuracy,
* CCP faced/caused,
* CCP-v2 faced/caused,
* probe/confirm workload,
* DPQ and Pressure Yield if present.

## Useful for

Building a player profile.

## Reveals

Whether the player was:

* accurate,
* stable,
* pressuring,
* pressured,
* tactical,
* quiet,
* resilient,
* error-prone under pressure,
* good at converting pressure,
* or mainly successful through opponent failure.

## If WDL Accuracy is high

The player preserved expected score well.

## If Mean ES Loss is low

The player avoided average expected-score losses.

## If RMS ES Loss is high while Mean ES Loss is low

The player usually played well but had occasional large errors.

## If Volatility is high

The player’s games had more evaluation movement around their moves.

Volatility can reflect:

* tactical play,
* unstable positions,
* mutual chances,
* or errors.

It is not automatically bad, but high volatility with high ES loss is usually dangerous.

## If Difficulty Caused is high

The player gave the opponent difficult problems.

## If Difficulty Faced is high

The player had to solve difficult problems.

## If Difficulty-Weighted Accuracy is high

The player solved hard positions well.

## If Difficulty-Weighted Accuracy is much lower than normal WDL Accuracy

The player’s accuracy dropped when positions became difficult.

This is a very important sign.

## If Pressure Yield Caused is high

The opponent lost expected score under this player’s pressure.

That means the player’s pressure was productive.

## If Pressure Yield Suffered is high

The player lost expected score under the opponent’s pressure.

That means the player had trouble solving pressure.

## If DPQ is high

The player caused high difficulty in a match that was itself difficult.

This is a pressure-quality or style-intensity marker.

---

# 10. Reading `game_summary_readable.csv`

This file gives one row per game.

It is essential for understanding match flow.

A match-level average may hide that the match had several types of games.

For example:

* one tactical collapse,
* several high-accuracy draws,
* one technical conversion,
* one wild mutual blunder game,
* one quiet but difficult game.

`game_summary_readable.csv` helps separate them.

## Useful for

Finding which games created the match story.

## Reveals

Game-by-game changes in accuracy, difficulty, volatility, conversion, CCP burden, and CCP-v2 search burden.

## If one game has low mutual accuracy

Both players made more errors than usual.

## If one game has high volatility

The game swung sharply.

## If one game has high difficulty but high accuracy

The players solved a difficult game well.

## If one game has high difficulty and low accuracy

The game’s difficulty produced mistakes.

## If one game has high CCP-v2 log difficulty

The recursive forcing tree was unusually large or deep.

## If one game has high quiet-pause burden

The forcing lines involved quiet preparatory moves or delayed continuations.

## If one game has high conversion

One player scored more than expected.

High conversion across several games may indicate practical pressure, defensive resilience, endgame conversion, or opponent collapse.

---

# 11. Reading `critical_moves.csv`

This file lists the largest WDL expected-score losses.

These are the biggest mistakes by expected score.

## Useful for

Finding the clearest turning points.

## Reveals

Where the game result changed most directly.

## If a move has high ES loss

The move gave away a large part of the player’s expected score.

## If a high-loss move has low difficulty

The mistake may have been a clear miss.

## If a high-loss move has high difficulty

The mistake may have occurred under genuine pressure.

## If both players have many high-loss moves

The game was unstable or error-prone.

## If one player has most high-loss moves

The match likely had a clear performance gap.

But `critical_moves.csv` alone does not explain difficulty.

That is why it should be paired with:

* `difficulty_critical_moves.csv`
* `ccp_v2_log_critical_moves.csv`
* root-branch diagnostics.

---

# 12. Reading `volatility_swings.csv`

This file lists the largest expected-score swings.

Volatility is not exactly the same as error.

A move can swing the evaluation because:

* it was a mistake,
* it forced a sharp line,
* the previous position was unstable,
* or the game crossed a win/draw/loss boundary.

## Useful for

Finding dramatic moments.

## Reveals

Which moves changed the practical game state most.

## If high

The game had large evaluation movement.

## If low

The game was stable.

## If both players produce volatility

The game may have been mutually sharp.

## If one player produces most negative volatility

That player likely made more destabilizing errors.

Volatility should be interpreted together with ES loss and result direction.

---

# 13. Reading `hardest_positions.csv`

This file lists the hardest all-legal positions.

It uses position-difficulty metrics such as:

* legal RMS loss,
* narrowness,
* effective good moves,
* best-second gap,
* soft-uncertainty difficulty.

## Useful for

Finding positions where the legal-move choice was narrow or dangerous.

## Reveals

Pure decision difficulty independent of whether the player failed.

## If high

The player had a difficult legal-move task.

## If low

The position was broad or forgiving.

## If both players have many high positions

The match was difficult for both.

## If one player faced more high positions

That player was under more objective position pressure.

## If the player still made accurate moves

That is a sign of strong defensive or calculational performance.

---

# 14. Reading `difficulty_critical_moves.csv`

This file combines difficulty with expected-score loss.

It asks:

> Which mistakes happened in difficult all-legal positions?

This is more informative than simple critical moves.

## Useful for

Separating simple blunders from difficult failures.

## Reveals

Where expected-score loss occurred under objective position difficulty.

## If a move ranks high

The player lost expected score in a position that was also narrow or hard.

## If a big WDL mistake does not rank high here

The mistake may have been costly but not especially hard by all-legal metrics.

## If a player appears often

That player’s errors tended to happen under difficult decision conditions.

## If both players appear often

The match may have been a difficult mutual struggle.

---

# 15. Reading `ccp_hardest_positions.csv`

This file lists positions with high CCP Search Difficulty.

CCP means:

* checks,
* captures,
* promotions.

The CCP layer measures immediate forcing-candidate burden and quiet-to-CCP pressure.

## Useful for

Finding positions with tactical forcing pressure.

## Reveals

Immediate tactical activity, candidate-move ambiguity, and forcing-move density.

## If high

There were many or heavy immediate forcing possibilities.

## If low

The position had little immediate forcing tension.

## If one player caused much higher CCP difficulty

That player created more direct tactical pressure.

## If both players are even

The match had mutual tactical forcing pressure.

## If CCP is high but CCP-v2 is low

The position may have had immediate tactics but not deep recursive continuation.

## If CCP is low but CCP-v2 is high

The position may have had quiet buildup, latent tactics, or deeper search structure.

---

# 16. Reading `ccp_v2_log_hardest_positions.csv`

This file lists positions with high log-scaled recursive CCP-v2 difficulty.

It is usually more useful than raw CCP-v2 hardest positions.

## Useful for

Finding positions with large recursive forcing-search burden.

## Reveals

Deep or broad forcing-line structure, including quiet pauses.

## If high

The candidate tree was large or deep.

## If low

The recursive forcing burden was small.

## If both players face high CCP-v2 log difficulty

The match was rich in sustained forcing or latent search tension.

## If one player causes much higher CCP-v2 log difficulty

That player repeatedly created recursive search problems.

## If CCP-v2 log is high but the player’s move was accurate

The player solved a difficult search problem.

## If CCP-v2 log is high and ES loss is high

The player failed in a difficult search-heavy position.

---

# 17. Reading `ccp_v2_log_critical_moves.csv`

This is one of the most important practical files.

It combines:

1. real WDL expected-score loss,
2. log-scaled CCP-v2 search difficulty.

So the top moves are not merely the biggest mistakes. They are the biggest mistakes under recursive forcing-search burden.

## Useful for

Finding the best post-WDL critical examples.

## Reveals

Where difficulty and error met.

## If a move ranks high

The player lost expected score in a high recursive search-burden position.

## If a move has high ES loss but lower log-critical rank

The error was large, but the CCP-v2 search burden may not have been especially high.

## If a move has high CCP-v2 difficulty but no ES loss

The player solved the problem; it belongs in hardest positions, not critical moves.

## If one player dominates this file

That player suffered more under recursive forcing pressure.

## If both players appear equally

The match had mutual search-pressure failures.

This file is excellent for article examples because it points to moves where a chess explanation is likely to be interesting.

---

# 18. Reading `ccp_v2_root_branch_summary.csv`

This file summarizes root-branch diagnostics.

It tells how the CCP-v2 search behaved overall.

Typical ideas include:

* probe branch count,
* confirm branch count,
* confirm share,
* branch score log,
* played-move inclusion,
* positive-payoff rate,
* CCP-root rate,
* quiet-root rate,
* child leaf count,
* subtree workload.

## Useful for

Understanding the search shape of the match.

## Reveals

Whether the match’s difficulty came from direct forcing moves, quiet moves, many candidates, or deep subtree work.

## If confirmed branch count is high

The position usually had many root candidates worth confirming.

## If confirm share is high

The confirm stage covered most of what the probe found.

## If played-move inclusion is high

The analyzer’s confirmed candidate set usually included the actual game move.

## If CCP-root rate is high

The match had more direct checks/captures/promotions at the root.

## If quiet-root rate is high

The match had more quiet candidate moves leading into forcing structure.

## If positive-payoff rate is high

Many branches had lines where the root move produced later benefit.

## If branch-score log is high

The confirmed branches were generally heavier.

---

# 19. Reading `ccp_v2_root_branch_ply_summary.csv`

This file gives one row per game ply.

It is one of the best diagnostic files for deep interpretation.

It can show:

* how many branches were probed,
* how many were confirmed,
* which move ranked highest,
* whether the played move was confirmed,
* the played move’s rank,
* confirmed positive-payoff count,
* total confirmed leaves,
* max confirmed branch score,
* top confirmed move.

## Useful for

Studying one position at a time.

## Reveals

Whether the played move was part of the serious candidate set, and how the search evaluated competing root moves.

## If played move rank is high

The played move was one of the main confirmed candidates.

## If played move rank is low

The move was less important in the confirmed search or possibly not selected.

## If top confirmed move differs from played move

The position may contain an important alternative.

## If positive-payoff count is high

Several root moves may have delayed tactical or strategic justification.

## If confirmed leaves are high

The position generated a large subtree.

This file is ideal when choosing positions for human annotation.

---

# 20. Reading `ccp_v2_root_branch_top_moves.csv`

This file lists the highest-scoring confirmed root branches.

It focuses on candidate moves, not just played moves.

## Useful for

Finding the moves that created the largest confirmed CCP-v2 branch burden.

## Reveals

Which root candidates carried the heaviest search-tree weight.

## If the played move appears high

The actual game move was a major search-burden move.

## If an unplayed move appears high

The position contained an important alternative candidate.

## If many top moves are CCP moves

The position had direct forcing character.

## If many top moves are quiet

The position had latent or preparatory forcing character.

This is especially valuable for style interpretation.

A tactical player may produce many direct CCP-root candidates.

A positional pressure player may produce more quiet-root candidates with later forcing payoff.

---

# 21. Reading `ccp_v2_root_branch_payoff_moves.csv`

This file lists root branches with positive or delayed payoff.

It is useful for attacking ideas, sacrifices, and quiet moves.

## Useful for

Finding moves whose value appears later in the branch.

## Reveals

Delayed tactical justification, quiet buildup, speculative ideas, and latent pressure.

## If high

The move produced later payoff inside the confirmed branch.

## If low or absent

The branch did not show clear positive payoff.

## If many quiet payoff moves appear

The player or match may have a quiet buildup style.

## If many sacrifice-like moves appear

The file may help explain speculative initiative.

This file should not be treated as proof that a move was objectively best. It is a diagnostic signal that the branch contained later payoff.

---

# 22. Reading `ccp_v2_root_branch_workload_rows.csv`

This file lists branches that consumed the most search work.

High workload is not the same as high importance.

A branch can be workload-heavy because:

* it has many continuations,
* it has long forcing lines,
* it has many quiet pauses,
* or the search tree is simply large.

## Useful for

Separating “large tree” from “important critical error.”

## Reveals

Where the analyzer spent its search effort.

## If high workload and high branch score

The branch was both large and important.

## If high workload but low branch score

The branch was large but may not have mattered much.

## If high workload and high ES loss

The position may be a major calculation failure.

## If high workload and no ES loss

The player may have successfully solved a difficult calculation problem.

---

# 23. Difficulty Share

Difficulty Share asks:

> What proportion of the match’s caused difficulty came from this player?

Formula:

> Difficulty Share(A) = Total Difficulty Caused(A) / [Total Difficulty Caused(A) + Total Difficulty Caused(B)]

This is a style-balance metric.

## Useful for

Measuring pressure asymmetry.

## Reveals

Whether one player created most of the match’s difficulty.

## If high

The player caused most of the difficulty.

## If low

The player caused little of the difficulty.

## If both players are near 50%

The match pressure was balanced.

## If uneven

One player was the main pressure creator by that metric.

This is especially useful when match averages hide asymmetry.

A match may have moderate average difficulty because one player caused very high difficulty while the other caused very little.

---

# 24. Difficulty Pressure Quality, DPQ

Difficulty Pressure Quality is the pressure analogue of Performance Quality.

Performance Quality combines a player’s accuracy with the game’s overall accuracy context.

Difficulty Pressure Quality combines a player’s caused difficulty with the match’s overall caused difficulty context.

A practical formula is:

> DPQ(A) = Difficulty Caused(A) × Match Average Difficulty Caused

where the difficulty caused values should usually be per-move means, not raw totals, when comparing matches of different length.

## Useful for

Measuring pressure created inside a high-difficulty environment.

## Reveals

Whether the player caused serious difficulty in a match that was itself difficult.

## If high

The player caused high pressure in a high-pressure match context.

## If low

The player either caused little difficulty, or the match’s general difficulty level was low.

## If both players are even

Both players contributed similarly to the match’s difficulty environment.

## If uneven

One player was the stronger pressure creator after adjusting for match context.

DPQ should be read as a style-pressure metric, not as direct playing strength.

A player can have high DPQ but still lose if the opponent solves the pressure well.

---

# 25. Pressure Yield

Pressure Yield connects difficulty to actual expected-score loss.

Difficulty caused alone asks:

> Did the player create pressure?

Pressure Yield asks:

> Did that pressure produce expected-score loss?

There are two main versions.

## Pressure Yield Suffered

This is the player’s own ES loss weighted by the difficulty they faced.

It answers:

> How much did the player lose under pressure?

Formula idea:

> Pressure Yield Suffered(A) = Σ(Difficulty Faced by A × ES Loss by A) / Σ(Difficulty Faced by A)

High Pressure Yield Suffered is bad for the player.

## Pressure Yield Caused

This is the opponent’s ES loss weighted by the difficulty caused by the player.

It answers:

> How much did the opponent lose under this player’s pressure?

Formula idea:

> Pressure Yield Caused(A) = Σ(Difficulty Caused by A × Opponent ES Loss) / Σ(Difficulty Caused by A)

High Pressure Yield Caused is good for the player.

These are continuous metrics. They do not use hard thresholds.

## Useful for

Connecting pressure to conversion.

## Reveals

Whether difficulty actually produced expected-score loss.

## If Pressure Yield Caused is high

The player’s pressure was productive.

## If Pressure Yield Caused is low

The opponent solved the pressure well, or the pressure was not practically damaging.

## If Pressure Yield Suffered is high

The player failed under pressure.

## If Pressure Yield Suffered is low

The player handled pressure well.

## If both players are even

Both players converted pressure similarly, or both defended similarly.

## If uneven

One player’s pressure was more effective, or one player suffered more under pressure.

This may become one of the most important bridges between style and result.

---

# 26. Combining the Metrics: Common Interpretation Patterns

The strongest conclusions usually come from combinations.

## Pattern 1: High accuracy + high faced difficulty

Interpretation:

> The player solved hard positions well.

This suggests strong defense, calculation, or practical resilience.

## Pattern 2: High accuracy + low faced difficulty

Interpretation:

> The player played accurately, but the task may have been relatively comfortable.

This can still be excellent play, but the difficulty context was lower.

## Pattern 3: Low accuracy + high faced difficulty

Interpretation:

> The player failed under difficult conditions.

This is a classic pressure-collapse profile.

## Pattern 4: Low accuracy + low faced difficulty

Interpretation:

> The player made errors even without high measured difficulty.

This may indicate clear mistakes, poor form, or non-calculation failures.

---

## Pattern 5: High caused difficulty + high Pressure Yield Caused

Interpretation:

> The player created pressure and the opponent cracked.

This is the strongest “pressure conversion” profile.

## Pattern 6: High caused difficulty + low Pressure Yield Caused

Interpretation:

> The player created pressure, but the opponent solved it.

This may describe a fighting but unsuccessful attacker, or a player who generated complexity without conversion.

## Pattern 7: Low caused difficulty + high conversion

Interpretation:

> The player converted without creating much measured difficulty.

Possible explanations:

* opponent self-destruction,
* technical endgame skill,
* small accumulated advantages,
* non-CCP strategic pressure not fully captured,
* opening preparation,
* or metric blind spots.

## Pattern 8: High caused difficulty + low conversion

Interpretation:

> The player created problems but did not convert.

Possible explanations:

* opponent defended well,
* pressure was speculative,
* pressure came too late,
* or the player later spoiled the advantage.

---

## Pattern 9: High CCP caused + lower CCP-v2 log caused

Interpretation:

> The player created more immediate forcing action than sustained recursive search burden.

This may suggest direct tactics, forcing initiative, or concrete calculation.

## Pattern 10: Low CCP caused + high CCP-v2 log caused

Interpretation:

> The player created more latent recursive search burden than immediate forcing action.

This may suggest quiet buildup, positional tension, delayed tactics, or hidden continuations.

## Pattern 11: High CCP-v2 quiet-pause burden

Interpretation:

> The forcing lines often involved quiet moves before later tactical continuation.

This is especially interesting for positional attackers, prophylactic players, and speculative players.

## Pattern 12: High root-branch quiet rate

Interpretation:

> The candidate tree was driven more by quiet root moves than by immediate checks/captures/promotions.

This can support a “quiet pressure” or “latent tension” interpretation.

---

## Pattern 13: High root-branch CCP rate

Interpretation:

> The candidate tree was driven by direct forcing moves.

This supports a tactical or concrete forcing style.

## Pattern 14: High positive-payoff rate

Interpretation:

> Many branches contained later payoff.

This can indicate tactical richness, latent threats, or quiet move justification.

## Pattern 15: High workload but low criticality

Interpretation:

> The position was large to search, but not necessarily decisive.

This can happen in complex but balanced positions.

## Pattern 16: High workload + high ES loss

Interpretation:

> The player failed in a truly search-heavy position.

This is a strong candidate for detailed annotation.

---

# 27. Style Profiles the Files Can Reveal

The metrics can suggest style profiles.

They do not prove personality or intention. But they can describe measured tendencies.

## The Technical Converter

Typical profile:

* high WDL Accuracy,
* low Mean ES Loss,
* low RMS ES Loss,
* positive Conversion,
* moderate caused difficulty,
* low Pressure Yield Suffered,
* high conversion in small edges.

Interpretation:

> The player may not create the wildest positions, but converts chances efficiently and avoids giving counterplay.

## The Tactical Pressure Player

Typical profile:

* high CCP Search Difficulty Caused,
* high CCP Candidate Effective Count Caused,
* high CCP-v2 log-critical opponent errors,
* high Pressure Yield Caused,
* opponent’s difficulty-weighted accuracy drops.

Interpretation:

> The player creates forcing problems that the opponent fails to solve.

## The Quiet Pressure Player

Typical profile:

* moderate immediate CCP,
* high CCP-v2 Log Difficulty Caused,
* high quiet-pause burden,
* high quiet-root rate,
* high root-branch payoff moves.

Interpretation:

> The player creates latent search-tree pressure through quiet buildup rather than immediate tactics.

## The Resilient Defender

Typical profile:

* high Difficulty Faced,
* high CCP-v2 Log Difficulty Faced,
* high Difficulty-Weighted Accuracy,
* low Pressure Yield Suffered,
* low conversion allowed.

Interpretation:

> The player repeatedly solves hard positions.

## The Volatile Fighter

Typical profile:

* high Volatility,
* high RMS ES Loss,
* high caused difficulty,
* high suffered yield,
* many critical moves for both sides.

Interpretation:

> The player creates chances but also gives chances.

## The Balanced Elite Match

Typical profile:

* both players high WDL Accuracy,
* low Mean ES Loss,
* similar difficulty caused/faced,
* similar Pressure Yield,
* similar DPQ,
* small conversion gap.

Interpretation:

> The match was decided by small margins rather than one-sided collapse.

## The Asymmetric Domination Match

Typical profile:

* one player has higher accuracy,
* opponent has higher Mean/RMS ES Loss,
* winner has much higher Difficulty Caused Share,
* winner has high Pressure Yield Caused,
* loser has low difficulty-weighted accuracy,
* conversion gap is large.

Interpretation:

> One player created pressure and the opponent failed to solve it.

---

# 28. How to Compare Two Matches

When comparing two matches, use this order.

## Step 1: Confirm parameter comparability

Check:

* analyzer version,
* reporter version,
* Stockfish version,
* main nodes,
* difficulty nodes,
* CCP-v2 depth,
* probe nodes,
* confirm nodes,
* confirm candidates,
* vision settings.

Do not overinterpret small raw CCP-v2 differences if parameters differ.

## Step 2: Compare WDL performance

Use:

* Score,
* Expected Score,
* Conversion,
* WDL Accuracy,
* Mean ES Loss,
* RMS ES Loss,
* Volatility.

This tells the basic result-quality story.

## Step 3: Compare all-legal difficulty

Use:

* Pure Difficulty Faced/Caused,
* Soft-Uncertainty Difficulty Faced/Caused,
* Legal RMS Loss,
* Narrowness,
* Effective Good Moves.

This tells whether the match was narrow, forgiving, or objectively difficult by legal-move choice.

## Step 4: Compare pressure creation

Use:

* Difficulty Caused,
* CCP Caused,
* CCP-v2 Log Caused,
* Difficulty Share,
* DPQ.

This tells who created pressure.

## Step 5: Compare pressure conversion

Use:

* Pressure Yield Caused,
* Pressure Yield Suffered,
* Difficulty-weighted accuracy,
* CCP-v2 log-weighted accuracy.

This tells whether the pressure mattered.

## Step 6: Compare critical examples

Use:

* `critical_moves.csv`,
* `difficulty_critical_moves.csv`,
* `ccp_v2_log_critical_moves.csv`.

This identifies article-worthy moments.

## Step 7: Compare root-branch style

Use:

* root-branch summary,
* root-branch top moves,
* root-branch payoff moves,
* root-branch workload rows.

This tells whether the match was direct, quiet, tactical, latent, or search-heavy.

---

# 29. A Simple Expert Reading Formula

A practical expert reading formula is:

> Result = performance + pressure + pressure response + conversion.

In file terms:

## Performance

Read:

* WDL Accuracy
* Mean ES Loss
* RMS ES Loss
* PQ
* Mutual Accuracy

## Pressure

Read:

* Difficulty Caused
* CCP Caused
* CCP-v2 Log Caused
* Difficulty Share
* DPQ

## Pressure response

Read:

* Difficulty-Weighted Accuracy
* Pressure Yield Suffered
* CCP-v2 Log Weighted Accuracy

## Conversion

Read:

* Score
* Expected Score
* Conversion
* game-by-game conversion

Then ask:

> Did the player win because they played more accurately, caused more difficulty, handled pressure better, converted better, or because the opponent failed under specific pressure?

That question is the bridge from spreadsheet to chess history.

---

# 30. Final Reading Checklist

When opening a new match report, ask these questions.

## Basic result

* Who won?
* What was the expected score?
* Was conversion high or low?
* Did the result exceed the engine-expected match score?

## Accuracy

* Who had higher WDL Accuracy?
* Who had lower Mean ES Loss?
* Who had lower RMS ES Loss?
* Was the gap large or tiny?

## Stability

* Who had more volatility?
* Were errors concentrated in a few large moments?
* Did the match contain many swings or mostly stable play?

## Difficulty

* Who faced more all-legal difficulty?
* Who caused more all-legal difficulty?
* Were positions narrow or forgiving?
* Were effective good moves low or high?

## Tactical pressure

* Who caused more CCP Search Difficulty?
* Was the pressure immediate or quiet-to-CCP?
* Were there many checks/captures/promotions?
* Were there many plausible forcing candidates?

## Recursive pressure

* Who caused more CCP-v2 Log Difficulty?
* Was quiet-pause burden high?
* Were max chain lengths high?
* Were root branches mostly CCP moves or quiet moves?

## Pressure conversion

* Who had higher Pressure Yield Caused?
* Who had higher Pressure Yield Suffered?
* Did difficulty actually produce expected-score loss?
* Did one player solve pressure better?

## Style

* Was the match tactical or quiet?
* Was pressure one-sided or mutual?
* Was the winner a converter, attacker, defender, or beneficiary of opponent errors?
* Did the loser fail under immediate tactics, recursive search, narrow positions, or ordinary WDL mistakes?

## Article examples

* Which moves rank high in `ccp_v2_log_critical_moves.csv`?
* Which positions rank high in `hardest_positions.csv`?
* Which root branches have delayed payoff?
* Which workload-heavy branches are worth human annotation?

---

# 31. The Main Lesson

The output files should not be read as a pile of separate numbers.

They should be read as layers.

The first layer says:

> What happened to expected score?

The second layer says:

> How difficult were the choices?

The third layer says:

> Who created the difficulty?

The fourth layer says:

> Who suffered under it?

The fifth layer says:

> Which concrete moves and branches explain it?

That is how the method turns engine output into chess interpretation.

A good article should not merely report:

> Player A had 98.3% accuracy.

It should be able to say:

> Player A maintained high accuracy while causing more tactical pressure, the opponent’s difficulty-weighted accuracy dropped, and the decisive moments came from log-critical positions where recursive forcing burden combined with real expected-score loss.

Or:

> The match had very high recursive CCP-v2 difficulty, but both players solved it well, so the result was decided by small conversion differences rather than one-sided tactical collapse.

Or:

> The winner did not cause much more total difficulty, but had much lower Pressure Yield Suffered and converted the opponent’s few mistakes more efficiently.

That is the purpose of reading the files carefully.

The numbers are not the final explanation.

They are a map showing where the explanation should be found.
