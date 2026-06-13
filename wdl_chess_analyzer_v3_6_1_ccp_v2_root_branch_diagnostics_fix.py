import argparse
import math
import statistics
import numbers
import time
import sys
import platform
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.pgn
import chess.engine
import pandas as pd


# ------------------------------------------------------------
# Basic statistics
# ------------------------------------------------------------

def is_number(value):
    """Return True only for finite numeric scalar values.

    Earlier v3.1.2 treated any non-None non-float-NaN value as numeric,
    so metadata strings such as the script version could reach float(...).
    This stricter helper supports Python and NumPy numeric scalars while
    excluding strings, booleans, None, NaN, and infinities.
    """
    if isinstance(value, bool) or value is None:
        return False
    if not isinstance(value, numbers.Real):
        return False
    return math.isfinite(float(value))


def is_es_value(value):
    """Return True for valid expected-score values only.

    CCP-v2 uses sentinel values such as -1.0 internally for "no descendant".
    Those sentinels must never be propagated as real ES values, because
    1 - (-1) would become an impossible 2.0 for the opponent.
    """
    return is_number(value) and 0.0 <= float(value) <= 1.0


def mean(values):
    values = [v for v in values if is_number(v)]
    return sum(values) / len(values) if values else None


def pstdev(values):
    values = [v for v in values if is_number(v)]
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    return statistics.pstdev(values)


def rms(values):
    values = [v for v in values if is_number(v)]
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))


def safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def weighted_average(values, weights):
    pairs = [
        (v, w)
        for v, w in zip(values, weights)
        if is_number(v) and is_number(w)
    ]

    if not pairs:
        return None

    numerator = sum(v * w for v, w in pairs)
    denominator = sum(w for _, w in pairs)

    if denominator == 0:
        return None

    return numerator / denominator


# ------------------------------------------------------------
# Engine limit / cache helpers
# ------------------------------------------------------------

def make_limit(depth=None, movetime=None, nodes=None):
    """Build a python-chess Limit. Prefer nodes, then movetime, then depth."""
    if nodes is not None:
        return chess.engine.Limit(nodes=nodes)
    if movetime is not None:
        return chess.engine.Limit(time=movetime)
    return chess.engine.Limit(depth=depth)


def limit_signature(label, depth=None, movetime=None, nodes=None):
    if nodes is not None:
        return f"{label}:nodes={nodes}"
    if movetime is not None:
        return f"{label}:time={movetime}"
    return f"{label}:depth={depth}"


def safe_sum(values):
    return sum(v for v in values if is_number(v))


# ------------------------------------------------------------
# WDL / Expected Score
# ------------------------------------------------------------

def result_score_for_white(result):
    if result == "1-0":
        return 1.0
    if result == "0-1":
        return 0.0
    if result == "1/2-1/2":
        return 0.5
    return None


def score_for_player(result, color):
    white_score = result_score_for_white(result)

    if white_score is None:
        return None

    return white_score if color == chess.WHITE else 1.0 - white_score


def terminal_expected_score_white(board):
    if not board.is_game_over(claim_draw=True):
        return None

    result = board.result(claim_draw=True)

    if result == "1-0":
        return 1.0
    if result == "0-1":
        return 0.0
    return 0.5


def extract_wdl_tuple(wdl_obj, pov_color):
    """
    Returns W, D, L from a given point of view.

    Stockfish WDL is usually in permille:
    W + D + L = 1000.
    """

    if hasattr(wdl_obj, "pov"):
        wdl = wdl_obj.pov(pov_color)
    else:
        wdl = wdl_obj

    wins = wdl.wins
    draws = wdl.draws
    losses = wdl.losses

    return wins, draws, losses


def expected_score_from_wdl(wdl_obj, pov_color):
    wins, draws, losses = extract_wdl_tuple(wdl_obj, pov_color)
    total = wins + draws + losses

    if total == 0:
        return None

    return (wins + 0.5 * draws) / total


def analyse_es_white(engine, board, limit, cache=None, cache_key_extra="main", stats=None):
    """
    Expected Score from White's perspective.

    ES = W + 0.5D

    If cache is supplied, positions are cached by FEN plus a limit signature.
    This helps with repeated positions and with avoiding duplicated played-move
    evaluations inside the difficulty loop.
    """

    terminal = terminal_expected_score_white(board)

    if terminal is not None:
        return terminal

    key = None
    if cache is not None:
        key = (board.fen(), cache_key_extra)
        if key in cache:
            if stats is not None:
                stats["cache_hits"] = stats.get("cache_hits", 0) + 1
            return cache[key]

    if stats is not None:
        stats["engine_calls"] = stats.get("engine_calls", 0) + 1

    info = engine.analyse(board, limit)

    if stats is not None:
        # Capture search-work diagnostics when python-chess exposes them.
        # These are especially useful for comparing node-limited vs time-limited runs.
        if is_number(info.get("nodes")):
            stats["nodes_searched_total"] = stats.get("nodes_searched_total", 0) + info.get("nodes")
        if is_number(info.get("time")):
            stats["engine_reported_time_total"] = stats.get("engine_reported_time_total", 0.0) + info.get("time")
        if is_number(info.get("nps")):
            stats.setdefault("nps_values", []).append(info.get("nps"))
        if is_number(info.get("hashfull")):
            stats.setdefault("hashfull_values", []).append(info.get("hashfull"))

    if "wdl" not in info:
        raise RuntimeError(
            "No WDL found. Check that Stockfish supports UCI_ShowWDL "
            "and that engine.configure({'UCI_ShowWDL': True}) worked."
        )

    value = expected_score_from_wdl(info["wdl"], chess.WHITE)

    if cache is not None and key is not None:
        cache[key] = value

    return value


def es_for_color(es_white, color):
    """
    Converts White expected score into the chosen player's expected score.
    """

    if es_white is None:
        return None
    if color == chess.WHITE:
        return es_white
    return 1.0 - es_white




# ------------------------------------------------------------
# CCP Search Difficulty helpers (Checks, Captures, Promotions)
# ------------------------------------------------------------

PIECE_VALUES = {
    chess.PAWN: 1.0,
    chess.KNIGHT: 3.0,
    chess.BISHOP: 3.0,
    chess.ROOK: 5.0,
    chess.QUEEN: 9.0,
    chess.KING: 0.0,
}


def piece_value(piece_or_type):
    """Classical material value used only for CCP diagnostics."""
    if piece_or_type is None:
        return 0.0
    if isinstance(piece_or_type, chess.Piece):
        return PIECE_VALUES.get(piece_or_type.piece_type, 0.0)
    return PIECE_VALUES.get(piece_or_type, 0.0)


def captured_piece_for_move(board, move):
    """Return the piece captured by move, including en passant."""
    if not board.is_capture(move):
        return None
    if board.is_en_passant(move):
        direction = -8 if board.turn == chess.WHITE else 8
        return board.piece_at(move.to_square + direction)
    return board.piece_at(move.to_square)


def promotion_gain_value(move):
    """Promotion gain over the original pawn; Q=8, R=4, B/N=2."""
    if move.promotion is None:
        return 0.0
    return max(0.0, piece_value(move.promotion) - piece_value(chess.PAWN))


def capture_material_value(board, move):
    return piece_value(captured_piece_for_move(board, move))


def ccp_material_event_value(board, move):
    """Material-event size for checks/captures/promotions diagnostics."""
    return capture_material_value(board, move) + promotion_gain_value(move)


def attacked_material_summary(board, victim_color, attacker_color=None):
    """Summarize victim_color material attacked by attacker_color.

    This is deliberately simple and classical-material based. It is not used as
    a replacement for Stockfish ES; it only supplies human-candidate diagnostics
    and a lightweight quiet-to-CCP threat proxy.
    """
    if attacker_color is None:
        attacker_color = not victim_color

    total = 0.0
    highest = 0.0
    count = 0
    for sq, piece in board.piece_map().items():
        if piece.color != victim_color:
            continue
        if board.attackers(attacker_color, sq):
            val = piece_value(piece)
            total += val
            highest = max(highest, val)
            count += 1
    return {
        "attacked_material_value": total,
        "highest_attacked_piece_value": highest,
        "attacked_material_count": count,
    }


def move_is_recapture(board, move, previous_move=None):
    """A simple recapture flag: capture on the previous move's destination."""
    if previous_move is None or not board.is_capture(move):
        return False
    return move.to_square == previous_move.to_square


def move_captures_attacker(board, move, mover_color):
    """True if the captured piece was attacking any of mover's material."""
    if not board.is_capture(move):
        return False
    captured_square = move.to_square
    if board.is_en_passant(move):
        captured_square = move.to_square + (-8 if mover_color == chess.WHITE else 8)
    captured_piece = board.piece_at(captured_square)
    if captured_piece is None:
        return False
    own_squares = chess.SquareSet(board.occupied_co[mover_color])
    return bool(board.attacks(captured_square) & own_squares)


def move_saves_material(board, move, mover_color):
    """True if mover's attacked material is lower after the move.

    This is intentionally a diagnostic, not an obviousness multiplier.
    """
    before = attacked_material_summary(board, victim_color=mover_color)
    before_total = before["attacked_material_value"]
    try:
        board.push(move)
        after = attacked_material_summary(board, victim_color=mover_color)
        after_total = after["attacked_material_value"]
    finally:
        board.pop()
    return after_total < before_total


def classify_ccp_move(board, move, previous_move=None):
    """Classify one move for Checks/Captures/Promotions diagnostics."""
    mover = board.turn
    is_check = board.gives_check(move)
    is_capture = board.is_capture(move)
    is_promotion = move.promotion is not None
    return {
        "is_check": bool(is_check),
        "is_capture": bool(is_capture),
        "is_promotion": bool(is_promotion),
        "is_ccp": bool(is_check or is_capture or is_promotion),
        "is_recapture": bool(move_is_recapture(board, move, previous_move=previous_move)),
        "captures_attacker": bool(move_captures_attacker(board, move, mover)),
        "saves_material": bool(move_saves_material(board, move, mover)),
        "capture_material_value": capture_material_value(board, move),
        "promotion_gain_value": promotion_gain_value(move),
        "material_event_value": ccp_material_event_value(board, move),
    }


def effective_count_from_weights(weights):
    weights = [w for w in weights if is_number(w) and w > 0]
    if not weights:
        return None
    total = sum(weights)
    if total <= 0:
        return None
    probs = [w / total for w in weights]
    denom = sum(p * p for p in probs)
    if denom <= 0:
        return None
    return 1.0 / denom


def analyze_ccp_search_difficulty(board, difficulty, es_before_mover, previous_move=None, tau=0.03, quiet_depth_bonus=1.5):
    """Compute Version-1 CCP Search Difficulty diagnostics.

    CCP = Checks, Captures, Promotions.

    Version 1 intentionally does NOT include an obviousness multiplier. Recapture,
    captures-attacker, and material-safety are saved only as diagnostics.

    Immediate CCP burden:
        sum over checking/capturing/promoting legal moves of
        |ES_after - ES_before| * exp(-(B - ES_after)/tau)

    Quiet-to-CCP burden:
        a lightweight non-null-move proxy for quiet moves that create material
        attack pressure, weighted by the same Stockfish plausibility term. This
        keeps "threats" as quiet moves before later CCP events without switching
        side-to-move or building a deep tree yet.
    """
    legal_moves = list(board.legal_moves)
    mover = board.turn
    opponent = not mover

    out = {
        "ccp_legal_check_count": 0,
        "ccp_legal_capture_count": 0,
        "ccp_legal_promotion_count": 0,
        "ccp_legal_immediate_count": 0,
        "ccp_attacked_material_value": None,
        "ccp_highest_attacked_piece_value": None,
        "ccp_attacked_material_count": None,
        "ccp_immediate_burden": 0.0,
        "ccp_quiet_to_ccp_burden": 0.0,
        "ccp_total_burden": 0.0,
        "ccp_candidate_effective_count": None,
        "ccp_candidate_ambiguity": 0.0,
        "ccp_search_difficulty_pure": 0.0,
        "ccp_search_difficulty_soft": 0.0,
    }

    attacked = attacked_material_summary(board, victim_color=mover)
    out.update({
        "ccp_attacked_material_value": attacked["attacked_material_value"],
        "ccp_highest_attacked_piece_value": attacked["highest_attacked_piece_value"],
        "ccp_attacked_material_count": attacked["attacked_material_count"],
    })

    move_rows = difficulty.get("_legal_move_rows") or []
    es_by_uci = {
        r.get("move_uci"): r.get("es_after_mover")
        for r in move_rows
        if r.get("move_uci") is not None
    }
    best_es = difficulty.get("legal_best_es_mover")
    soft_leverage = difficulty.get("soft_uncertainty_leverage")

    if not is_number(best_es):
        return out

    mover_attacks_before = attacked_material_summary(board, victim_color=opponent, attacker_color=mover)
    candidate_weights = []
    immediate_burden = 0.0
    quiet_burden = 0.0

    best_move_uci = None
    best_move_es = None
    for uci, es in es_by_uci.items():
        if is_number(es) and (best_move_es is None or es > best_move_es):
            best_move_es = es
            best_move_uci = uci

    played_flags = {}
    best_flags = {}

    for move in legal_moves:
        uci = move.uci()
        flags = classify_ccp_move(board, move, previous_move=previous_move)
        es_after = es_by_uci.get(uci)
        if not is_number(es_after):
            continue

        if flags["is_check"]:
            out["ccp_legal_check_count"] += 1
        if flags["is_capture"]:
            out["ccp_legal_capture_count"] += 1
        if flags["is_promotion"]:
            out["ccp_legal_promotion_count"] += 1
        if flags["is_ccp"]:
            out["ccp_legal_immediate_count"] += 1

        loss_from_best = max(0.0, best_es - es_after)
        plausibility = math.exp(-loss_from_best / tau) if tau > 0 else 0.0
        es_swing = abs(es_after - es_before_mover) if is_number(es_before_mover) else 0.0

        if flags["is_ccp"]:
            value = es_swing
            # Material is only a secondary floor: it helps flag forcing material
            # events in positions where WDL ES is locally compressed.
            material_floor = min(1.0, flags["material_event_value"] / 9.0) * 0.05
            value = max(value, material_floor)
            score = value * plausibility
            immediate_burden += score
            candidate_weights.append(plausibility)
        else:
            # Quiet-to-CCP Version 1: proxy quiet threats by newly attacked material
            # after the quiet move. This avoids null-move threat mode and deep tree
            # expansion while still detecting quiet moves that create later captures.
            try:
                board.push(move)
                mover_attacks_after = attacked_material_summary(board, victim_color=opponent, attacker_color=mover)
            finally:
                board.pop()
            delta_total = max(0.0, mover_attacks_after["attacked_material_value"] - mover_attacks_before["attacked_material_value"])
            delta_highest = max(0.0, mover_attacks_after["highest_attacked_piece_value"] - mover_attacks_before["highest_attacked_piece_value"])
            future_ccp_proxy = min(1.0, max(delta_total / 9.0, delta_highest / 9.0))
            if future_ccp_proxy > 0:
                score = quiet_depth_bonus * future_ccp_proxy * plausibility
                quiet_burden += score
                candidate_weights.append(plausibility * future_ccp_proxy)

        if uci == best_move_uci:
            best_flags = flags

    n_eff = effective_count_from_weights(candidate_weights)
    ambiguity = math.log(1.0 + n_eff) if is_number(n_eff) else 0.0
    total_burden = immediate_burden + quiet_burden
    pure = total_burden * ambiguity
    soft = pure * soft_leverage if is_number(soft_leverage) else None

    out.update({
        "ccp_immediate_burden": immediate_burden,
        "ccp_quiet_to_ccp_burden": quiet_burden,
        "ccp_total_burden": total_burden,
        "ccp_candidate_effective_count": n_eff,
        "ccp_candidate_ambiguity": ambiguity,
        "ccp_search_difficulty_pure": pure,
        "ccp_search_difficulty_soft": soft,
    })

    # Played/best flags are filled by caller for the actual played move too.
    for prefix, flags in (("ccp_best", best_flags),):
        out[f"{prefix}_is_check"] = bool(flags.get("is_check", False))
        out[f"{prefix}_is_capture"] = bool(flags.get("is_capture", False))
        out[f"{prefix}_is_promotion"] = bool(flags.get("is_promotion", False))
        out[f"{prefix}_is_ccp"] = bool(flags.get("is_ccp", False))
        out[f"{prefix}_is_recapture"] = bool(flags.get("is_recapture", False))
        out[f"{prefix}_captures_attacker"] = bool(flags.get("captures_attacker", False))
        out[f"{prefix}_saves_material"] = bool(flags.get("saves_material", False))

    return out


def played_ccp_flags(board, move, previous_move=None):
    flags = classify_ccp_move(board, move, previous_move=previous_move)
    return {
        "ccp_played_is_check": bool(flags["is_check"]),
        "ccp_played_is_capture": bool(flags["is_capture"]),
        "ccp_played_is_promotion": bool(flags["is_promotion"]),
        "ccp_played_is_ccp": bool(flags["is_ccp"]),
        "ccp_played_is_recapture": bool(flags["is_recapture"]),
        "ccp_played_captures_attacker": bool(flags["captures_attacker"]),
        "ccp_played_saves_material": bool(flags["saves_material"]),
    }


# ------------------------------------------------------------
# CCP Search Difficulty Version 2 helpers
# ------------------------------------------------------------

def _ccp_v2_soft_plausibility(best_es, es, tau):
    if not is_number(best_es) or not is_number(es) or tau <= 0:
        return 0.0
    return math.exp(-max(0.0, best_es - es) / tau)


def _ccp_v2_update_best_es(result, es_white, depth_from_node):
    """Track best descendant ES for both colors within a subtree."""
    if not is_es_value(es_white):
        return
    es_black = 1.0 - float(es_white)
    if es_white > result.get("max_es_white", -1.0):
        result["max_es_white"] = es_white
        result["best_depth_white"] = depth_from_node
    if es_black > result.get("max_es_black", -1.0):
        result["max_es_black"] = es_black
        result["best_depth_black"] = depth_from_node



def _ccp_v2_cap_exhausted(state, max_engine_evals_per_root):
    """Return True if the CCP-v2 per-root evaluation cap has been reached."""
    return bool(max_engine_evals_per_root and max_engine_evals_per_root > 0 and state.get("evals", 0) >= max_engine_evals_per_root)


