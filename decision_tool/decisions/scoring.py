"""
scoring.py — Hiring Decision Engine

INPUT:
    criteria = [
        {'id': 1, 'name': 'Salary',       'weight': 40, 'is_cost': False},
        {'id': 2, 'name': 'Experience',   'weight': 30, 'is_cost': False},
        {'id': 3, 'name': 'Test Score',   'weight': 30, 'is_cost': False},
    ]
    candidates = [
        {'id': 1, 'name': 'Alice', 'values': {1: 55000, 2: 7, 3: 82}},
        {'id': 2, 'name': 'Bob',   'values': {1: 48000, 2: 5, 3: 91}},
        {'id': 3, 'name': 'Carol', 'values': {1: 62000, 2: 9, 3: 74}},
    ]

HOW NORMALIZATION WORKS:
    Each criteria value is normalized across all candidates using min-max.
    This puts all criteria on a 0-1 scale regardless of their original units.

    benefit criteria (higher is better):
        normalized = (value - min) / (max - min)

    cost criteria (lower is better, e.g. notice period in weeks):
        normalized = (max - value) / (max - min)

    Edge case — all candidates have identical value for a criteria:
        normalized = 0.5  (neutral — this criteria has no discriminating power)

    Edge case — only 2 candidates:
        Works correctly. One gets 0, other gets 1.
        The final scores will still differ because weights distribute
        across multiple criteria — they won't both be 0.5 unless
        every single criteria is perfectly balanced, which reflects reality.

FINAL SCORE:
    score = sum( normalized_value_i * normalized_weight_i ) for all criteria i
    Result is between 0 and 1, displayed as percentage.
"""

from django.conf import settings


# ── Smart scale defaults ───────────────────────────────────────────────────────
# Maps keyword patterns to (min, max, unit_label).
# Applied automatically when user leaves scale_min/scale_max blank.
# This prevents "4 vs 5 on a 10-point scale" from stretching to 0%–100%.

_SMART_SCALES = [
    # Test / aptitude scores
    (['test score', 'aptitude', 'written test', 'assessment score',
      'gre', 'gmat', 'ielts', 'toefl'], 0, 100, 'score /100'),

    # Experience in years
    (['experience', 'years of exp', 'work exp', 'relevant exp',
      'total exp', 'exp years'], 0, 20, 'yrs'),

    # Salary in INR / rupees — realistic range 0–10L (most hiring roles)
    (['salary', 'ctc', 'package', 'compensation', 'rupees', 'inr',
      'lpa', 'lakh'], 0, 1000000, '₹ (0–10L)'),

    # Notice period — days
    (['notice period', 'notice days', 'joining days'], 0, 180, 'days'),

    # Notice period — weeks
    (['notice weeks'], 0, 26, 'weeks'),

    # Notice period — months
    (['notice months', 'notice period (months)'], 0, 6, 'months'),

    # Age
    (['age'], 18, 60, 'yrs'),

    # Communication / soft skill ratings (0–10)
    (['communication', 'soft skill', 'leadership', 'teamwork',
      'attitude', 'culture fit', 'rating', 'score /10', 'out of 10'], 0, 10, '/10'),

    # IQ / cognitive
    (['iq', 'cognitive'], 70, 160, 'pts'),
]


def detect_smart_scale(criteria_name):
    """
    Given a criteria name, return (min, max, label) if a known scale pattern matches.
    Returns None if no match — caller should fall back to auto-scaling.
    Matching is case-insensitive substring.
    """
    name_lower = criteria_name.lower().strip()
    for keywords, mn, mx, label in _SMART_SCALES:
        for kw in keywords:
            if kw in name_lower:
                return mn, mx, label
    return None


def normalize_weights(criteria):
    """
    Convert raw weights (any whole numbers) to proportions summing to 1.
    e.g. [40, 30, 30] → [0.4, 0.3, 0.3]
    """
    total = sum(c['weight'] for c in criteria)
    if total == 0:
        equal = 1.0 / len(criteria)
        return {c['id']: equal for c in criteria}
    return {c['id']: c['weight'] / total for c in criteria}


def _get_val(values_dict, criteria_id):
    """
    Safely get a value from the candidate values dict.
    Handles both int and string keys — Django session JSON converts int keys to strings.
    """
    # Try int key first, then string key
    if criteria_id in values_dict:
        return float(values_dict[criteria_id])
    str_key = str(criteria_id)
    if str_key in values_dict:
        return float(values_dict[str_key])
    return 0.0


