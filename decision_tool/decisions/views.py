import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import HiringDecision, HiringCriteria, Candidate, CandidateValue
from .forms import RoleTitleForm, CriteriaFormSet, CandidateNameFormSet, CandidateValueForm
from .scoring import run_scoring, run_scoring_with_role


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_scoring_input(session):
    """
    Convert session data into the exact format run_scoring() expects.
    criteria list: [{'id', 'name', 'weight', 'is_cost', 'description'}, ...]
    candidates list: [{'id', 'name', 'values': {criteria_id: raw_value}}, ...]
    """
    criteria   = session.get('criteria', [])
    candidates = session.get('candidates', [])
    return criteria, candidates


# ── Step 1: Role title ────────────────────────────────────────────────────────

def step1_role(request):
    if request.method == 'POST':
        form = RoleTitleForm(request.POST)
        if form.is_valid():
            request.session['role_title'] = form.cleaned_data['role_title']
            request.session.modified = True
            return redirect('step2_criteria')
    else:
        form = RoleTitleForm(initial={'role_title': request.session.get('role_title', '')})
    return render(request, 'decisions/step1_role.html', {'form': form, 'step': 1})


# ── Step 2: Criteria + weights ─────────────────────────────────────────────────

def step2_criteria(request):
    if not request.session.get('role_title'):
        return redirect('step1_role')

    if request.method == 'POST':
        formset = CriteriaFormSet(request.POST, prefix='cr')
        if formset.is_valid():
            criteria_data = []
            for i, f in enumerate(formset.forms):
                d = f.cleaned_data
                if d:
                    criteria_data.append({
                        'id':          i + 1,
                        'name':        d['name'],
                        'weight':      d['weight'],
                        'is_cost':     d.get('is_cost', False),
                        'description': d.get('description', ''),
                        'scale_min':   d.get('scale_min'),   # None if not set
                        'scale_max':   d.get('scale_max'),   # None if not set
                    })
            if len(criteria_data) < 2:
                messages.error(request, "Please add at least 2 criteria.")
            else:
                request.session['criteria'] = criteria_data
                request.session.modified = True
                return redirect('step3_candidates')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        saved = request.session.get('criteria', [])
        initial = [
            {'name': c['name'], 'weight': c['weight'],
             'is_cost': c['is_cost'], 'description': c.get('description', ''),
             'scale_min': c.get('scale_min'), 'scale_max': c.get('scale_max')}
            for c in saved
        ] if saved else [
            {'name': 'Salary',        'weight': 40},
            {'name': 'Experience',    'weight': 30},
            {'name': 'Test Score',    'weight': 30},
        ]
        formset = CriteriaFormSet(prefix='cr', initial=initial)

    return render(request, 'decisions/step2_criteria.html', {
        'formset': formset,
        'step':    2,
        'role':    request.session.get('role_title'),
    })


# ── Step 3: Candidate names ────────────────────────────────────────────────────

def step3_candidates(request):
    if not request.session.get('criteria'):
        return redirect('step2_criteria')

    error = None

    if request.method == 'POST':
        # Read directly from POST — do not rely on formset validation
        # which can silently drop JS-added rows beyond the initial count
        total = int(request.POST.get('ca-TOTAL_FORMS', 0))
        candidates_data = []
        for i in range(total):
            name = request.POST.get(f'ca-{i}-name', '').strip()
            if name:
                candidates_data.append({
                    'id':     len(candidates_data) + 1,
                    'name':   name,
                    'values': {},
                })

        if len(candidates_data) < 2:
            error = "Please add at least 2 candidates."
        else:
            request.session['candidates'] = candidates_data
            request.session.modified = True
            return redirect('step4_values')

    # Build display list for GET (or re-render after error)
    saved = request.session.get('candidates', [])
    candidate_names = [c['name'] for c in saved] if saved else ['', '']

    if error:
        messages.error(request, error)

    return render(request, 'decisions/step3_candidates.html', {
        'candidate_names': candidate_names,
        'step':            3,
        'role':            request.session.get('role_title'),
    })


# ── Step 4: Raw values per candidate ──────────────────────────────────────

def step4_values(request):
    criteria   = request.session.get('criteria')
    candidates = request.session.get('candidates')

    if not criteria or not candidates:
        return redirect('step3_candidates')

    forms_list = [
        CandidateValueForm(
            request.POST if request.method == 'POST' else None,
            prefix=f'cv_{c["id"]}',
            criteria_list=criteria,
            candidate_name=c['name'],
        )
        for c in candidates
    ]

    if request.method == 'POST':
        if all(f.is_valid() for f in forms_list):
            for i, f in enumerate(forms_list):
                candidates[i]['values'] = f.get_values(criteria)
            request.session['candidates'] = candidates
            request.session.modified = True
            return redirect('results')
        else:
            messages.error(request, "Please fill in all values for every candidate.")

    # Build per-candidate cards: each card has the candidate name + list of
    # (criteria_info, field, errors) rows — one entry per criteria.
    # This drives the new card-per-candidate layout in the template.
    candidate_cards = []
    for i, (cand, form) in enumerate(zip(candidates, forms_list)):
        rows = []
        for c in criteria:
            fname = f'c_{c["id"]}'
            try:
                field  = form[fname]
                errors = field.errors
            except KeyError:
                field  = ''
                errors = []
            rows.append({
                'criteria_name': c['name'],
                'weight':        c['weight'],
                'is_cost':       c.get('is_cost', False),
                'description':   c.get('description', ''),
                'field':         field,
                'errors':        errors,
            })
        candidate_cards.append({
            'number': i + 1,
            'name':   cand['name'],
            'rows':   rows,
        })

    return render(request, 'decisions/step4_values.html', {
        'candidate_cards': candidate_cards,
        'criteria':        criteria,
        'step':            4,
        'role':            request.session.get('role_title'),
    })