def _ccp_v2_eval_position_with_cap(engine, board, limit, cache, cache_key_extra, stats, state, max_engine_evals_per_root):
    """Evaluate one position for CCP-v2, respecting a per-root eval-attempt cap."""
    if _ccp_v2_cap_exhausted(state, max_engine_evals_per_root):
        state["cap_hit"] = True
        if stats is not None:
            stats["ccp_v2_eval_cap_hits"] = stats.get("ccp_v2_eval_cap_hits", 0) + 1
        return None
    state["evals"] = state.get("evals", 0) + 1
    if stats is not None:
        stats["ccp_v2_eval_attempts"] = stats.get("ccp_v2_eval_attempts", 0) + 1
    return analyse_es_white(
        engine,
        board,
        limit,
        cache=cache,
        cache_key_extra=cache_key_extra,
        stats=stats,
    )


def _ccp_v2_quiet_proxy(board, move, mover, opponent, attacks_before):
    """Cheap, non-engine proxy for whether a quiet move may create later CCP relevance.

    This is intentionally not a final score. It only decides which quiet moves are
    worth evaluating inside the CCP-v2 candidate tree. A quiet move that increases
    attacks on opposing material is more likely to be a quiet-to-CCP candidate.
    """
    try:
        board.push(move)
        attacks_after = attacked_material_summary(board, victim_color=opponent, attacker_color=mover)
    finally:
        board.pop()
    delta_total = max(0.0, attacks_after["attacked_material_value"] - attacks_before["attacked_material_value"])
    delta_highest = max(0.0, attacks_after["highest_attacked_piece_value"] - attacks_before["highest_attacked_piece_value"])
    return min(1.0, max(delta_total / 9.0, delta_highest / 9.0))





def _ccp_v2_ideal_vision_proxy(board, move, mover, opponent, depth=0, max_branch=6, decay=0.65):
    """Cheap one-sided "ideal vision" proxy for quiet-move prioritization.

    This deliberately does NOT try to replace Stockfish. It is a non-engine
    resource-allocation heuristic: after the candidate move, temporarily let
    the same side move again (opponent "unbothered"/pass approximation) and
    ask whether that side can build checks, captures, promotions, or increasing
    attacks on material within a few self-move steps.

    The proxy is used only to rank/select quiet candidates before expensive
    CCP-v2 engine evaluation. It is not used as the final CCP difficulty value.
    Because chess has no pass, this is an approximation and is disabled unless
    --ccp-v2-vision-depth is positive.
    """
    if depth is None or depth <= 0:
        return 0.0
    try:
        before_attack = attacked_material_summary(board, victim_color=opponent, attacker_color=mover)
        flags = classify_ccp_move(board, move)
        material_event = ccp_material_event_value(board, move) / 9.0
        immediate = 0.0
        if flags.get("is_check"):
            immediate = max(immediate, 0.50)
        if flags.get("is_promotion"):
            immediate = max(immediate, 8.0 / 9.0)
        if flags.get("is_capture"):
            immediate = max(immediate, min(1.0, material_event))

        board.push(move)
        old_turn = board.turn
        try:
            # Opponent-pass approximation: keep asking what the original mover
            # would like to do next if allowed to continue the vision.
            board.turn = mover
            after_attack = attacked_material_summary(board, victim_color=opponent, attacker_color=mover)
            delta_total = max(0.0, after_attack["attacked_material_value"] - before_attack["attacked_material_value"])
            delta_highest = max(0.0, after_attack["highest_attacked_piece_value"] - before_attack["highest_attacked_piece_value"])
            attack_gain = min(1.0, max(delta_total / 9.0, delta_highest / 9.0))
            base = max(immediate, attack_gain)

            if depth <= 1 or board.is_game_over(claim_draw=True):
                return base

            child_rows = []
            for child_move in list(board.legal_moves):
                try:
                    child_flags = classify_ccp_move(board, child_move)
                    child_event = ccp_material_event_value(board, child_move) / 9.0
                    child_ccp = 0.0
                    if child_flags.get("is_check"):
                        child_ccp = max(child_ccp, 0.50)
                    if child_flags.get("is_promotion"):
                        child_ccp = max(child_ccp, 8.0 / 9.0)
                    if child_flags.get("is_capture"):
                        child_ccp = max(child_ccp, min(1.0, child_event))
                    # Quiet moves can still be valuable if they increase future
                    # attack pressure; recurse to see whether they become CCP.
                    child_rows.append((child_ccp, child_move))
                except Exception:
                    continue
            child_rows.sort(key=lambda x: x[0], reverse=True)
            if max_branch and max_branch > 0:
                child_rows = child_rows[:max_branch]
            best_child = 0.0
            for _, child_move in child_rows:
                best_child = max(best_child, _ccp_v2_ideal_vision_proxy(
                    board, child_move, mover, opponent,
                    depth=depth-1, max_branch=max_branch, decay=decay,
                ))
            return max(base, base + decay * best_child)
        finally:
            board.turn = old_turn
            board.pop()
    except Exception:
        # Candidate selection must never fail the real analysis.
        try:
            if board.move_stack and board.peek() == move:
                board.pop()
        except Exception:
            pass
        return 0.0


def _ccp_v2_select_candidate_moves(
    board,
    previous_move=None,
    quiet_candidates=4,
    include_all_root_quiet=False,
    root_played_move=None,
    root_node=False,
    stats=None,
    vision_depth=0,
    vision_branch=6,
    vision_decay=0.65,
    vision_mode="root",
    vision_candidates=12,
    root_allowed_moves=None,
):
    """Select candidate moves for a CCP-v2 tree node before engine evaluation.

    The expensive v3.3 implementation evaluated every legal child at every
    expanded tree node. This version evaluates only:
      * all checks, captures, and promotions;
      * quiet moves with positive cheap quiet-to-CCP proxy, capped by
        quiet_candidates unless include_all_root_quiet is enabled at the root;
      * the actual played move at the root, if supplied.

    v3.4.2 important change:
      The optional one-sided ideal-vision proxy is no longer run for every
      quiet move at every internal CCP-v2 node. By default it is ROOT-ONLY and
      PRE-FILTERED: first compute the cheap attack-gain quiet proxy, then run
      vision only on the top --ccp-v2-vision-candidates shallow quiet moves
      (plus the forced played root move if present). This prevents Python-side
      vision recursion from dominating runtime.
    """
    mover = board.turn
    opponent = not mover
    legal_moves = list(board.legal_moves)
    if stats is not None:
        stats["ccp_v2_legal_moves_seen"] = stats.get("ccp_v2_legal_moves_seen", 0) + len(legal_moves)

    # Normalize vision controls. Depth 0 or mode "off" disables vision.
    vision_mode = (vision_mode or "root").lower()
    use_vision_here = bool(
        vision_depth and vision_depth > 0 and
        vision_mode != "off" and
        (vision_mode == "all" or (vision_mode == "root" and root_node))
    )

    attacks_before = attacked_material_summary(board, victim_color=opponent, attacker_color=mover)
    ccp_rows = []
    quiet_rows_all = []
    root_played_uci = root_played_move.uci() if root_played_move is not None else None
    allowed_root_set = set(root_allowed_moves or []) if root_node else set()

    for move in legal_moves:
        flags = classify_ccp_move(board, move, previous_move=previous_move)
        row = {
            "move": move,
            "move_uci": move.uci(),
            "flags": flags,
            "quiet_proxy": 0.0,
            "quiet_attack_proxy": 0.0,
            "quiet_vision_proxy": 0.0,
            "forced_inclusion": False,
        }
        if flags.get("is_ccp"):
            ccp_rows.append(row)
        else:
            proxy = _ccp_v2_quiet_proxy(board, move, mover, opponent, attacks_before)
            row["quiet_proxy"] = proxy
            row["quiet_attack_proxy"] = proxy
            if root_node and ((root_played_uci and row["move_uci"] == root_played_uci) or row["move_uci"] in allowed_root_set):
                row["forced_inclusion"] = True
            # Keep all quiet rows temporarily so root-only vision can be applied
            # to a small pre-filtered pool before final pruning.
            quiet_rows_all.append(row)

    # Deduplicate quiet rows, preserving forced played move if present.
    dedup = {}
    for row in quiet_rows_all:
        old = dedup.get(row["move_uci"])
        if old is None or row.get("forced_inclusion"):
            dedup[row["move_uci"]] = row
    quiet_rows_all = list(dedup.values())

    # Optional root-only / pre-filtered vision pass.
    if use_vision_here and quiet_rows_all:
        if vision_candidates is None:
            vision_candidates = 12
        # Forced played move should be eligible even if its shallow proxy is 0.
        forced = [r for r in quiet_rows_all if r.get("forced_inclusion")]
        non_forced_positive = [r for r in quiet_rows_all if (not r.get("forced_inclusion")) and r.get("quiet_attack_proxy", 0.0) > 0]
        non_forced_positive.sort(key=lambda r: r.get("quiet_attack_proxy", 0.0), reverse=True)
        if vision_candidates >= 0:
            vision_pool = forced + non_forced_positive[:vision_candidates]
        else:
            vision_pool = forced + non_forced_positive
        # Deduplicate pool.
        pool_by_uci = {}
        for r in vision_pool:
            pool_by_uci[r["move_uci"]] = r
        vision_pool = list(pool_by_uci.values())
        if stats is not None:
            stats["ccp_v2_vision_candidate_moves_seen"] = stats.get("ccp_v2_vision_candidate_moves_seen", 0) + len(vision_pool)
        for row in vision_pool:
            t0 = time.perf_counter()
            vision_proxy = _ccp_v2_ideal_vision_proxy(
                board,
                row["move"],
                mover,
                opponent,
                depth=vision_depth,
                max_branch=vision_branch,
                decay=vision_decay,
            )
            if stats is not None:
                stats["ccp_v2_vision_probes"] = stats.get("ccp_v2_vision_probes", 0) + 1
                stats["ccp_v2_vision_seconds"] = stats.get("ccp_v2_vision_seconds", 0.0) + (time.perf_counter() - t0)
            row["quiet_vision_proxy"] = vision_proxy
            row["quiet_proxy"] = max(row.get("quiet_attack_proxy", 0.0), vision_proxy)
    elif vision_depth and vision_depth > 0 and stats is not None:
        if vision_mode == "root" and not root_node:
            stats["ccp_v2_vision_skipped_nonroot_nodes"] = stats.get("ccp_v2_vision_skipped_nonroot_nodes", 0) + 1

    # Keep quiet moves with positive final proxy, plus forced played move.
    quiet_rows = [r for r in quiet_rows_all if r.get("quiet_proxy", 0.0) > 0 or r.get("forced_inclusion")]
    quiet_rows.sort(key=lambda r: (1 if r.get("forced_inclusion") else 0, r.get("quiet_proxy", 0.0)), reverse=True)

    if not (root_node and include_all_root_quiet):
        if quiet_candidates is None:
            quiet_candidates = 4
        if quiet_candidates >= 0:
            # Always preserve a forced played move if present.
            forced = [r for r in quiet_rows if r.get("forced_inclusion")]
            non_forced = [r for r in quiet_rows if not r.get("forced_inclusion")]
            quiet_rows = forced + non_forced[:quiet_candidates]

    selected = ccp_rows + quiet_rows
    # Deduplicate again in case a legal move is somehow included twice.
    by_uci = {}
    for row in selected:
        by_uci[row["move_uci"]] = row
    selected = list(by_uci.values())

    if stats is not None:
        stats["ccp_v2_ccp_candidates_selected"] = stats.get("ccp_v2_ccp_candidates_selected", 0) + len(ccp_rows)
        stats["ccp_v2_quiet_candidates_selected"] = stats.get("ccp_v2_quiet_candidates_selected", 0) + len(quiet_rows)
        stats["ccp_v2_candidate_moves_selected"] = stats.get("ccp_v2_candidate_moves_selected", 0) + len(selected)
    return selected

def _ccp_v2_eval_moves(engine, board, limit, cache, cache_key_extra, stats, state, max_engine_evals_per_root=0, quiet_candidates=4, include_all_root_quiet=False, root_played_move=None, root_node=False, previous_move=None, vision_depth=0, vision_branch=6, vision_decay=0.65, vision_mode="root", vision_candidates=12, root_allowed_moves=None):
    """Evaluate selected CCP-v2 candidate moves, not every legal move.

    Values are stored from the local mover's perspective. This avoids the v3.3
    all-legal mini-scan at every internal CCP-v2 tree node.
    """
    mover = board.turn
    candidates = _ccp_v2_select_candidate_moves(
        board,
        previous_move=previous_move,
        quiet_candidates=quiet_candidates,
        include_all_root_quiet=include_all_root_quiet,
        root_played_move=root_played_move,
        root_node=root_node,
        stats=stats,
        vision_depth=vision_depth,
        vision_branch=vision_branch,
        vision_decay=vision_decay,
        vision_mode=vision_mode,
        vision_candidates=vision_candidates,
        root_allowed_moves=root_allowed_moves,
    )
    if root_node and root_allowed_moves:
        allowed = set(root_allowed_moves)
        candidates = [r for r in candidates if r.get("move_uci") in allowed]
    rows = []
    for row in candidates:
        if _ccp_v2_cap_exhausted(state, max_engine_evals_per_root):
            state["cap_hit"] = True
            if stats is not None:
                stats["ccp_v2_child_evals_skipped_by_cap"] = stats.get("ccp_v2_child_evals_skipped_by_cap", 0) + 1
            break
        move = row["move"]
        board.push(move)
        es_after_white = _ccp_v2_eval_position_with_cap(
            engine,
            board,
            limit,
            cache,
            cache_key_extra,
            stats,
            state,
            max_engine_evals_per_root,
        )
        board.pop()
        if not is_number(es_after_white):
            continue
        row = dict(row)
        row.update({
            "es_after_white": es_after_white,
            "es_after_mover": es_for_color(es_after_white, mover),
        })
        rows.append(row)
        if stats is not None:
            stats["ccp_v2_child_moves_evaluated"] = stats.get("ccp_v2_child_moves_evaluated", 0) + 1
    return rows

def _ccp_v2_candidate_order(rows, best_es, tau, max_branch=0, min_plausibility=0.0):
    """Order candidate moves for tree expansion.

    Conceptually, CCP-v2 can include all quiet moves. Practically, this function
    allows optional pruning by local inferiority/plausibility and optional branch
    cap. A max_branch of 0 means no branch-count cap.
    """
    ordered = []
    for r in rows:
        es = r.get("es_after_mover")
        if not is_number(es):
            continue
        plaus = _ccp_v2_soft_plausibility(best_es, es, tau)
        if plaus < min_plausibility:
            continue
        r = dict(r)
        r["plausibility"] = plaus
        # Prefer plausible moves; within equal plausibility, CCP moves first.
        r["priority"] = (plaus, 1 if r["flags"].get("is_ccp") else 0)
        ordered.append(r)
    ordered.sort(key=lambda x: x["priority"], reverse=True)
    if max_branch and max_branch > 0:
        ordered = ordered[:max_branch]
    return ordered


