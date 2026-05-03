"""V0+P7+medium against ONLY the Background of the Merger section of mac-gray.

This simulates the curated-prescan path (Python evidence_map identifies the
relevant section; only that section reaches the LLM).
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, '/tmp')
from lf_matrix import probe  # noqa


async def main():
    text = Path("/tmp/macgray_background.md").read_text(encoding="utf-8")
    label = "V0:P7:medium:macgray_background_only"
    rec = await probe("V0", "P7", reasoning="medium", label=label, window=text)
    print(json.dumps(rec, sort_keys=True, default=str))


if __name__ == "__main__":
    asyncio.run(main())