# ── Results ────────────────────────────────────────────────────────────────────

def results(request):
    criteria, candidates = _build_scoring_input(request.session)
    role = request.session.get('role_title', 'Hiring Decision')

    if not criteria or len(candidates) < 2:
        messages.error(request, "Not enough data. Please start from the beginning.")
        return redirect('step1_role')

    # Make sure all candidates have values
    for c in candidates:
        if not c.get('values'):
            return redirect('step4_values')

    result = run_scoring_with_role(criteria, candidates, role=role)
    if result is None:
        messages.error(request, "Scoring failed. Please check your inputs.")
        return redirect('step4_values')

    # Warn if a criteria dominated unexpectedly
    dominant = result['dominant_criteria']
    if dominant['delta'] > 15:
        messages.warning(
            request,
            f"'{dominant['name']}' drove {dominant['actual_pct']}% of the final score "
            f"but was only weighted at {dominant['stated_pct']}%. "
            f"It had more influence than intended."
        )

    return render(request, 'decisions/results.html', {
        'role':     role,
        'result':   result,
        'criteria': criteria,
    })


# ── AJAX: recalculate with adjusted weights ────────────────────────────────────

@require_POST
def recalculate(request):
    try:
        body = json.loads(request.body)
        updated_weights = body.get('weights', {})
        criteria, candidates = _build_scoring_input(request.session)

        if not criteria or not candidates:
            return JsonResponse({'error': 'Session expired.'}, status=400)

        # Apply updated weights (keep as integers)
        modified = []
        for c in criteria:
            try:
                w = int(float(updated_weights.get(str(c['id']), c['weight'])))
                w = max(1, w)
            except (ValueError, TypeError):
                w = c['weight']
            modified.append({**c, 'weight': w})

        result = run_scoring(modified, candidates)
        if result is None:
            return JsonResponse({'error': 'Scoring failed.'}, status=400)

        return JsonResponse({
            'ranked': [
                {
                    'rank':           r['rank'],
                    'candidate_name': r['candidate_name'],
                    'total_pct':      r['total_pct'],
                }
                for r in result['ranked']
            ],
            'is_stable':        result['is_stable'],
            'stability_detail': result['stability_detail'],
            'score_gap':        result['score_gap'],
        })

    except (json.JSONDecodeError, KeyError) as e:
        return JsonResponse({'error': str(e)}, status=400)


# ── Save to database ───────────────────────────────────────────────────────────

def save_decision(request):
    criteria, candidates = _build_scoring_input(request.session)
    role = request.session.get('role_title')

    if not all([criteria, candidates, role]):
        messages.error(request, "Nothing to save.")
        return redirect('results')

    decision = HiringDecision.objects.create(
        user=request.user if request.user.is_authenticated else None,
        role_title=role
    )

    criteria_map = {}
    for c in criteria:
        obj = HiringCriteria.objects.create(
            decision=decision, name=c['name'], weight=c['weight'],
            is_cost=c.get('is_cost', False),
            description=c.get('description', ''), order=c['id']
        )
        criteria_map[c['id']] = obj

    for cand in candidates:
        cand_obj = Candidate.objects.create(decision=decision, name=cand['name'])
        for cid, val in cand['values'].items():
            CandidateValue.objects.create(
                candidate=cand_obj,
                criteria=criteria_map[int(cid)],
                value=val
            )

    messages.success(request, f"Saved: {role}")
    return redirect('decision_detail', pk=decision.pk)


# ── History ────────────────────────────────────────────────────────────────────

def decision_list(request):
    decisions = HiringDecision.objects.prefetch_related('criteria', 'candidates').all()
    return render(request, 'decisions/decision_list.html', {'decisions': decisions})


def decision_detail(request, pk):
    decision = get_object_or_404(
        HiringDecision.objects.prefetch_related('criteria', 'candidates__values__criteria'),
        pk=pk
    )
    criteria = [
        {'id': c.id, 'name': c.name, 'weight': c.weight,
         'is_cost': c.is_cost, 'description': c.description}
        for c in decision.criteria.all()
    ]
    candidates = []
    for cand in decision.candidates.all():
        values = {v.criteria_id: v.value for v in cand.values.select_related('criteria')}
        candidates.append({'id': cand.id, 'name': cand.name, 'values': values})

    result = run_scoring(criteria, candidates)
    return render(request, 'decisions/results.html', {
        'role': decision.role_title, 'result': result,
        'criteria': criteria, 'saved': True, 'decision': decision,
    })


def start_over(request):
    for key in ['role_title', 'criteria', 'candidates']:
        request.session.pop(key, None)
    return redirect('step1_role')


# ── Step 4 grid helper (used by template) ─────────────────────────────────────
# The grid is: grid[criteria_index][candidate_index] = (field_html, error_html)
# Built in the view so the template only does simple loops.