def analyze_ccp_v2_node(
    engine,
    board,
    limit,
    cache,
    cache_key_extra,
    stats,
    depth_remaining,
    tau=0.03,
    max_tree_nodes=200,
    max_branch=0,
    min_plausibility=0.0,
    alpha_chain=0.25,
    beta_quiet=0.50,
    child_weight=0.50,
    state=None,
    in_forcing_chain=False,
    max_engine_evals_per_root=0,
    quiet_candidates=4,
    include_all_root_quiet=False,
    root_played_move=None,
    root_node=False,
    previous_move=None,
    vision_depth=0,
    vision_branch=6,
    vision_decay=0.65,
    vision_mode="root",
    vision_candidates=12,
    root_allowed_moves=None,
):
    """Recursive CCP Search Difficulty v2 candidate-tree search.

    CCP-v2 is experimental and intentionally separate from the objective
    all-legal difficulty metrics and CCP-v1 root burden.

    Core principles:
      * CCP = checks, captures, promotions.
      * Immediate positive CCP gains count directly.
      * Quiet moves and initially negative CCP moves count only if deeper CCP
        continuation restores/improves ES across the node's preference balance.
      * Branches fade continuously by local inferiority via a soft plausibility
        weight exp(-(B_node - ES_i) / tau).
      * The tree stops by depth, tree-node budget, terminal positions, or lack
        of candidate continuation.
    """
    if state is None:
        state = {"nodes": 0, "evals": 0, "cap_hit": False}
    if state.get("nodes", 0) >= max_tree_nodes:
        return {
            "branch_scores": [],
            "branch_total": 0.0,
            "branch_max": 0.0,
            "branch_mean": 0.0,
            "branch_effective_count": None,
            "branch_ambiguity": 0.0,
            "max_chain_length": 0,
            "total_chain_length": 0,
            "quiet_pause_count": 0,
            "quiet_pause_burden": 0.0,
            "nodes_searched": 0,
            "leaf_count": 1,
            "has_ccp": False,
            "max_es_white": es_for_color(es_for_color(None, chess.WHITE), chess.WHITE) if False else -1.0,
            "max_es_black": -1.0,
            "best_depth_white": None,
            "best_depth_black": None,
            "root_branch_rows": [],
        }

    state["nodes"] = state.get("nodes", 0) + 1
    if stats is not None:
        stats["ccp_v2_positions"] = stats.get("ccp_v2_positions", 0) + 1

    mover = board.turn
    es_node_white = _ccp_v2_eval_position_with_cap(
        engine,
        board,
        limit,
        cache,
        cache_key_extra,
        stats,
        state,
        max_engine_evals_per_root,
    )
    es_node_mover = es_for_color(es_node_white, mover)

    result = {
        "branch_scores": [],
        "branch_total": 0.0,
        "branch_max": 0.0,
        "branch_mean": 0.0,
        "branch_effective_count": None,
        "branch_ambiguity": 0.0,
        "max_chain_length": 0,
        "total_chain_length": 0,
        "quiet_pause_count": 0,
        "quiet_pause_burden": 0.0,
        "nodes_searched": 1,
        "leaf_count": 0,
        "has_ccp": False,
        "max_es_white": -1.0,
        "max_es_black": -1.0,
        "best_depth_white": None,
        "best_depth_black": None,
        "root_branch_rows": [],
    }
    _ccp_v2_update_best_es(result, es_node_white, 0)

    if depth_remaining <= 0 or board.is_game_over(claim_draw=True) or not is_number(es_node_mover):
        result["leaf_count"] = 1
        return result

    rows = _ccp_v2_eval_moves(
        engine,
        board,
        limit,
        cache,
        cache_key_extra,
        stats,
        state,
        max_engine_evals_per_root=max_engine_evals_per_root,
        quiet_candidates=quiet_candidates,
        include_all_root_quiet=include_all_root_quiet,
        root_played_move=root_played_move,
        root_node=root_node,
        previous_move=previous_move,
        vision_depth=vision_depth,
        vision_branch=vision_branch,
        vision_decay=vision_decay,
        vision_mode=vision_mode,
        vision_candidates=vision_candidates,
        root_allowed_moves=root_allowed_moves,
    )
    es_values = [r["es_after_mover"] for r in rows if is_number(r.get("es_after_mover"))]
    if not es_values:
        result["leaf_count"] = 1
        return result

    best_es = max(es_values)
    candidates = _ccp_v2_candidate_order(
        rows,
        best_es=best_es,
        tau=tau,
        max_branch=max_branch,
        min_plausibility=min_plausibility,
    )
    if not candidates:
        result["leaf_count"] = 1
        return result

    # Immediate local CCP existence is a diagnostic and quiescence indicator.
    result["has_ccp"] = any(r["flags"].get("is_ccp") for r in candidates)

    for r in candidates:
        if state.get("nodes", 0) >= max_tree_nodes:
            break
        move = r["move"]
        flags = r["flags"]
        es_after = r.get("es_after_mover")
        es_after_white = r.get("es_after_white")
        plaus = r.get("plausibility", 0.0)
        if not is_number(es_after) or not is_number(plaus):
            continue

        _ccp_v2_update_best_es(result, es_after_white, 1)

        gain = max(0.0, es_after - es_node_mover)
        pre_loss = max(0.0, es_node_mover - es_after)
        is_ccp = bool(flags.get("is_ccp"))

        immediate_value = gain if is_ccp else 0.0
        child = None
        child_best_for_mover = None
        payoff_depth = None
        delayed_payoff = 0.0
        quiet_pause = 0
        quiet_pause_burden = 0.0
        branch_chain = 1 if is_ccp else 0
        branch_total_chain = branch_chain
        branch_has_ccp = is_ccp
        leaf_count_add = 0

        if depth_remaining > 1:
            board.push(move)
            child = analyze_ccp_v2_node(
                engine=engine,
                board=board,
                limit=limit,
                cache=cache,
                cache_key_extra=cache_key_extra,
                stats=stats,
                depth_remaining=depth_remaining - 1,
                tau=tau,
                max_tree_nodes=max_tree_nodes,
                max_branch=max_branch,
                min_plausibility=min_plausibility,
                alpha_chain=alpha_chain,
                beta_quiet=beta_quiet,
                child_weight=child_weight,
                state=state,
                in_forcing_chain=(in_forcing_chain or is_ccp),
                max_engine_evals_per_root=max_engine_evals_per_root,
                quiet_candidates=quiet_candidates,
                include_all_root_quiet=include_all_root_quiet,
                root_played_move=None,
                root_node=False,
                previous_move=move,
                vision_depth=vision_depth,
                vision_branch=vision_branch,
                vision_decay=vision_decay,
                vision_mode=vision_mode,
                vision_candidates=vision_candidates,
            )
            board.pop()

        if child is not None:
            result["nodes_searched"] += child.get("nodes_searched", 0)
            leaf_count_add += child.get("leaf_count", 0)
            branch_has_ccp = branch_has_ccp or bool(child.get("has_ccp"))

            # Propagate best descendant ES for both colors, with depths shifted by +1.
            child_max_white = child.get("max_es_white")
            child_max_black = child.get("max_es_black")
            if is_es_value(child_max_white):
                depth = child.get("best_depth_white")
                _ccp_v2_update_best_es(result, child_max_white, (depth + 1) if is_number(depth) else 1)
            if is_es_value(child_max_black):
                depth = child.get("best_depth_black")
                esw = 1.0 - float(child_max_black)
                _ccp_v2_update_best_es(result, esw, (depth + 1) if is_number(depth) else 1)

            if mover == chess.WHITE:
                child_best_for_mover = child_max_white if is_es_value(child_max_white) else None
                payoff_depth = child.get("best_depth_white")
            else:
                child_best_for_mover = child_max_black if is_es_value(child_max_black) else None
                payoff_depth = child.get("best_depth_black")
            if is_es_value(child_best_for_mover):
                payoff_depth = payoff_depth if is_number(payoff_depth) else 1
                # Quiet moves and initially negative forcing moves get value only
                # if later CCP/search restores or improves the mover's ES over the
                # current node's preference balance.
                raw_payoff = max(0.0, child_best_for_mover - es_node_mover)
                survival = math.exp(-pre_loss / tau) if tau > 0 else 0.0
                depth_bonus = 1.0 + alpha_chain * max(0.0, payoff_depth)
                delayed_payoff = raw_payoff * survival * depth_bonus

            if (not is_ccp) and branch_has_ccp and delayed_payoff > 0:
                quiet_pause = 1 + int(child.get("quiet_pause_count", 0))
                quiet_pause_burden = delayed_payoff + float(child.get("quiet_pause_burden", 0.0) or 0.0)
            else:
                quiet_pause = int(child.get("quiet_pause_count", 0) or 0)
                quiet_pause_burden = float(child.get("quiet_pause_burden", 0.0) or 0.0)

            branch_chain = (1 if is_ccp else 0) + int(child.get("max_chain_length", 0) or 0)
            branch_total_chain = (1 if is_ccp else 0) + int(child.get("total_chain_length", 0) or 0)
        else:
            leaf_count_add += 1

        child_branch_total = float(child.get("branch_total", 0.0) if child is not None else 0.0)
        branch_core = immediate_value + delayed_payoff + child_weight * child_branch_total
        chain_bonus = 1.0 + alpha_chain * branch_chain
        quiet_bonus = 1.0 + beta_quiet * quiet_pause
        branch_score = plaus * branch_core * chain_bonus * quiet_bonus

        if root_node:
            try:
                move_san = board.san(move)
            except Exception:
                move_san = ""
            child_nodes = child.get("nodes_searched", 0) if child is not None else 0
            child_leaf_count = child.get("leaf_count", 1) if child is not None else 1
            child_max_chain = child.get("max_chain_length", 0) if child is not None else 0
            child_quiet_pause_count = child.get("quiet_pause_count", 0) if child is not None else 0
            child_quiet_pause_burden = child.get("quiet_pause_burden", 0.0) if child is not None else 0.0
            result.setdefault("root_branch_rows", []).append({
                "move_uci": move.uci(),
                "move_san": move_san,
                "root_played_move": bool(root_played_move is not None and move == root_played_move),
                "is_ccp": bool(is_ccp),
                "is_check": bool(flags.get("is_check")),
                "is_capture": bool(flags.get("is_capture")),
                "is_promotion": bool(flags.get("is_promotion")),
                "is_recapture": bool(flags.get("is_recapture")),
                "captures_attacker": bool(flags.get("captures_attacker")),
                "saves_material": bool(flags.get("saves_material")),
                "quiet_attack_proxy": r.get("quiet_attack_proxy"),
                "quiet_vision_proxy": r.get("quiet_vision_proxy"),
                "quiet_proxy": r.get("quiet_proxy"),
                "forced_inclusion": bool(r.get("forced_inclusion")),
                "es_node_mover": es_node_mover,
                "es_after_mover": es_after,
                "es_delta_from_node": (es_after - es_node_mover) if is_number(es_after) and is_number(es_node_mover) else None,
                "local_best_es": best_es,
                "local_loss_vs_best": (best_es - es_after) if is_number(best_es) and is_number(es_after) else None,
                "gain": gain,
                "pre_loss": pre_loss,
                "plausibility": plaus,
                "immediate_value": immediate_value,
                "delayed_payoff": delayed_payoff,
                "best_descendant_es_for_root_mover": child_best_for_mover,
                "payoff_depth": payoff_depth,
                "has_positive_payoff": bool(is_es_value(child_best_for_mover) and is_es_value(es_node_mover) and child_best_for_mover > es_node_mover),
                "branch_core": branch_core,
                "branch_chain": branch_chain,
                "branch_total_chain": branch_total_chain,
                "branch_has_ccp": bool(branch_has_ccp),
                "quiet_pause": quiet_pause,
                "quiet_pause_burden": quiet_pause_burden,
                "child_nodes_searched": child_nodes,
                "child_leaf_count": child_leaf_count,
                "child_max_chain_length": child_max_chain,
                "child_quiet_pause_count": child_quiet_pause_count,
                "child_quiet_pause_burden": child_quiet_pause_burden,
                "child_branch_total": child_branch_total,
                "branch_score": branch_score,
                "branch_score_log": math.log1p(branch_score) if is_number(branch_score) and branch_score >= 0 else None,
            })

        if branch_score > 0:
            result["branch_scores"].append(branch_score)
        result["max_chain_length"] = max(result["max_chain_length"], branch_chain)
        result["total_chain_length"] += branch_total_chain
        result["quiet_pause_count"] += quiet_pause
        result["quiet_pause_burden"] += quiet_pause_burden
        result["leaf_count"] += leaf_count_add
        result["has_ccp"] = result["has_ccp"] or branch_has_ccp

    scores = result["branch_scores"]
    result["branch_total"] = sum(scores)
    result["branch_max"] = max(scores) if scores else 0.0
    result["branch_mean"] = mean(scores) or 0.0
    n_eff = effective_count_from_weights(scores)
    result["branch_effective_count"] = n_eff
    result["branch_ambiguity"] = math.log(1.0 + n_eff) if is_number(n_eff) else 0.0
    if result["leaf_count"] == 0:
        result["leaf_count"] = 1
    return result


def analyze_ccp_v2_search_difficulty(
    engine,
    board,
    limit,
    cache,
    cache_key_extra,
    stats,
    root_best_es_mover,
    tau=0.03,
    depth=5,
    max_tree_nodes=200,
    max_branch=0,
    min_plausibility=0.0,
    alpha_chain=0.25,
    beta_quiet=0.50,
    child_weight=0.50,
    max_engine_evals_per_root=0,
    quiet_candidates=4,
    include_all_root_quiet=False,
    root_played_move=None,
    vision_depth=0,
    vision_branch=6,
    vision_decay=0.65,
    vision_mode="root",
    vision_candidates=12,
):
    """Top-level wrapper for CCP Search Difficulty v2."""
    if depth <= 0 or max_tree_nodes <= 0:
        return {
            "ccp_v2_available": False,
        }

    state = {"nodes": 0, "evals": 0, "cap_hit": False}
    root = analyze_ccp_v2_node(
        engine=engine,
        board=board,
        limit=limit,
        cache=cache,
        cache_key_extra=cache_key_extra,
        stats=stats,
        depth_remaining=depth,
        tau=tau,
        max_tree_nodes=max_tree_nodes,
        max_branch=max_branch,
        min_plausibility=min_plausibility,
        alpha_chain=alpha_chain,
        beta_quiet=beta_quiet,
        child_weight=child_weight,
        state=state,
        in_forcing_chain=False,
        max_engine_evals_per_root=max_engine_evals_per_root,
        quiet_candidates=quiet_candidates,
        include_all_root_quiet=include_all_root_quiet,
        root_played_move=root_played_move,
        root_node=True,
        previous_move=None,
        vision_depth=vision_depth,
        vision_branch=vision_branch,
        vision_decay=vision_decay,
        vision_mode=vision_mode,
        vision_candidates=vision_candidates,
        root_allowed_moves=None,
    )
    pure = root.get("branch_total", 0.0) * root.get("branch_ambiguity", 0.0)
    leverage = _clamp01(4.0 * root_best_es_mover * (1.0 - root_best_es_mover)) if is_number(root_best_es_mover) else None
    soft_leverage = math.sqrt(leverage) if is_number(leverage) else None
    soft = pure * soft_leverage if is_number(soft_leverage) else None
    mean_chain = safe_div(root.get("total_chain_length", 0), max(1, root.get("leaf_count", 1)))

    return {
        "ccp_v2_available": True,
        "ccp_v2_depth": depth,
        "ccp_v2_nodes_searched": root.get("nodes_searched", state.get("nodes", 0)),
        "ccp_v2_eval_attempts": state.get("evals", 0),
        "ccp_v2_cap_hit": bool(state.get("cap_hit", False)),
        "ccp_v2_vision_depth": vision_depth,
        "ccp_v2_vision_branch": vision_branch,
        "ccp_v2_vision_decay": vision_decay,
        "ccp_v2_vision_mode": vision_mode,
        "ccp_v2_vision_candidates": vision_candidates,
        "ccp_v2_leaf_count": root.get("leaf_count"),
        "ccp_v2_max_chain_length": root.get("max_chain_length"),
        "ccp_v2_total_chain_length": root.get("total_chain_length"),
        "ccp_v2_mean_chain_length": mean_chain,
        "ccp_v2_quiet_pause_count": root.get("quiet_pause_count"),
        "ccp_v2_quiet_pause_burden": root.get("quiet_pause_burden"),
        "ccp_v2_branch_total": root.get("branch_total"),
        "ccp_v2_branch_max": root.get("branch_max"),
        "ccp_v2_branch_mean": root.get("branch_mean"),
        "ccp_v2_branch_effective_count": root.get("branch_effective_count"),
        "ccp_v2_branch_ambiguity": root.get("branch_ambiguity"),
        "ccp_v2_search_difficulty_pure": pure,
        "ccp_v2_search_difficulty_soft": soft,
        "_ccp_v2_root_branch_rows": list(root.get("root_branch_rows") or []),
    }



def _ccp_v2_branch_priority_score(row, mode="log", saturation_k=1.0):
    """Stable root-branch priority for two-stage probe/confirm selection.

    Raw recursive CCP-v2 branch scores can span many orders of magnitude. For
    choosing which probed root branches deserve higher-node confirmation, log is
    usually the safest default: it preserves ordering while preventing a single
    astronomical branch from monopolizing the confirm set.
    """
    score = row.get("branch_score", 0.0)
    if not is_number(score) or score <= 0:
        return 0.0
    mode = (mode or "log").lower()
    if mode == "raw":
        return score
    if mode == "saturated":
        k = saturation_k if is_number(saturation_k) and saturation_k > 0 else 1.0
        return score / (score + k)
    # default: log
    return math.log1p(score)


def _ccp_v2_summarize_root(root, state, root_best_es_mover):
    """Convert a CCP-v2 root search object into the public per-move fields."""
    pure = root.get("branch_total", 0.0) * root.get("branch_ambiguity", 0.0)
    leverage = _clamp01(4.0 * root_best_es_mover * (1.0 - root_best_es_mover)) if is_number(root_best_es_mover) else None
    soft_leverage = math.sqrt(leverage) if is_number(leverage) else None
    soft = pure * soft_leverage if is_number(soft_leverage) else None
    mean_chain = safe_div(root.get("total_chain_length", 0), max(1, root.get("leaf_count", 1)))
    return {
        "ccp_v2_available": True,
        "ccp_v2_nodes_searched": root.get("nodes_searched", state.get("nodes", 0)),
        "ccp_v2_eval_attempts": state.get("evals", 0),
        "ccp_v2_cap_hit": bool(state.get("cap_hit", False)),
        "ccp_v2_leaf_count": root.get("leaf_count"),
        "ccp_v2_max_chain_length": root.get("max_chain_length"),
        "ccp_v2_total_chain_length": root.get("total_chain_length"),
        "ccp_v2_mean_chain_length": mean_chain,
        "ccp_v2_quiet_pause_count": root.get("quiet_pause_count"),
        "ccp_v2_quiet_pause_burden": root.get("quiet_pause_burden"),
        "ccp_v2_branch_total": root.get("branch_total"),
        "ccp_v2_branch_max": root.get("branch_max"),
        "ccp_v2_branch_mean": root.get("branch_mean"),
        "ccp_v2_branch_effective_count": root.get("branch_effective_count"),
        "ccp_v2_branch_ambiguity": root.get("branch_ambiguity"),
        "ccp_v2_search_difficulty_pure": pure,
        "ccp_v2_search_difficulty_soft": soft,
    }


