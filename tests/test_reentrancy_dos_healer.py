import pytest
from healing.reentrancy_dos_healer import ReentrancyDosHealer


class TestReentrancyDosHealer:
    # 1. Unit Tests
    def test_benign_loop_with_break_remains_unchanged(self):
        code = """
while True:
    print("processing")
    break
"""
        healer = ReentrancyDosHealer()
        healed, count = healer.heal_source(code)
        assert count == 0
        assert "RuntimeError" not in healed

    def test_benign_loop_with_return_remains_unchanged(self):
        code = """
def worker():
    while 1:
        return 42
"""
        healer = ReentrancyDosHealer()
        healed, count = healer.heal_source(code)
        assert count == 0

    # 2. Integration Tests
    def test_heal_unbounded_infinite_loop(self):
        code = """
def bad_daemon():
    while True:
        pass
"""
        healer = ReentrancyDosHealer(max_iterations=50)
        healed, count = healer.heal_source(code)
        assert count == 1
        assert "RuntimeError('AutoCure: Unbounded loop execution halted')" in healed

        # Verify executable behavior
        local_scope = {}
        exec(healed, local_scope)
        with pytest.raises(RuntimeError, match="AutoCure: Unbounded loop execution halted"):
            local_scope["bad_daemon"]()

    # 3. Regression Tests
    def test_finite_condition_while_loop_not_intercepted(self):
        code = """
i = 0
while i < 10:
    i += 1
"""
        healer = ReentrancyDosHealer()
        healed, count = healer.heal_source(code)
        assert count == 0
        assert "RuntimeError" not in healed
