"""Exact message-ID reconciliation for the synthetic L1/L2 fixture."""

from marketob_api.database import Connection, Database


def verify_receipts(database: Database, bots: int, steady: int, burst: int) -> dict[str, int]:
    with database.transaction() as connection:
        result = receipt_manifest(connection, bots, steady, burst)
    assert result == {
        "expected": bots + steady + burst,
        "actual": bots + steady + burst,
        "missing": 0,
        "unexpected": 0,
    }
    return result


def receipt_manifest(connection: Connection, bots: int, steady: int, burst: int) -> dict[str, int]:
    row = connection.execute(
        "WITH expected AS ("
        "SELECT bot_id,'seed' AS message_id FROM bots UNION ALL "
        "SELECT b.bot_id,'steady_'||n FROM generate_series(0,%s-1) n "
        "JOIN bots b ON b.name='L1 bot '||(n %% %s) UNION ALL "
        "SELECT b.bot_id,'burst_'||n FROM generate_series(0,%s-1) n "
        "JOIN bots b ON b.name='L1 bot '||(n %% %s)) "
        "SELECT (SELECT count(*) FROM expected) AS expected, "
        "(SELECT count(*) FROM message_receipts) AS actual, "
        "(SELECT count(*) FROM (SELECT * FROM expected EXCEPT "
        "SELECT bot_id,message_id FROM message_receipts) q) AS missing, "
        "(SELECT count(*) FROM (SELECT bot_id,message_id FROM message_receipts EXCEPT "
        "SELECT * FROM expected) q) AS unexpected",
        (steady, bots, burst, bots),
    ).fetchone()
    assert row is not None
    return {k: int(v) for k, v in row.items()}