def analyze_ccp_v2_search_difficulty_two_stage(
    engine,
    board,
    probe_limit,
    confirm_limit,
    cache,
    cache_key_extra,
    stats,
    root_best_es_mover,
    tau=0.03,
    depth=5,
    probe_depth=None,
    max_tree_nodes=200,
    probe_max_tree_nodes=None,
    max_branch=0,
    min_plausibility=0.0,
    alpha_chain=0.25,
    beta_quiet=0.50,
    child_weight=0.50,
    probe_max_engine_evals_per_root=0,
    confirm_max_engine_evals_per_root=0,
    confirm_candidates=8,
    confirm_score_mode="log",
    saturation_k=1.0,
    quiet_candidates=4,
    include_all_root_quiet=False,
    root_played_move=None,
    vision_depth=0,
    vision_branch=6,
    vision_decay=0.65,
    vision_mode="root",
    vision_candidates=12,
):
    """Two-stage CCP-v2 search.

    Stage 1 probes a broad root candidate set with a cheaper engine budget.
    Stage 2 re-runs the recursive search using the normal/confirm budget, but at
    the root it keeps only the top probed branches according to a stable priority
    score. Below the root, normal candidate selection is used.

    This is an allocation optimization: final CCP-v2 values come from the
    confirmation search, not directly from the cheap probe values.
    """
    if depth <= 0 or max_tree_nodes <= 0:
        return {"ccp_v2_available": False}

    probe_depth = probe_depth if probe_depth is not None and probe_depth > 0 else depth
    probe_max_tree_nodes = probe_max_tree_nodes if probe_max_tree_nodes is not None and probe_max_tree_nodes > 0 else max_tree_nodes

    probe_state = {"nodes": 0, "evals": 0, "cap_hit": False}
    probe_root = analyze_ccp_v2_node(
        engine=engine,
        board=board,
        limit=probe_limit,
        cache=cache,
        cache_key_extra=f"{cache_key_extra}:probe",
        stats=stats,
        depth_remaining=probe_depth,
        tau=tau,
        max_tree_nodes=probe_max_tree_nodes,
        max_branch=max_branch,
        min_plausibility=min_plausibility,
        alpha_chain=alpha_chain,
        beta_quiet=beta_quiet,
        child_weight=child_weight,
        state=probe_state,
        in_forcing_chain=False,
        max_engine_evals_per_root=probe_max_engine_evals_per_root,
        quiet_candidates=quiet_candidates,
        include_all_root_quiet=include_all_root_quiet,
        root_played_move=root_played_move,
        root_node=True,
        previous_move=None,
        vision_depth=vision_depth,
        vision_branch=vision_branch,
        vision_decay=vision_decay,
        vision_mode=vision_mode,
        vision_candidates=vision_candidates,
        root_allowed_moves=None,
    )

    probe_rows = list(probe_root.get("root_branch_rows") or [])
    for r in probe_rows:
        r["confirm_priority"] = _ccp_v2_branch_priority_score(r, mode=confirm_score_mode, saturation_k=saturation_k)
    probe_rows.sort(key=lambda r: (r.get("confirm_priority", 0.0), r.get("plausibility", 0.0)), reverse=True)

    if confirm_candidates is None or confirm_candidates == 0:
        selected_rows = probe_rows
    elif confirm_candidates < 0:
        selected_rows = probe_rows
    else:
        selected_rows = probe_rows[:confirm_candidates]

    allowed = [r.get("move_uci") for r in selected_rows if r.get("move_uci")]
    if root_played_move is not None and root_played_move.uci() not in allowed:
        # Preserve the played move so critical-move diagnostics can still examine
        # the actual game choice even if the probe did not rank it highly.
        allowed.append(root_played_move.uci())

    confirm_state = {"nodes": 0, "evals": 0, "cap_hit": False}
    confirm_root = analyze_ccp_v2_node(
        engine=engine,
        board=board,
        limit=confirm_limit,
        cache=cache,
        cache_key_extra=f"{cache_key_extra}:confirm",
        stats=stats,
        depth_remaining=depth,
        tau=tau,
        max_tree_nodes=max_tree_nodes,
        max_branch=max_branch,
        min_plausibility=min_plausibility,
        alpha_chain=alpha_chain,
        beta_quiet=beta_quiet,
        child_weight=child_weight,
        state=confirm_state,
        in_forcing_chain=False,
        max_engine_evals_per_root=confirm_max_engine_evals_per_root,
        quiet_candidates=quiet_candidates,
        include_all_root_quiet=include_all_root_quiet,
        root_played_move=root_played_move,
        root_node=True,
        previous_move=None,
        # Confirmation is restricted to the probe-selected root moves, so it does
        # not need to rerun the expensive root vision proxy. The original vision
        # settings are still recorded in the returned diagnostics below.
        vision_depth=0,
        vision_branch=vision_branch,
        vision_decay=vision_decay,
        vision_mode="off",
        vision_candidates=vision_candidates,
        root_allowed_moves=allowed,
    )

    # Build root-branch diagnostics from both stages. These rows are not stored
    # in per_move_wdl.csv; they are written to ccp_v2_root_branch_diagnostics.csv.
    probe_rank_by_uci = {}
    for idx, r in enumerate(probe_rows, start=1):
        if r.get("move_uci"):
            probe_rank_by_uci[r.get("move_uci")] = idx
    selected_set = set(allowed)
    root_branch_diag_rows = []
    for idx, r in enumerate(probe_rows, start=1):
        rr = dict(r)
        rr.update({
            "ccp_v2_stage": "probe",
            "stage_rank": idx,
            "probe_rank": idx,
            "confirm_rank": None,
            "confirm_priority": r.get("confirm_priority"),
            "selected_for_confirm": bool(r.get("move_uci") in selected_set),
            "probe_root_branch_count": len(probe_rows),
            "confirm_root_moves_selected": len(set(allowed)),
            "confirm_score_mode": confirm_score_mode,
        })
        root_branch_diag_rows.append(rr)
    confirm_rows = list(confirm_root.get("root_branch_rows") or [])
    confirm_rows.sort(key=lambda r: (r.get("branch_score_log") if is_number(r.get("branch_score_log")) else -1.0, r.get("plausibility", 0.0)), reverse=True)
    for idx, r in enumerate(confirm_rows, start=1):
        rr = dict(r)
        uci = rr.get("move_uci")
        rr.update({
            "ccp_v2_stage": "confirm",
            "stage_rank": idx,
            "probe_rank": probe_rank_by_uci.get(uci),
            "confirm_rank": idx,
            "confirm_priority": None,
            "selected_for_confirm": True,
            "probe_root_branch_count": len(probe_rows),
            "confirm_root_moves_selected": len(set(allowed)),
            "confirm_score_mode": confirm_score_mode,
        })
        root_branch_diag_rows.append(rr)

    out = _ccp_v2_summarize_root(confirm_root, confirm_state, root_best_es_mover)
    out.update({
        "ccp_v2_two_stage_enabled": True,
        "ccp_v2_depth": depth,
        "ccp_v2_probe_depth": probe_depth,
        "ccp_v2_probe_nodes_searched": probe_root.get("nodes_searched", probe_state.get("nodes", 0)),
        "ccp_v2_probe_eval_attempts": probe_state.get("evals", 0),
        "ccp_v2_probe_cap_hit": bool(probe_state.get("cap_hit", False)),
        "ccp_v2_probe_root_branch_count": len(probe_rows),
        "ccp_v2_probe_branch_total": probe_root.get("branch_total"),
        "ccp_v2_probe_branch_max": probe_root.get("branch_max"),
        "ccp_v2_probe_branch_ambiguity": probe_root.get("branch_ambiguity"),
        "ccp_v2_confirm_candidates": confirm_candidates,
        "ccp_v2_confirm_score_mode": confirm_score_mode,
        "ccp_v2_confirm_root_moves_selected": len(set(allowed)),
        "ccp_v2_confirm_root_moves_uci": ";".join(allowed[:64]),
        "ccp_v2_vision_depth": vision_depth,
        "ccp_v2_vision_branch": vision_branch,
        "ccp_v2_vision_decay": vision_decay,
        "ccp_v2_vision_mode": vision_mode,
        "ccp_v2_vision_candidates": vision_candidates,
        "_ccp_v2_root_branch_rows": root_branch_diag_rows,
    })
    return out

# ------------------------------------------------------------
# Position difficulty from all legal moves
# ------------------------------------------------------------

def _clamp01(value):
    if value is None:
        return None
    return max(0.0, min(1.0, value))


def softmax_effective_move_count(losses, tau):
    """
    Convert legal-move losses into a soft quality-mass distribution and
    return inverse-Simpson effective number of good moves.

    q_i = exp(-loss_i / tau)
    p_i = q_i / sum(q)
    N_eff = 1 / sum(p_i^2)
    """

    if not losses:
        return None, []
    if tau <= 0:
        raise ValueError("difficulty_tau must be positive.")

    weights = [math.exp(-max(0.0, loss) / tau) for loss in losses]
    total = sum(weights)

    if total == 0:
        return None, []

    probs = [w / total for w in weights]
    denom = sum(p * p for p in probs)

    if denom == 0:
        return None, probs

    return 1.0 / denom, probs


def entropy_effective_move_count(probs):
    """
    Entropy effective number of good moves. This is saved as a diagnostic
    alternative to inverse-Simpson N_eff.
    """

    if not probs:
        return None

    h = -sum(p * math.log(p) for p in probs if p > 0)
    return math.exp(h)


def analyze_position_difficulty(engine, board, limit, tau=0.03, cache=None, cache_key_extra="difficulty", stats=None, mode="all-legal", multipv=10, hybrid_deep_limit=None, hybrid_topk=5, hybrid_cache_key_extra="difficulty_hybrid"):
    """
    Computes continuous position-difficulty metrics from every legal move.

    Perspective: side to move.

    For every legal move i:
        ES_i = expected score for side to move after playing i
        B    = max_i ES_i
        L_i  = B - ES_i

    Main difficulty:
        D_pure = Narrowness * sqrt(RMSLossLegal)

    Result-context variants are also saved, but the raw D_pure should be
    treated as the least philosophically loaded difficulty estimate.
    """

    mover = board.turn
    legal_moves = list(board.legal_moves)
    n = len(legal_moves)

    if n == 0:
        return {
            "difficulty_available": False,
            "legal_move_count": 0,
        }

    move_rows = []

    if stats is not None:
        stats["difficulty_positions"] = stats.get("difficulty_positions", 0) + 1
        stats["legal_moves_seen"] = stats.get("legal_moves_seen", 0) + n

    if mode == "multipv":
        # Fast approximation: only Stockfish's top-K root moves are scored.
        # This is useful for narrowness among plausible moves, but it is not a
        # full all-legal RMS distribution.
        k = min(max(1, multipv), n)
        if stats is not None:
            stats["multipv_positions"] = stats.get("multipv_positions", 0) + 1
            stats["multipv_requested"] = stats.get("multipv_requested", 0) + k
            stats["engine_calls"] = stats.get("engine_calls", 0) + 1
        info_list = engine.analyse(board, limit, multipv=k)
        if isinstance(info_list, dict):
            info_list = [info_list]
        if stats is not None:
            # A MultiPV call is one engine call, but may return several info lines.
            for info in info_list:
                if is_number(info.get("nodes")):
                    stats["nodes_searched_total"] = stats.get("nodes_searched_total", 0) + info.get("nodes")
                if is_number(info.get("time")):
                    stats["engine_reported_time_total"] = stats.get("engine_reported_time_total", 0.0) + info.get("time")
                if is_number(info.get("nps")):
                    stats.setdefault("nps_values", []).append(info.get("nps"))
                if is_number(info.get("hashfull")):
                    stats.setdefault("hashfull_values", []).append(info.get("hashfull"))
        for info in info_list:
            pv = info.get("pv") or []
            if not pv or "wdl" not in info:
                continue
            move = pv[0]
            # Root WDL is from the side-to-move perspective before making the move.
            # For comparability with all-legal rows, evaluate ES after the root move
            # from the mover's perspective by reading the WDL from mover POV.
            es_after_mover = expected_score_from_wdl(info["wdl"], mover)
            es_after_white = es_after_mover if mover == chess.WHITE else 1.0 - es_after_mover
            move_rows.append({
                "move_uci": move.uci(),
                "es_after_white": es_after_white,
                "es_after_mover": es_after_mover,
            })
    else:
        # all-legal and hybrid both begin with a shallow/normal all-legal pass.
        for move in legal_moves:
            board.push(move)
            es_after_white = analyse_es_white(
                engine,
                board,
                limit,
                cache=cache,
                cache_key_extra=cache_key_extra,
                stats=stats,
            )
            board.pop()

            es_after_mover = es_for_color(es_after_white, mover)
            move_rows.append({
                "move_uci": move.uci(),
                "es_after_white": es_after_white,
                "es_after_mover": es_after_mover,
            })

        if mode == "hybrid" and hybrid_deep_limit is not None and hybrid_topk > 0:
            # Re-evaluate only the best K shallow moves at a deeper/alternate budget.
            top_rows = sorted(
                [r for r in move_rows if is_number(r.get("es_after_mover"))],
                key=lambda r: r["es_after_mover"],
                reverse=True,
            )[:hybrid_topk]
            replacement_by_uci = {}
            for r in top_rows:
                move = chess.Move.from_uci(r["move_uci"])
                board.push(move)
                es_after_white = analyse_es_white(
                    engine,
                    board,
                    hybrid_deep_limit,
                    cache=cache,
                    cache_key_extra=hybrid_cache_key_extra,
                    stats=stats,
                )
                board.pop()
                replacement_by_uci[r["move_uci"]] = {
                    "es_after_white": es_after_white,
                    "es_after_mover": es_for_color(es_after_white, mover),
                }
            for r in move_rows:
                repl = replacement_by_uci.get(r["move_uci"])
                if repl:
                    r.update(repl)
                    r["hybrid_deep_reanalysed"] = True
                else:
                    r["hybrid_deep_reanalysed"] = False

    es_values = [r["es_after_mover"] for r in move_rows if is_number(r["es_after_mover"])]

    if not es_values:
        return {
            "difficulty_available": False,
            "legal_move_count": n,
        }

    best_es = max(es_values)
    best_move_uci = None
    for r in move_rows:
        if is_number(r.get("es_after_mover")) and r.get("es_after_mover") == best_es:
            best_move_uci = r.get("move_uci")
            break
    worst_es = min(es_values)
    mean_legal_es = mean(es_values)
    sd_legal_es = pstdev(es_values)

    losses = [max(0.0, best_es - r["es_after_mover"]) for r in move_rows]
    mean_legal_loss = mean(losses)
    rms_legal_loss = rms(losses)
    sd_legal_loss = pstdev(losses)
    legal_loss_swing = best_es - worst_es

    n_eff, probs = softmax_effective_move_count(losses, tau=tau)
    n_eff_entropy = entropy_effective_move_count(probs)

    if n <= 1 or n_eff is None:
        # With only one legal move there is no choice-distribution difficulty.
        # Narrowness is set to 1, but RMS legal loss will be 0, so D_pure is 0.
        narrowness = 1.0
    else:
        narrowness = 1.0 - ((n_eff - 1.0) / (n - 1.0))
        narrowness = _clamp01(narrowness)

    if n <= 1 or n_eff_entropy is None:
        narrowness_entropy = 1.0
    else:
        narrowness_entropy = 1.0 - ((n_eff_entropy - 1.0) / (n - 1.0))
        narrowness_entropy = _clamp01(narrowness_entropy)

    uncertainty_leverage = _clamp01(4.0 * best_es * (1.0 - best_es))
    soft_uncertainty_leverage = math.sqrt(uncertainty_leverage) if uncertainty_leverage is not None else None
    side_to_move_risk_leverage = _clamp01(1.0 - best_es)
    defender_pressure_leverage = _clamp01(best_es)
    swing_leverage = _clamp01(legal_loss_swing)

    sqrt_rms_legal_loss = math.sqrt(rms_legal_loss) if rms_legal_loss is not None else None
    position_difficulty_pure = (
        narrowness * sqrt_rms_legal_loss
        if narrowness is not None and sqrt_rms_legal_loss is not None
        else None
    )

    position_difficulty_uncertainty = (
        position_difficulty_pure * uncertainty_leverage
        if position_difficulty_pure is not None and uncertainty_leverage is not None
        else None
    )
    position_difficulty_soft_uncertainty = (
        position_difficulty_pure * soft_uncertainty_leverage
        if position_difficulty_pure is not None and soft_uncertainty_leverage is not None
        else None
    )
    position_difficulty_risk = (
        position_difficulty_pure * side_to_move_risk_leverage
        if position_difficulty_pure is not None and side_to_move_risk_leverage is not None
        else None
    )
    position_difficulty_defender_pressure = (
        position_difficulty_pure * defender_pressure_leverage
        if position_difficulty_pure is not None and defender_pressure_leverage is not None
        else None
    )
    position_difficulty_swing = (
        position_difficulty_pure * swing_leverage
        if position_difficulty_pure is not None and swing_leverage is not None
        else None
    )

    sorted_es_desc = sorted(es_values, reverse=True)
    best_second_gap = (
        sorted_es_desc[0] - sorted_es_desc[1]
        if len(sorted_es_desc) >= 2
        else None
    )
    best_third_gap = (
        sorted_es_desc[0] - sorted_es_desc[2]
        if len(sorted_es_desc) >= 3
        else None
    )

    return {
        "difficulty_available": True,
        "difficulty_mode": mode,
        "legal_move_count": n,
        "legal_moves_evaluated_for_difficulty": len(move_rows),
        "legal_best_es_mover": best_es,
        "legal_best_move_uci": best_move_uci,
        "legal_worst_es_mover": worst_es,
        "legal_mean_es_mover": mean_legal_es,
        "legal_sd_es_mover": sd_legal_es,
        "legal_loss_swing": legal_loss_swing,
        "legal_mean_loss": mean_legal_loss,
        "legal_rms_loss": rms_legal_loss,
        "legal_sd_loss": sd_legal_loss,
        "legal_sqrt_rms_loss": sqrt_rms_legal_loss,
        "effective_good_moves": n_eff,
        "effective_good_moves_entropy": n_eff_entropy,
        "narrowness": narrowness,
        "narrowness_entropy": narrowness_entropy,
        "uncertainty_leverage": uncertainty_leverage,
        "soft_uncertainty_leverage": soft_uncertainty_leverage,
        "side_to_move_risk_leverage": side_to_move_risk_leverage,
        "defender_pressure_leverage": defender_pressure_leverage,
        "swing_leverage": swing_leverage,
        "position_difficulty_pure": position_difficulty_pure,
        "position_difficulty_pure_x100": position_difficulty_pure * 100.0 if position_difficulty_pure is not None else None,
        "position_difficulty_uncertainty": position_difficulty_uncertainty,
        "position_difficulty_soft_uncertainty": position_difficulty_soft_uncertainty,
        "position_difficulty_risk": position_difficulty_risk,
        "position_difficulty_defender_pressure": position_difficulty_defender_pressure,
        "position_difficulty_swing": position_difficulty_swing,
        "best_second_gap": best_second_gap,
        "best_third_gap": best_third_gap,
        "_legal_move_rows": move_rows,
    }


def played_move_distribution_stats(difficulty, played_move_uci, played_es_after_mover):
    """
    Adds played-move rank, percentile, and distribution-based loss.
    Rank is 1 = best. Percentile is 1.0 = best, 0.0 = worst.
    """

    move_rows = difficulty.get("_legal_move_rows") or []
    if not move_rows or played_es_after_mover is None:
        return {
            "played_legal_loss": None,
            "played_move_rank": None,
            "played_move_percentile": None,
        }

    best_es = difficulty.get("legal_best_es_mover")
    played_legal_loss = max(0.0, best_es - played_es_after_mover) if best_es is not None else None

    sorted_values = sorted(
        [(r["move_uci"], r["es_after_mover"]) for r in move_rows if is_number(r["es_after_mover"])],
        key=lambda item: item[1],
        reverse=True,
    )

    rank = None
    for idx, (uci, _) in enumerate(sorted_values, start=1):
        if uci == played_move_uci:
            rank = idx
            break

    n = len(sorted_values)
    if rank is None or n <= 1:
        percentile = 1.0 if rank == 1 else None
    else:
        percentile = 1.0 - ((rank - 1.0) / (n - 1.0))

    return {
        "played_legal_loss": played_legal_loss,
        "played_move_rank": rank,
        "played_move_percentile": percentile,
    }


