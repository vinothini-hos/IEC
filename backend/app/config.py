"""
Central app configuration, loaded from environment variables (.env).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Postgres
    database_url: str = "postgresql://iec_user:iec_pass@localhost:5432/iec_mailbox"

    # Gmail API (reuses the OAuth client + Pub/Sub topic already set up
    # in Google Cloud Console for this project)
    gmail_credentials_path: str = "./credentials/gmail_credentials.json"
    gmail_token_path: str = "./credentials/gmail_token.json"
    gmail_user_email: str = "me"  # "me" = the authenticated account
    gmail_pubsub_topic: str = ""  # e.g. projects/<project>/topics/gmail-notifications
    gmail_poll_interval_seconds: int = 30  # background auto-sync cadence

    # Local disk storage for attachments on mail we receive, downloaded
    # from Gmail during sync (attachments we send are not persisted)
    attachment_storage_dir: str = "./storage/attachments"

    # Local disk storage for extracted equipment specification JSON, one
    # file per thread (see extraction.py)
    specification_storage_dir: str = "./storage/specifications"

    # Local disk storage for stage-2 template-consolidation JSON, one
    # subfolder per thread, one file per equipment (see template_consolidation.py)
    data_extraction_storage_dir: str = "./storage/data_extraction"

    # Local disk storage for raw per-sheet cell JSON consolidated from xlsx/xlsm
    # attachments before extraction, one subfolder per thread then per attachment
    # (see sheet_consolidation.py)
    sheet_consolidation_storage_dir: str = "./storage/sheet_consolidation"

    # Local disk storage for the deterministic, human-readable per-sheet JSON
    # resolved from the raw cell data above (see structure_mapping.py) - this
    # is what actually gets fed into Stage 1 extraction for xlsx/xlsm attachments
    structured_sheets_storage_dir: str = "./storage/structured_sheets"

    # App
    cors_origins: list[str] = ["http://localhost:5173"]

    # Sign-off name used on auto-generated clarification emails
    email_signature_name: str = "IEC Fabchem"

    # Blank query-sheet templates filled in and attached to clarification
    # emails (see spec_template.py) — column layout must match
    # SO2_TEMPLATE_FIELDS / CL2_TEMPLATE_FIELDS row order in template_consolidation.py
    so2_template_path: str = r"C:\Users\iec_a\Documents\IEC Queries - SO2 template.xlsx"
    cl2_template_path: str = r"C:\Users\iec_a\Documents\IEC Queries - CL2 template.xlsx"

    # Similar Projects (RAG) — local on-disk Qdrant storage (one collection
    # per equipment type, see rag_vector_store.py) and where a thread's
    # retrieval result JSON gets saved (see rag_service.py)
    rag_index_dir: str = "./storage/rag_index_v2"
    # Separate on-disk Qdrant store for the generated sample_data/ RFQs (see
    # generate_sample_rfqs.py / index_sample_data.py) — kept fully apart from
    # rag_index_dir so synthetic data can never end up in a real search.
    rag_index_sample_dir: str = "./storage/rag_index_v3"
    # True while tuning the dense+BM25+RRF+field-match pipeline against the
    # 100-per-type sample data in rag_index_sample_dir — flip to False once
    # validated, to point Similar Projects at the real rag_index_dir history.
    rag_use_sample_index: bool = True
    similar_projects_storage_dir: str = "./storage/similar_projects"

    # Similar Projects ranking pipeline tuning (see rag_service.py) — how
    # many candidates each retrieval method contributes before RRF fusion,
    # and the RRF rank-discount constant (60 is the standard default).
    rag_dense_pool_size: int = 30
    rag_bm25_pool_size: int = 30
    rag_rrf_k: int = 60
    # Folders of past-project DATA_EXTRACTION .json files to index as history,
    # one per equipment type — see index_rag_history.py
    rag_history_dir_so2: str = "./rag_history/SO2"
    rag_history_dir_cl2: str = "./rag_history/CL2"

    # LLM backend — local Ollama server (see llm_client.py). Replaces the
    # earlier direct Anthropic/Claude calls in extraction.py,
    # template_consolidation.py, and rag_justification.py.
    ollama_base_url: str = "http://213.173.110.199:36724"
    ollama_model: str = "qwen-custom"

    # Every call_llm() call (from extraction.py, template_consolidation.py,
    # rag_justification.py alike) logs its prompt and response here, one
    # timestamped subfolder per call — see llm_client.py.
    llm_calls_storage_dir: str = "./storage/llm_calls"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="IEC_", extra="ignore")


settings = Settings()
