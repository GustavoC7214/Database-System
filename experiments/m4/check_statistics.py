"""Inspect real ANALYZE statistics for the Module 4 benchmark."""

from experiments.m4.validate_workload import load_statistics


def main() -> None:
    statistics = load_statistics(refresh=True)

    for name, stats in statistics.items():
        print(f"\n{name}")
        print(f"  Tuples: {stats.n_tuples}")
        print(f"  Pages: {stats.n_pages}")
        print(f"  Width: {stats.width:.2f}")

        for column, details in stats.columns.items():
            print(
                f"  {column}: "
                f"NDV={details.ndv}, "
                f"min={details.minimum}, "
                f"max={details.maximum}"
            )


if __name__ == "__main__":
    main()
