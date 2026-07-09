# Detaillierter Deployment Guide

Dieser Guide fuehrt Schritt fuer Schritt durch das Deployment des Feature-Branches `feature/cherwell-change-grafana-report`. Er beschreibt auch, wo die Einstellungen im Azure Portal, Entra Admin Center, Cherwell und Grafana zu finden sind.

Der Feature-Branch enthaelt:

- Azure Automation Runbook zum Scannen auslaufender App-Registration-Credentials.
- FastAPI Web App fuer Entscheidungen der Verantwortlichen.
- Cosmos DB als Case-Speicher.
- Microsoft Graph fuer App Registration, User Lookup, Mailversand und Secret-Erneuerung.
- Bitwarden Send fuer die Uebergabe neu erzeugter Secrets.
- Cherwell Change-Erstellung und Status-Polling.
- Automatische alte Secret-Loeschung nach abgeschlossenem Cherwell Change.
- Log Analytics Export und Grafana Dashboard.

## 1. Vorbereitung

### 1.1 Benoetigte Informationen sammeln

Lege dir vor dem Start diese Werte bereit:

- Azure Subscription Name und Subscription ID.
- Ziel-Resource-Group.
- Azure Tenant ID.
- Name der Shared Mailbox.
- URL des internen REST-Systems.
- Cherwell Base URL.
- Cherwell Token URL.
- Cherwell Client ID.
- Cherwell Change Template ID.
- Liste der Cherwell Statuswerte, die als abgeschlossen gelten.
- Geplanter Name der Web App.
- Geplanter Name des Cosmos DB Accounts.
- Geplanter Name des Key Vaults.
- Log Analytics Workspace Name.
- Data Collection Endpoint URL.
- Data Collection Rule Immutable ID.
- Grafana URL und Admin-Zugriff.
- GitHub Repository URL.

### 1.2 Azure Portal oeffnen

1. Oeffne `https://portal.azure.com`.
2. Melde dich mit einem Konto an, das Azure-Ressourcen erstellen darf.
3. Stelle oben rechts sicher, dass der richtige Tenant ausgewaehlt ist.
4. Oeffne oben die Suche und pruefe, ob du die gewuenschte Subscription sehen kannst.

## 2. Resource Group

1. Im Azure Portal oben in die Suche klicken.
2. `Resource groups` eingeben.
3. **Resource groups** oeffnen.
4. **Create** auswaehlen.
5. Subscription auswaehlen.
6. Resource Group Name eingeben, z. B. `rg-credential-renewal-prod`.
7. Region auswaehlen.
8. **Review + create** auswaehlen.
9. **Create** auswaehlen.

## 3. Cosmos DB erstellen

### 3.1 Cosmos DB Account

1. Im Azure Portal oben suchen nach `Azure Cosmos DB`.
2. **Azure Cosmos DB** oeffnen.
3. **Create** auswaehlen.
4. API auswaehlen: **Azure Cosmos DB for NoSQL**.
5. Subscription und Resource Group auswaehlen.
6. Account Name eingeben, z. B. `cosmos-credential-renewal-prod`.
7. Location auswaehlen.
8. Capacity Mode passend zur Umgebung auswaehlen.
9. **Review + create**.
10. **Create**.

### 3.2 Database und Container

1. Den erstellten Cosmos DB Account oeffnen.
2. Links im Menue **Data Explorer** auswaehlen.
3. **New Container** auswaehlen.
4. Database ID: `credential-renewal`.
5. Container ID: `credential-renewal-cases`.
6. Partition key: `/caseId`.
7. Throughput je nach Umgebung setzen.
8. **OK** auswaehlen.

## 4. Key Vault

### 4.1 Key Vault erstellen

1. Im Azure Portal oben suchen nach `Key vaults`.
2. **Key vaults** oeffnen.
3. **Create** auswaehlen.
4. Subscription und Resource Group auswaehlen.
5. Key Vault Name setzen, z. B. `kv-credential-renewal-prod`.
6. Region auswaehlen.
7. Permission model nach Unternehmensstandard waehlen, empfohlen: **Azure role-based access control**.
8. **Review + create**.
9. **Create**.

### 4.2 Secrets erstellen

1. Key Vault oeffnen.
2. Links **Objects > Secrets** auswaehlen.
3. **Generate/Import** auswaehlen.
4. Secret `credential-renewal-link-signing-key` mit langem Zufallswert erstellen.
5. Wieder **Generate/Import** auswaehlen.
6. Secret `cherwell-client-secret` mit dem Cherwell Client Secret erstellen.

