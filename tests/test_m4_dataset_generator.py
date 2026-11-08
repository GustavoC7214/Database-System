"""Regression tests for the Module 4 benchmark generator."""

import pytest

from experiments.m4.generate_dataset import (
    generate_customers,
    generate_dataset,
    generate_orders,
    generate_payments,
    generate_shipments,
)


@pytest.mark.parametrize(
    ("scale", "expected"),
    [
        (1, 240),
        (2, 480),
        (10, 2400),
    ],
)
def test_customer_count(scale, expected):
    assert len(generate_customers(scale)) == expected


def test_scaled_order_count():
    assert len(generate_orders(10)) == 9600


def test_payments_match_orders():
    orders = generate_orders(2)
    payments = generate_payments(2)

    assert len(orders) == len(payments)

    order_amounts = {oid: amount for oid, _, amount, _ in orders}

    for _, oid, _, amount in payments:
        assert order_amounts[oid] == amount


def test_shipments_reference_existing_orders():
    order_ids = {row[0] for row in generate_orders(2)}

    for _, oid, _, _ in generate_shipments(2):
        assert oid in order_ids


def test_customer_foreign_keys():
    customer_ids = {row[0] for row in generate_customers(2)}

    for _, cid, _, _ in generate_orders(2):
        assert cid in customer_ids


def test_region_tier_correlation():
    customers = generate_customers(10)

    matching = sum(region == tier for _, region, tier, _ in customers)

    assert matching == 2160


def test_generation_is_deterministic():
    assert generate_customers(2) == generate_customers(2)
    assert generate_orders(2) == generate_orders(2)
    assert generate_payments(2) == generate_payments(2)
    assert generate_shipments(2) == generate_shipments(2)


def test_scale_one_preserves_original_data():
    assert generate_customers(1)[0] == (1, 1, 1, 25)
    assert generate_orders(1)[0] == (1, 1, 57, 1)
    assert generate_payments(1)[0] == (1, 1, 4, 57)
    assert generate_shipments(1)[0] == (1, 1, 1, 8)


@pytest.mark.parametrize("scale", [0, -1])
def test_invalid_scale(scale, tmp_path):
    with pytest.raises(ValueError, match="Scale must be at least 1"):
        generate_dataset(tmp_path / "db", scale=scale)


def test_generate_disk_database(tmp_path):
    counts = generate_dataset(tmp_path / "db", scale=2)

    assert counts == {
        "Customers": 480,
        "Orders": 1920,
        "Payments": 1920,
        "Shipments": 1920,
    }


def test_existing_database_is_protected(tmp_path):
    db_dir = tmp_path / "db"
    generate_dataset(db_dir)

    with pytest.raises(FileExistsError):
        generate_dataset(db_dir)
