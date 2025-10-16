from app.core.dp import (
    DifferentialPrivacyAccountant,
    PrivacyBudgetExceeded,
    geometric_mechanism,
    laplace_mechanism,
)


def test_laplace_noise_is_deterministic_with_seed():
    accountant = DifferentialPrivacyAccountant(total_epsilon=5.0)
    value = laplace_mechanism(10.0, epsilon=0.5, accountant=accountant, seed=123)
    repeat = laplace_mechanism(10.0, epsilon=0.5, accountant=accountant, seed=123)
    assert value == repeat


def test_geometric_noise_respects_budget():
    accountant = DifferentialPrivacyAccountant(total_epsilon=1.0)
    geometric_mechanism(5, epsilon=0.4, accountant=accountant, seed=7)
    geometric_mechanism(5, epsilon=0.4, accountant=accountant, seed=8)
    try:
        geometric_mechanism(5, epsilon=0.25, accountant=accountant, seed=9)
    except PrivacyBudgetExceeded:
        pass
    else:  # pragma: no cover - belt and braces
        assert False, "expected budget exhaustion"
