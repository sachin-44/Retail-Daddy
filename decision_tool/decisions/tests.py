from django.test import TestCase, Client
from django.urls import reverse
import json

from .scoring import (
    normalize_weights, get_bounds, normalize_value,
    compute_scores, compute_contributions,
    run_sensitivity, run_scoring,
)


class NormalizeWeightsTests(TestCase):

    def test_sum_to_one(self):
        c = [{'id':1,'weight':40},{'id':2,'weight':30},{'id':3,'weight':30}]
        r = normalize_weights(c)
        self.assertAlmostEqual(sum(r.values()), 1.0)

    def test_ratio_preserved(self):
        c = [{'id':1,'weight':1},{'id':2,'weight':3}]
        r = normalize_weights(c)
        self.assertAlmostEqual(r[2]/r[1], 3.0)

    def test_arbitrary_equals_percentage(self):
        c1 = [{'id':1,'weight':1},{'id':2,'weight':2},{'id':3,'weight':3}]
        c2 = [{'id':1,'weight':10},{'id':2,'weight':20},{'id':3,'weight':30}]
        r1 = normalize_weights(c1)
        r2 = normalize_weights(c2)
        for k in [1,2,3]:
            self.assertAlmostEqual(r1[k], r2[k])

    def test_zero_total_gives_equal(self):
        c = [{'id':1,'weight':0},{'id':2,'weight':0}]
        r = normalize_weights(c)
        self.assertAlmostEqual(r[1], 0.5)


class NormalizeValueTests(TestCase):

    def test_benefit_mid(self):
        self.assertAlmostEqual(normalize_value(50, 0, 100, False, False), 0.5)

    def test_benefit_min(self):
        self.assertAlmostEqual(normalize_value(0, 0, 100, False, False), 0.0)

    def test_benefit_max(self):
        self.assertAlmostEqual(normalize_value(100, 0, 100, False, False), 1.0)

    def test_cost_inverted(self):
        self.assertAlmostEqual(normalize_value(0, 0, 100, False, True), 1.0)
        self.assertAlmostEqual(normalize_value(100, 0, 100, False, True), 0.0)

    def test_all_same_returns_neutral(self):
        self.assertAlmostEqual(normalize_value(50, 50, 50, True, False), 0.5)


class ComputeScoresTests(TestCase):

    def setUp(self):
        self.criteria = [
            {'id':1,'name':'Salary','weight':50,'is_cost':False},
            {'id':2,'name':'Experience','weight':50,'is_cost':False},
        ]

    def test_better_candidate_ranks_first(self):
        candidates = [
            {'id':1,'name':'Alice','values':{1:70000, 2:9}},
            {'id':2,'name':'Bob',  'values':{1:40000, 2:3}},
        ]
        result = compute_scores(self.criteria, candidates)
        self.assertEqual(result[0]['candidate_name'], 'Alice')

    def test_scores_differ_not_always_50_50(self):
        candidates = [
            {'id':1,'name':'Alice','values':{1:70000, 2:9}},
            {'id':2,'name':'Bob',  'values':{1:40000, 2:3}},
        ]
        result = compute_scores(self.criteria, candidates)
        self.assertNotAlmostEqual(result[0]['total_score'], result[1]['total_score'], places=2)

    def test_equal_values_give_equal_scores(self):
        candidates = [
            {'id':1,'name':'Alice','values':{1:55000, 2:6}},
            {'id':2,'name':'Bob',  'values':{1:55000, 2:6}},
        ]
        result = compute_scores(self.criteria, candidates)
        self.assertAlmostEqual(result[0]['total_score'], result[1]['total_score'])

    def test_scores_between_0_and_1(self):
        candidates = [
            {'id':1,'name':'Alice','values':{1:80000, 2:10}},
            {'id':2,'name':'Bob',  'values':{1:30000, 2:2}},
            {'id':3,'name':'Carol','values':{1:55000, 2:6}},
        ]
        result = compute_scores(self.criteria, candidates)
        for r in result:
            self.assertGreaterEqual(r['total_score'], 0)
            self.assertLessEqual(r['total_score'], 1)

    def test_rank_1_has_highest_score(self):
        candidates = [
            {'id':1,'name':'A','values':{1:90000, 2:8}},
            {'id':2,'name':'B','values':{1:50000, 2:5}},
            {'id':3,'name':'C','values':{1:35000, 2:2}},
        ]
        result = compute_scores(self.criteria, candidates)
        self.assertEqual(result[0]['rank'], 1)
        for r in result[1:]:
            self.assertGreaterEqual(result[0]['total_score'], r['total_score'])

    def test_cost_criteria_lower_value_scores_higher(self):
        criteria = [{'id':1,'name':'Notice Period','weight':100,'is_cost':True}]
        candidates = [
            {'id':1,'name':'Alice','values':{1:2}},   # 2 weeks notice — better
            {'id':2,'name':'Bob',  'values':{1:12}},  # 12 weeks notice — worse
        ]
        result = compute_scores(criteria, candidates)
        self.assertEqual(result[0]['candidate_name'], 'Alice')


