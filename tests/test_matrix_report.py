from linkflow_probe.runner import gate_status


def test_gate_go_when_tier1_supported() -> None:
    entries = [
        {"capability": "sdk_connectivity", "tier": 1, "status": "supported"},
        {"capability": "strict_structured_output_minimal", "tier": 1, "status": "supported"},
        {"capability": "strict_structured_output_nested", "tier": 1, "status": "supported"},
        {"capability": "tool_call_single_round", "tier": 1, "status": "supported"},
        {"capability": "tool_call_multi_turn_loop", "tier": 1, "status": "supported"},
        {"capability": "tool_use_plus_final_structured_output", "tier": 1, "status": "supported"},
        {"capability": "error_and_retry_taxonomy", "tier": 1, "status": "supported"},
        {"capability": "bounded_concurrency", "tier": 1, "status": "supported"},
    ]

    assert gate_status(entries) == "GO"


def test_gate_no_go_when_required_capability_unsupported() -> None:
    entries = [
        {"capability": "sdk_connectivity", "tier": 1, "status": "supported"},
        {"capability": "strict_structured_output_minimal", "tier": 1, "status": "unsupported"},
    ]

    assert gate_status(entries) == "NO_GO"
