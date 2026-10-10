import json

import pytest

import DGM_outer


@pytest.fixture
def parent_archive(tmp_path, monkeypatch):
    initial = tmp_path / 'initial'
    initial.mkdir()
    # Exercise task selection without requesting diagnostic logs or model calls.
    monkeypatch.setattr(DGM_outer.random, 'random', lambda: 1.0)
    monkeypatch.setattr(DGM_outer, 'any_exceeding_context_length', lambda *args: False)

    def write(unresolved, empty=None):
        metadata = {'overall_performance': {
            'accuracy_score': 1.0,
            'total_resolved_ids': ['solved-task'],
            'total_unresolved_ids': unresolved,
            'total_emptypatch_ids': empty or [],
        }}
        (initial / 'metadata.json').write_text(json.dumps(metadata))
        return str(tmp_path)

    return write


@pytest.mark.parametrize('empty_patches', [[], ['empty-task']])
def test_swe_parent_without_unresolved_tasks_is_skipped(parent_archive, empty_patches):
    output_dir = parent_archive([], empty_patches)

    assert DGM_outer.choose_selfimproves(output_dir, ['initial'], 1) == []


def test_swe_parent_with_unresolved_task_can_still_be_selected(parent_archive):
    output_dir = parent_archive(['failed-task'])

    assert DGM_outer.choose_selfimproves(output_dir, ['initial'], 1) == [
        ('initial', 'failed-task')
    ]


def test_polyglot_keeps_its_resolved_task_fallback(parent_archive):
    output_dir = parent_archive([])

    assert DGM_outer.choose_selfimproves(output_dir, ['initial'], 1, polyglot=True) == [
        ('initial', 'solved-task')
    ]
