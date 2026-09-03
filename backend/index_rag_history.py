r"""
CLI: index a folder of past projects' DATA_EXTRACTION .json files (one
equipment type at a time) into that equipment type's Qdrant collection —
see app/rag_service.py for the retrieval side used by the Spec Extraction
"Similar Projects" step.

Usage:
    python index_rag_history.py --equipment-type SO2 --data-dir path\to\so2_projects
    python index_rag_history.py --equipment-type CL2 --data-dir path\to\cl2_projects

With no --data-dir, indexes the default folder from config.py
(IEC_RAG_HISTORY_DIR_SO2 / IEC_RAG_HISTORY_DIR_CL2 in .env):

    python index_rag_history.py --equipment-type SO2
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


def default_dir_for(equipment_type: str) -> str:
    return settings.rag_history_dir_so2 if equipment_type == "SO2" else settings.rag_history_dir_cl2


def main():
    parser = argparse.ArgumentParser(
        description="Index past projects for one equipment type's Similar Projects search."
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="Folder of past projects' DATA_EXTRACTION .json files (default: from config.py)",
    )
    parser.add_argument("--equipment-type", required=True, choices=["SO2", "CL2"])
    args = parser.parse_args()

    data_dir = Path(args.data_dir or default_dir_for(args.equipment_type))
    if not data_dir.is_dir():
        print(f"ERROR: {data_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        print(f"No .json files found in {data_dir}")
        return

    field_defs, _ = get_template_fields(args.equipment_type)
    field_labels = dict(field_defs) if field_defs else {}

    store = VectorStore(settings.rag_index_dir, vector_dim=rag_embedder.EMBEDDING_DIM)

    print(f"Indexing {len(json_files)} project(s) for equipment type '{args.equipment_type}' from {data_dir}...")

    texts = []
    entries = []
    for path in json_files:
        with open(path, "r") as f:
            data_extraction = json.load(f)
        source_text = rag_text_representation.build_source_text(data_extraction, field_labels)
        texts.append(source_text)
        entries.append((path.stem, data_extraction, source_text))

    print("Generating embeddings (downloads the BGE-M3 model on first run, ~2.2GB)...")
    vectors = rag_embedder.embed_texts(texts)

    for (project_id, data_extraction, source_text), vector in zip(entries, vectors):
        store.upsert_project(
            args.equipment_type,
            project_id,
            vector,
            payload={
                "fields": data_extraction.get("fields", {}),
                "key_points": data_extraction.get("key_points", []),
                "source_text": source_text,
            },
        )
        print(f"  indexed: {project_id}")

    total = store.count(args.equipment_type)
    print(f"\nDone. '{args.equipment_type}' collection now has {total} project(s) indexed.")


if __name__ == "__main__":
    main()
