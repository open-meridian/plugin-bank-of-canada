"""The catalogue, from code, as the deployment approves it."""

from __future__ import annotations

from bank_of_canada.declaration import DECLARATION


def test_three_datasets_rates_and_prices() -> None:
    assert [d.key for d in DECLARATION.catalogue] == [
        "boc_rates",
        "boc_curves",
        "boc_fx",
    ]
    kinds = {d.key: list(d.data_types)[0] for d in DECLARATION.catalogue}
    assert kinds["boc_fx"] == "meridian.v1.Price" and kinds["boc_curves"] == "meridian.v1.Rate"
    for dataset in DECLARATION.catalogue:
        assert dataset.day_time_zone == "America/Toronto" and dataset.vendor == "Bank of Canada"
        assert dataset.gap_recovery == "backfill" and not dataset.calendar_id
        said = dataset.terms_and_pricing
        assert "credit to the Bank" in said and "free on the Bank's website" in said
        assert len(said) <= 2000
    fx = DECLARATION.catalogue[2].terms_and_pricing
    assert "not meant as a benchmark" in fx


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
