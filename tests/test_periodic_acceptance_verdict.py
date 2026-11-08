"""The offline marker is neither an improvement nor a reason to mask incomplete trials."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_periodic_improvement_docker import verify_offline_verdict
from evaluation.core import EvaluationError
from evaluation.semantic import ROLES, observation, verdict


def result(latency=1):
    expected={'counts':{'build':{'ok':1,'failed':0}}}
    records={role:[observation('HERMES_OFFLINE_OK',expected,latency if role=='candidate' else 1)
                   for _ in range(3)] for role in ROLES}
    report={**verdict(records),'evaluation_attempts':9,'generation_requests_consumed':1}
    return {'status':report['state']},report


class OfflineVerdictTests(unittest.TestCase):
    def test_real_verdict_holds_fixed_marker_without_latency_regression(self):
        final,report=result()
        self.assertEqual(report['state'],'HOLD')
        verify_offline_verdict(final,report)

    def test_real_verdict_rejects_latency_without_accepting_marker(self):
        final,report=result(2)
        self.assertEqual(report['state'],'REJECTED')
        self.assertEqual(report['decision']['reasons'],['LATENCY_LIMIT','INSUFFICIENT_GAIN'])
        verify_offline_verdict(final,report)

    def test_incomplete_timeout_or_positive_state_cannot_pass(self):
        for state in ('STOPPED','RECOVERY_REQUIRED','AWAITING_HUMAN_APPROVAL','PASS',None):
            final,report=result()
            final['status']=report['state']=state
            with self.subTest(state=state),self.assertRaises(EvaluationError):
                verify_offline_verdict(final,report)
        for count in (0,1,8,10,True):
            final,report=result()
            report['evaluation_attempts']=count
            with self.subTest(attempts=count),self.assertRaises(EvaluationError):
                verify_offline_verdict(final,report)

    def test_mismatched_state_counts_control_and_generation_are_rejected(self):
        changes=[lambda f,r:f.update(status='REJECTED'),
                 lambda f,r:r.update(counts={'candidate':0}),
                 lambda f,r:r['counts'].update(candidate=1),
                 lambda f,r:r['counts'].update(candidate=False),
                 lambda f,r:r.update(control_valid=False),
                 lambda f,r:r.update(control_valid=1),
                 lambda f,r:r.update(generation_requests_consumed=2),
                 lambda f,r:r.update(generation_requests_consumed=True)]
        for change in changes:
            final,report=result()
            change(final,report)
            with self.assertRaises(EvaluationError):
                verify_offline_verdict(final,report)

    def test_only_fixed_marker_latency_rejection_is_accepted(self):
        for decision in ({'status':'FAIL','reasons':['COST_LIMIT','INSUFFICIENT_GAIN']},
                         {'status':'FAIL','reasons':['LATENCY_LIMIT']},
                         {'status':'PASS','reasons':[]},
                         {'status':'HOLD','reasons':['EVALUATION_CONTAMINATED']},None):
            final,report=result(2)
            report['decision']=deepcopy(decision)
            with self.subTest(decision=decision),self.assertRaises(EvaluationError):
                verify_offline_verdict(final,report)


if __name__=='__main__':unittest.main()
