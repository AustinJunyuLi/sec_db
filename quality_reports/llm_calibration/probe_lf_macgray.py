"""V0+P7+medium against the full mac-gray filing — the longest in the corpus.

Imports the proven probe() from lf_matrix.py. Reads API key from env only.
"""
import asyncio, json, sys, time
from pathlib import Path
sys.path.insert(0, '/tmp')
from lf_matrix import probe  # noqa


async def main():
    src = Path("/Users/austinli/Projects/sec_graph/data/filings/mac-gray/raw.md")
    text = src.read_text(encoding="utf-8")
    label = "V0:P7:medium:macgray_full"
    rec = await probe("V0", "P7", reasoning="medium", label=label, window=text)
    print(json.dumps(rec, sort_keys=True, default=str))


if __name__ == "__main__":
    asyncio.run(main())
