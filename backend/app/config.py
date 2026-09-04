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

    # App
    cors_origins: list[str] = ["http://localhost:5173"]

    # Sign-off name used on auto-generated clarification emails
    email_signature_name: str = "IEC Fabchem"

    # Blank query-sheet templates filled in and attached to clarification
    # emails (see spec_template.py) — column layout must match
    # SO2_TEMPLATE_FIELDS / CL2_TEMPLATE_FIELDS row order in template_consolidation.py
    so2_template_path: str = r"C:\Users\iec_a\OneDrive\Documents\IEC Queries - SO2 template.xlsx"
    cl2_template_path: str = r"C:\Users\iec_a\OneDrive\Documents\IEC Queries - CL2 template.xlsx"

    # Similar Projects (RAG) — local on-disk Qdrant storage (one collection
    # per equipment type, see rag_vector_store.py) and where a thread's
    # retrieval result JSON gets saved (see rag_service.py)
    rag_index_dir: str = "./storage/rag_index"
    similar_projects_storage_dir: str = "./storage/similar_projects"
    # Folders of past-project DATA_EXTRACTION .json files to index as history,
    # one per equipment type — see index_rag_history.py
    rag_history_dir_so2: str = "./rag_history/SO2"
    rag_history_dir_cl2: str = "./rag_history/CL2"

    # LLM backend — local Ollama server (see llm_client.py). Replaces the
    # earlier direct Anthropic/Claude calls in extraction.py,
    # template_consolidation.py, and rag_reranker.py.
    ollama_base_url: str = "http://192.168.1.6:11434"
    ollama_model: str = "qwen3:4b"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="IEC_", extra="ignore")


settings = Settings()
