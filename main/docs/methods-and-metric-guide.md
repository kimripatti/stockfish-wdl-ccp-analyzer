CONTENTS:

CHESS ANALYTICS 00.1: Methods, Parts 1: Measuring World-Championship Roads with Stockfish 18 WDL

1. The Basic Units of the Analysis
2. Expected Score
3. Expected-Score Loss
4. WDL Accuracy
5. Game Accuracy
6. Mutual Accuracy
7. Performance Quality
8. Dominance
9. Volatility
10. RMS Expected-Score Loss
11. Error Concentration
12. Score, Expected Score, and Conversion
13. HardRAP and SoftRAP
14. How the Metrics Form One Whole
15. Why WDL Is Preferable Here to Pawn Evaluation
16. Why This Series Is Worth Doing

CHESS ANALYTICS 00.2: Methods, Part 2 — Post-WDL Difficulty Metrics

1. WDL Metrics: Measuring Lost Scoring Chances
2. All-Legal Difficulty: How Narrow Was the Position?
3. Difficulty-Weighted Accuracy: Accuracy Under Pressure
4. CCP Difficulty: Checks, Captures, and Promotions
5. CCP-v2: Recursive Forcing-Line Search Difficulty
6. CCP-v2 Vision: Looking for Quiet Ideas Before Forcing Lines
7. CCP-v2 Two-Stage Probe/Confirm: Search Cheaply, Then Confirm Seriously
8. CCP-v2 Root-Branch Diagnostics: What Did the Search Actually Prefer?
9. CCP-v2 Log-Critical Moves: Where Difficulty Meets Damage
10. What the Post-WDL Metrics Add
11. Short Chronological Summary of Analyzer v3.6.1
12. Practical Reading Guide

- - - - -

This article series studies World-Championship matches and World-Championship qualification runs with a modern engine-based method.

The basic idea is simple:

Put every move of great historical matches under Stockfish 18, translate each position into win/draw/loss chances, and then ask: who preserved winning chances better, who lost chances more often, who created volatility, who converted chances into points, and who stayed more consistent?

Stockfish 18 is far stronger than any human player. Its strength is so far above human World Champions that comparing it to humans by normal Elo becomes difficult. This makes it useful as a reference point: not because it “understands chess like a human,” but because it gives a very strong, consistent measuring stick.

The purpose is not to reduce chess greatness to one number. The purpose is to create a performance profile:

Did the player win by accuracy?

By lower error?

By better conversion?

By forcing volatility?

By making fewer severe mistakes?

By staying stable over many games?

By outperforming the opponent in critical moments?

The analysis uses three main tools:

Stockfish 18 with WDL evaluation
wdl_chess_analyzer_v2.py, which analyzes the PGN games with Stockfish
make_wdl_report_v3.py, which turns the raw data into match reports with values, standard deviations, ratios, and player comparisons

- - - - -

1. The Basic Units of the Analysis

A match is made of games.

A game is made of turns.

One full turn contains:
White move + Black move

In engine language, each individual half-move is often called a ply.

So:
1 turn = 2 plies

If a game has:
n turns

then it has approximately:
2n plies

Each ply can be evaluated by Stockfish 18.

For every position, Stockfish can estimate:


Win

Draw

Loss

These are usually shown as values per 1000, for example:


WDL = 120, 850, 30

This does not mean Stockfish just played 1000 Monte Carlo games from the position. It is better understood as a calibrated probability-style model. In this example:


Win = 120/1000 = 0.120

Draw = 850/1000 = 0.850

Loss = 30/1000 = 0.030

So the position is mostly drawish, but with some winning chances.

- - - - -

2. Expected Score


From Win, Draw, and Loss, we define:


Expected Score = ES

ES = W + 0.5D

A win is worth: 1

A draw is worth: 0.5

A loss is worth: 0

So if Stockfish says:


W = 0.20

D = 0.70

L = 0.10

then:


Expected Score = 0.20 + 0.5(0.70)

Expected Score = 0.55

That means the position is worth about 0.55 points.

Useful for
Expected Score tells us how valuable a position is in actual chess result terms.

