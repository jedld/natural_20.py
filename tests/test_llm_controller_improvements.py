"""Tests for LLM controller improvements: path dedup, interact scoring, healing targeting."""
import pytest
from natural20.utils.movement import simplify_path


class TestSimplifyPath:
    def test_no_backtracking(self):
        path = [[0, 4], [0, 3], [0, 2], [1, 2]]
        assert simplify_path(path) == [[0, 4], [0, 3], [0, 2], [1, 2]]

    def test_oscillation_removed(self):
        # The exact scenario from the bug report
        path = [[0, 4], [0, 3], [0, 2], [1, 2], [0, 2], [1, 2]]
        assert simplify_path(path) == [[0, 4], [0, 3], [0, 2], [1, 2]]

    def test_full_loop_collapsed(self):
        # A→B→C→A should collapse to just A
        path = [[0, 0], [1, 0], [1, 1], [0, 0]]
        assert simplify_path(path) == [[0, 0]]

    def test_loop_then_continue(self):
        # A→B→C→B→D: loop B→C→B collapses, then continues to D
        path = [[0, 0], [1, 0], [2, 0], [1, 0], [1, 1]]
        assert simplify_path(path) == [[0, 0], [1, 0], [1, 1]]

    def test_empty_path(self):
        assert simplify_path([]) == []

    def test_single_step(self):
        assert simplify_path([[3, 4]]) == [[3, 4]]

    def test_two_step_no_backtrack(self):
        assert simplify_path([[0, 0], [1, 0]]) == [[0, 0], [1, 0]]

    def test_two_step_backtrack(self):
        path = [[0, 0], [1, 0], [0, 0]]
        assert simplify_path(path) == [[0, 0]]

    def test_triple_oscillation(self):
        path = [[0, 0], [1, 0], [0, 0], [1, 0], [0, 0]]
        assert simplify_path(path) == [[0, 0]]

    def test_preserves_tuples_as_lists(self):
        # Input has tuples, output should be lists
        path = [(0, 0), (1, 0), (2, 0)]
        result = simplify_path(path)
        assert result == [[0, 0], [1, 0], [2, 0]]
