from __future__ import annotations

from functools import lru_cache
from html import escape

from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from credential_renewal.auth import is_authorized_responsible, principal_from_easy_auth_header
from credential_renewal.azure_identity import ManagedIdentityTokenProvider
from credential_renewal.bitwarden import BitwardenSendClient
from credential_renewal.config import Settings
from credential_renewal.cosmos_store import CosmosArchiveStore, CosmosCaseStore
from credential_renewal.graph_client import GraphClient
from credential_renewal.models import CaseState, CredentialCase, CredentialType
from credential_renewal.tokens import TokenError, validate_case_token
from credential_renewal.workflow import CaseWorkflow

app = FastAPI(title="Azure App Credential Renewal")


@lru_cache(maxsize=1)
def build_dependencies() -> tuple[Settings, CosmosCaseStore, CaseWorkflow]:
    settings = Settings.from_environment()
    graph = GraphClient(settings.graph_base_url, ManagedIdentityTokenProvider())
    store = CosmosCaseStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_container)
    archive_store = CosmosArchiveStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_archive_container)
    workflow = CaseWorkflow(store, graph, BitwardenSendClient(), archive_store)
    return settings, store, workflow


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def view_case(
    case_id: str,
    token: str,
    request: Request,
    x_ms_client_principal: str | None = Header(default=None),
    x_user_principal_name: str | None = Header(default=None),
) -> HTMLResponse:
    settings, store, _workflow = build_dependencies()
    principal = _principal_or_401(x_ms_client_principal, x_user_principal_name)
    _validate_token_or_403(token, case_id, settings.link_signing_key)
    case = _authorized_case_or_403(store, case_id, principal)
    return HTMLResponse(_render_case(case, token, principal, request.url_for("view_case", case_id=case_id)))


@app.post("/cases/{case_id}/renew")
def renew_secret(
    case_id: str,
    token: str = Form(...),
    x_ms_client_principal: str | None = Header(default=None),
    x_user_principal_name: str | None = Header(default=None),
) -> RedirectResponse:
    settings, store, workflow = build_dependencies()
    principal = _principal_or_401(x_ms_client_principal, x_user_principal_name)
    _validate_token_or_403(token, case_id, settings.link_signing_key)
    _authorized_case_or_403(store, case_id, principal)
    workflow.renew_secret(case_id, principal)
    return RedirectResponse(f"/cases/{case_id}?token={token}", status_code=303)


@app.post("/cases/{case_id}/defer")
def defer_case(
    case_id: str,
    token: str = Form(...),
    x_ms_client_principal: str | None = Header(default=None),
    x_user_principal_name: str | None = Header(default=None),
) -> RedirectResponse:
    settings, store, workflow = build_dependencies()
    principal = _principal_or_401(x_ms_client_principal, x_user_principal_name)
    _validate_token_or_403(token, case_id, settings.link_signing_key)
    _authorized_case_or_403(store, case_id, principal)
    workflow.defer(case_id, principal)
    return RedirectResponse(f"/cases/{case_id}?token={token}", status_code=303)


@app.post("/cases/{case_id}/delete-old-secret")
def delete_old_secret(
    case_id: str,
    token: str = Form(...),
    confirmed: str = Form(...),
    x_ms_client_principal: str | None = Header(default=None),
    x_user_principal_name: str | None = Header(default=None),
) -> RedirectResponse:
    settings, store, workflow = build_dependencies()
    principal = _principal_or_401(x_ms_client_principal, x_user_principal_name)
    _validate_token_or_403(token, case_id, settings.link_signing_key)
    _authorized_case_or_403(store, case_id, principal)
    workflow.delete_old_secret(case_id, principal, confirmed=confirmed == "yes")
    return RedirectResponse(f"/cases/{case_id}?token={token}", status_code=303)


