"""Unknown Docker outcomes in the acceptance driver must retain controller pending state."""
from pathlib import Path
from threading import Event
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_unattended_stop_docker import EvaluationError,wait_until_stopped
from run_mock_improvement import execute_trial,control_intake


class StopTrialCleanupTests(unittest.TestCase):
    def test_ambiguous_create_attempts_cleanup_and_preserves_unknown_outcome(self):
        box=Mock();box.options.return_value=['create']
        box.checked.side_effect=EvaluationError('DOCKER_COMMAND_FAILED')
        box.cleanup.side_effect=EvaluationError('CREATE_OUTCOME_UNKNOWN')
        name='hermes-eval-'+'a'*32
        with patch('run_unattended_stop_docker.subprocess.Popen') as process:
            with self.assertRaisesRegex(EvaluationError,'ISOLATION_CLEANUP_FAILED') as raised:
                wait_until_stopped(box,Path('/unused'),name,Event(),[])
        box.cleanup.assert_called_once_with(name,ambiguous=True)
        self.assertEqual(raised.exception.pending_container,name)
        process.assert_not_called()

    def test_known_cleanup_preserves_the_original_create_failure(self):
        box=Mock();box.options.return_value=['create']
        box.checked.side_effect=EvaluationError('DOCKER_COMMAND_FAILED')
        box.cleanup.return_value=None
        with self.assertRaisesRegex(EvaluationError,'DOCKER_COMMAND_FAILED'):
            wait_until_stopped(box,Path('/unused'),'hermes-eval-'+'b'*32,Event(),[])
        box.cleanup.assert_called_once_with('hermes-eval-'+'b'*32,ambiguous=True)

    def test_created_worker_cleanup_failure_keeps_pending_despite_broken_pipe(self):
        box=Mock();box.options.return_value=['create']
        box.inspect.side_effect=[{'Id':'c'*64},{'State':{'Running':True}},{'State':{'Running':False}}]
        box.cleanup.side_effect=EvaluationError('CONTAINER_NOT_REMOVED')
        process=Mock();process.wait.return_value=137
        process.stdin.close.side_effect=OSError('synthetic broken pipe')
        entered=Event();name='hermes-eval-'+'c'*32
        with patch('run_unattended_stop_docker.subprocess.Popen',return_value=process):
            with self.assertRaisesRegex(EvaluationError,'ISOLATION_CLEANUP_FAILED') as raised:
                wait_until_stopped(box,Path('/unused'),name,entered,[])
        self.assertTrue(entered.is_set())
        self.assertEqual(raised.exception.pending_container,name)
        box.cleanup.assert_called_once_with(name,ambiguous=False)

    def test_unknown_cleanup_survives_execution_receipt_and_blocks_resume(self):
        box=Mock();box.options.return_value=['create']
        box.checked.side_effect=EvaluationError('DOCKER_COMMAND_FAILED')
        box.cleanup.side_effect=EvaluationError('CREATE_OUTCOME_UNKNOWN')
        def transport(root,data,work,deadline,name):
            wait_until_stopped(box,root,name,Event(),[])
        with tempfile.TemporaryDirectory() as tmp,patch('delegation.hermes_cloud.response',side_effect=transport):
            state=Path(tmp).resolve()/'state'
            packet={'event_id':'d'*64,'snapshot_hash':'e'*64}
            with self.assertRaisesRegex(EvaluationError,'ISOLATION_CLEANUP_FAILED'):
                execute_trial(packet,lambda:b'PUBLIC_SYNTHETIC',state,lambda *_:self.fail('no success result'),
                              isolated=True,cloud=True)
            self.assertTrue((state/'isolation-pending.json').is_file())
            for action in ('stop','resume'):
                with self.assertRaisesRegex(EvaluationError,'ISOLATION_PENDING'):
                    control_intake(state,action)
            self.assertTrue((state/'intake-stop.json').is_file())


if __name__=='__main__':unittest.main()
