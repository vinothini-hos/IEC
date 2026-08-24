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

    # App
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="IEC_")


settings = Settings()