Reveals
It tells us whether a player is likely to win, draw, or lose from a position.

If high
The player is doing well. A value near 1 means the position is close to winning.

If low
The player is doing badly. A value near 0 means the position is close to losing.

If both players are even
The position is balanced.

If uneven
One player has better practical chances.

- - - - -

3. Expected-Score Loss

Now we ask: how much did a move damage the player’s expected result?

We define:


Expected-Score Loss = ESLoss

ESLoss = max(0, ES_{best} – ES_{played})

where:


ES_{best} = {Expected Score after Stockfish’s best move}

ES_{played} = {Expected Score after the move actually played}

Example:

Stockfish’s best move keeps:


ES = 0.70

The player’s move gives:


ES = 0.55

Then:


ESLoss = 0.70 – 0.55 = 0.15

The move lost 0.15 expected points.

Useful for
Measuring how much a move damaged the player’s expected result.

Reveals
Mistakes in terms of lost scoring chances, not merely lost pawn evaluation.

If high
The move was costly. It may have turned a win into a draw, or a draw into a loss.

If low
The move preserved the player’s chances well.

If both players have similar losses
They made similar amounts of practical error.

If uneven
The player with higher losses gave away more scoring chances.

- - - - -

4. WDL Accuracy

From Expected-Score Loss, we define:


WDL Accuracy = 100 times (1 – ESLoss)

So if a move loses:


ESLoss = 0.00

then:


WDL Accuracy = 100

If a move loses:


ESLoss = 0.20

then:


WDL Accuracy = 80

If a move loses:


ESLoss = 0.50

then:


WDL Accuracy = 50

Useful for
Giving each move a simple accuracy score based on lost expected score.

Reveals
How well the player preserved their practical result chances.

If high
The player usually avoided damaging moves.

If low
The player often lost expected score.

If both players are even
They played at similar technical quality.

If uneven
The more accurate player preserved chances better.

- - - - -

5. Game Accuracy

For two players:


Accuracy(A) = {Player A’s WDL Accuracy}

Accuracy(B) = {Player B’s WDL Accuracy}

Then:


Game Accuracy = {Accuracy(A)+Accuracy(B)} / {2}

Useful for
Measuring the average technical quality of the whole game.

Reveals
Whether the game was clean or error-filled overall.

If high
Both players together produced a technically accurate game.

If low
The game contained more lost expected score.

If both players are even
The game was balanced in accuracy.

If uneven
The average may hide that one player played much better than the other.

- - - - -

6. Mutual Accuracy

Mutual Accuracy = {Accuracy(A) times Accuracy(B)} / {100}

This is stricter than Game Accuracy.

A game where both players score 95 is very strong mutually.

A game where one scores 99 and the other 80 may still have decent Game Accuracy, but lower Mutual Accuracy.

Useful for
Measuring two-sided quality.

Reveals
Whether both players maintained high standards.

If high
The game was a high-resistance struggle.

If low
At least one player lost significant expected score.

If both players are even
Mutual Accuracy and Game Accuracy tell a similar story.

If uneven
Mutual Accuracy punishes the imbalance more strongly.

- - - - -

7. Performance Quality

Performance Quality = PQ

For Player A:


Performance Quality(A) = Accuracy(A) times ({Game Accuracy} / {100})

For Player B:


Performance Quality(B) = Accuracy(B) times ({Game Accuracy} / {100})

This asks:

How impressive was this player’s accuracy, considering the quality of the whole game?

Useful for
Adjusting individual accuracy by the game’s overall level.

Reveals
Whether a player’s accuracy came in a strong, mutually accurate game or in a weaker game.

If high
The player was accurate in a high-quality environment.

If low
Either the player’s accuracy was low, or the game quality was low.

If both players are even
They performed similarly in context.

If uneven
One player’s accuracy was more impressive in context.

8. Dominance

Dominance(A) = Accuracy(A) – Accuracy(B)

Dominance(B) = Accuracy(B) – Accuracy(A)

Useful for
Measuring the accuracy gap between the players.

Reveals
Who outplayed whom technically.

