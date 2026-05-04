"""Scale test: V0+P7 at full PetSmart and Saks filings.

Subset of lf_matrix.py — same probe() function, but pulls full-filing input.
Reads API key from LINKFLOW_API_KEY env. Writes nothing to disk.
"""
import asyncio, json, os, sys, time
from pathlib import Path
sys.path.insert(0, '/tmp')
from lf_matrix import probe, SCHEMAS, PROMPTS, _client  # noqa

EXAMPLES = Path("/Users/austinli/Projects/sec_graph/data/examples")

async def main():
    petsmart = (EXAMPLES / "petsmart-inc.md").read_text(encoding="utf-8")
    saks = (EXAMPLES / "saks.md").read_text(encoding="utf-8")
    targets = [
        ("V0:P7:medium:petsmart_full", "V0", "P7", "medium", petsmart),
        ("V0:P7:medium:saks_full", "V0", "P7", "medium", saks),
    ]
    for label, schema_id, prompt_id, reasoning, window in targets:
        rec = await probe(schema_id, prompt_id, reasoning=reasoning, label=label, window=window)
        print(json.dumps(rec, sort_keys=True, default=str))

if __name__ == "__main__":
    asyncio.run(main())