def get_bounds(criteria, candidates):
    """
    For each criteria, determine the min and max to use for normalization.

    Priority:
      1. If the user set scale_min AND scale_max on the criteria, use those.
         This fixes the "tiny candidate gap dominates the scale" problem.
         e.g. Experience: user sets min=0, max=10.
              Candidates with 4 and 5 years → 0.40 and 0.50 (not 0.00 and 1.00)

      2. Otherwise fall back to auto min-max from the candidate values.
         One candidate gets 0.00, one gets 1.00.

    all_same is True when the effective range is negligibly small —
    in that case normalization returns 0.5 (neutral, no discriminating power).
    """
    bounds = {}
    for c in criteria:
        vals = [_get_val(cand['values'], c['id']) for cand in candidates]
        actual_min = min(vals)
        actual_max = max(vals)

        # Use user-defined scale if both bounds are provided
        user_min = c.get('scale_min')
        user_max = c.get('scale_max')

        scale_source = 'auto'   # 'user' | 'smart' | 'auto'

        if user_min is not None and user_max is not None and user_max > user_min:
            mn = float(user_min)
            mx = float(user_max)
            scale_source = 'user'

        else:
            # Try smart scale — uses criteria name to pick a sensible range
            smart = detect_smart_scale(c.get('name', ''))
            if smart is not None:
                s_min, s_max, _ = smart
                # Only apply smart scale if it actually contains all candidates
                # and the candidate range is at most 50% of the smart range
                # (if candidates span a bigger range, auto-scale is more honest)
                smart_range = s_max - s_min
                cand_span   = actual_max - actual_min
                fits_in_scale = (actual_min >= s_min and actual_max <= s_max)
                spread_ratio  = (cand_span / smart_range) if smart_range > 0 else 1

                if fits_in_scale and spread_ratio <= 0.70:
                    mn = float(s_min)
                    mx = float(s_max)
                    scale_source = 'smart'
                else:
                    mn = actual_min
                    mx = actual_max
            else:
                mn = actual_min
                mx = actual_max

        value_range = mx - mn
        significance_threshold = max(abs(mx) * 0.01, 0.01)
        all_same = (value_range < significance_threshold)

        bounds[c['id']] = {
            'min':         mn,
            'max':         mx,
            'range':       value_range,
            'all_same':    all_same,
            'user_defined': scale_source == 'user',
            'smart_scale':  scale_source == 'smart',
            'scale_source': scale_source,
        }
    return bounds


def normalize_value(value, min_val, max_val, all_same, is_cost=False):
    """
    Normalize a single raw value to [0, 1].

    - If all candidates have the same value: return 0.5 (no discriminating power)
    - benefit criteria: (value - min) / (max - min)
    - cost criteria:    (max - value) / (max - min)
    """
    if all_same:
        return 0.5

    norm = (float(value) - min_val) / (max_val - min_val)

    if is_cost:
        norm = 1.0 - norm

    return round(max(0.0, min(1.0, norm)), 4)