Diese Werte duerfen nicht in Git gespeichert werden.

## 5. Azure App Service fuer Web App

### 5.1 Web App erstellen

1. Im Azure Portal oben suchen nach `App Services`.
2. **App Services** oeffnen.
3. **Create** > **Web App** auswaehlen.
4. Subscription und Resource Group auswaehlen.
5. Name setzen, z. B. `app-credential-renewal-prod`.
6. Publish: **Code**.
7. Runtime stack: **Python 3.11** oder neuer.
8. Operating System: **Linux**.
9. Region auswaehlen.
10. App Service Plan erstellen oder bestehenden auswaehlen.
11. **Review + create**.
12. **Create**.

### 5.2 Managed Identity aktivieren

1. Web App oeffnen.
2. Links **Settings > Identity** auswaehlen.
3. Tab **System assigned** oeffnen.
4. Status auf **On** setzen.
5. **Save** auswaehlen.
6. Bestaetigen.
7. Object ID notieren.

### 5.3 App Service Authentication aktivieren

1. Web App oeffnen.
2. Links **Settings > Authentication** auswaehlen.
3. **Add identity provider** auswaehlen.
4. Identity provider: **Microsoft**.
5. Tenant type: Workforce/current tenant.
6. App registration: neue App Registration erstellen lassen oder bestehende waehlen.
7. Authentication settings:
   - Restrict access: **Require authentication**.
   - Unauthenticated requests: fuer Website meist **HTTP 302 redirect**.
8. **Add** auswaehlen.

Die Web App prueft danach zusaetzlich im Code, ob der angemeldete Benutzer Responsible User des Cases ist.

### 5.4 App Settings setzen

1. Web App oeffnen.
2. Links **Settings > Environment variables** oder **Settings > Configuration** auswaehlen.
3. Tab **App settings** oeffnen.
4. Diese Werte hinzufuegen:

```text
TENANT_ID=<tenant-id>
EXPIRY_WINDOW_DAYS=30
GRAPH_BASE_URL=https://graph.microsoft.com/v1.0
INTERNAL_API_BASE_URL=https://internal-api.example.com
COSMOS_ACCOUNT_URL=https://<cosmos-account>.documents.azure.com:443/
COSMOS_DATABASE=credential-renewal
COSMOS_CONTAINER=credential-renewal-cases
WEBAPP_PUBLIC_BASE_URL=https://<web-app-name>.azurewebsites.net
MAIL_SHARED_MAILBOX=credential-renewal@example.com
BITWARDEN_MODE=send
KEY_VAULT_URL=https://<key-vault-name>.vault.azure.net/
LINK_SIGNING_KEY_SECRET_NAME=credential-renewal-link-signing-key
CHERWELL_BASE_URL=https://cherwell.example.com/api
CHERWELL_TOKEN_URL=https://cherwell.example.com/token
CHERWELL_CLIENT_ID=credential-renewal
CHERWELL_AUTH_SECRET_NAME=cherwell-client-secret
CHERWELL_CHANGE_TEMPLATE_ID=<template-id>
CHERWELL_COMPLETED_STATUSES=Closed,Completed,Resolved
LOG_ANALYTICS_DCE_URL=https://<dce-name>.<region>.ingest.monitor.azure.com
LOG_ANALYTICS_DCR_IMMUTABLE_ID=<dcr-immutable-id>
LOG_ANALYTICS_STREAM_NAME=Custom-CredentialRenewalCases_CL
```

5. **Save** auswaehlen.
6. Web App neu starten, wenn Azure dazu auffordert.

### 5.5 Startup Command setzen

1. Web App oeffnen.
2. Links **Settings > Configuration** auswaehlen.
3. Tab **General settings** oeffnen.
4. Feld **Startup Command** setzen:

```bash
python -m uvicorn credential_renewal.web_app:app --host 0.0.0.0 --port 8000
```

5. **Save** auswaehlen.

### 5.6 Deployment aus GitHub

1. Web App oeffnen.
2. Links **Deployment > Deployment Center** auswaehlen.
3. Source: **GitHub**.
4. GitHub Account autorisieren.
5. Organization, Repository und Branch `feature/cherwell-change-grafana-report` auswaehlen.
6. Build Provider nach Unternehmensstandard auswaehlen.
7. **Save** auswaehlen.
8. Deployment Log pruefen.

