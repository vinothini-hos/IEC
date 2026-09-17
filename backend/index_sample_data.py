r"""
CLI: index the generated sample_data/{TYPE}/manifest.json RFQs (see
generate_sample_rfqs.py) into their own on-disk Qdrant store at
settings.rag_index_sample_dir ("./storage/rag_index_v3" by default) —
completely separate from settings.rag_index_dir ("./storage/rag_index_v2"),
the real store rag_service.py's live Similar Projects search queries.

Reads the manifest's ground-truth fields/customer data directly rather than
re-running the (slow, local) LLM extraction on all 200 sample documents.

Usage:
    python index_sample_data.py --equipment-type SO2
    python index_sample_data.py --equipment-type CL2
    python index_sample_data.py --equipment-type SO2 --manifest path\to\manifest.json
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import rag_embedder, rag_text_representation  # noqa: E402
from app.config import settings  # noqa: E402
from app.rag_vector_store import VectorStore  # noqa: E402
from app.template_consolidation import get_template_fields  # noqa: E402


def default_manifest_for(equipment_type: str) -> Path:
    return Path(__file__).parent / "sample_data" / equipment_type / "manifest.json"


def main():
    parser = argparse.ArgumentParser(
        description="Index generated sample RFQs into the separate rag_index_v3 sample store."
    )
    parser.add_argument(
        "--manifest", default=None,
        help="Path to manifest.json from generate_sample_rfqs.py (default: sample_data/<TYPE>/manifest.json)",
    )
    parser.add_argument("--equipment-type", required=True, choices=["SO2", "CL2"])
    args = parser.parse_args()

    manifest_path = Path(args.manifest or default_manifest_for(args.equipment_type))
    if not manifest_path.is_file():
        print(f"ERROR: {manifest_path} not found — run generate_sample_rfqs.py first", file=sys.stderr)
        sys.exit(1)

    entries = json.loads(manifest_path.read_text())
    if not entries:
        print(f"No entries found in {manifest_path}")
        return

    field_defs, _ = get_template_fields(args.equipment_type)
    field_labels = dict(field_defs) if field_defs else {}

    store = VectorStore(settings.rag_index_sample_dir, vector_dim=rag_embedder.EMBEDDING_DIM)

    print(f"Indexing {len(entries)} sample project(s) for '{args.equipment_type}' from {manifest_path}...")
    print(f"Target store: {settings.rag_index_sample_dir}")

    texts = []
    for entry in entries:
        data_extraction = {"fields": entry["fields"], "key_points": []}
        texts.append(rag_text_representation.build_source_text(data_extraction, field_labels))

    print("Generating embeddings (downloads the BGE-M3 model on first run, ~2.2GB)...")
    vectors = rag_embedder.embed_texts(texts)

    for entry, source_text, vector in zip(entries, texts, vectors):
        store.upsert_project(
            args.equipment_type,
            entry["project_id"],
            vector,
            payload={
                "fields": entry["fields"],
                "key_points": [],
                "source_text": source_text,
                "customer_details": entry.get("customer"),
                "boq": [],
                "source_format": entry.get("format"),
                "source_style": entry.get("style"),
            },
        )
        print(f"  indexed: {entry['project_id']}")

    total = store.count(args.equipment_type)
    print(f"\nDone. '{args.equipment_type}' collection in {settings.rag_index_sample_dir} now has {total} project(s) indexed.")


if __name__ == "__main__":
    main()