def compute_scores(criteria, candidates):
    """
    Core scoring function.
    Normalizes raw values per criteria, then multiplies by normalized weights.
    Returns list of result dicts sorted by total_score descending.
    """
    norm_weights = normalize_weights(criteria)
    bounds = get_bounds(criteria, candidates)

    results = []
    for cand in candidates:
        breakdown = {}      # criteria_id -> weighted normalized score
        norm_vals = {}      # criteria_id -> normalized value (after cost inversion, used for scoring)
        raw_scale_pos = {}  # criteria_id -> raw scale position 0-1 (before inversion, for display)
        total = 0.0

        for c in criteria:
            raw = _get_val(cand['values'], c['id'])
            b = bounds[c['id']]

            # Raw scale position (benefit direction always) — for display only
            if b['all_same']:
                pos = 0.5
            else:
                pos = (float(raw) - b['min']) / (b['max'] - b['min'])
                pos = round(max(0.0, min(1.0, pos)), 4)
            raw_scale_pos[c['id']] = pos

            norm = normalize_value(
                raw,
                b['min'],
                b['max'],
                b['all_same'],
                c.get('is_cost', False)
            )

            weighted = norm * norm_weights[c['id']]
            norm_vals[c['id']] = norm
            breakdown[c['id']] = round(weighted, 4)
            total += weighted

        results.append({
            'candidate_id':   cand['id'],
            'candidate_name': cand['name'],
            'raw_values':     dict(cand['values']),
            'norm_values':    norm_vals,
            'raw_scale_pos':  raw_scale_pos,
            'breakdown':      breakdown,
            'total_score':    round(total, 4),
            'total_pct':      round(total * 100, 1),
        })

    # Sort highest score first
    results.sort(key=lambda x: x['total_score'], reverse=True)

    # Assign ranks — tie-aware
    prev_score = None
    rank = 0
    for i, r in enumerate(results):
        if r['total_score'] != prev_score:
            rank = i + 1
        r['rank'] = rank
        prev_score = r['total_score']

    # ── Pool rank per criteria ─────────────────────────────────────────────
    # For each criteria, rank candidates by their raw value (benefit: highest first;
    # cost: lowest first). Stored as pool_rank[criteria_id] = 1-based rank.
    # This lets the template show "Best in pool" alongside the absolute band label.
    for c in criteria:
        is_cost = c.get('is_cost', False)
        # Build (candidate_id, raw_value) list
        vals = [(r['candidate_id'], _get_val(r['raw_values'], c['id'])) for r in results]
        # Sort: cost → ascending (lower=better), benefit → descending
        vals_sorted = sorted(vals, key=lambda x: x[1], reverse=(not is_cost))
        pool_order = {cid: i + 1 for i, (cid, _) in enumerate(vals_sorted)}
        for r in results:
            if 'pool_rank' not in r:
                r['pool_rank'] = {}
            r['pool_rank'][c['id']] = pool_order[r['candidate_id']]

    return results


def compute_contributions(scored_results, criteria):
    """
    For each candidate, what % of their total score came from each criteria?
    Also builds stated-vs-actual weight comparison.
    """
    for r in scored_results:
        total = r['total_score']
        r['contribution_pct'] = {}
        for c in criteria:
            ws = r['breakdown'].get(c['id'], 0)
            r['contribution_pct'][c['id']] = round((ws / total * 100), 1) if total > 0 else 0.0

    # Average actual contribution across all candidates
    avg_actual = {}
    for c in criteria:
        vals = [r['contribution_pct'].get(c['id'], 0) for r in scored_results]
        avg_actual[c['id']] = round(sum(vals) / len(vals), 1)

    # Stated vs actual table
    total_weight = sum(c['weight'] for c in criteria)
    stated_vs_actual = []
    for c in criteria:
        stated_pct = round(c['weight'] / total_weight * 100, 1) if total_weight > 0 else 0
        actual_pct = avg_actual[c['id']]
        stated_vs_actual.append({
            'criteria_id': c['id'],
            'name':        c['name'],
            'stated_pct':  stated_pct,
            'actual_pct':  actual_pct,
            'delta':       round(abs(stated_pct - actual_pct), 1),
        })

    return scored_results, stated_vs_actual


def run_sensitivity(criteria, candidates, delta=None):
    """
    Shift each weight by ±delta% and check if the top-ranked candidate changes.
    """
    if delta is None:
        delta = getattr(settings, 'SENSITIVITY_DELTA', 0.1)

    baseline = compute_scores(criteria, candidates)
    baseline_winner = baseline[0]['candidate_id']

    flip_count = 0
    total_tests = 0

    for i in range(len(criteria)):
        for direction in [1, -1]:
            modified = [dict(c) for c in criteria]
            modified[i]['weight'] = max(1, modified[i]['weight'] * (1 + direction * delta))
            result = compute_scores(modified, candidates)
            total_tests += 1
            if result[0]['candidate_id'] != baseline_winner:
                flip_count += 1

    threshold = getattr(settings, 'STABILITY_THRESHOLD', 0.5)
    is_stable = (flip_count / total_tests) < threshold if total_tests > 0 else True

    winner = baseline[0]['candidate_name']
    if is_stable:
        detail = f"{winner} held the top rank in {total_tests - flip_count} out of {total_tests} weight variation tests."
    else:
        detail = f"The top candidate changed in {flip_count} out of {total_tests} tests. This decision is sensitive — review your weights."

    return is_stable, detail