If high for one player
That player had a clear accuracy edge.

If close to zero
The players were technically close.

If even
The result may have depended on conversion, timing, or one critical mistake.

If uneven
One player was more accurate across the game or match.

- - - - -

9. Volatility

WDL Volatility = {average absolute Expected-Score swing per move}

In simpler terms:

How much did the game’s expected result move around?

A quiet technical game has low volatility.

A wild tactical game has high volatility.

Useful for
Measuring instability, sharpness, and turning points.

Reveals
Whether the game was calm, tactical, chaotic, or full of swings.

If high
The game changed direction often or contained major turning points.

If low
The game was stable and controlled.

If both players are even
Both players contributed similarly to the game’s movement.

If uneven
One player’s moves were associated with more swings.

Important: high volatility is not automatically bad. It can mean brilliant complications, tactical shots, sacrifices, or mistakes. Volatility tells us that the game moved; accuracy tells us whether the movement was good or bad.

- - - - -

10. RMS Expected-Score Loss

Root Mean Square Expected-Score Loss = RMSESLoss


RMSESLoss = sqrt{(1/n) ∑ ESLoss_i^2}

This punishes large errors more strongly than small ones.

Useful for
Measuring severe mistakes without arbitrary blunder labels.

Reveals
Whether a player’s errors were small and steady, or rare and severe.

If high
The player made one or more large practical mistakes.

If low
The player avoided major expected-score losses.

If both players are even
Their severe-error burden was similar.

If uneven
One player suffered more damaging mistakes.

- - - - -

11. Error Concentration

Error Concentration = {RMSESLoss} / {MeanESLoss}

Useful for
Finding out whether errors are spread out or concentrated.

Reveals
The shape of a player’s mistakes.

If high
The player may have played well most of the time, but made a few big errors.

If low
The player’s errors were more evenly distributed.

If both players are even
Their error patterns were similar.

If uneven
One player’s errors were more concentrated into decisive moments.

- - - - -

12. Score, Expected Score, and Conversion

The actual game score is:


Score ∈ {1, 0.5, 0}

Then:


Conversion = Score – Expected Score

Useful for
Measuring whether the player scored more or less than the engine-flow suggested.

Reveals
Practical conversion, resilience, missed chances, and escape ability.

If high
The player scored more than expected.

If low or negative
The player scored less than expected.

If both players are even
The result matched the flow of the game.

If uneven
One player converted chances better than the other.

- - - - -

13. HardRAP and SoftRAP

Hard Result-Adjusted Performance = HardRAP


HardRAP = PQ times Score

This gives full credit for wins, half credit for draws, and zero credit for losses.


Soft Result-Adjusted Performance = SoftRAP


SoftRAP = PQ times (0.5 + 0.5Score)

This gives:


Win = 1.00

Draw = 0.75

Loss = 0.50

Useful for
Combining quality and result.

Reveals
Whether good play became match points.

If high
The player both played well and scored well.

If low
The player either played poorly, failed to score, or both.

If HardRAP and SoftRAP differ greatly
The player may have had good-quality losses or draws that HardRAP punishes more strictly.

- - - - -

14. How the Metrics Form One Whole

The complete performance profile is not one formula only. It is more like a dashboard.

Each metric answers a different question.


WDL Accuracy

asks:

How well did the player preserve expected score move by move?


MeanESLoss

asks:

How much expected score did the player lose on average?


RMSESLoss

asks:

Were there big damaging mistakes?


ErrorConcentration

asks:

Were the errors spread out, or concentrated into a few disasters?


GameAccuracy

asks:

How clean was the whole game?


MutualAccuracy

asks:

Did both players play accurately?


PerformanceQuality

asks:

Was the player’s accuracy impressive in the context of the game?


Dominance

asks:

Who was more accurate?


Volatility

asks:

How unstable or swingy was the game?


Conversion

asks:

Did the player turn chances into actual points?


HardRAP
and SoftRAP

ask:

How much performance quality became competitive success?

So a possible complete performance equation, not as a single final truth but as a useful profile, is:


Performance Profile = Accuracy + Error Control + Stability + Contextual Quality + Dominance + Conversion + Result Adjustment