### 5.7 Health Check pruefen

Oeffne im Browser:

```text
https://<web-app-name>.azurewebsites.net/healthz
```

Erwartete Antwort:

```json
{"status":"ok"}
```

## 6. Bitwarden vorbereiten

1. Klaere mit dem Bitwarden Enterprise Admin, wie CLI-Authentifizierung fuer Workloads erfolgen soll.
2. Stelle sicher, dass die Web App Runtime Zugriff auf `bw` hat.
3. Teste in einer Staging-Umgebung, ob `bw send create` funktioniert.
4. Lege Policies fuer kurze Laufzeit und limitierten Zugriff fest.
5. Stelle sicher, dass keine Secret-Werte in Logs landen.

## 7. Cherwell vorbereiten

### 7.1 API Client

1. Cherwell Admin-Oberflaeche oeffnen.
2. In den Bereich fuer API Clients beziehungsweise Security/Integrationen wechseln.
3. Einen Client fuer `credential-renewal` erstellen.
4. Client ID notieren.
5. Client Secret erzeugen und direkt in Key Vault als `cherwell-client-secret` speichern.
6. Token URL notieren.

### 7.2 Change Template

1. Cherwell Admin-Oberflaeche oeffnen.
2. In den Change-Management-Bereich wechseln.
3. Standard Change Template fuer Credential Cleanup erstellen oder auswaehlen.
4. Template ID notieren.
5. Pflichtfelder pruefen:
   - Summary
   - Description
   - External Reference
   - Service Management Reference
   - Owner/Responsible
   - Credential Ablaufdatum
6. Statuswerte notieren, die als abgeschlossen gelten, z. B. `Closed`, `Completed`, `Resolved`.

### 7.3 Cherwell Test

1. Mit einem Test-Client Token abrufen.
2. Testweise einen Change in Cherwell erstellen.
3. Pruefen, ob die Change Nummer zurueckgegeben wird.
4. Statusabfrage fuer den Change testen.
5. Den Change in Cherwell abschliessen.
6. Pruefen, ob die API den abgeschlossenen Status liefert.

## 8. Log Analytics fuer Grafana

### 8.1 Workspace

1. Im Azure Portal oben suchen nach `Log Analytics workspaces`.
2. **Log Analytics workspaces** oeffnen.
3. **Create** auswaehlen oder bestehenden Workspace oeffnen.
4. Subscription, Resource Group und Region setzen.
5. Workspace Name notieren.

### 8.2 Data Collection Endpoint

1. Im Azure Portal oben suchen nach `Data Collection Endpoints`.
2. **Data Collection Endpoints** oeffnen.
3. **Create** auswaehlen.
4. Name setzen, z. B. `dce-credential-renewal-prod`.
5. Region passend zum Workspace waehlen.
6. **Review + create** und **Create**.
7. Endpoint URL notieren. Diese wird `LOG_ANALYTICS_DCE_URL`.

### 8.3 Data Collection Rule

1. Im Azure Portal oben suchen nach `Data Collection Rules`.
2. **Data Collection Rules** oeffnen.
3. **Create** auswaehlen.
4. Name setzen, z. B. `dcr-credential-renewal-prod`.
5. Ziel-Workspace auswaehlen.
6. Custom Logs Stream fuer `CredentialRenewalCases_CL` definieren.
7. Immutable ID der DCR notieren. Diese wird `LOG_ANALYTICS_DCR_IMMUTABLE_ID`.
8. Stream Name setzen: `Custom-CredentialRenewalCases_CL`.

## 9. Azure Automation Account

### 9.1 Automation Account erstellen

1. Im Azure Portal oben suchen nach `Automation Accounts`.
2. **Automation Accounts** oeffnen.
3. **Create** auswaehlen.
4. Subscription und Resource Group auswaehlen.
5. Name setzen, z. B. `aa-credential-renewal-prod`.
6. Region auswaehlen.
7. **Review + create**.
8. **Create**.

### 9.2 Managed Identity aktivieren

1. Automation Account oeffnen.
2. Links **Account Settings > Identity** auswaehlen.
3. Tab **System assigned** oeffnen.
4. Status auf **On** setzen.
5. **Save** auswaehlen.
6. Object ID notieren.

### 9.3 Python Packages bereitstellen

1. Automation Account oeffnen.
2. Links **Shared Resources > Python packages** auswaehlen.
3. Benoetigte Packages aus `requirements.txt` bereitstellen:
   - `azure-cosmos`
   - `azure-identity`
   - `azure-keyvault-secrets`
   - `requests`