def _principal_or_401(easy_auth_header: str | None, fallback_upn: str | None) -> str:
    principal = principal_from_easy_auth_header(easy_auth_header) or fallback_upn
    if not principal:
        raise HTTPException(status_code=401, detail="Entra ID login is required.")
    return principal


def _validate_token_or_403(token: str, case_id: str, signing_key: str) -> None:
    try:
        validate_case_token(token, case_id, signing_key)
    except TokenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _authorized_case_or_403(store, case_id: str, principal: str) -> CredentialCase:
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    if not is_authorized_responsible(principal, [user.email for user in case.responsible_users]):
        raise HTTPException(status_code=403, detail="You are not responsible for this case.")
    return case


def _render_case(case: CredentialCase, token: str, principal: str, case_url) -> str:
    renew_disabled = case.old_credential.credential_type != CredentialType.SECRET or case.state == CaseState.RENEWED_OLD_SECRET_REMOVED
    old_delete_available = case.state == CaseState.RENEWED_PENDING_OLD_SECRET_REMOVAL
    bitwarden_html = ""
    if case.bitwarden_send:
        bitwarden_html = f"<p><strong>New secret:</strong> <a href=\"{escape(case.bitwarden_send['accessUrl'])}\">Open Bitwarden Send</a></p>"

    delete_form = ""
    if old_delete_available:
        delete_form = f"""
        <form method="post" action="/cases/{escape(case.case_id)}/delete-old-secret" onsubmit="return confirm('This will delete the old client secret. Systems still using it can fail immediately. Continue?');">
          <input type="hidden" name="token" value="{escape(token)}" />
          <input type="hidden" name="confirmed" value="yes" />
          <button class="danger" type="submit">Delete old secret</button>
        </form>
        """

    renew_form = ""
    if not renew_disabled:
        renew_form = f"""
        <form method="post" action="/cases/{escape(case.case_id)}/renew">
          <input type="hidden" name="token" value="{escape(token)}" />
          <button type="submit">Renew secret</button>
        </form>
        """

    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Credential renewal case</title>
      <style>
        body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1f2937; }}
        main {{ max-width: 920px; margin: auto; }}
        dl {{ display: grid; grid-template-columns: 220px 1fr; gap: .5rem 1rem; }}
        dt {{ font-weight: 700; }}
        button {{ padding: .7rem 1rem; border: 1px solid #2563eb; background: #2563eb; color: white; border-radius: 6px; cursor: pointer; }}
        button.danger {{ border-color: #b91c1c; background: #b91c1c; }}
        .actions {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1.5rem; }}
      </style>
    </head>
    <body>
      <main>
        <h1>{escape(case.azure_application.display_name)}</h1>
        <p>Signed in as {escape(principal)}. This case link can be reused until the old credential expires.</p>
        <dl>
          <dt>Case ID</dt><dd>{escape(case.case_id)}</dd>
          <dt>State</dt><dd>{escape(case.state.value)}</dd>
          <dt>App ID</dt><dd>{escape(case.azure_application.app_id)}</dd>
          <dt>Service management reference</dt><dd>{escape(case.azure_application.service_management_reference or "")}</dd>
          <dt>Credential type</dt><dd>{escape(case.old_credential.credential_type.value)}</dd>
          <dt>Old credential key ID</dt><dd>{escape(case.old_credential.key_id)}</dd>
          <dt>Old credential expiry</dt><dd>{escape(case.old_credential.end_date_time.isoformat())}</dd>
          <dt>Decision editable until</dt><dd>{escape(case.decision_editable_until.isoformat() if case.decision_editable_until else "No decision yet")}</dd>
        </dl>
        {bitwarden_html}
        <section class="actions">
          {renew_form}
          <form method="post" action="/cases/{escape(case.case_id)}/defer">
            <input type="hidden" name="token" value="{escape(token)}" />
            <button type="submit">Do not renew</button>
          </form>
          {delete_form}
        </section>
      </main>
    </body>
    </html>
    """
