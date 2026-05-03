# Linkflow P7 Matrix Probe

- run_id: `2026-05-03T175805Z_linkflow-p7-matrix_c7a97707aa798218c1bb6ab6204002f87f0955bc6ba14f4fee4864894795f35c`
- model: `gpt-5.5`
- dry_run: `False`
- records: 12 total, 11 ok, 1 failed

## Interpretation

- Background-section calls are the production-relevant winner. All six Background cells completed, parsed, passed Pydantic, returned 10/10 coverage, and had zero quote ambiguity.
- Medium is enough for PetSmart, but high repaired the only Background quote miss on Mac-Gray and materially increased Zep claims. High costs about 2.8x-3.1x wall time and far more reasoning tokens.
- Whole-raw filing calls are not production-clean. They completed in most cells, but every valid raw cell had quote misses, PetSmart/Zep medium had quote ambiguity, and Mac-Gray raw medium failed to produce valid completed JSON.
- The current schema plus P7 prompt is not the problem. The failure mode is input scope: enormous raw filings degrade evidence binding and provider completion.

## Results

| slug | scope | effort | status | claims | coverage | quote match | quote misses | ambiguous | latency s | tokens in/out/reason |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| mac-gray | background | medium | ok | 70 | 10 | 0.9857 | 1 | 0 | 103.4 | 16441/8878/841 |
| mac-gray | background | high | ok | 74 | 10 | 1.0 | 0 | 0 | 283.8 | 16441/19154/9840 |
| mac-gray | raw | medium | provider_incomplete_salvaged |  |  |  |  |  | 29.4 | None/None/None |
| mac-gray | raw | high | ok | 78 | 10 | 0.9487 | 4 | 0 | 262.3 | 138554/19987/9680 |
| petsmart-inc | background | medium | ok | 52 | 10 | 1.0 | 0 | 0 | 75.3 | 6786/6838/516 |
| petsmart-inc | background | high | ok | 54 | 10 | 1.0 | 0 | 0 | 218.7 | 6786/15137/9322 |
| petsmart-inc | raw | medium | ok | 68 | 10 | 0.9853 | 1 | 3 | 111.0 | 145636/9552/1522 |
| petsmart-inc | raw | high | ok | 59 | 10 | 0.9831 | 1 | 0 | 249.8 | 145636/16945/9322 |
| zep | background | medium | ok | 48 | 10 | 1.0 | 0 | 0 | 95.7 | 9245/7039/1509 |
| zep | background | high | ok | 64 | 10 | 1.0 | 0 | 0 | 298.7 | 9245/18738/11462 |
| zep | raw | medium | ok | 65 | 10 | 0.9846 | 1 | 1 | 104.1 | 137563/8357/1034 |
| zep | raw | high | ok | 57 | 10 | 0.9825 | 1 | 0 | 209.0 | 137563/16480/8286 |

Artifacts are sanitized. They contain hashes and counts only, not prompts, filing text, quote text, provider output, or credentials.
