import argparse
import importlib
import json
import sys
import types
from unittest import mock

import pytest


# DGM_outer imports runtime-only Docker helpers that are not needed for these
# unit tests. Stub those modules so the selection and CLI logic stay isolated.
self_improve_step = types.ModuleType('self_improve_step')
self_improve_step.self_improve = mock.Mock()

docker_utils = types.ModuleType('utils.docker_utils')
docker_utils.setup_logger = mock.Mock()

with mock.patch.dict(
    sys.modules,
    {
        'self_improve_step': self_improve_step,
        'utils.docker_utils': docker_utils,
    },
):
    DGM_outer = importlib.import_module('DGM_outer')


SCORES = {
    'initial': 0.2,
    'medium-score': 0.5,
    'high-score': 0.9,
}


class ParsedArguments(Exception):
    pass


def write_candidate_metadata(output_dir):
    for commit, score in SCORES.items():
        commit_dir = output_dir / commit
        commit_dir.mkdir()
        metadata = {
            'overall_performance': {
                'accuracy_score': score,
                'total_unresolved_ids': [f'{commit}-task'],
                'total_emptypatch_ids': [],
                'total_resolved_ids': [],
            },
        }
        if commit != 'initial':
            metadata['parent_commit'] = 'initial'
        (commit_dir / 'metadata.json').write_text(json.dumps(metadata))


def select_best_parents(tmp_path, selfimprove_size):
    write_candidate_metadata(tmp_path)
    entries = DGM_outer.choose_selfimproves(
        tmp_path,
        list(SCORES),
        selfimprove_size,
        method='best',
        polyglot=True,
    )
    return [parent_commit for parent_commit, _ in entries]


@pytest.mark.parametrize(
    ('selfimprove_size', 'expected_parents'),
    [
        (1, ['high-score']),
        (2, ['high-score', 'medium-score']),
    ],
)
def test_choose_selfimproves_best_selects_highest_scores_first(
    tmp_path, selfimprove_size, expected_parents
):
    assert select_best_parents(tmp_path, selfimprove_size) == expected_parents


def test_choose_selfimproves_best_handles_size_larger_than_candidates(tmp_path):
    selected_parents = select_best_parents(tmp_path, len(SCORES) + 1)

    assert selected_parents[:len(SCORES)] == [
        'high-score',
        'medium-score',
        'initial',
    ]
    assert set(selected_parents) == set(SCORES)


def parse_main_args(monkeypatch, argv):
    original_parse_args = argparse.ArgumentParser.parse_args

    def parse_args(parser):
        raise ParsedArguments(original_parse_args(parser, argv))

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', parse_args)
    with pytest.raises(ParsedArguments) as parsed:
        DGM_outer.main()
    return parsed.value.args[0]


@pytest.mark.parametrize('method', ['best', 'score_child_prop'])
def test_cli_accepts_parent_selection_method(monkeypatch, method):
    args = parse_main_args(
        monkeypatch,
        ['--choose_selfimproves_method', method],
    )

    assert args.choose_selfimproves_method == method


def test_cli_rejects_concatenated_parent_selection_method(monkeypatch):
    original_parse_args = argparse.ArgumentParser.parse_args

    def parse_args(parser):
        return original_parse_args(
            parser,
            ['--choose_selfimproves_method', 'score_child_propbest'],
        )

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', parse_args)
    with pytest.raises(SystemExit):
        DGM_outer.main()