def weighted_loss_and_accuracy(losses, weights):
    weighted_loss = weighted_average(losses, weights)
    weighted_accuracy = 100.0 * (1.0 - weighted_loss) if weighted_loss is not None else None
    if weighted_accuracy is not None:
        weighted_accuracy = max(0.0, min(100.0, weighted_accuracy))
    return weighted_loss, weighted_accuracy


# ------------------------------------------------------------
# Analysis
# ------------------------------------------------------------

def analyze_game(
    engine,
    game,
    game_id,
    main_limit,
    main_cache_key,
    difficulty_limit=None,
    difficulty_cache_key=None,
    hybrid_deep_limit=None,
    hybrid_cache_key=None,
    cache=None,
    stats=None,
    weighting="ply",
    compute_difficulty=True,
    difficulty_tau=0.03,
    difficulty_mode="all-legal",
    difficulty_multipv=10,
    difficulty_hybrid_topk=5,
    ccp_v2_enabled=False,
    ccp_v2_two_stage=False,
    ccp_v2_limit=None,
    ccp_v2_probe_limit=None,
    ccp_v2_cache_key=None,
    ccp_v2_probe_cache_key=None,
    ccp_v2_tau=None,
    ccp_v2_depth=5,
    ccp_v2_probe_depth=None,
    ccp_v2_max_tree_nodes=200,
    ccp_v2_probe_max_tree_nodes=None,
    ccp_v2_max_branch=0,
    ccp_v2_min_plausibility=0.0,
    ccp_v2_alpha_chain=0.25,
    ccp_v2_beta_quiet=0.50,
    ccp_v2_child_weight=0.50,
    ccp_v2_max_engine_evals_per_root=0,
    ccp_v2_probe_max_engine_evals_per_root=0,
    ccp_v2_confirm_candidates=8,
    ccp_v2_confirm_score_mode="log",
    ccp_v2_saturation_k=1.0,
    ccp_v2_quiet_candidates=4,
    ccp_v2_include_all_root_quiet=False,
    ccp_v2_vision_depth=0,
    ccp_v2_vision_branch=6,
    ccp_v2_vision_decay=0.65,
    ccp_v2_vision_mode="root",
    ccp_v2_vision_candidates=12,
):
    """
    Player A = White
    Player B = Black

    WDL Accuracy is based on:

        ESLoss = max(0, ES_best_before_move - ES_after_played_move)

    where ES_best_before_move is Stockfish's expected score for the
    player to move before the move.

    Difficulty extension:

        For each pre-move position, all legal moves are separately evaluated.
        The resulting legal-move ES distribution gives Narrowness,
        Legal RMS Loss, Pure Position Difficulty, and result-context variants.
    """

    white_name = game.headers.get("White", "White")
    black_name = game.headers.get("Black", "Black")
    result = game.headers.get("Result", "*")

    board = game.board()
    moves = list(game.mainline_moves())

    # Position expected scores:
    # E[0] = expected score for White in starting position
    # E[i] = expected score for White after ply i
    es_white_positions = [analyse_es_white(
        engine,
        board,
        main_limit,
        cache=cache,
        cache_key_extra=main_cache_key,
        stats=stats,
    )]

    movers = []
    pre_move_boards = []
    previous_moves = []
    previous_move = None

    for move in moves:
        movers.append(board.turn)
        pre_move_boards.append(board.copy(stack=False))
        previous_moves.append(previous_move)
        board.push(move)
        previous_move = move
        es_white_positions.append(analyse_es_white(
            engine,
            board,
            main_limit,
            cache=cache,
            cache_key_extra=main_cache_key,
            stats=stats,
        ))

    per_move_rows = []
    ccp_v2_root_branch_rows = []

    acc_A_moves = []
    acc_B_moves = []

    es_loss_A_moves = []
    es_loss_B_moves = []
    es_loss_game_moves = []

    swing_A_moves = []
    swing_B_moves = []
    swing_game_moves = []

    difficulty_metric_names = [
        "position_difficulty_pure",
        "position_difficulty_uncertainty",
        "position_difficulty_soft_uncertainty",
        "position_difficulty_risk",
        "position_difficulty_defender_pressure",
        "position_difficulty_swing",
    ]

    ccp_metric_names = [
        "ccp_search_difficulty_pure",
        "ccp_search_difficulty_soft",
    ]

    ccp_v2_metric_names = [
        "ccp_v2_search_difficulty_pure",
        "ccp_v2_search_difficulty_soft",
    ]

    difficulty_A = {name: [] for name in difficulty_metric_names}
    difficulty_B = {name: [] for name in difficulty_metric_names}
    difficulty_game = {name: [] for name in difficulty_metric_names}

    difficulty_weighted_loss_A = {name: [] for name in difficulty_metric_names}
    difficulty_weighted_loss_B = {name: [] for name in difficulty_metric_names}
    difficulty_weighted_loss_game = {name: [] for name in difficulty_metric_names}

    ccp_difficulty_A = {name: [] for name in ccp_metric_names}
    ccp_difficulty_B = {name: [] for name in ccp_metric_names}
    ccp_difficulty_game = {name: [] for name in ccp_metric_names}
    ccp_weighted_loss_A = {name: [] for name in ccp_metric_names}
    ccp_weighted_loss_B = {name: [] for name in ccp_metric_names}
    ccp_weighted_loss_game = {name: [] for name in ccp_metric_names}

    ccp_immediate_burden_A = []
    ccp_immediate_burden_B = []
    ccp_immediate_burden_game = []
    ccp_quiet_to_ccp_burden_A = []
    ccp_quiet_to_ccp_burden_B = []
    ccp_quiet_to_ccp_burden_game = []
    ccp_candidate_effective_count_A = []
    ccp_candidate_effective_count_B = []
    ccp_candidate_effective_count_game = []

    ccp_v2_difficulty_A = {name: [] for name in ccp_v2_metric_names}
    ccp_v2_difficulty_B = {name: [] for name in ccp_v2_metric_names}
    ccp_v2_difficulty_game = {name: [] for name in ccp_v2_metric_names}
    ccp_v2_weighted_loss_A = {name: [] for name in ccp_v2_metric_names}
    ccp_v2_weighted_loss_B = {name: [] for name in ccp_v2_metric_names}
    ccp_v2_weighted_loss_game = {name: [] for name in ccp_v2_metric_names}

    ccp_v2_nodes_searched_A = []
    ccp_v2_nodes_searched_B = []
    ccp_v2_nodes_searched_game = []
    ccp_v2_eval_attempts_A = []
    ccp_v2_eval_attempts_B = []
    ccp_v2_eval_attempts_game = []
    ccp_v2_cap_hit_A = []
    ccp_v2_cap_hit_B = []
    ccp_v2_cap_hit_game = []
    ccp_v2_leaf_count_A = []
    ccp_v2_leaf_count_B = []
    ccp_v2_leaf_count_game = []
    ccp_v2_max_chain_length_A = []
    ccp_v2_max_chain_length_B = []
    ccp_v2_max_chain_length_game = []
    ccp_v2_mean_chain_length_A = []
    ccp_v2_mean_chain_length_B = []
    ccp_v2_mean_chain_length_game = []
    ccp_v2_quiet_pause_count_A = []
    ccp_v2_quiet_pause_count_B = []
    ccp_v2_quiet_pause_count_game = []
    ccp_v2_quiet_pause_burden_A = []
    ccp_v2_quiet_pause_burden_B = []
    ccp_v2_quiet_pause_burden_game = []
    ccp_v2_branch_total_A = []
    ccp_v2_branch_total_B = []
    ccp_v2_branch_total_game = []
    ccp_v2_branch_effective_count_A = []
    ccp_v2_branch_effective_count_B = []
    ccp_v2_branch_effective_count_game = []
    ccp_v2_branch_ambiguity_A = []
    ccp_v2_branch_ambiguity_B = []
    ccp_v2_branch_ambiguity_game = []

    legal_rms_loss_A = []
    legal_rms_loss_B = []
    legal_rms_loss_game = []
    narrowness_A = []
    narrowness_B = []
    narrowness_game = []
    effective_good_moves_A = []
    effective_good_moves_B = []
    effective_good_moves_game = []

    n = len(moves)

    for ply_index, move in enumerate(moves, start=1):
        mover = movers[ply_index - 1]

        es_before_white = es_white_positions[ply_index - 1]
        es_after_white = es_white_positions[ply_index]

        # This is the key WDL-accuracy calculation.
        # Before the move, Stockfish's ES already represents best-play expectation.
        es_best_before_mover = es_for_color(es_before_white, mover)
        es_after_played_mover = es_for_color(es_after_white, mover)

        es_loss = max(0.0, es_best_before_mover - es_after_played_mover)

        move_accuracy = 100.0 * (1.0 - es_loss)

        # Prevent rare numerical weirdness from leaving the 0..100 range.
        move_accuracy = max(0.0, min(100.0, move_accuracy))

        swing_white = abs(es_after_white - es_before_white)

        if mover == chess.WHITE:
            player_label = "A"
            acc_A_moves.append(move_accuracy)
            es_loss_A_moves.append(es_loss)
            swing_A_moves.append(swing_white)
        else:
            player_label = "B"
            acc_B_moves.append(move_accuracy)
            es_loss_B_moves.append(es_loss)
            swing_B_moves.append(swing_white)

        swing_game_moves.append(swing_white)
        es_loss_game_moves.append(es_loss)

        difficulty = {}
        played_dist_stats = {}

        if compute_difficulty:
            difficulty = analyze_position_difficulty(
                engine=engine,
                board=pre_move_boards[ply_index - 1],
                limit=difficulty_limit or main_limit,
                tau=difficulty_tau,
                cache=cache,
                cache_key_extra=difficulty_cache_key or main_cache_key,
                stats=stats,
                mode=difficulty_mode,
                multipv=difficulty_multipv,
                hybrid_deep_limit=hybrid_deep_limit,
                hybrid_topk=difficulty_hybrid_topk,
                hybrid_cache_key_extra=hybrid_cache_key or (difficulty_cache_key or main_cache_key),
            )
            played_dist_stats = played_move_distribution_stats(
                difficulty=difficulty,
                played_move_uci=move.uci(),
                played_es_after_mover=es_after_played_mover,
            )

            ccp_stats = analyze_ccp_search_difficulty(
                board=pre_move_boards[ply_index - 1],
                difficulty=difficulty,
                es_before_mover=es_best_before_mover,
                previous_move=previous_moves[ply_index - 1],
                tau=difficulty_tau,
            )
            ccp_stats.update(played_ccp_flags(
                pre_move_boards[ply_index - 1],
                move,
                previous_move=previous_moves[ply_index - 1],
            ))

            if ccp_v2_enabled:
                if ccp_v2_two_stage:
                    ccp_v2_stats = analyze_ccp_v2_search_difficulty_two_stage(
                        engine=engine,
                        board=pre_move_boards[ply_index - 1],
                        probe_limit=ccp_v2_probe_limit or ccp_v2_limit or difficulty_limit or main_limit,
                        confirm_limit=ccp_v2_limit or difficulty_limit or main_limit,
                        cache=cache,
                        cache_key_extra=ccp_v2_cache_key or difficulty_cache_key or main_cache_key,
                        stats=stats,
                        root_best_es_mover=es_best_before_mover,
                        tau=ccp_v2_tau if ccp_v2_tau is not None else difficulty_tau,
                        depth=ccp_v2_depth,
                        probe_depth=ccp_v2_probe_depth,
                        max_tree_nodes=ccp_v2_max_tree_nodes,
                        probe_max_tree_nodes=ccp_v2_probe_max_tree_nodes,
                        max_branch=ccp_v2_max_branch,
                        min_plausibility=ccp_v2_min_plausibility,
                        alpha_chain=ccp_v2_alpha_chain,
                        beta_quiet=ccp_v2_beta_quiet,
                        child_weight=ccp_v2_child_weight,
                        probe_max_engine_evals_per_root=ccp_v2_probe_max_engine_evals_per_root,
                        confirm_max_engine_evals_per_root=ccp_v2_max_engine_evals_per_root,
                        confirm_candidates=ccp_v2_confirm_candidates,
                        confirm_score_mode=ccp_v2_confirm_score_mode,
                        saturation_k=ccp_v2_saturation_k,
                        quiet_candidates=ccp_v2_quiet_candidates,
                        include_all_root_quiet=ccp_v2_include_all_root_quiet,
                        root_played_move=move,
                        vision_depth=ccp_v2_vision_depth,
                        vision_branch=ccp_v2_vision_branch,
                        vision_decay=ccp_v2_vision_decay,
                        vision_mode=ccp_v2_vision_mode,
                        vision_candidates=ccp_v2_vision_candidates,
                    )
                else:
                    ccp_v2_stats = analyze_ccp_v2_search_difficulty(
                        engine=engine,
                        board=pre_move_boards[ply_index - 1],
                        limit=ccp_v2_limit or difficulty_limit or main_limit,
                        cache=cache,
                        cache_key_extra=ccp_v2_cache_key or difficulty_cache_key or main_cache_key,
                        stats=stats,
                        root_best_es_mover=es_best_before_mover,
                        tau=ccp_v2_tau if ccp_v2_tau is not None else difficulty_tau,
                        depth=ccp_v2_depth,
                        max_tree_nodes=ccp_v2_max_tree_nodes,
                        max_branch=ccp_v2_max_branch,
                        min_plausibility=ccp_v2_min_plausibility,
                        alpha_chain=ccp_v2_alpha_chain,
                        beta_quiet=ccp_v2_beta_quiet,
                        child_weight=ccp_v2_child_weight,
                        max_engine_evals_per_root=ccp_v2_max_engine_evals_per_root,
                        quiet_candidates=ccp_v2_quiet_candidates,
                        include_all_root_quiet=ccp_v2_include_all_root_quiet,
                        root_played_move=move,
                        vision_depth=ccp_v2_vision_depth,
                        vision_branch=ccp_v2_vision_branch,
                        vision_decay=ccp_v2_vision_decay,
                        vision_mode=ccp_v2_vision_mode,
                        vision_candidates=ccp_v2_vision_candidates,
                    )
                ccp_stats.update(ccp_v2_stats)

            # Pull root-branch diagnostics out of CCP-v2 stats before these
            # stats are flattened into the normal per-move row.
            raw_branch_rows = []
            if ccp_v2_enabled:
                raw_branch_rows = list(ccp_stats.get("_ccp_v2_root_branch_rows") or [])
                ccp_stats.pop("_ccp_v2_root_branch_rows", None)
                pre_board_for_branch = pre_move_boards[ply_index - 1]
                try:
                    played_move_san_for_branch = pre_board_for_branch.san(move)
                except Exception:
                    played_move_san_for_branch = ""
                best_move_uci_for_branch = difficulty.get("legal_best_move_uci", "")
                best_move_san_for_branch = ""
                if best_move_uci_for_branch:
                    try:
                        best_move_san_for_branch = pre_board_for_branch.san(chess.Move.from_uci(best_move_uci_for_branch))
                    except Exception:
                        best_move_san_for_branch = ""
                for br in raw_branch_rows:
                    br2 = dict(br)
                    br2.update({
                        "game_id": game_id,
                        "ply": ply_index,
                        "move_no": (ply_index + 1) // 2,
                        "mover": "White" if mover == chess.WHITE else "Black",
                        "player": white_name if mover == chess.WHITE else black_name,
                        "player_label": player_label,
                        "played_move_uci": move.uci(),
                        "played_move_san": played_move_san_for_branch,
                        "best_move_uci": best_move_uci_for_branch,
                        "best_move_san": best_move_san_for_branch,
                        "wdl_es_loss": es_loss,
                        "wdl_move_accuracy": move_accuracy,
                        "es_best_before_mover": es_best_before_mover,
                        "es_after_played_mover": es_after_played_mover,
                    })
                    ccp_v2_root_branch_rows.append(br2)

            target_ccp_difficulty = ccp_difficulty_A if mover == chess.WHITE else ccp_difficulty_B
            target_ccp_weighted_loss = ccp_weighted_loss_A if mover == chess.WHITE else ccp_weighted_loss_B
            for metric_name in ccp_metric_names:
                weight = ccp_stats.get(metric_name)
                target_ccp_difficulty[metric_name].append(weight)
                ccp_difficulty_game[metric_name].append(weight)
                target_ccp_weighted_loss[metric_name].append(es_loss)
                ccp_weighted_loss_game[metric_name].append(es_loss)

            if mover == chess.WHITE:
                ccp_immediate_burden_A.append(ccp_stats.get("ccp_immediate_burden"))
                ccp_quiet_to_ccp_burden_A.append(ccp_stats.get("ccp_quiet_to_ccp_burden"))
                ccp_candidate_effective_count_A.append(ccp_stats.get("ccp_candidate_effective_count"))
            else:
                ccp_immediate_burden_B.append(ccp_stats.get("ccp_immediate_burden"))
                ccp_quiet_to_ccp_burden_B.append(ccp_stats.get("ccp_quiet_to_ccp_burden"))
                ccp_candidate_effective_count_B.append(ccp_stats.get("ccp_candidate_effective_count"))
            ccp_immediate_burden_game.append(ccp_stats.get("ccp_immediate_burden"))
            ccp_quiet_to_ccp_burden_game.append(ccp_stats.get("ccp_quiet_to_ccp_burden"))
            ccp_candidate_effective_count_game.append(ccp_stats.get("ccp_candidate_effective_count"))

            if ccp_v2_enabled:
                target_ccp_v2_difficulty = ccp_v2_difficulty_A if mover == chess.WHITE else ccp_v2_difficulty_B
                target_ccp_v2_weighted_loss = ccp_v2_weighted_loss_A if mover == chess.WHITE else ccp_v2_weighted_loss_B
                for metric_name in ccp_v2_metric_names:
                    weight = ccp_stats.get(metric_name)
                    target_ccp_v2_difficulty[metric_name].append(weight)
                    ccp_v2_difficulty_game[metric_name].append(weight)
                    target_ccp_v2_weighted_loss[metric_name].append(es_loss)
                    ccp_v2_weighted_loss_game[metric_name].append(es_loss)

                if mover == chess.WHITE:
                    ccp_v2_nodes_searched_A.append(ccp_stats.get("ccp_v2_nodes_searched"))
                    ccp_v2_eval_attempts_A.append(ccp_stats.get("ccp_v2_eval_attempts"))
                    ccp_v2_cap_hit_A.append(1.0 if ccp_stats.get("ccp_v2_cap_hit") else 0.0)
                    ccp_v2_leaf_count_A.append(ccp_stats.get("ccp_v2_leaf_count"))
                    ccp_v2_max_chain_length_A.append(ccp_stats.get("ccp_v2_max_chain_length"))
                    ccp_v2_mean_chain_length_A.append(ccp_stats.get("ccp_v2_mean_chain_length"))
                    ccp_v2_quiet_pause_count_A.append(ccp_stats.get("ccp_v2_quiet_pause_count"))
                    ccp_v2_quiet_pause_burden_A.append(ccp_stats.get("ccp_v2_quiet_pause_burden"))
                    ccp_v2_branch_total_A.append(ccp_stats.get("ccp_v2_branch_total"))
                    ccp_v2_branch_effective_count_A.append(ccp_stats.get("ccp_v2_branch_effective_count"))
                    ccp_v2_branch_ambiguity_A.append(ccp_stats.get("ccp_v2_branch_ambiguity"))
                else:
                    ccp_v2_nodes_searched_B.append(ccp_stats.get("ccp_v2_nodes_searched"))
                    ccp_v2_eval_attempts_B.append(ccp_stats.get("ccp_v2_eval_attempts"))
                    ccp_v2_cap_hit_B.append(1.0 if ccp_stats.get("ccp_v2_cap_hit") else 0.0)
                    ccp_v2_leaf_count_B.append(ccp_stats.get("ccp_v2_leaf_count"))
                    ccp_v2_max_chain_length_B.append(ccp_stats.get("ccp_v2_max_chain_length"))
                    ccp_v2_mean_chain_length_B.append(ccp_stats.get("ccp_v2_mean_chain_length"))
                    ccp_v2_quiet_pause_count_B.append(ccp_stats.get("ccp_v2_quiet_pause_count"))
                    ccp_v2_quiet_pause_burden_B.append(ccp_stats.get("ccp_v2_quiet_pause_burden"))
                    ccp_v2_branch_total_B.append(ccp_stats.get("ccp_v2_branch_total"))
                    ccp_v2_branch_effective_count_B.append(ccp_stats.get("ccp_v2_branch_effective_count"))
                    ccp_v2_branch_ambiguity_B.append(ccp_stats.get("ccp_v2_branch_ambiguity"))

                ccp_v2_nodes_searched_game.append(ccp_stats.get("ccp_v2_nodes_searched"))
                ccp_v2_eval_attempts_game.append(ccp_stats.get("ccp_v2_eval_attempts"))
                ccp_v2_cap_hit_game.append(1.0 if ccp_stats.get("ccp_v2_cap_hit") else 0.0)
                ccp_v2_leaf_count_game.append(ccp_stats.get("ccp_v2_leaf_count"))
                ccp_v2_max_chain_length_game.append(ccp_stats.get("ccp_v2_max_chain_length"))
                ccp_v2_mean_chain_length_game.append(ccp_stats.get("ccp_v2_mean_chain_length"))
                ccp_v2_quiet_pause_count_game.append(ccp_stats.get("ccp_v2_quiet_pause_count"))
                ccp_v2_quiet_pause_burden_game.append(ccp_stats.get("ccp_v2_quiet_pause_burden"))
                ccp_v2_branch_total_game.append(ccp_stats.get("ccp_v2_branch_total"))
                ccp_v2_branch_effective_count_game.append(ccp_stats.get("ccp_v2_branch_effective_count"))
                ccp_v2_branch_ambiguity_game.append(ccp_stats.get("ccp_v2_branch_ambiguity"))

            # Do not write the per-legal-move internal object to CSV rows.
            difficulty.pop("_legal_move_rows", None)

            target_difficulty = difficulty_A if mover == chess.WHITE else difficulty_B
            target_weighted_loss = difficulty_weighted_loss_A if mover == chess.WHITE else difficulty_weighted_loss_B

            for metric_name in difficulty_metric_names:
                weight = difficulty.get(metric_name)
                target_difficulty[metric_name].append(weight)
                difficulty_game[metric_name].append(weight)

                target_weighted_loss[metric_name].append(es_loss)
                difficulty_weighted_loss_game[metric_name].append(es_loss)

            if mover == chess.WHITE:
                legal_rms_loss_A.append(difficulty.get("legal_rms_loss"))
                narrowness_A.append(difficulty.get("narrowness"))
                effective_good_moves_A.append(difficulty.get("effective_good_moves"))
            else:
                legal_rms_loss_B.append(difficulty.get("legal_rms_loss"))
                narrowness_B.append(difficulty.get("narrowness"))
                effective_good_moves_B.append(difficulty.get("effective_good_moves"))

            legal_rms_loss_game.append(difficulty.get("legal_rms_loss"))
            narrowness_game.append(difficulty.get("narrowness"))
            effective_good_moves_game.append(difficulty.get("effective_good_moves"))

        row = {
            "game_id": game_id,
            "ply": ply_index,
            "move_uci": move.uci(),
            "mover": "White" if mover == chess.WHITE else "Black",
            "player_label": player_label,

            "es_before_white": es_before_white,
            "es_after_white": es_after_white,

            "es_best_before_mover": es_best_before_mover,
            "es_after_played_mover": es_after_played_mover,

            "wdl_es_loss": es_loss,
            "wdl_move_accuracy": move_accuracy,
            "wdl_volatility_swing": swing_white,
        }

        row.update(difficulty)
        row.update(played_dist_stats)
        if compute_difficulty:
            row.update(ccp_stats)
        per_move_rows.append(row)

    # ------------------------------------------------------------
    # 1. Accuracy metrics
    # ------------------------------------------------------------

    A = mean(acc_A_moves)
    B = mean(acc_B_moves)

    accuracy_sd_A = pstdev(acc_A_moves)
    accuracy_sd_B = pstdev(acc_B_moves)

    game_accuracy = mean([A, B])
    mutual_accuracy = (A * B / 100.0) if A is not None and B is not None else None

    pq_A = A * game_accuracy / 100.0 if A is not None and game_accuracy is not None else None
    pq_B = B * game_accuracy / 100.0 if B is not None and game_accuracy is not None else None

    dominance_A = A - B if A is not None and B is not None else None
    dominance_B = B - A if A is not None and B is not None else None

    # ------------------------------------------------------------
    # 2. Engine-flow metrics, WDL-based
    # ------------------------------------------------------------

    volatility_A = mean(swing_A_moves)
    volatility_B = mean(swing_B_moves)
    volatility_game = mean(swing_game_moves)

    volatility_sd_A = pstdev(swing_A_moves)
    volatility_sd_B = pstdev(swing_B_moves)
    volatility_sd_game = pstdev(swing_game_moves)

    total_volatility_A = sum(swing_A_moves)
    total_volatility_B = sum(swing_B_moves)
    total_volatility_game = sum(swing_game_moves)

    mean_es_loss_A = mean(es_loss_A_moves)
    mean_es_loss_B = mean(es_loss_B_moves)
    mean_es_loss_game = mean(es_loss_A_moves + es_loss_B_moves)

    es_loss_sd_A = pstdev(es_loss_A_moves)
    es_loss_sd_B = pstdev(es_loss_B_moves)
    es_loss_sd_game = pstdev(es_loss_A_moves + es_loss_B_moves)

    rms_es_loss_A = rms(es_loss_A_moves)
    rms_es_loss_B = rms(es_loss_B_moves)
    rms_es_loss_game = rms(es_loss_A_moves + es_loss_B_moves)

    error_concentration_A = safe_div(rms_es_loss_A, mean_es_loss_A)
    error_concentration_B = safe_div(rms_es_loss_B, mean_es_loss_B)
    error_concentration_game = safe_div(rms_es_loss_game, mean_es_loss_game)

    # ------------------------------------------------------------
    # 3. Difficulty metrics
    # ------------------------------------------------------------

    difficulty_summary = {}

    if compute_difficulty:
        for metric_name in difficulty_metric_names:
            a_weights = difficulty_A[metric_name]
            b_weights = difficulty_B[metric_name]
            game_weights = difficulty_game[metric_name]

            short_name = metric_name.replace("position_difficulty_", "difficulty_")

            difficulty_summary[f"mean_{short_name}_A"] = mean(a_weights)
            difficulty_summary[f"mean_{short_name}_B"] = mean(b_weights)
            difficulty_summary[f"mean_{short_name}_game"] = mean(game_weights)
            difficulty_summary[f"sd_{short_name}_A"] = pstdev(a_weights)
            difficulty_summary[f"sd_{short_name}_B"] = pstdev(b_weights)
            difficulty_summary[f"sd_{short_name}_game"] = pstdev(game_weights)
            difficulty_summary[f"total_{short_name}_A"] = sum(v for v in a_weights if is_number(v))
            difficulty_summary[f"total_{short_name}_B"] = sum(v for v in b_weights if is_number(v))
            difficulty_summary[f"total_{short_name}_game"] = sum(v for v in game_weights if is_number(v))

            dw_loss_A, dw_acc_A = weighted_loss_and_accuracy(es_loss_A_moves, a_weights)
            dw_loss_B, dw_acc_B = weighted_loss_and_accuracy(es_loss_B_moves, b_weights)
            dw_loss_game, dw_acc_game = weighted_loss_and_accuracy(
                es_loss_game_moves,
                game_weights,
            )

            difficulty_summary[f"{short_name}_weighted_es_loss_A"] = dw_loss_A
            difficulty_summary[f"{short_name}_weighted_es_loss_B"] = dw_loss_B
            difficulty_summary[f"{short_name}_weighted_es_loss_game"] = dw_loss_game
            difficulty_summary[f"{short_name}_weighted_accuracy_A"] = dw_acc_A
            difficulty_summary[f"{short_name}_weighted_accuracy_B"] = dw_acc_B
            difficulty_summary[f"{short_name}_weighted_accuracy_game"] = dw_acc_game

        difficulty_summary.update({
            "mean_legal_rms_loss_A": mean(legal_rms_loss_A),
            "mean_legal_rms_loss_B": mean(legal_rms_loss_B),
            "mean_legal_rms_loss_game": mean(legal_rms_loss_game),
            "sd_legal_rms_loss_A": pstdev(legal_rms_loss_A),
            "sd_legal_rms_loss_B": pstdev(legal_rms_loss_B),
            "sd_legal_rms_loss_game": pstdev(legal_rms_loss_game),
            "mean_narrowness_A": mean(narrowness_A),
            "mean_narrowness_B": mean(narrowness_B),
            "mean_narrowness_game": mean(narrowness_game),
            "sd_narrowness_A": pstdev(narrowness_A),
            "sd_narrowness_B": pstdev(narrowness_B),
            "sd_narrowness_game": pstdev(narrowness_game),
            "mean_effective_good_moves_A": mean(effective_good_moves_A),
            "mean_effective_good_moves_B": mean(effective_good_moves_B),
            "mean_effective_good_moves_game": mean(effective_good_moves_game),
            "sd_effective_good_moves_A": pstdev(effective_good_moves_A),
            "sd_effective_good_moves_B": pstdev(effective_good_moves_B),
            "sd_effective_good_moves_game": pstdev(effective_good_moves_game),
        })

        for metric_name in ccp_metric_names:
            short_name = metric_name
            a_weights = ccp_difficulty_A[metric_name]
            b_weights = ccp_difficulty_B[metric_name]
            game_weights = ccp_difficulty_game[metric_name]

            difficulty_summary[f"mean_{short_name}_A"] = mean(a_weights)
            difficulty_summary[f"mean_{short_name}_B"] = mean(b_weights)
            difficulty_summary[f"mean_{short_name}_game"] = mean(game_weights)
            difficulty_summary[f"sd_{short_name}_A"] = pstdev(a_weights)
            difficulty_summary[f"sd_{short_name}_B"] = pstdev(b_weights)
            difficulty_summary[f"sd_{short_name}_game"] = pstdev(game_weights)
            difficulty_summary[f"total_{short_name}_A"] = safe_sum(a_weights)
            difficulty_summary[f"total_{short_name}_B"] = safe_sum(b_weights)
            difficulty_summary[f"total_{short_name}_game"] = safe_sum(game_weights)

            ccp_dw_loss_A, ccp_dw_acc_A = weighted_loss_and_accuracy(es_loss_A_moves, a_weights)
            ccp_dw_loss_B, ccp_dw_acc_B = weighted_loss_and_accuracy(es_loss_B_moves, b_weights)
            ccp_dw_loss_game, ccp_dw_acc_game = weighted_loss_and_accuracy(es_loss_game_moves, game_weights)

            difficulty_summary[f"{short_name}_weighted_es_loss_A"] = ccp_dw_loss_A
            difficulty_summary[f"{short_name}_weighted_es_loss_B"] = ccp_dw_loss_B
            difficulty_summary[f"{short_name}_weighted_es_loss_game"] = ccp_dw_loss_game
            difficulty_summary[f"{short_name}_weighted_accuracy_A"] = ccp_dw_acc_A
            difficulty_summary[f"{short_name}_weighted_accuracy_B"] = ccp_dw_acc_B
            difficulty_summary[f"{short_name}_weighted_accuracy_game"] = ccp_dw_acc_game

        difficulty_summary.update({
            "mean_ccp_immediate_burden_A": mean(ccp_immediate_burden_A),
            "mean_ccp_immediate_burden_B": mean(ccp_immediate_burden_B),
            "mean_ccp_immediate_burden_game": mean(ccp_immediate_burden_game),
            "sd_ccp_immediate_burden_A": pstdev(ccp_immediate_burden_A),
            "sd_ccp_immediate_burden_B": pstdev(ccp_immediate_burden_B),
            "sd_ccp_immediate_burden_game": pstdev(ccp_immediate_burden_game),
            "mean_ccp_quiet_to_ccp_burden_A": mean(ccp_quiet_to_ccp_burden_A),
            "mean_ccp_quiet_to_ccp_burden_B": mean(ccp_quiet_to_ccp_burden_B),
            "mean_ccp_quiet_to_ccp_burden_game": mean(ccp_quiet_to_ccp_burden_game),
            "sd_ccp_quiet_to_ccp_burden_A": pstdev(ccp_quiet_to_ccp_burden_A),
            "sd_ccp_quiet_to_ccp_burden_B": pstdev(ccp_quiet_to_ccp_burden_B),
            "sd_ccp_quiet_to_ccp_burden_game": pstdev(ccp_quiet_to_ccp_burden_game),
            "mean_ccp_candidate_effective_count_A": mean(ccp_candidate_effective_count_A),
            "mean_ccp_candidate_effective_count_B": mean(ccp_candidate_effective_count_B),
            "mean_ccp_candidate_effective_count_game": mean(ccp_candidate_effective_count_game),
            "sd_ccp_candidate_effective_count_A": pstdev(ccp_candidate_effective_count_A),
            "sd_ccp_candidate_effective_count_B": pstdev(ccp_candidate_effective_count_B),
            "sd_ccp_candidate_effective_count_game": pstdev(ccp_candidate_effective_count_game),
        })

        if ccp_v2_enabled:
            for metric_name in ccp_v2_metric_names:
                a_weights = ccp_v2_difficulty_A[metric_name]
                b_weights = ccp_v2_difficulty_B[metric_name]
                game_weights = ccp_v2_difficulty_game[metric_name]
                difficulty_summary[f"mean_{metric_name}_A"] = mean(a_weights)
                difficulty_summary[f"mean_{metric_name}_B"] = mean(b_weights)
                difficulty_summary[f"mean_{metric_name}_game"] = mean(game_weights)
                difficulty_summary[f"sd_{metric_name}_A"] = pstdev(a_weights)
                difficulty_summary[f"sd_{metric_name}_B"] = pstdev(b_weights)
                difficulty_summary[f"sd_{metric_name}_game"] = pstdev(game_weights)
                difficulty_summary[f"total_{metric_name}_A"] = safe_sum(a_weights)
                difficulty_summary[f"total_{metric_name}_B"] = safe_sum(b_weights)
                difficulty_summary[f"total_{metric_name}_game"] = safe_sum(game_weights)

                v2_dw_loss_A, v2_dw_acc_A = weighted_loss_and_accuracy(es_loss_A_moves, a_weights)
                v2_dw_loss_B, v2_dw_acc_B = weighted_loss_and_accuracy(es_loss_B_moves, b_weights)
                v2_dw_loss_game, v2_dw_acc_game = weighted_loss_and_accuracy(es_loss_game_moves, game_weights)
                difficulty_summary[f"{metric_name}_weighted_es_loss_A"] = v2_dw_loss_A
                difficulty_summary[f"{metric_name}_weighted_es_loss_B"] = v2_dw_loss_B
                difficulty_summary[f"{metric_name}_weighted_es_loss_game"] = v2_dw_loss_game
                difficulty_summary[f"{metric_name}_weighted_accuracy_A"] = v2_dw_acc_A
                difficulty_summary[f"{metric_name}_weighted_accuracy_B"] = v2_dw_acc_B
                difficulty_summary[f"{metric_name}_weighted_accuracy_game"] = v2_dw_acc_game

            difficulty_summary.update({
                "mean_ccp_v2_nodes_searched_A": mean(ccp_v2_nodes_searched_A),
                "mean_ccp_v2_nodes_searched_B": mean(ccp_v2_nodes_searched_B),
                "mean_ccp_v2_nodes_searched_game": mean(ccp_v2_nodes_searched_game),
                "mean_ccp_v2_eval_attempts_A": mean(ccp_v2_eval_attempts_A),
                "mean_ccp_v2_eval_attempts_B": mean(ccp_v2_eval_attempts_B),
                "mean_ccp_v2_eval_attempts_game": mean(ccp_v2_eval_attempts_game),
                "mean_ccp_v2_cap_hit_A": mean(ccp_v2_cap_hit_A),
                "mean_ccp_v2_cap_hit_B": mean(ccp_v2_cap_hit_B),
                "mean_ccp_v2_cap_hit_game": mean(ccp_v2_cap_hit_game),
                "mean_ccp_v2_leaf_count_A": mean(ccp_v2_leaf_count_A),
                "mean_ccp_v2_leaf_count_B": mean(ccp_v2_leaf_count_B),
                "mean_ccp_v2_leaf_count_game": mean(ccp_v2_leaf_count_game),
                "mean_ccp_v2_max_chain_length_A": mean(ccp_v2_max_chain_length_A),
                "mean_ccp_v2_max_chain_length_B": mean(ccp_v2_max_chain_length_B),
                "mean_ccp_v2_max_chain_length_game": mean(ccp_v2_max_chain_length_game),
                "mean_ccp_v2_mean_chain_length_A": mean(ccp_v2_mean_chain_length_A),
                "mean_ccp_v2_mean_chain_length_B": mean(ccp_v2_mean_chain_length_B),
                "mean_ccp_v2_mean_chain_length_game": mean(ccp_v2_mean_chain_length_game),
                "mean_ccp_v2_quiet_pause_count_A": mean(ccp_v2_quiet_pause_count_A),
                "mean_ccp_v2_quiet_pause_count_B": mean(ccp_v2_quiet_pause_count_B),
                "mean_ccp_v2_quiet_pause_count_game": mean(ccp_v2_quiet_pause_count_game),
                "mean_ccp_v2_quiet_pause_burden_A": mean(ccp_v2_quiet_pause_burden_A),
                "mean_ccp_v2_quiet_pause_burden_B": mean(ccp_v2_quiet_pause_burden_B),
                "mean_ccp_v2_quiet_pause_burden_game": mean(ccp_v2_quiet_pause_burden_game),
                "mean_ccp_v2_branch_total_A": mean(ccp_v2_branch_total_A),
                "mean_ccp_v2_branch_total_B": mean(ccp_v2_branch_total_B),
                "mean_ccp_v2_branch_total_game": mean(ccp_v2_branch_total_game),
                "mean_ccp_v2_branch_effective_count_A": mean(ccp_v2_branch_effective_count_A),
                "mean_ccp_v2_branch_effective_count_B": mean(ccp_v2_branch_effective_count_B),
                "mean_ccp_v2_branch_effective_count_game": mean(ccp_v2_branch_effective_count_game),
                "mean_ccp_v2_branch_ambiguity_A": mean(ccp_v2_branch_ambiguity_A),
                "mean_ccp_v2_branch_ambiguity_B": mean(ccp_v2_branch_ambiguity_B),
                "mean_ccp_v2_branch_ambiguity_game": mean(ccp_v2_branch_ambiguity_game),
                "sd_ccp_v2_branch_total_A": pstdev(ccp_v2_branch_total_A),
                "sd_ccp_v2_branch_total_B": pstdev(ccp_v2_branch_total_B),
                "sd_ccp_v2_branch_total_game": pstdev(ccp_v2_branch_total_game),
            })

    # ------------------------------------------------------------
    # 4. Result metrics
    # ------------------------------------------------------------

    score_A = score_for_player(result, chess.WHITE)
    score_B = score_for_player(result, chess.BLACK)

    hard_rap_A = pq_A * score_A if pq_A is not None and score_A is not None else None
    hard_rap_B = pq_B * score_B if pq_B is not None and score_B is not None else None

    hard_rap_game = (
        hard_rap_A + hard_rap_B
        if hard_rap_A is not None and hard_rap_B is not None
        else None
    )

    soft_rap_A = (
        pq_A * (0.5 + 0.5 * score_A)
        if pq_A is not None and score_A is not None
        else None
    )

    soft_rap_B = (
        pq_B * (0.5 + 0.5 * score_B)
        if pq_B is not None and score_B is not None
        else None
    )

    soft_rap_game = (
        soft_rap_A + soft_rap_B
        if soft_rap_A is not None and soft_rap_B is not None
        else None
    )

    # Expected score over the whole game-flow.
    # From White's perspective, and therefore Player A's perspective.
    if weighting == "ply":
        weights = list(range(1, len(es_white_positions) + 1))
    else:
        weights = [1] * len(es_white_positions)

    expected_score_A = weighted_average(es_white_positions, weights)
    expected_score_B = 1.0 - expected_score_A if expected_score_A is not None else None

    conversion_A = (
        score_A - expected_score_A
        if score_A is not None and expected_score_A is not None
        else None
    )

    conversion_B = (
        score_B - expected_score_B
        if score_B is not None and expected_score_B is not None
        else None
    )

    conversion_game = (
        abs(conversion_A) + abs(conversion_B)
        if conversion_A is not None and conversion_B is not None
        else None
    )

    per_game_row = {
        "game_id": game_id,
        "white": white_name,
        "black": black_name,
        "player_A": white_name,
        "player_B": black_name,
        "result": result,
        "plies": n,

        # Accuracy metrics
        "accuracy_A_wdl": A,
        "accuracy_B_wdl": B,
        "accuracy_sd_A_wdl": accuracy_sd_A,
        "accuracy_sd_B_wdl": accuracy_sd_B,
        "game_accuracy_wdl": game_accuracy,
        "mutual_accuracy_wdl": mutual_accuracy,
        "pq_A_wdl": pq_A,
        "pq_B_wdl": pq_B,
        "dominance_A_wdl": dominance_A,
        "dominance_B_wdl": dominance_B,

        # Volatility metrics
        "volatility_A_wdl": volatility_A,
        "volatility_B_wdl": volatility_B,
        "volatility_game_wdl": volatility_game,
        "volatility_sd_A_wdl": volatility_sd_A,
        "volatility_sd_B_wdl": volatility_sd_B,
        "volatility_sd_game_wdl": volatility_sd_game,
        "total_volatility_A_wdl": total_volatility_A,
        "total_volatility_B_wdl": total_volatility_B,
        "total_volatility_game_wdl": total_volatility_game,

        # Expected-score loss metrics
        "mean_es_loss_A": mean_es_loss_A,
        "mean_es_loss_B": mean_es_loss_B,
        "mean_es_loss_game": mean_es_loss_game,
        "es_loss_sd_A": es_loss_sd_A,
        "es_loss_sd_B": es_loss_sd_B,
        "es_loss_sd_game": es_loss_sd_game,
        "rms_es_loss_A": rms_es_loss_A,
        "rms_es_loss_B": rms_es_loss_B,
        "rms_es_loss_game": rms_es_loss_game,
        "error_concentration_A": error_concentration_A,
        "error_concentration_B": error_concentration_B,
        "error_concentration_game": error_concentration_game,

        # Result metrics
        "score_A": score_A,
        "score_B": score_B,
        "hard_rap_A": hard_rap_A,
        "hard_rap_B": hard_rap_B,
        "hard_rap_game": hard_rap_game,
        "soft_rap_A": soft_rap_A,
        "soft_rap_B": soft_rap_B,
        "soft_rap_game": soft_rap_game,
        "expected_score_A": expected_score_A,
        "expected_score_B": expected_score_B,
        "conversion_A": conversion_A,
        "conversion_B": conversion_B,
        "conversion_game": conversion_game,
    }

    per_game_row.update(difficulty_summary)

    return per_game_row, per_move_rows, ccp_v2_root_branch_rows