More explicitly:


Performance Profile = WDLAccuracy + MeanESLoss + RMSESLoss + ErrorConcentration + GameAccuracy + MutualAccuracy + PQ + Dominance + Volatility + Conversion + HardRAP + SoftRAP

This does not mean we simply add all numbers together blindly. Instead, we read them as connected layers.

Example:

A player with high Accuracy, low Mean ES Loss, low RMS Loss, and low Volatility probably played clean, stable chess.

A player with high Accuracy, high Volatility, and high Conversion may have played sharp dynamic chess and handled complications well.

A player with similar Accuracy to the opponent but much better Conversion may have been more practical in decisive moments.

A player with good average Accuracy but high RMS Loss may have played well most of the time but made one or two decisive mistakes.

A player with high Dominance but poor Conversion may have outplayed the opponent but failed to score.

A player with high Mutual Accuracy in a match probably faced strong resistance.

This is the main point of the whole system:

Instead of saying only “Player X was accurate,” we can ask what kind of accuracy it was: stable, volatile, dominant, mutually resisted, result-converted, or error-prone in rare moments.

- - - - -

15. Why WDL Is Preferable Here to Pawn Evaluation

Traditional engine analysis often uses pawn units:


+1.00

-0.50

+3.00

These are useful, but they can be misleading.

A change from:


0.00 to -2.00

is usually enormous, because a drawn position may have become losing.

But a change from:


-8.00 to -10.00

may matter much less, because the position was already lost.

WDL Expected Score handles this more naturally. It asks:

How much did the player’s expected result change?

That is why this article series uses WDL-based metrics as the foundation.

- - - - -

16. Why This Series Is Worth Doing

Chess history contains many claims:

Fischer was uniquely dominant.

Karpov was incredibly stable.

Kasparov was dynamic and deep.

Carlsen converted tiny edges better than anyone.

Older champions were brilliant but less engine-clean.

Modern games are more accurate but sometimes less decisive.

These claims are often true in spirit, but they are hard to compare precisely.

This project tries to make them more measurable.

By applying the same Stockfish 18 WDL method to different World-Championship runs and matches, we can compare champions through several lenses:

accuracy
resistance
dominance
volatility
error severity
consistency
conversion
result-adjusted performance
The final goal is not to replace human chess understanding. The goal is to make the structure of greatness more visible.

A champion may be great because he is cleaner.

Another may be great because he converts better.

Another may be great because he survives chaos.

Another may be great because he gives the opponent no chances.

These metrics help us describe those differences.

Below is a draftable Intro Part 2/3. I made it beginner-friendly and chronological: from WDL, to position difficulty, to forcing-move difficulty, to CCP-v2, vision, probe/confirm, and root-branch diagnostics. Your Part 1 explains the Stockfish 18 WDL foundation, including expected score, expected-score loss, WDL Accuracy, Game Accuracy, Mutual Accuracy, PQ, Dominance, Volatility, RMS loss, Error Concentration, Conversion, and RAP-style result-adjusted metrics. (Thinking Metrics)

- - - - -

- - - - -

- - - - -

CHESS ANALYTICS 00.1: Methods, Part 2 — Post-WDL Difficulty Metrics

The first part introduced the basic WDL method: Stockfish estimates win/draw/loss chances, those chances are turned into expected score, and each move is measured by how much expected score it loses.

That already tells us a lot:

who preserved winning chances,
who lost expected score,
who played more accurately,
who created volatility,
who converted chances into points.
But it does not fully answer another important question:

How hard was the move to find?

A move can be accurate for different reasons. Sometimes the best move is obvious: there is only one legal capture, one simple recapture, or one forced checkmate. Other times the best move is hidden among many plausible alternatives, tactical continuations, quiet preparatory moves, and branching forcing lines.

So the later versions of the analyzer add a second layer:

not only “how good was the move?”, but also “how demanding was the position or search task?”

The current analyzer, v3.6.1, can be understood as a chronological stack of six main layers.

- - - - -

1. WDL Metrics: Measuring Lost Scoring Chances

