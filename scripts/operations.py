"""Workspace alias for the operations module shipped with the API image."""

from marketob_api.operations import alerts, log_metrics, main, snapshot, statistics

__all__ = ["alerts", "log_metrics", "main", "snapshot", "statistics"]

if __name__ == "__main__":
    main()