4. Bei Abhaengigkeitsproblemen Packages als Wheel-Dateien nach Unternehmensstandard importieren.

### 9.4 Scan Runbook erstellen

1. Automation Account oeffnen.
2. Links **Process Automation > Runbooks** auswaehlen.
3. **Create a runbook** auswaehlen.
4. Name: `Scan-AppRegistration-Credentials`.
5. Runbook type: Python.
6. Runtime Version passend zur Umgebung auswaehlen.
7. **Create**.
8. Projektdateien beziehungsweise Paket bereitstellen.
9. Entry Point: `credential_renewal.runbook_scan.main`.

### 9.5 Cherwell Status Runbook erstellen

1. Automation Account oeffnen.
2. Links **Process Automation > Runbooks** auswaehlen.
3. **Create a runbook** auswaehlen.
4. Name: `Poll-Cherwell-Credential-Changes`.
5. Runbook type: Python.
6. Entry Point: `credential_renewal.cherwell_status_scan.main`.
7. Dieses Runbook fragt Cherwell ab und loescht alte Client Secrets nach abgeschlossenem Change.

### 9.6 Reporting Export Runbook erstellen

1. Automation Account oeffnen.
2. Links **Process Automation > Runbooks** auswaehlen.
3. **Create a runbook** auswaehlen.
4. Name: `Export-CredentialRenewal-Reporting`.
5. Runbook type: Python.
6. Entry Point: `credential_renewal.reporting_export.main`.
7. Dieses Runbook schreibt flache Case-Daten nach Log Analytics.

### 9.7 Schedules erstellen

1. Automation Account oeffnen.
2. Links **Shared Resources > Schedules** auswaehlen.
3. Schedule `daily-credential-scan` erstellen, z. B. taeglich.
4. Schedule `cherwell-status-15min` erstellen, z. B. alle 15 Minuten oder nach Betriebsstandard.
5. Schedule `reporting-export-hourly` erstellen, z. B. stuendlich.
6. Jeden Schedule ueber **Runbook > Link to schedule** mit dem passenden Runbook verbinden.

## 10. Rechte vergeben

### 10.1 Cosmos DB Zugriff

1. Cosmos DB Account oeffnen.
2. Links **Access control (IAM)** auswaehlen.
3. **Add > Add role assignment** auswaehlen.
4. Rolle nach Unternehmensstandard fuer Cosmos DB Datenzugriff waehlen.
5. Managed Identity der Web App auswaehlen.
6. Wiederholen fuer Automation Account.

### 10.2 Key Vault Zugriff

1. Key Vault oeffnen.
2. Links **Access control (IAM)** auswaehlen, wenn RBAC aktiv ist.
3. **Add role assignment** auswaehlen.
4. Rolle fuer Secret-Lesezugriff waehlen, z. B. Key Vault Secrets User.
5. Web App Identity zuweisen.
6. Automation Account Identity zuweisen.

### 10.3 Microsoft Graph Rechte

Die Managed Identities brauchen Graph App Permissions. Typische Rechte:

- `Application.Read.All`
- `User.Read.All`
- `Mail.Send`
- `Application.ReadWrite.OwnedBy` oder `Application.ReadWrite.All`

Vorgehen nach Unternehmensstandard:

1. Entra Admin Center oeffnen: `https://entra.microsoft.com`.
2. **Identity > Applications > App registrations** oder **Enterprise applications** oeffnen.
3. Die Service Principal/Managed Identity suchen.
4. API Permissions beziehungsweise App Role Assignments konfigurieren.
5. Admin Consent erteilen.

### 10.4 Log Analytics Ingestion Rechte

1. Data Collection Rule oder Resource Group oeffnen.
2. Links **Access control (IAM)** auswaehlen.
3. **Add role assignment** auswaehlen.
4. Rolle fuer Monitoring Metrics Publisher beziehungsweise Logs Ingestion nach Unternehmensstandard vergeben.
5. Automation Account Identity auswaehlen.

## 11. Internes REST-System pruefen

1. Stelle sicher, dass `INTERNAL_API_BASE_URL` aus Azure erreichbar ist.
2. Endpoint pruefen:

```http
GET /applications/{serviceManagementReference}/responsibles
```

3. Die Antwort muss `responsibles` enthalten.
4. Jeder Responsible muss `email` oder `upn` enthalten.
5. Anzeigenamen allein reichen nicht.