The base layer is still the WDL system.

Stockfish gives a position in terms of win, draw, and loss chances. These are turned into expected score:

Expected Score = Win + 0.5 × Draw

Then the analyzer compares the player’s move with Stockfish’s preferred move:

Expected-Score Loss = Expected Score after best move − Expected Score after played move

From this, the analyzer creates WDL Accuracy:

WDL Accuracy = 100 × (1 − Expected-Score Loss)

In simple terms:

100 means the move preserved the player’s expected result perfectly.
90 means the move lost 0.10 expected points.
50 means the move lost 0.50 expected points, roughly like turning a win into a draw or a draw into a loss.
This is the foundation. All later difficulty metrics still depend on the same basic question:

How much did the move damage the player’s expected result?

- - - - -

2. All-Legal Difficulty: How Narrow Was the Position?

The first post-WDL layer asks:

In this position, how many reasonable moves were there?

To answer this, the analyzer can evaluate every legal move in a position. It then looks at how much worse the alternatives are compared with the best move.

A position is easier if many legal moves keep the player’s expected score close to the best move.

A position is harder if only one or two moves preserve the player’s chances, while the others lose expected score.

The main ideas are:

Legal RMS Loss
This measures how bad the average legal move is, compared with the best move.

If most legal moves are bad, Legal RMS Loss is high.

Narrowness
This measures how selective the position is.

A narrow position is one where the player has few good choices.

Effective Good Moves
This estimates how many moves function like “good enough” options.

If Effective Good Moves is near 1, the position is almost “only move” territory.

If it is high, the player had many acceptable choices.

Soft-Uncertainty Difficulty
This adjusts difficulty by the practical uncertainty of the position.

A position that is already completely winning or completely lost may be technically sharp, but less practically uncertain. A position where the game result is still unclear receives more practical weight.

In simple terms:

All-legal difficulty measures how hard the position was if we look at every possible legal move.

- - - - -

3. Difficulty-Weighted Accuracy: Accuracy Under Pressure

Once we know how difficult a position was, we can ask:

Did the player stay accurate in the difficult positions?

This creates difficulty-weighted accuracy metrics.

A normal accuracy score treats every move equally.

A difficulty-weighted score gives more importance to positions where the player had a harder choice.

This is useful because two players may have similar raw WDL Accuracy, but one player may have achieved it in easier positions, while the other player kept accuracy in narrow, dangerous, unclear positions.

In simple terms:

Difficulty-weighted accuracy asks whether the player was accurate when accuracy was hardest to maintain.

- - - - -

4. CCP Difficulty: Checks, Captures, and Promotions

The next layer focuses on forcing moves.

In chess, some moves immediately demand attention:

checks,
captures,
promotions.
The analyzer calls these CCP moves.

This is a deliberately simple model. It does not understand every possible threat or strategic idea. But it captures a large part of tactical calculation, because forcing moves are often the backbone of concrete chess analysis.

CCP Difficulty asks:

How many forcing candidate moves existed, and how demanding were they?

It looks at things such as:

how many legal checks are available,
how many captures are available,
whether promotions are possible,
how many forcing candidates are plausible,
whether quiet moves lead to future forcing moves.
A position with many relevant checks, captures, and tactical continuations becomes more forcing-search heavy.

In simple terms:

CCP Difficulty measures the tactical forcing burden of the position.

- - - - -

5. CCP-v2: Recursive Forcing-Line Search Difficulty

The first CCP layer looks mainly at immediate forcing material.

CCP-v2 goes deeper.

Instead of only asking what checks, captures, and promotions exist right now, CCP-v2 asks:

If we follow forcing continuations forward, how large and demanding does the forcing tree become?

This means CCP-v2 recursively explores selected forcing continuations. It tries to estimate the search burden created by chains of forcing moves.

Important CCP-v2 concepts include:

Expanded Positions
How many positions the CCP-v2 tree actually searched.

Leaf Count
How many terminal endpoints the forcing-tree search produced.

Max Chain Length
How deep the longest forcing continuation went.

If this number is high, the position may contain long tactical forcing lines.

