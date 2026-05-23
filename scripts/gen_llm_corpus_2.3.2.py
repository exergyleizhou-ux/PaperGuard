"""Generate a synthetic LLM-prose corpus to mine for T6 dictionary updates.

Calls a chat-completion endpoint 30 times across varied academic topics
and writes the concatenated output to a single file. Then run:

    paperguard refresh-ai-dict \\
        --corpus scripts/llm_corpus_2.3.2.txt \\
        --provider other \\
        --min-count 2 --min-per-million 150 \\
        --dry-run

to surface candidate 2-4-grams the current dictionary doesn't cover.

Used 2026-05-23 to mine cliproxy gpt-5.4-mini output for the 2.3.2
dictionary update. Reproducible with any OpenAI-compatible endpoint
that returns chat completions.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

ENDPOINT = os.environ["PAPERGUARD_LLM_BASE_URL"].rstrip("/") + "/chat/completions"
API_KEY = os.environ["PAPERGUARD_LLM_API_KEY"]
MODEL = os.environ.get("PAPERGUARD_LLM_MODEL", "gpt-5.4-mini")

TOPICS = [
    "CRISPR-Cas9 off-target effects in mammalian cells",
    "single-cell RNA sequencing batch effects",
    "Alzheimer's disease amyloid-beta hypothesis",
    "machine learning interpretability in medical imaging",
    "climate change effects on Arctic sea ice",
    "perovskite solar cell efficiency",
    "tumor microenvironment and immunotherapy resistance",
    "deep brain stimulation in Parkinson's",
    "biofilm formation in chronic wound infections",
    "graphene-based supercapacitor electrodes",
    "ocean acidification and coral bleaching",
    "blockchain consensus algorithms",
    "antibiotic resistance in nosocomial infections",
    "neural plasticity after stroke recovery",
    "circular economy in industrial manufacturing",
    "long-COVID neurological sequelae",
    "lithium-ion battery thermal runaway",
    "agricultural microbiome and crop yield",
    "quantum error correction codes",
    "gut microbiota and metabolic syndrome",
    "5G mmWave channel modeling",
    "wildfire smoke and respiratory health",
    "metasurface optics for AR/VR displays",
    "epigenetic regulation of gene expression",
    "supply chain resilience after disruptions",
    "exoplanet atmospheric biosignatures",
    "nanomedicine for drug delivery",
    "groundwater contamination by PFAS",
    "Mars sample return mission planning",
    "renewable hydrogen production scaling",
]


def prompt_for(topic: str) -> str:
    return (
        f"Write a 100-word paragraph for an academic paper introduction "
        f"about: {topic}. Use formal academic English suitable for a "
        f"Nature-tier journal. Do not include citations. Output only "
        f"the paragraph text."
    )


def main() -> int:
    out_path = Path("scripts/llm_corpus_2.3.2.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    chunks: list[str] = []
    with httpx.Client(
        timeout=60,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 PaperGuard/2.3.2 dict-refresh",
        },
    ) as client:
        for i, topic in enumerate(TOPICS, 1):
            body = {
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": prompt_for(topic)},
                ],
                "max_tokens": 400,
                "temperature": 0.4,
            }
            try:
                r = client.post(ENDPOINT, json=body)
                r.raise_for_status()
                data = r.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if not content:
                    print(f"[{i:2d}/{len(TOPICS)}] EMPTY    {topic[:50]}",
                          file=sys.stderr)
                    continue
                chunks.append(content.strip())
                print(
                    f"[{i:2d}/{len(TOPICS)}] {len(content.split()):4d} words   "
                    f"{topic[:50]}", file=sys.stderr,
                )
            except Exception as e:  # noqa: BLE001
                print(f"[{i:2d}/{len(TOPICS)}] FAIL {e!r} {topic[:50]}",
                      file=sys.stderr)
            # Light rate-limit politeness on the proxy.
            time.sleep(0.3)
    body_text = "\n\n".join(chunks) + "\n"
    out_path.write_text(body_text, encoding="utf-8")
    n_paragraphs = len(chunks)
    n_words = len(body_text.split())
    print(
        f"\nWrote {n_paragraphs}/{len(TOPICS)} paragraphs "
        f"= {n_words} words to {out_path}",
        file=sys.stderr,
    )
    print(json.dumps({
        "paragraphs": n_paragraphs,
        "words": n_words,
        "model": MODEL,
        "out": str(out_path),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
