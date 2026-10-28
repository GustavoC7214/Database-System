import pytest

from src.execution.memory import MemoryBudget


def test_initial_budget():
    budget = MemoryBudget(4)

    assert budget.capacity == 4
    assert budget.available == 4
    assert budget.used == 0
    assert budget.peak == 0


def test_acquire_and_release():
    budget = MemoryBudget(8)

    budget.acquire(3)

    assert budget.used == 3
    assert budget.available == 5
    assert budget.peak == 3

    budget.acquire(4)

    assert budget.used == 7
    assert budget.peak == 7

    budget.release(5)

    assert budget.used == 2
    assert budget.available == 6
    assert budget.peak == 7


def test_budget_exceeded():
    budget = MemoryBudget(4)
    budget.acquire(3)

    with pytest.raises(RuntimeError, match="Memory budget exceeded"):
        budget.acquire(2)

    assert budget.used == 3


def test_invalid_frame_count():
    with pytest.raises(ValueError):
        MemoryBudget(3)


def test_invalid_acquire():
    budget = MemoryBudget(4)

    with pytest.raises(ValueError):
        budget.acquire(-1)


def test_invalid_release():
    budget = MemoryBudget(4)

    with pytest.raises(ValueError):
        budget.release(-1)

    with pytest.raises(RuntimeError):
        budget.release(1)


def test_full_budget_and_reuse():
    budget = MemoryBudget(4)

    budget.acquire(4)
    assert budget.available == 0

    budget.release(4)
    assert budget.available == 4

    budget.acquire(4)
    assert budget.peak == 4
