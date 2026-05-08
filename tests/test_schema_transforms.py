from linkflow_probe.schemas import nested_claim_schema, strictify_schema


def test_strictify_adds_required_and_forbids_extra_recursively() -> None:
    schema = {
        "type": "object",
        "properties": {
            "outer": {
                "type": "object",
                "properties": {"inner": {"type": "string", "title": "Inner"}},
            }
        },
    }

    strict = strictify_schema(schema)

    assert strict["additionalProperties"] is False
    assert strict["required"] == ["outer"]
    assert strict["properties"]["outer"]["additionalProperties"] is False
    assert strict["properties"]["outer"]["required"] == ["inner"]
    assert "title" not in strict["properties"]["outer"]["properties"]["inner"]


def test_strictify_does_not_mutate_input() -> None:
    schema = nested_claim_schema()
    strict = strictify_schema(schema)

    assert strict is not schema
    assert schema["properties"]["payload"]["additionalProperties"] is False
