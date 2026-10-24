"""Atomic permission invalidation independent of notification queue capacity."""

from marketob_api.database import Connection


def invalidate_access(connection: Connection) -> None:
    # Call once, after permission/reconciliation writes, in their transaction.
    # The dispatcher uses this same row lock: later deliveries cannot reuse the marker.
    connection.execute(
        "UPDATE delivery_state SET watermark=watermark+1,retention_floor=watermark+1"
    )
