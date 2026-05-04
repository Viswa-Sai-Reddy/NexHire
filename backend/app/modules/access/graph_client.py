"""Microsoft Graph AD provisioning client.

Three operations used by S4:
  * `create_user(...)` — POST /v1.0/users with `accountEnabled=false`.
  * `enable_user(user_id)` — PATCH `accountEnabled=true` on start day.
  * `disable_user(user_id)` — PATCH `accountEnabled=false` on closure
    (S5 entry point).

S4 wires the request shapes; the credential is loaded from settings
via DefaultAzureCredential. In dev (no Graph creds), every call returns
a dev-prefixed pseudo ID so the rest of the FSM keeps moving.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import get_settings
from app.shared.exceptions import GraphApiError

logger = logging.getLogger("nexhire.access.graph")


@dataclass(frozen=True, slots=True)
class CreatedAdUser:
    aad_object_id: str
    user_principal_name: str
    temporary_password: str


async def create_user(
    *,
    display_name: str,
    upn: str,
    mail_nickname: str,
) -> CreatedAdUser:
    cfg = get_settings()
    if not (cfg.graph_tenant_id and cfg.graph_client_id and cfg.graph_client_secret):
        # Dev shortcut.
        return CreatedAdUser(
            aad_object_id=f"dev-{mail_nickname}",
            user_principal_name=upn,
            temporary_password="DevTemp!1234",
        )
    try:
        from msgraph.graph_service_client import GraphServiceClient
        from azure.identity.aio import ClientSecretCredential
        from msgraph.generated.models.user import User as GraphUser
        from msgraph.generated.models.password_profile import PasswordProfile
        import secrets

        credential = ClientSecretCredential(
            tenant_id=cfg.graph_tenant_id,
            client_id=cfg.graph_client_id,
            client_secret=cfg.graph_client_secret,
        )
        client = GraphServiceClient(credentials=credential, scopes=["https://graph.microsoft.com/.default"])
        temporary_password = "Tmp" + secrets.token_urlsafe(16) + "!1"
        body = GraphUser(
            account_enabled=False,
            display_name=display_name,
            mail_nickname=mail_nickname,
            user_principal_name=upn,
            password_profile=PasswordProfile(
                force_change_password_next_sign_in=True,
                password=temporary_password,
            ),
        )
        result = await client.users.post(body)
        return CreatedAdUser(
            aad_object_id=str(result.id),
            user_principal_name=upn,
            temporary_password=temporary_password,
        )
    except Exception as exc:  # noqa: BLE001 — graph errors are integration errors
        logger.exception("nexhire.access.graph.create_failed")
        raise GraphApiError() from exc


async def set_account_enabled(*, aad_object_id: str, enabled: bool) -> None:
    cfg = get_settings()
    if not (cfg.graph_tenant_id and cfg.graph_client_id and cfg.graph_client_secret):
        return  # dev no-op
    try:
        from msgraph.graph_service_client import GraphServiceClient
        from azure.identity.aio import ClientSecretCredential
        from msgraph.generated.models.user import User as GraphUser

        credential = ClientSecretCredential(
            tenant_id=cfg.graph_tenant_id,
            client_id=cfg.graph_client_id,
            client_secret=cfg.graph_client_secret,
        )
        client = GraphServiceClient(credentials=credential, scopes=["https://graph.microsoft.com/.default"])
        await client.users.by_user_id(aad_object_id).patch(
            GraphUser(account_enabled=enabled)
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("nexhire.access.graph.patch_failed")
        raise GraphApiError() from exc


__all__ = ["CreatedAdUser", "create_user", "set_account_enabled"]


# Suppress unused-import warning when the file is loaded standalone.
_ = Optional