def generate_narrative(role, criteria, scored_results, stated_vs_actual, is_stable, stability_detail, score_gap):
    """
    Generate a plain-English written explanation of the hiring decision.
    Explains WHO was chosen, WHY, which criteria drove the result,
    how each candidate compared, and whether the decision is trustworthy.
    """
    winner = scored_results[0]
    winner_name = winner['candidate_name']
    winner_pct = winner['total_pct']
    num_candidates = len(scored_results)
    bounds = {c['id']: {} for c in criteria}

    # ── Paragraph 1: Recommendation ──────────────────────────────────────────
    if num_candidates == 2:
        runner = scored_results[1]
        gap_desc = ""
        if score_gap is not None:
            gap_pct = round(score_gap * 100, 1)
            if gap_pct >= 20:
                gap_desc = f" by a clear margin of {gap_pct} percentage points"
            elif gap_pct >= 10:
                gap_desc = f" by {gap_pct} percentage points"
            else:
                gap_desc = f" by a narrow margin of {gap_pct} percentage points"
        p1 = (
            f"Based on the weighted scoring analysis for the {role} role, "
            f"the recommended candidate is {winner_name}, who achieved a total score of "
            f"{winner_pct}%{gap_desc} ahead of {runner['candidate_name']} "
            f"({runner['total_pct']}%)."
        )
    else:
        others = ", ".join(r['candidate_name'] for r in scored_results[1:])
        p1 = (
            f"Based on the weighted scoring analysis for the {role} role, "
            f"the recommended candidate is {winner_name}, who ranked first with a score of "
            f"{winner_pct}% out of {num_candidates} candidates evaluated ({others})."
        )

    # ── Paragraph 2: What drove the decision ─────────────────────────────────
    # Sort criteria by their actual contribution to winner's score
    winner_breakdown = winner['breakdown']
    sorted_criteria = sorted(criteria, key=lambda c: winner_breakdown.get(c['id'], 0), reverse=True)
    top_criteria = sorted_criteria[0]
    top_raw = _get_val(winner['raw_values'], top_criteria['id'])
    top_norm = winner['norm_values'].get(top_criteria['id'], 0)

    direction_word = "lower" if top_criteria.get('is_cost') else "higher"
    performance_word = "best" if top_norm >= 0.8 else ("well" if top_norm >= 0.5 else "moderately")

    total_weight = sum(c['weight'] for c in criteria)
    top_weight_pct = round(top_criteria['weight'] / total_weight * 100, 0)

    p2 = (
        f"The most influential factor in this decision was {top_criteria['name']} "
        f"(weighted at {int(top_weight_pct)}% of the total score). "
        f"{winner_name} performed {performance_word} on this criteria with a value of {top_raw}, "
        f"where {direction_word} values are preferred. "
    )

    # Add second most influential if it exists
    if len(sorted_criteria) > 1:
        second = sorted_criteria[1]
        second_raw = _get_val(winner['raw_values'], second['id'])
        second_norm = winner['norm_values'].get(second['id'], 0)
        second_word = "strongly" if second_norm >= 0.8 else ("adequately" if second_norm >= 0.5 else "less competitively")
        p2 += (
            f"The second most weighted factor was {second['name']}, "
            f"where {winner_name} scored {second_word} with a value of {second_raw}."
        )

    # ── Paragraph 3: Head-to-head comparison ─────────────────────────────────
    comparisons = []
    for c in criteria:
        vals = [(r['candidate_name'], _get_val(r['raw_values'], c['id']),
                 r['norm_values'].get(c['id'], 0)) for r in scored_results]
        # Find best performer on this criteria
        if c.get('is_cost'):
            best = min(vals, key=lambda x: x[1])
        else:
            best = max(vals, key=lambda x: x[1])

        all_vals_str = ", ".join(f"{name}: {val}" for name, val, _ in vals)
        direction = "lower" if c.get('is_cost') else "higher"

        # Only note if winner led or lost on this criteria
        if best[0] == winner_name:
            comparisons.append(
                f"On {c['name']}, {winner_name} led with {best[1]} ({direction} is better; candidates scored: {all_vals_str})."
            )
        else:
            comparisons.append(
                f"On {c['name']}, {best[0]} had the strongest result at {best[1]}, "
                f"while {winner_name} scored {_get_val(winner['raw_values'], c['id'])} (candidates: {all_vals_str})."
            )

    p3 = "Looking at each criteria individually: " + " ".join(comparisons)

    # ── Paragraph 4: Blindspot / stated vs actual ─────────────────────────────
    blindspots = [row for row in stated_vs_actual if row['delta'] > 15]
    if blindspots:
        bs_parts = []
        for bs in blindspots:
            if bs['actual_pct'] > bs['stated_pct']:
                bs_parts.append(
                    f"{bs['name']} was set at {bs['stated_pct']}% but actually drove "
                    f"{bs['actual_pct']}% of the result — {bs['delta']} points more than intended"
                )
            else:
                bs_parts.append(
                    f"{bs['name']} was set at {bs['stated_pct']}% but only contributed "
                    f"{bs['actual_pct']}% — {bs['delta']} points less influence than expected"
                )
        p4 = (
            f"A notable discrepancy was detected between the stated priorities and what actually "
            f"drove the scores: {'; '.join(bs_parts)}. "
            f"This can happen when candidates are clustered closely on some criteria, "
            f"causing other criteria to carry disproportionate weight in differentiating them. "
            f"You may wish to review whether the weighting reflects your true priorities."
        )
    else:
        p4 = (
            f"The stated priorities aligned well with what actually drove the scores. "
            f"Each criteria contributed close to its intended weight, indicating the "
            f"weighting scheme is working as designed and the result reflects your priorities accurately."
        )

    # ── Paragraph 5: Sensitivity / confidence ────────────────────────────────
    if is_stable:
        p5 = (
            f"This recommendation is robust. {stability_detail} "
            f"This means the decision does not depend on the precise weights you assigned — "
            f"{winner_name} is the stronger candidate across a range of weighting scenarios, "
            f"and you can proceed with confidence."
        )
    else:
        p5 = (
            f"This recommendation requires caution. {stability_detail} "
            f"The result is sensitive to how the criteria are weighted, meaning a different "
            f"emphasis could produce a different winner. Before proceeding, consider whether "
            f"your weights truly reflect your priorities, or whether a second-round interview "
            f"would help resolve the uncertainty."
        )

    return {
        'recommendation': p1,
        'decision_drivers': p2,
        'candidate_comparison': p3,
        'blindspot_analysis': p4,
        'confidence_assessment': p5,
    }