## 12. Grafana Dashboard importieren

1. Grafana oeffnen.
2. Links im Grafana-Menue **Connections > Data sources** oeffnen.
3. Azure Monitor Datasource konfigurieren oder bestehende auswaehlen.
4. Links **Dashboards** oeffnen.
5. **New** oder **Import** auswaehlen.
6. Datei `grafana/credential-renewal-cases-dashboard.json` importieren.
7. Azure Monitor Datasource auswaehlen.
8. Dashboard speichern.
9. Filter testen:
   - Azure App Name
   - Owner
   - Cherwell ID

## 13. Smoke Test

1. Entra Admin Center oeffnen.
2. **Identity > Applications > App registrations** auswaehlen.
3. Test-App-Registration erstellen oder bestehende Test-App oeffnen.
4. Unter **Certificates & secrets** ein Secret mit kurzer Laufzeit anlegen.
5. `serviceManagementReference` mit internem App-Kuerzel setzen.
6. Internes REST-System fuer dieses Kuerzel konfigurieren.
7. Scan Runbook manuell starten.
8. Cosmos DB **Data Explorer** oeffnen.
9. Case in `credential-renewal-cases` pruefen.
10. Cherwell Change ID und Change Nummer im Case pruefen.
11. Cherwell UI oeffnen und Change pruefen.
12. Mailzustellung an Responsible User pruefen.
13. Link in der Mail oeffnen.
14. Entra ID Login pruefen.
15. **Renew secret** klicken.
16. Bitwarden Send Link pruefen.
17. In Entra ID pruefen, dass altes und neues Secret vorhanden sind.
18. Cherwell Change in Cherwell abschliessen.
19. Cherwell Status Runbook manuell starten.
20. In Entra ID pruefen, dass das alte Secret entfernt wurde.
21. Reporting Export Runbook manuell starten.
22. Grafana Dashboard oeffnen.
23. Nach Azure App Name, Owner und Cherwell ID suchen.

## 14. Fehlendes internes App-Kuerzel testen

1. App Registration mit auslaufendem Credential ohne `serviceManagementReference` vorbereiten.
2. Scan Runbook starten.
3. Erwartung:
   - Kein Cosmos Case.
   - Kein Cherwell Change.
   - Keine Mail.
4. Internes App-Kuerzel nachtragen.
5. Scan Runbook erneut starten.
6. Erwartung:
   - Cosmos Case wird erstellt.
   - Cherwell Change wird erstellt.
   - Mail wird versendet.

## 15. Zertifikat-Test

1. Test-App-Registration mit bald auslaufendem Zertifikat vorbereiten.
2. Scan Runbook starten.
3. Cherwell Change pruefen.
4. Cherwell Change abschliessen.
5. Cherwell Status Runbook starten.
6. Erwartung: Case Status wird `manual_certificate_removal_required`.
7. Erwartung: Kein automatisches Entfernen des Zertifikats.

## 16. Betriebsueberwachung

Pruefe regelmaessig:

- Automation Account > **Process Automation > Jobs**.
- Web App > **Monitoring > Log stream**.
- Web App > **Monitoring > Application Insights**, falls aktiv.
- Cosmos DB > **Monitoring > Metrics**.
- Key Vault > **Monitoring > Logs**.
- Graph Permission Fehler in Runbook/Web-App-Logs.
- Cherwell API Fehler.
- Bitwarden Send Fehler.
- Log Analytics Ingestion Fehler.
- Grafana Query Fehler.

## 17. Sicherheitscheck

- Keine Secret-Werte in Cosmos DB.
- Keine Secret-Werte in Logs.
- Keine Secret-Werte in Mails.
- Keine Secret-Werte in Log Analytics.
- Web-App-Link ist signiert.
- Web-App-Link laeuft mit dem alten Credential ab.
- Entra ID Login ist aktiv.
- Responsible-User-Pruefung funktioniert.
- Altes Secret wird nach Cherwell Completion automatisch geloescht.
- Zertifikate werden nicht automatisch geloescht.

## 18. Referenzen

- Azure App Service Authentication: https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad
- Python auf Azure App Service: https://learn.microsoft.com/en-us/azure/app-service/configure-language-python
- Azure Automation Managed Identity: https://learn.microsoft.com/en-us/azure/automation/learn/powershell-runbook-managed-identity
- Cosmos DB Container: https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-create-container