class ContributionTests(TestCase):

    def test_contributions_sum_to_100(self):
        criteria = [
            {'id':1,'name':'Salary','weight':60,'is_cost':False},
            {'id':2,'name':'Experience','weight':40,'is_cost':False},
        ]
        candidates = [
            {'id':1,'name':'Alice','values':{1:70000,2:8}},
            {'id':2,'name':'Bob',  'values':{1:50000,2:4}},
            {'id':3,'name':'Carol','values':{1:60000,2:6}},
        ]
        scored = compute_scores(criteria, candidates)
        scored, _ = compute_contributions(scored, criteria)
        for r in scored:
            total = sum(r['contribution_pct'].values())
            self.assertAlmostEqual(total, 100.0, places=0)


class SensitivityTests(TestCase):

    def test_clear_winner_is_stable(self):
        criteria = [
            {'id':1,'name':'A','weight':50,'is_cost':False},
            {'id':2,'name':'B','weight':50,'is_cost':False},
        ]
        candidates = [
            {'id':1,'name':'Strong','values':{1:100,2:100}},
            {'id':2,'name':'Weak',  'values':{1:10, 2:10}},
        ]
        is_stable, _ = run_sensitivity(criteria, candidates)
        self.assertTrue(is_stable)

    def test_opposed_candidates_flagged_unstable(self):
        criteria = [
            {'id':1,'name':'A','weight':50,'is_cost':False},
            {'id':2,'name':'B','weight':50,'is_cost':False},
        ]
        candidates = [
            {'id':1,'name':'Alice','values':{1:100,2:0}},
            {'id':2,'name':'Bob',  'values':{1:0,  2:100}},
        ]
        is_stable, _ = run_sensitivity(criteria, candidates)
        self.assertFalse(is_stable)


class RunScoringIntegrationTests(TestCase):

    def setUp(self):
        self.criteria = [
            {'id':1,'name':'Salary','weight':40,'is_cost':False},
            {'id':2,'name':'Experience','weight':35,'is_cost':False},
            {'id':3,'name':'Test Score','weight':25,'is_cost':False},
        ]
        self.candidates = [
            {'id':1,'name':'Alice','values':{1:65000,2:8,3:88}},
            {'id':2,'name':'Bob',  'values':{1:52000,2:5,3:92}},
            {'id':3,'name':'Carol','values':{1:71000,2:10,3:75}},
        ]

    def test_returns_all_required_keys(self):
        result = run_scoring(self.criteria, self.candidates)
        self.assertIsNotNone(result)
        for key in ['ranked','stated_vs_actual','is_stable','stability_detail','dominant_criteria','score_gap','top_candidate']:
            self.assertIn(key, result)

    def test_three_candidates_have_distinct_scores(self):
        result = run_scoring(self.criteria, self.candidates)
        scores = [r['total_score'] for r in result['ranked']]
        # Not all the same
        self.assertGreater(max(scores) - min(scores), 0.01)

    def test_returns_none_for_single_candidate(self):
        result = run_scoring(self.criteria, [self.candidates[0]])
        self.assertIsNone(result)


class ViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.criteria = [
            {'id':1,'name':'Salary','weight':40,'is_cost':False,'description':''},
            {'id':2,'name':'Experience','weight':35,'is_cost':False,'description':''},
            {'id':3,'name':'Test Score','weight':25,'is_cost':False,'description':''},
        ]
        self.candidates = [
            {'id':1,'name':'Alice','values':{1:65000,2:8,3:88}},
            {'id':2,'name':'Bob',  'values':{1:52000,2:5,3:92}},
        ]

    def test_step1_loads(self):
        r = self.client.get(reverse('step1_role'))
        self.assertEqual(r.status_code, 200)

    def test_step1_post_valid(self):
        r = self.client.post(reverse('step1_role'), {'role_title': 'Backend Developer'})
        self.assertRedirects(r, reverse('step2_criteria'))

    def test_results_redirects_without_session(self):
        r = self.client.get(reverse('results'))
        self.assertRedirects(r, reverse('step1_role'))

    def test_recalculate_returns_json(self):
        s = self.client.session
        s['criteria']   = self.criteria
        s['candidates'] = self.candidates
        s.save()
        r = self.client.post(
            reverse('recalculate'),
            data=json.dumps({'weights': {'1': 60, '2': 20, '3': 20}}),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('ranked', data)
        self.assertIn('is_stable', data)

    def test_recalculate_no_session_returns_400(self):
        r = self.client.post(
            reverse('recalculate'),
            data=json.dumps({'weights': {'1': 50}}),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)
