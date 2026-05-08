# Linkflow probe run

- Probe run id: `20260508T123815Z`
- Model: `gpt-5.5`
- Gate: `GO`

## Tier 1 matrix

- P1 `sdk_connectivity`: `supported` - completed with text='OK'
- P1 `model_and_reasoning_acceptance`: `supported` - supported=['low', 'medium', 'high']; failures=[]
- P1 `strict_structured_output_minimal`: `supported` - validated=True; keys=['confidence', 'label', 'reason']
- P1 `strict_structured_output_nested`: `supported` - nullable:supported; nonnullable:supported
- P1 `tool_call_single_round`: `supported` - final_text='Synthetic target signed an NDA on 2026-01-02.'
- P1 `tool_call_multi_turn_loop`: `supported` - tool_results=3; final_text='The paragraph about Buyer A’s confidentiality agreement is:\n\n“On January 2, 2026, Buyer A entered into a confidentiality agreement with Target Co.”'
- P1 `tool_use_plus_final_structured_output`: `supported` - tool_results=3; payload={'paragraph_id': 'p1', 'quote': 'On January 2, 2026, Buyer A entered into a confidentiality agreement with Target Co.', 'reason': 'The paragraph directly states that Buyer A entered into a confidentiality agreement with Target Co. on January 2, 2026, and the quote was verified verbatim.', 'verdict': 'confirm'}
- P1 `error_and_retry_taxonomy`: `supported` - invalid_model:classified; invalid_schema:classified; timeout:classified
- P1 `bounded_concurrency`: `supported` - max_supported=8; concurrency_1:1/1; concurrency_2:2/2; concurrency_4:4/4; concurrency_8:8/8
- P2 `streaming_event_shapes`: `supported` - event_types=['ResponseCompletedEvent', 'ResponseContentPartAddedEvent', 'ResponseContentPartDoneEvent', 'ResponseCreatedEvent', 'ResponseInProgressEvent', 'ResponseOutputItemAddedEvent', 'ResponseOutputItemDoneEvent', 'ResponseTextDeltaEvent', 'ResponseTextDoneEvent[TypeVar]']
