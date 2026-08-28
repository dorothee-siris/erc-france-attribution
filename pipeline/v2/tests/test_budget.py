from budget import BudgetGuard


def test_budget_guard_warns_then_stops_at_configured_limits():
    guard = BudgetGuard(warning_tokens=25_000, hard_tokens=40_000)
    guard.record(input_chars=80_000, output_chars=4_000)
    assert guard.estimated_tokens == 21_000
    assert not guard.warning_reached
    guard.record(input_chars=20_000, output_chars=0)
    assert guard.warning_reached
    assert not guard.hard_stop
    guard.record(input_chars=60_000, output_chars=0)
    assert guard.hard_stop


def test_budget_guard_refuses_more_cases_after_hard_stop():
    guard = BudgetGuard(warning_tokens=10, hard_tokens=20)
    guard.record(input_chars=81, output_chars=0)
    assert not guard.can_start_case()
