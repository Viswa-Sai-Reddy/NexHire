from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Reads from environment + `.env`.

    In production the secret-bearing fields are resolved from Azure Key Vault
    via `DefaultAzureCredential` (see infrastructure.azure_keyvault); the env
    variable then holds a vault reference rather than the raw secret.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Runtime ────────────────────────────────────────────
    nexhire_env: Literal["development", "staging", "production"] = "development"
    nexhire_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    nexhire_api_prefix: str = "/api/v1"

    # ── Database ───────────────────────────────────────────
    database_url: str = Field(default="postgresql+asyncpg://localhost/nexhire")
    database_pool_size: int = 10
    database_pool_overflow: int = 20

    # ── Frontend base URL ──────────────────────────────────
    # Used in transactional emails (action links, candidate portal links,
    # OpenSign webhook URL). No trailing slash.
    frontend_base_url: str = "http://localhost:5173"

    # ── Redis ──────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── JWT ────────────────────────────────────────────────
    jwt_private_key_pem: str = ""
    jwt_public_key_pem: str = ""
    jwt_kid: str = "nexhire-jwt-2026"
    jwt_issuer: str = "https://nexhire.local"
    jwt_audience: str = "nexhire-api"
    jwt_access_ttl_seconds: int = 28_800   # 8h
    jwt_refresh_ttl_seconds: int = 86_400  # 24h

    # ── Azure Key Vault ────────────────────────────────────
    azure_key_vault_url: str = ""

    # ── Azure Blob Storage ─────────────────────────────────
    # When `azure_blob_account_key` is set, the Blob client uses shared-key
    # auth (and SAS generation has the key it needs). When it's empty,
    # auth falls back to DefaultAzureCredential (Managed Identity / az login).
    azure_blob_account_url: str = ""
    azure_blob_account_key: str = ""
    azure_blob_container_documents: str = "documents"
    azure_blob_container_temp: str = "temp-uploads"

    # ── Azure OpenAI ───────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment_gpt4o: str = "gpt-4o"
    azure_openai_deployment_embeddings: str = "text-embedding-3-large"

    # ── Azure Document Intelligence ────────────────────────
    azure_doc_intelligence_endpoint: str = ""
    azure_doc_intelligence_key: str = ""

    # ── Application Insights ───────────────────────────────
    applicationinsights_connection_string: str = ""

    # ── Microsoft Graph ────────────────────────────────────
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""

    # ── AD provisioning mode ───────────────────────────────
    # `graph` calls Microsoft Graph to create real Azure AD accounts.
    # `postgres` records a synthetic `intern-<id>@nexhire.local` username
    # in the `interns` row only — no Graph call attempted. Use `postgres`
    # when interns don't need to log into corporate AD systems.
    ad_provisioning_mode: Literal["graph", "postgres"] = "postgres"

    # ── Gmail ──────────────────────────────────────────────
    # Two send paths supported:
    #   * Service-account + domain-wide delegation (Workspace).
    #   * SMTP with an App Password (personal Gmail). When `gmail_app_password`
    #     is set, SMTP wins regardless of the service-account JSON path.
    gmail_service_account_json_path: str = ""
    gmail_sender_email: str = ""
    gmail_domain_delegated_user: str = ""
    gmail_app_password: str = ""

    # ── OpenSign ───────────────────────────────────────────
    opensign_base_url: str = ""
    opensign_api_key: str = ""
    opensign_webhook_signing_secret: str = ""

    # ── NDA template ──────────────────────────────────────
    # Resolves in this order: local path → Blob (`templates/nda-<ver>.pdf`)
    # → bundled placeholder. See `nda.service._load_nda_template`.
    nda_template_local_path: str = ""
    nda_template_version: str = "v1"

    # ── PAN encryption ─────────────────────────────────────
    pan_hmac_pepper: str = ""
    pan_aes_key: str = ""

    # ── Rate limiting ──────────────────────────────────────
    rate_limit_per_minute_default: int = 120
    rate_limit_per_minute_ai: int = 20
    rate_limit_per_minute_unauth: int = 10

    # ── AI cost guardrail ──────────────────────────────────
    ai_daily_cost_ceiling_inr: int = 2_000

    # ── Bootstrap seed ─────────────────────────────────────
    seed_program_owner_email: str = "program-owner@example.com"
    seed_program_owner_name: str = "NexHire Program Owner"

    @property
    def is_production(self) -> bool:
        return self.nexhire_env == "production"

    @property
    def is_development(self) -> bool:
        return self.nexhire_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton. Override in tests via `get_settings.cache_clear()`."""
    return Settings()