Quiet-Pause Burden
Sometimes a forcing sequence includes a quiet move that does not immediately check, capture, or promote, but still keeps the forcing idea alive.

Quiet-pause burden tries to measure those non-immediate moments inside otherwise forcing play.

Branch Total
This is the raw recursive tree-mass score.

It can become extremely large. Because of that, it is useful as an experimental diagnostic, but dangerous as a public headline metric.

Log CCP-v2 Difficulty
To make CCP-v2 more readable, the report also uses log-scaled CCP-v2 metrics.

The log version compresses enormous raw values into a more human-sized scale.

In simple terms:

Raw CCP-v2 asks “how large did the forcing tree become?”
Log CCP-v2 asks the same question on a scale that is easier to compare and publish.

For practical reporting, the log version is currently preferred.

- - - - -

6. CCP-v2 Vision: Looking for Quiet Ideas Before Forcing Lines

Some tactical ideas do not begin with a check, capture, or promotion.

A player may first make a quiet move that prepares a later forcing sequence.

For example, a move may:

increase pressure on a piece,
line up an attack,
prepare a future capture,
create a hidden tactical resource.
The “vision” layer is an attempt to notice some of these quiet preparatory moves.

It does not replace Stockfish. It does not prove that the quiet move is good. It simply helps the analyzer decide which quiet candidate moves are worth sending into the more expensive CCP-v2 search.

In simple terms:

CCP-v2 Vision helps the analyzer notice quiet moves that may lead to forcing play later.

It is a candidate-selection tool, not a final judge.

- - - - -

7. CCP-v2 Two-Stage Probe/Confirm: Search Cheaply, Then Confirm Seriously

CCP-v2 can be expensive because forcing trees can grow very quickly.

The two-stage system was added to use the engine budget more intelligently.

It works like this:

Stage 1: Probe
The analyzer first performs a cheaper search.

The goal is not to fully analyze everything.

The goal is to identify promising root branches:

Which candidate moves seem most worth deeper confirmation?

Stage 2: Confirm
The analyzer then spends a larger search budget only on the selected candidates.

This makes the method more controlled.

Instead of giving every possible branch the same expensive treatment, the analyzer first filters, then confirms.

In simple terms:

Probe/confirm means: search broadly and cheaply first, then search the most relevant branches more seriously.

This is especially useful because CCP-v2 trees can become enormous. Without probe/confirm, the analyzer may spend too much effort on low-value branches.

- - - - -

8. CCP-v2 Root-Branch Diagnostics: What Did the Search Actually Prefer?

The newest layer, added in analyzer v3.6, is root-branch diagnostics.

This produces a separate table where each candidate root move receives its own diagnostic row.

Instead of only saying:

this position had CCP-v2 difficulty 25,

the analyzer can now show:

these were the candidate root moves, this is how they ranked, this is how much search work they consumed, and this is whether they were selected for confirmation.

Root-branch diagnostics can show:

which candidate moves were probed,
which candidate moves were confirmed,
whether the played move was among them,
whether the move was a check, capture, promotion, or quiet move,
how the branch scored,
how much subtree work was spent under that branch,
how many leaves it produced,
how deep its forcing line went,
whether it had delayed payoff,
whether it was selected by the probe stage for confirmation.

In simple terms:

Root-branch diagnostics show the internal candidate-move search behind the CCP-v2 number.

This is important because it lets us inspect the analyzer’s reasoning more directly. We can ask not only “was the position difficult?”, but also:

Which candidate moves made it difficult?

- - - - -

9. CCP-v2 Log-Critical Moves: Where Difficulty Meets Damage

The most useful practical CCP-v2 output is currently:

ccp_v2_log_critical_moves.csv

This file combines two ideas:

the move lost real expected score;
the position had log-scaled CCP-v2 search burden.
So a move becomes highly ranked when it was both:

costly, and
difficult in a forcing-search sense.
This is better than simply listing the largest blunders, because not every blunder is equally difficult.

It is also better than simply listing the hardest positions, because not every hard position led to a mistake.

In simple terms:

Log-critical moves are the places where a difficult forcing-search burden met an actual expected-score loss.

For article writing, this is probably the best current CCP-v2 file.

- - - - -

10. What the Post-WDL Metrics Add

The original WDL metrics answer:

How accurately did the players preserve their scoring chances?

The post-WDL metrics add:

How difficult were those chances to preserve?

The all-legal difficulty layer measures the general narrowness of the position.

The CCP layer measures immediate forcing-move burden.

The CCP-v2 layer measures deeper forcing-line search burden.

The vision layer helps discover quiet moves that may lead into forcing play.

The probe/confirm layer makes the search more efficient.

The root-branch diagnostics show what candidate branches the analyzer actually considered.

Together, these additions move the project from pure accuracy measurement toward a fuller performance profile:

accuracy,
error size,
volatility,
conversion,
positional narrowness,
forcing-move burden,
recursive tactical search burden,
candidate-branch selection,
and critical-move difficulty.
The goal is still not to reduce chess to one number.

The goal is to describe the shape of a performance.

Did the player simply avoid mistakes?

Did the player face narrower choices?

Did the opponent create more forcing problems?

Did the player survive long tactical chains?

Did the mistakes come in easy positions or hard ones?

Did a move fail because the player missed a deep forcing continuation?

These are the questions that the post-WDL metrics try to make measurable.

- - - - -

11. Short Chronological Summary of Analyzer v3.6.1

1. WDL Metrics
Measures move quality by expected-score loss.

Useful for answering: who preserved practical scoring chances better?

2. Match and Game Metrics
Combines move-level WDL values into game and match summaries: Accuracy, Game Accuracy, Mutual Accuracy, PQ, Dominance, Volatility, RMS Loss, Error Concentration, Conversion, HardRAP, and SoftRAP.

Useful for answering: what was the overall performance profile?

3. All-Legal Difficulty Metrics
Evaluates all legal moves in a position to estimate how narrow or forgiving the position was.

Useful for answering: did the player have many acceptable moves, or only a few?

4. Difficulty-Weighted Accuracy
Weights expected-score loss by difficulty.

Useful for answering: did the player stay accurate in the harder positions?

5. CCP Difficulty Metrics
Counts and evaluates forcing-move burden from checks, captures, and promotions.

Useful for answering: how tactical and forcing was the immediate candidate-move situation?

6. CCP-v2 Recursive Search Difficulty
Follows selected forcing continuations deeper into the tree.

Useful for answering: how large and deep was the forcing-line search burden?

7. Log CCP-v2 Metrics
Compresses huge raw CCP-v2 values into a more usable scale.

Useful for answering: how can we compare recursive search burden without raw outliers dominating everything?

8. CCP-v2 Vision
Uses a cheap quiet-move heuristic to find quiet moves that may lead to later forcing ideas.

Useful for answering: are there quiet preparatory moves that deserve CCP-v2 attention?

9. Two-Stage Probe/Confirm
First probes candidate branches cheaply, then confirms selected branches with higher budget.

Useful for answering: how can the analyzer spend expensive search time on the most relevant branches?

10. Root-Branch Diagnostics
Writes one row per candidate root move in the CCP-v2 search.

Useful for answering: which moves were considered, which were confirmed, and why did the tree become difficult?

11. v3.6.1 Sentinel Fix
Prevents invalid internal placeholder values from being treated as real expected scores.

Useful for ensuring that descendant expected-score values stay inside the valid 0–1 range.

- - - - -

12. Practical Reading Guide

For most readers, the order of importance is probably:

WDL Accuracy
Mean and RMS Expected-Score Loss
Game Accuracy and Mutual Accuracy
Performance Quality and Dominance
Volatility and Conversion
All-Legal Difficulty
Difficulty-Weighted Accuracy
CCP Difficulty
CCP-v2 Log Difficulty
CCP-v2 Log-Critical Moves
Root-Branch Diagnostics
The first five tell us what happened in the game.

The next three tell us how difficult the positions were.

The last three tell us where tactical search burden and actual mistakes met.

That is the main conceptual expansion from the original WDL method to analyzer v3.6.1.