def run_scoring(criteria, candidates):
    """
    Full pipeline: normalize → score → rank → contributions → sensitivity.
    """
    if not criteria or len(candidates) < 2:
        return None

    scored = compute_scores(criteria, candidates)
    scored, stated_vs_actual = compute_contributions(scored, criteria)
    is_stable, stability_detail = run_sensitivity(criteria, candidates)
    dominant = max(stated_vs_actual, key=lambda x: x['actual_pct'])
    score_gap = round(scored[0]['total_score'] - scored[1]['total_score'], 4) if len(scored) > 1 else None

    # Build scale info for display in results — shows which criteria used fixed bounds
    bounds = get_bounds(criteria, candidates)
    scale_info = {}
    for c in criteria:
        b = bounds[c['id']]
        smart_label = None
        smart = detect_smart_scale(c.get('name', ''))
        if smart and b.get('smart_scale'):
            smart_label = smart[2]  # unit label e.g. '₹', 'yrs', 'score /100'
        scale_info[c['id']] = {
            'user_defined':  b.get('user_defined', False),
            'smart_scale':   b.get('smart_scale', False),
            'scale_source':  b.get('scale_source', 'auto'),
            'min':           b['min'],
            'max':           b['max'],
            'smart_label':   smart_label,
        }

    return {
        'ranked':            scored,
        'stated_vs_actual':  stated_vs_actual,
        'is_stable':         is_stable,
        'stability_detail':  stability_detail,
        'dominant_criteria': dominant,
        'score_gap':         score_gap,
        'top_candidate':     scored[0]['candidate_name'],
        'scale_info':        scale_info,
        'num_candidates':    len(scored),
    }


def run_scoring_with_role(criteria, candidates, role=''):
    """
    Full pipeline including narrative generation.
    Call this from the results view, passing the role title.
    """
    result = run_scoring(criteria, candidates)
    if result is None:
        return None

    narrative = generate_narrative(
        role=role,
        criteria=criteria,
        scored_results=result['ranked'],
        stated_vs_actual=result['stated_vs_actual'],
        is_stable=result['is_stable'],
        stability_detail=result['stability_detail'],
        score_gap=result['score_gap'],
    )
    result['narrative'] = narrative
    return result