def summarize_games(per_game_df):
    rows = []

    numeric_cols = per_game_df.select_dtypes(include="number").columns

    for col in numeric_cols:
        values = per_game_df[col].dropna().tolist()

        rows.append({
            "metric": col,
            "mean": mean(values),
            "population_sd": pstdev(values),
            "n": len(values),
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Stockfish 18 WDL-based chess metrics analyzer with legal-move difficulty estimates."
    )

    parser.add_argument("pgn", help="Input PGN file")
    parser.add_argument("--stockfish", required=True, help="Path to Stockfish executable")
    # Backward-compatible generic limits. If --main-* or --difficulty-* are
    # omitted, these are used as defaults.
    parser.add_argument("--depth", type=int, default=16, help="Default search depth")
    parser.add_argument("--movetime", type=float, default=None, help="Default move time in seconds")
    parser.add_argument("--nodes", type=int, default=None, help="Default node limit")

    # Separate normal WDL and difficulty budgets.
    parser.add_argument("--main-depth", type=int, default=None, help="Search depth for normal WDL game-flow analysis")
    parser.add_argument("--main-movetime", type=float, default=None, help="Move time in seconds for normal WDL game-flow analysis")
    parser.add_argument("--main-nodes", type=int, default=None, help="Node limit for normal WDL game-flow analysis")
    parser.add_argument("--difficulty-depth", type=int, default=None, help="Search depth for all-legal difficulty analysis")
    parser.add_argument("--difficulty-movetime", type=float, default=None, help="Move time in seconds for all-legal difficulty analysis")
    parser.add_argument("--difficulty-nodes", type=int, default=None, help="Node limit for all-legal difficulty analysis")
    parser.add_argument("--hybrid-depth", type=int, default=None, help="Optional deeper depth for hybrid top-K re-analysis")
    parser.add_argument("--hybrid-movetime", type=float, default=None, help="Optional deeper movetime for hybrid top-K re-analysis")
    parser.add_argument("--hybrid-nodes", type=int, default=None, help="Optional deeper node limit for hybrid top-K re-analysis")

    parser.add_argument("--threads", type=int, default=1, help="Number of Stockfish CPU threads")
    parser.add_argument("--hash", dest="hash_mb", type=int, default=16, help="Stockfish hash size in MB")
    parser.add_argument(
        "--weighting",
        choices=["uniform", "ply"],
        default="ply",
        help="ExpectedScore weighting method for Conversion"
    )
    parser.add_argument(
        "--outdir",
        default="wdl_output_v3_difficulty",
        help="Output directory"
    )
    parser.add_argument(
        "--no-difficulty",
        action="store_true",
        help="Disable difficulty analysis and run like the original v2 analyzer."
    )
    parser.add_argument(
        "--difficulty-mode",
        choices=["all-legal", "multipv", "hybrid"],
        default="all-legal",
        help="Difficulty method: all-legal = evaluate every legal move; multipv = top-K only; hybrid = all-legal shallow plus deeper top-K re-analysis."
    )
    parser.add_argument(
        "--difficulty-multipv",
        type=int,
        default=10,
        help="Top-K moves for --difficulty-mode multipv. Default: 10"
    )
    parser.add_argument(
        "--difficulty-hybrid-topk",
        type=int,
        default=5,
        help="Top-K shallow legal moves re-analysed with the hybrid limit. Default: 5"
    )
    parser.add_argument(
        "--difficulty-tau",
        type=float,
        default=0.03,
        help="Softmax sensitivity for legal-move losses. Smaller = stricter near-best separation. Default: 0.03"
    )
    parser.add_argument("--ccp-v2", action="store_true", help="Enable experimental CCP Search Difficulty Version 2 candidate-tree search.")
    parser.add_argument("--ccp-v2-depth", type=int, default=5, help="Maximum CCP-v2 candidate-tree depth in plies. Default: 5")
    parser.add_argument("--ccp-v2-nodes", type=int, default=10000, help="Node limit per CCP-v2 confirm/tree-node evaluation. Default: 10000")
    parser.add_argument("--ccp-v2-two-stage", action="store_true", help="Enable two-stage CCP-v2: cheap broad probe, then higher-node confirmation on selected root branches.")
    parser.add_argument("--ccp-v2-probe-nodes", type=int, default=None, help="Node limit per CCP-v2 probe evaluation. If omitted, uses --ccp-v2-nodes.")
    parser.add_argument("--ccp-v2-probe-movetime", type=float, default=None, help="Optional movetime per CCP-v2 probe evaluation.")
    parser.add_argument("--ccp-v2-probe-engine-depth", type=int, default=None, help="Optional engine depth per CCP-v2 probe evaluation, used only if probe nodes/movetime are omitted.")
    parser.add_argument("--ccp-v2-probe-depth", type=int, default=None, help="Maximum recursive depth for the probe stage. If omitted, uses --ccp-v2-depth.")
    parser.add_argument("--ccp-v2-probe-max-expanded-positions", dest="ccp_v2_probe_max_tree_nodes", type=int, default=None, help="Maximum expanded CCP-v2 positions per root during the probe stage. If omitted, uses --ccp-v2-max-expanded-positions.")
    parser.add_argument("--ccp-v2-probe-max-engine-calls-per-root", dest="ccp_v2_probe_max_engine_evals_per_root", type=int, default=0, help="Maximum probe evaluation attempts per root. 0 = no explicit probe cap. Default: 0")
    parser.add_argument("--ccp-v2-confirm-candidates", type=int, default=8, help="Number of probed root branches confirmed at the normal CCP-v2 budget. -1 = all probed branches. Default: 8")
    parser.add_argument("--ccp-v2-confirm-score-mode", choices=["log", "raw", "saturated"], default="log", help="Stable priority score used to choose confirmation branches from probe branches. Default: log")
    parser.add_argument("--ccp-v2-saturation-k", type=float, default=1.0, help="k for saturated confirmation priority raw/(raw+k). Default: 1.0")
    parser.add_argument("--ccp-v2-movetime", type=float, default=None, help="Optional movetime per CCP-v2 confirm/tree-node evaluation.")
    parser.add_argument("--ccp-v2-engine-depth", type=int, default=None, help="Optional engine depth per CCP-v2 tree-node evaluation, used only if nodes/movetime are omitted.")
    parser.add_argument("--ccp-v2-max-tree-nodes", "--ccp-v2-max-expanded-positions", dest="ccp_v2_max_tree_nodes", type=int, default=200, help="Maximum expanded CCP-v2 positions per root. This is not the same as engine calls. Default: 200")
    parser.add_argument("--ccp-v2-max-engine-calls-per-root", dest="ccp_v2_max_engine_evals_per_root", type=int, default=0, help="Maximum CCP-v2 position/move evaluation attempts per root. 0 = no explicit eval cap. Default: 0")
    parser.add_argument("--ccp-v2-quiet-candidates", type=int, default=4, help="Maximum positive-proxy quiet candidates evaluated per CCP-v2 node. -1 = all positive-proxy quiet candidates. Default: 4")
    parser.add_argument("--ccp-v2-include-all-root-quiet", action="store_true", help="At the root only, evaluate all quiet moves as candidates; deeper nodes still use --ccp-v2-quiet-candidates.")
    parser.add_argument("--ccp-v2-vision-depth", type=int, default=0, help="Optional one-sided ideal-vision depth for quiet candidate prioritization. 0 = disabled. Default: 0")
    parser.add_argument("--ccp-v2-vision-branch", type=int, default=6, help="Maximum child moves per ply in the one-sided ideal-vision proxy. Default: 6")
    parser.add_argument("--ccp-v2-vision-decay", type=float, default=0.65, help="Depth decay for the one-sided ideal-vision proxy. Default: 0.65")
    parser.add_argument("--ccp-v2-vision-mode", choices=["off", "root", "all"], default="root", help="Where to run the expensive one-sided vision proxy. root = root node only (default); all = every CCP-v2 node; off = disabled even if depth > 0.")
    parser.add_argument("--ccp-v2-vision-candidates", type=int, default=12, help="Maximum pre-filtered positive-proxy quiet moves per eligible node that receive the expensive vision proxy. -1 = all positive-proxy quiet moves. Default: 12")
    parser.add_argument("--ccp-v2-max-branch", type=int, default=0, help="Optional post-evaluation branch cap per tree node. 0 = no branch-count cap. Default: 0")
    parser.add_argument("--ccp-v2-min-plausibility", type=float, default=0.0, help="Optional soft plausibility cutoff for branch expansion. Default: 0.0")
    parser.add_argument("--ccp-v2-tau", type=float, default=None, help="Softmax tau for CCP-v2. Defaults to --difficulty-tau.")
    parser.add_argument("--ccp-v2-alpha-chain", type=float, default=0.25, help="CCP-v2 chain-length bonus coefficient. Default: 0.25")
    parser.add_argument("--ccp-v2-beta-quiet", type=float, default=0.50, help="CCP-v2 quiet-pause bonus coefficient. Default: 0.50")
    parser.add_argument("--ccp-v2-child-weight", type=float, default=0.50, help="CCP-v2 child subtree contribution weight. Default: 0.50")

    args = parser.parse_args()

    pgn_path = Path(args.pgn)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    main_depth = args.main_depth if args.main_depth is not None else args.depth
    main_movetime = args.main_movetime if args.main_movetime is not None else args.movetime
    main_nodes = args.main_nodes if args.main_nodes is not None else args.nodes

    difficulty_depth = args.difficulty_depth if args.difficulty_depth is not None else args.depth
    difficulty_movetime = args.difficulty_movetime if args.difficulty_movetime is not None else args.movetime
    difficulty_nodes = args.difficulty_nodes if args.difficulty_nodes is not None else args.nodes

    hybrid_depth = args.hybrid_depth
    hybrid_movetime = args.hybrid_movetime
    hybrid_nodes = args.hybrid_nodes

    main_limit = make_limit(depth=main_depth, movetime=main_movetime, nodes=main_nodes)
    difficulty_limit = make_limit(depth=difficulty_depth, movetime=difficulty_movetime, nodes=difficulty_nodes)
    hybrid_limit = None
    if hybrid_depth is not None or hybrid_movetime is not None or hybrid_nodes is not None:
        hybrid_limit = make_limit(depth=hybrid_depth or difficulty_depth, movetime=hybrid_movetime, nodes=hybrid_nodes)

    ccp_v2_limit = None
    ccp_v2_probe_limit = None
    if args.ccp_v2:
        ccp_v2_limit = make_limit(depth=args.ccp_v2_engine_depth or difficulty_depth, movetime=args.ccp_v2_movetime, nodes=args.ccp_v2_nodes)
        probe_nodes = args.ccp_v2_probe_nodes if args.ccp_v2_probe_nodes is not None else args.ccp_v2_nodes
        probe_depth = args.ccp_v2_probe_engine_depth or args.ccp_v2_engine_depth or difficulty_depth
        ccp_v2_probe_limit = make_limit(depth=probe_depth, movetime=args.ccp_v2_probe_movetime, nodes=probe_nodes)

    main_cache_key = limit_signature("main", depth=main_depth, movetime=main_movetime, nodes=main_nodes)
    difficulty_cache_key = limit_signature("difficulty", depth=difficulty_depth, movetime=difficulty_movetime, nodes=difficulty_nodes)
    hybrid_cache_key = (
        limit_signature("hybrid", depth=hybrid_depth or difficulty_depth, movetime=hybrid_movetime, nodes=hybrid_nodes)
        if hybrid_limit is not None else None
    )
    ccp_v2_cache_key = (
        limit_signature("ccp_v2_confirm", depth=args.ccp_v2_engine_depth or difficulty_depth, movetime=args.ccp_v2_movetime, nodes=args.ccp_v2_nodes)
        if args.ccp_v2 else None
    )
    ccp_v2_probe_cache_key = (
        limit_signature("ccp_v2_probe", depth=args.ccp_v2_probe_engine_depth or args.ccp_v2_engine_depth or difficulty_depth, movetime=args.ccp_v2_probe_movetime, nodes=(args.ccp_v2_probe_nodes if args.ccp_v2_probe_nodes is not None else args.ccp_v2_nodes))
        if args.ccp_v2 else None
    )

    per_game_rows = []
    per_move_rows_all = []
    ccp_v2_root_branch_rows_all = []
    analysis_cache = {}
    stats = {
        "engine_calls": 0,
        "cache_hits": 0,
        "difficulty_positions": 0,
        "legal_moves_seen": 0,
        "multipv_positions": 0,
        "multipv_requested": 0,
        "ccp_v2_positions": 0,
        "ccp_v2_legal_moves_seen": 0,
        "ccp_v2_eval_attempts": 0,
        "ccp_v2_eval_cap_hits": 0,
        "ccp_v2_child_moves_evaluated": 0,
        "ccp_v2_candidate_moves_selected": 0,
        "ccp_v2_ccp_candidates_selected": 0,
        "ccp_v2_quiet_candidates_selected": 0,
        "ccp_v2_child_evals_skipped_by_cap": 0,
        "ccp_v2_vision_probes": 0,
        "ccp_v2_vision_candidate_moves_seen": 0,
        "ccp_v2_vision_seconds": 0.0,
        "ccp_v2_vision_skipped_nonroot_nodes": 0,
        "nodes_searched_total": 0,
        "engine_reported_time_total": 0.0,
        "nps_values": [],
        "hashfull_values": [],
    }
    started_at = time.perf_counter()

    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        engine.configure({
            "UCI_ShowWDL": True,
            "Threads": args.threads,
            "Hash": args.hash_mb,
        })

        with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
            game_id = 1

            while True:
                game = chess.pgn.read_game(pgn_file)

                if game is None:
                    break

                print(
                    f"Analyzing game {game_id}: "
                    f"{game.headers.get('White', 'White')} vs "
                    f"{game.headers.get('Black', 'Black')}"
                )

                if not args.no_difficulty:
                    print(
                        f"  Difficulty mode: {args.difficulty_mode}; "
                        f"main={main_cache_key}; difficulty={difficulty_cache_key}"
                    )
                    if args.ccp_v2:
                        print(
                            f"  CCP v2 enabled: ccp_v2={ccp_v2_cache_key}; two_stage={args.ccp_v2_two_stage}; "
                            f"probe={ccp_v2_probe_cache_key}; depth={args.ccp_v2_depth}; max_expanded_positions={args.ccp_v2_max_tree_nodes}; "
                            f"max_evals_per_root={args.ccp_v2_max_engine_evals_per_root}; quiet_candidates={args.ccp_v2_quiet_candidates}; "
                            f"vision_depth={args.ccp_v2_vision_depth}; vision_branch={args.ccp_v2_vision_branch}; "
                            f"vision_mode={args.ccp_v2_vision_mode}; vision_candidates={args.ccp_v2_vision_candidates}"
                        )

                per_game_row, per_move_rows, ccp_v2_root_branch_rows = analyze_game(
                    engine=engine,
                    game=game,
                    game_id=game_id,
                    main_limit=main_limit,
                    main_cache_key=main_cache_key,
                    difficulty_limit=difficulty_limit,
                    difficulty_cache_key=difficulty_cache_key,
                    hybrid_deep_limit=hybrid_limit,
                    hybrid_cache_key=hybrid_cache_key,
                    cache=analysis_cache,
                    stats=stats,
                    weighting=args.weighting,
                    compute_difficulty=not args.no_difficulty,
                    difficulty_tau=args.difficulty_tau,
                    difficulty_mode=args.difficulty_mode,
                    difficulty_multipv=args.difficulty_multipv,
                    difficulty_hybrid_topk=args.difficulty_hybrid_topk,
                    ccp_v2_enabled=args.ccp_v2,
                    ccp_v2_two_stage=args.ccp_v2_two_stage,
                    ccp_v2_limit=ccp_v2_limit,
                    ccp_v2_probe_limit=ccp_v2_probe_limit,
                    ccp_v2_cache_key=ccp_v2_cache_key,
                    ccp_v2_probe_cache_key=ccp_v2_probe_cache_key,
                    ccp_v2_tau=args.ccp_v2_tau,
                    ccp_v2_depth=args.ccp_v2_depth,
                    ccp_v2_probe_depth=args.ccp_v2_probe_depth,
                    ccp_v2_max_tree_nodes=args.ccp_v2_max_tree_nodes,
                    ccp_v2_probe_max_tree_nodes=args.ccp_v2_probe_max_tree_nodes,
                    ccp_v2_max_branch=args.ccp_v2_max_branch,
                    ccp_v2_min_plausibility=args.ccp_v2_min_plausibility,
                    ccp_v2_alpha_chain=args.ccp_v2_alpha_chain,
                    ccp_v2_beta_quiet=args.ccp_v2_beta_quiet,
                    ccp_v2_child_weight=args.ccp_v2_child_weight,
                    ccp_v2_max_engine_evals_per_root=args.ccp_v2_max_engine_evals_per_root,
                    ccp_v2_probe_max_engine_evals_per_root=args.ccp_v2_probe_max_engine_evals_per_root,
                    ccp_v2_confirm_candidates=args.ccp_v2_confirm_candidates,
                    ccp_v2_confirm_score_mode=args.ccp_v2_confirm_score_mode,
                    ccp_v2_saturation_k=args.ccp_v2_saturation_k,
                    ccp_v2_quiet_candidates=args.ccp_v2_quiet_candidates,
                    ccp_v2_include_all_root_quiet=args.ccp_v2_include_all_root_quiet,
                    ccp_v2_vision_depth=args.ccp_v2_vision_depth,
                    ccp_v2_vision_branch=args.ccp_v2_vision_branch,
                    ccp_v2_vision_decay=args.ccp_v2_vision_decay,
                    ccp_v2_vision_mode=args.ccp_v2_vision_mode,
                    ccp_v2_vision_candidates=args.ccp_v2_vision_candidates,
                )

                per_game_rows.append(per_game_row)
                per_move_rows_all.extend(per_move_rows)
                ccp_v2_root_branch_rows_all.extend(ccp_v2_root_branch_rows)

                game_id += 1

    per_game_df = pd.DataFrame(per_game_rows)
    per_move_df = pd.DataFrame(per_move_rows_all)
    ccp_v2_root_branch_df = pd.DataFrame(ccp_v2_root_branch_rows_all)
    summary_df = summarize_games(per_game_df)

    elapsed_seconds = time.perf_counter() - started_at

    per_game_path = outdir / "per_game_wdl_metrics.csv"
    per_move_path = outdir / "per_move_wdl.csv"
    summary_path = outdir / "summary_wdl_metrics.csv"
    metadata_path = outdir / "analysis_metadata.csv"
    metadata_wide_path = outdir / "analysis_metadata_wide.csv"
    root_branch_path = outdir / "ccp_v2_root_branch_diagnostics.csv"

    per_game_df.to_csv(per_game_path, index=False)
    per_move_df.to_csv(per_move_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    if not ccp_v2_root_branch_df.empty:
        ccp_v2_root_branch_df.to_csv(root_branch_path, index=False)

    def _serial(value):
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.12g}"
        return str(value)

    legal_moves_seen = stats.get("legal_moves_seen", 0)
    engine_calls = stats.get("engine_calls", 0)
    cache_hits = stats.get("cache_hits", 0)
    total_cache_lookups = engine_calls + cache_hits

    nps_values = stats.get("nps_values", [])
    hashfull_values = stats.get("hashfull_values", [])
    nodes_searched_total = stats.get("nodes_searched_total", 0)
    engine_reported_time_total = stats.get("engine_reported_time_total", 0.0)

    metadata = {
        "analyzer_version": "v3.6.1_ccp_v2_root_branch_diagnostics_es_sentinel_fix",
        "difficulty_formula_version": "objective: pure=narrowness*sqrt(legal_rms_loss); soft=pure*sqrt(4B(1-B)); CCP v1: checks+captures+promotions immediate burden plus quiet-to-CCP material-threat proxy, no obviousness multiplier; CCP v2.2/3.4: recursive candidate tree with selected CCP + positive-proxy quiet candidates, optional root-only/pre-filtered one-sided ideal-vision quiet prioritization, optional two-stage probe/confirm search, directed ES gains, delayed payoff for quiet/sacrifice lines, chain length, quiet pauses, local plausibility weighting, and explicit workload caps",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "pgn_path": str(pgn_path),
        "stockfish_path": str(args.stockfish),
        "outdir": str(outdir),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "pandas_version": getattr(pd, "__version__", "unknown"),
        "python_chess_version": getattr(chess, "__version__", "unknown"),
        "threads": args.threads,
        "hash_mb": args.hash_mb,
        "weighting": args.weighting,
        "no_difficulty": args.no_difficulty,
        "difficulty_mode": args.difficulty_mode,
        "difficulty_tau": args.difficulty_tau,
        "difficulty_multipv": args.difficulty_multipv,
        "difficulty_hybrid_topk": args.difficulty_hybrid_topk,
        "ccp_v2_enabled": args.ccp_v2,
        "ccp_v2_two_stage": args.ccp_v2_two_stage,
        "ccp_v2_depth": args.ccp_v2_depth,
        "ccp_v2_probe_depth": args.ccp_v2_probe_depth,
        "ccp_v2_nodes": args.ccp_v2_nodes,
        "ccp_v2_probe_nodes": args.ccp_v2_probe_nodes,
        "ccp_v2_movetime": args.ccp_v2_movetime,
        "ccp_v2_engine_depth": args.ccp_v2_engine_depth,
        "ccp_v2_probe_engine_depth": args.ccp_v2_probe_engine_depth,
        "ccp_v2_probe_movetime": args.ccp_v2_probe_movetime,
        "ccp_v2_max_tree_nodes": args.ccp_v2_max_tree_nodes,
        "ccp_v2_probe_max_tree_nodes": args.ccp_v2_probe_max_tree_nodes,
        "ccp_v2_max_engine_evals_per_root": args.ccp_v2_max_engine_evals_per_root,
        "ccp_v2_probe_max_engine_evals_per_root": args.ccp_v2_probe_max_engine_evals_per_root,
        "ccp_v2_confirm_candidates": args.ccp_v2_confirm_candidates,
        "ccp_v2_confirm_score_mode": args.ccp_v2_confirm_score_mode,
        "ccp_v2_saturation_k": args.ccp_v2_saturation_k,
        "ccp_v2_quiet_candidates": args.ccp_v2_quiet_candidates,
        "ccp_v2_include_all_root_quiet": args.ccp_v2_include_all_root_quiet,
        "ccp_v2_vision_depth": args.ccp_v2_vision_depth,
        "ccp_v2_vision_branch": args.ccp_v2_vision_branch,
        "ccp_v2_vision_decay": args.ccp_v2_vision_decay,
        "ccp_v2_vision_mode": args.ccp_v2_vision_mode,
        "ccp_v2_vision_candidates": args.ccp_v2_vision_candidates,
        "ccp_v2_vision_probes": stats.get("ccp_v2_vision_probes", 0),
        "ccp_v2_vision_candidate_moves_seen": stats.get("ccp_v2_vision_candidate_moves_seen", 0),
        "ccp_v2_vision_seconds": stats.get("ccp_v2_vision_seconds", 0.0),
        "ccp_v2_vision_skipped_nonroot_nodes": stats.get("ccp_v2_vision_skipped_nonroot_nodes", 0),
        "ccp_v2_max_branch": args.ccp_v2_max_branch,
        "ccp_v2_min_plausibility": args.ccp_v2_min_plausibility,
        "ccp_v2_tau": args.ccp_v2_tau if args.ccp_v2_tau is not None else args.difficulty_tau,
        "ccp_v2_alpha_chain": args.ccp_v2_alpha_chain,
        "ccp_v2_beta_quiet": args.ccp_v2_beta_quiet,
        "ccp_v2_child_weight": args.ccp_v2_child_weight,
        "main_depth": main_depth,
        "main_movetime": main_movetime,
        "main_nodes": main_nodes,
        "difficulty_depth": difficulty_depth,
        "difficulty_movetime": difficulty_movetime,
        "difficulty_nodes": difficulty_nodes,
        "hybrid_depth": hybrid_depth,
        "hybrid_movetime": hybrid_movetime,
        "hybrid_nodes": hybrid_nodes,
        "main_limit_signature": main_cache_key,
        "difficulty_limit_signature": difficulty_cache_key,
        "hybrid_limit_signature": hybrid_cache_key,
        "ccp_v2_limit_signature": ccp_v2_cache_key,
        "ccp_v2_probe_limit_signature": ccp_v2_probe_cache_key,
        "games_analyzed": len(per_game_rows),
        "plies_analyzed": len(per_move_rows_all),
        "ccp_v2_root_branch_diagnostic_rows": len(ccp_v2_root_branch_rows_all),
        "difficulty_positions": stats.get("difficulty_positions", 0),
        "legal_moves_seen": legal_moves_seen,
        "ccp_v2_positions": stats.get("ccp_v2_positions", 0),
        "ccp_v2_legal_moves_seen": stats.get("ccp_v2_legal_moves_seen", 0),
        "ccp_v2_eval_attempts": stats.get("ccp_v2_eval_attempts", 0),
        "ccp_v2_eval_cap_hits": stats.get("ccp_v2_eval_cap_hits", 0),
        "ccp_v2_child_moves_evaluated": stats.get("ccp_v2_child_moves_evaluated", 0),
        "ccp_v2_candidate_moves_selected": stats.get("ccp_v2_candidate_moves_selected", 0),
        "ccp_v2_ccp_candidates_selected": stats.get("ccp_v2_ccp_candidates_selected", 0),
        "ccp_v2_quiet_candidates_selected": stats.get("ccp_v2_quiet_candidates_selected", 0),
        "ccp_v2_child_evals_skipped_by_cap": stats.get("ccp_v2_child_evals_skipped_by_cap", 0),
        "average_ccp_v2_legal_moves_seen_per_position": safe_div(stats.get("ccp_v2_legal_moves_seen", 0), stats.get("ccp_v2_positions", 0)),
        "average_ccp_v2_candidate_moves_selected_per_position": safe_div(stats.get("ccp_v2_candidate_moves_selected", 0), stats.get("ccp_v2_positions", 0)),
        "average_ccp_v2_child_moves_evaluated_per_position": safe_div(stats.get("ccp_v2_child_moves_evaluated", 0), stats.get("ccp_v2_positions", 0)),
        "average_ccp_v2_vision_probes_per_root_ply": safe_div(stats.get("ccp_v2_vision_probes", 0), len(per_move_rows_all)),
        "average_ccp_v2_vision_seconds_per_probe": safe_div(stats.get("ccp_v2_vision_seconds", 0.0), stats.get("ccp_v2_vision_probes", 0)),
        "average_legal_moves_per_difficulty_position": safe_div(legal_moves_seen, stats.get("difficulty_positions", 0)),
        "engine_calls": engine_calls,
        "cache_hits": cache_hits,
        "cache_size": len(analysis_cache),
        "cache_hit_rate": safe_div(cache_hits, total_cache_lookups),
        "multipv_positions": stats.get("multipv_positions", 0),
        "multipv_requested": stats.get("multipv_requested", 0),
        "nodes_searched_total": nodes_searched_total,
        "average_nodes_per_engine_call": safe_div(nodes_searched_total, engine_calls),
        "engine_reported_time_total": engine_reported_time_total,
        "average_engine_reported_time_per_call": safe_div(engine_reported_time_total, engine_calls),
        "mean_nps_reported": mean(nps_values),
        "max_nps_reported": max(nps_values) if nps_values else None,
        "mean_hashfull_reported_permille": mean(hashfull_values),
        "max_hashfull_reported_permille": max(hashfull_values) if hashfull_values else None,
        "elapsed_seconds": elapsed_seconds,
        "elapsed_minutes": elapsed_seconds / 60.0,
        "plies_per_second": safe_div(len(per_move_rows_all), elapsed_seconds),
        "legal_moves_seen_per_second": safe_div(legal_moves_seen, elapsed_seconds),
        "engine_calls_per_second": safe_div(engine_calls, elapsed_seconds),
    }

    # Long key-value metadata:
    # One row per metadata field, with both text and numeric columns.
    # This is easier to inspect in spreadsheet software than a plain 2-column
    # key/value file, and it avoids the impression that numeric fields were
    # "missing" when a spreadsheet auto-formats mixed-type values as text.
    metadata_long_rows = []
    for idx, (k, v) in enumerate(metadata.items(), start=1):
        serialized = _serial(v)
        numeric_value = None
        value_type = type(v).__name__
        if isinstance(v, bool):
            numeric_value = 1.0 if v else 0.0
        elif is_number(v):
            numeric_value = float(v)
        elif isinstance(serialized, str):
            # Keep numeric-looking strings also available as numbers, except NaN.
            try:
                parsed = float(serialized)
                if not math.isnan(parsed):
                    numeric_value = parsed
            except Exception:
                pass

        metadata_long_rows.append({
            "field_order": idx,
            "key": k,
            "value": serialized,
            "value_type": value_type,
            "numeric_value": numeric_value,
        })

    pd.DataFrame(metadata_long_rows).to_csv(metadata_path, index=False)

    # One-row wide metadata is easier to join into later aggregate reports.
    pd.DataFrame([{k: _serial(v) for k, v in metadata.items()}]).to_csv(metadata_wide_path, index=False)

    print("\nDone.")
    print(f"Per-game metrics: {per_game_path}")
    print(f"Per-move data:    {per_move_path}")
    print(f"Summary metrics:  {summary_path}")
    print(f"Metadata:         {metadata_path}")
    print(f"Metadata wide:    {metadata_wide_path}")
    print(f"Elapsed seconds:  {elapsed_seconds:.2f}")
    if legal_moves_seen:
        print(f"Legal eval rate:  {safe_div(legal_moves_seen, elapsed_seconds):.2f} legal moves/second")


if __name__ == "__main__":
    main()
