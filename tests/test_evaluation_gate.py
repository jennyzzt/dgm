from unittest.mock import Mock

import pytest

import self_improve_step


@pytest.mark.parametrize('backend', ['swe', 'polyglot'])
@pytest.mark.parametrize(
    'num_evals,resolved,should_expand',
    [(1, 1, False), (2, 2, False), (2, 3, True), (1, 2, True)],
)
def test_expansion_threshold_accounts_for_repeated_evaluations(
    monkeypatch, tmp_path, backend, num_evals, resolved, should_expand
):
    harness = Mock(return_value=['evaluation'] * num_evals)
    monkeypatch.setattr(self_improve_step, 'harness' if backend == 'swe' else 'polyglot_harness', harness)
    monkeypatch.setattr(self_improve_step, 'make_report', Mock())
    monkeypatch.setattr(self_improve_step, 'get_all_performance', Mock(return_value=([], {
        'total_resolved_instances': resolved,
        'total_submitted_instances': 2 * num_evals,
        'accuracy_score': resolved / (2 * num_evals),
    })))
    monkeypatch.setattr(self_improve_step, 'safe_log', Mock())

    run = getattr(self_improve_step, f'run_harness_{backend}')
    run(
        entry='task-a', model_name_or_path='candidate', patch_files=[],
        num_evals=num_evals, output_dir=str(tmp_path), metadata={}, run_id='candidate',
        test_more_threshold=0.75, test_task_list=['task-a', 'task-b'],
        test_task_list_more=['task-c'],
    )

    assert harness.call_count == (2 if should_expand else 1)
