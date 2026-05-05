import duckdb

from sec_graph.judgments.derive import derive_judgments
from sec_graph.schema import init_schema


def test_range_bid_derives_informal_judgment() -> None:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_deal_cycle_actor_and_bid_event(
        conn,
        event_id="deal_event_1",
        bid_value_lower=10.0,
        bid_value_upper=12.0,
        event_subtype="ioi_submitted",
    )

    derive_judgments(conn, run_id="run-1")

    row = conn.execute(
        "SELECT judgment_key, judgment_value, judgment_status, rule_id FROM judgments"
    ).fetchone()
    assert row == ("bid_formality", "informal", "accepted", "bid_formality_v1")


def test_missing_formality_substrate_creates_review_flag() -> None:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_deal_cycle_actor_and_bid_event(
        conn,
        event_id="deal_event_1",
        bid_value_lower=None,
        bid_value_upper=None,
        event_subtype="final_round_bid",
    )

    derive_judgments(conn, run_id="run-1")

    flag = conn.execute(
        "SELECT flag_type, severity, reason_code FROM review_flags"
    ).fetchone()
    assert flag == ("judgment_substrate_missing", "review", "formality_substrate_missing")


def test_observed_drop_gets_projected_fate_judgment() -> None:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_deal_cycle_actor_and_event(conn, event_id="deal_event_1", event_subtype="withdrawn_by_bidder")

    derive_judgments(conn, run_id="run-1")

    row = conn.execute(
        "SELECT judgment_key, judgment_value, judgment_status FROM judgments WHERE judgment_key = 'projected_fate'"
    ).fetchone()
    assert row == ("projected_fate", "observed_drop", "accepted")


def test_financial_advisor_relation_gets_process_role_judgment() -> None:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_advises_relation(conn, relation_id="deal_relation_1", subject_label="Evercore", object_label="Target")

    derive_judgments(conn, run_id="run-1")

    row = conn.execute(
        """
        SELECT judgment_key, judgment_value, judgment_status
        FROM judgments
        WHERE target_table = 'actor_relations'
        """
    ).fetchone()
    assert row == ("process_role", "financial_advisor", "accepted")


def test_advisor_confidentiality_is_not_bidder_nda() -> None:
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _seed_advises_relation(conn, relation_id="deal_relation_1", subject_label="Evercore", object_label="Target")

    derive_judgments(conn, run_id="run-1")

    values = {
        row[0]
        for row in conn.execute(
            "SELECT judgment_value FROM judgments WHERE judgment_key = 'agreement_kind'"
        ).fetchall()
    }
    assert "target_bidder_nda" not in values


def _seed_deal_cycle_actor_and_bid_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    event_id: str,
    bid_value_lower: float | None,
    bid_value_upper: float | None,
    event_subtype: str,
) -> None:
    _seed_deal_cycle_actor(conn)
    conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            event_id,
            "run-1",
            "deal_deal_1",
            "deal_cycle_1",
            "bid",
            event_subtype,
            "2024-01-02",
            f"{event_subtype} event",
            None,
            bid_value_lower,
            bid_value_upper,
            "USD_per_share",
            "cash",
        ],
    )
    conn.execute(
        "INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)",
        ["deal_link_1", "run-1", event_id, "deal_actor_2", "bid_submitter", None],
    )


def _seed_deal_cycle_actor_and_event(
    conn: duckdb.DuckDBPyConnection,
    *,
    event_id: str,
    event_subtype: str,
) -> None:
    _seed_deal_cycle_actor(conn)
    conn.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            event_id,
            "run-1",
            "deal_deal_1",
            "deal_cycle_1",
            "process" if event_subtype != "merger_agreement_executed" else "transaction",
            event_subtype,
            "2024-01-02",
            f"{event_subtype} event",
            None,
            None,
            None,
            None,
            None,
        ],
    )
    conn.execute(
        "INSERT INTO event_actor_links VALUES (?, ?, ?, ?, ?, ?)",
        ["deal_link_1", "run-1", event_id, "deal_actor_2", "bid_submitter", None],
    )


def _seed_deal_cycle_actor(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO deals VALUES (?, ?, ?, ?, ?)",
        ["deal_deal_1", "run-1", "deal", "deal_actor_1", "2024-01-01"],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_1", "run-1", "deal_deal_1", "Target", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_2", "run-1", "deal_deal_1", "Party A", "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO process_cycles VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["deal_cycle_1", "run-1", "deal_deal_1", 1, "primary sale process", "2024-01-01", "2024-01-03"],
    )


def _seed_advises_relation(
    conn: duckdb.DuckDBPyConnection,
    *,
    relation_id: str,
    subject_label: str,
    object_label: str,
) -> None:
    del object_label
    _seed_deal_cycle_actor(conn)
    conn.execute(
        "INSERT INTO actors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["deal_actor_3", "run-1", "deal_deal_1", subject_label, "organization", "named", None, None, None, None],
    )
    conn.execute(
        "INSERT INTO actor_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            relation_id,
            "run-1",
            "deal_deal_1",
            "deal_actor_3",
            "deal_actor_1",
            "advises",
            None,
            "deal_cycle_1",
            None,
            "2024-01-01",
            None,
            "high",
        ],
    )
