import os

from automationassets import get_automation_variable


VARIABLE_NAMES = [
    "TENANT_ID",
    "EXPIRY_WINDOW_DAYS",
    "GRAPH_BASE_URL",
    "INTERNAL_API_BASE_URL",
    "COSMOS_ACCOUNT_URL",
    "COSMOS_DATABASE",
    "COSMOS_CONTAINER",
    "COSMOS_APP_OVERVIEW_CONTAINER",
    "COSMOS_ARCHIVE_CONTAINER",
    "WEBAPP_PUBLIC_BASE_URL",
    "MAIL_SHARED_MAILBOX",
    "DEPARTMENT_SUMMARY_MAILBOX",
    "BITWARDEN_MODE",
    "KEY_VAULT_URL",
    "LINK_SIGNING_KEY_SECRET_NAME",
    "CHERWELL_BASE_URL",
    "CHERWELL_TOKEN_URL",
    "CHERWELL_CLIENT_ID",
    "CHERWELL_AUTH_SECRET_NAME",
    "CHERWELL_CHANGE_TEMPLATE_ID",
    "CHERWELL_COMPLETED_STATUSES",
    "LOG_ANALYTICS_DCE_URL",
    "LOG_ANALYTICS_DCR_IMMUTABLE_ID",
    "LOG_ANALYTICS_CASES_STREAM_NAME",
    "LOG_ANALYTICS_OVERVIEW_STREAM_NAME",
    "LOG_ANALYTICS_ARCHIVE_STREAM_NAME",
]


def load_automation_variables() -> None:
    for name in VARIABLE_NAMES:
        try:
            value = get_automation_variable(name)
        except Exception:
            continue
        if value not in (None, ""):
            os.environ[name] = str(value)


load_automation_variables()

from credential_renewal.runbook_scan import main


main()
