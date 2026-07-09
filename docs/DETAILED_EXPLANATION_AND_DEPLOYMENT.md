# Ausfuehrliche Erklaerung und Deployment Guide

Dieses Dokument beschreibt, wie die Azure App Credential Renewal Loesung funktioniert und wie sie in Azure ausgerollt wird. Es ergaenzt die technische `README.md` und ist als Schritt-fuer-Schritt-Erklaerung fuer Betrieb, Deployment und Review gedacht.

## 1. Gesamtarchitektur

Die Loesung besteht aus zwei aktiven Komponenten:

1. **Azure Automation Runbook**
   - Scannt alle Entra ID App Registrations.
   - Prueft Secrets und Zertifikate auf Ablauf innerhalb des konfigurierten Zeitfensters.
   - Liest `serviceManagementReference` als internes App-Kuerzel.
   - Fragt ein internes REST-System nach Verantwortlichen und App-Metadaten.
   - Sucht die Verantwortlichen in Entra ID.
   - Erstellt oder aktualisiert Faelle in Cosmos DB.
   - Versendet Benachrichtigungen aus einer Shared Mailbox.

2. **Azure Web App mit FastAPI**
   - Zeigt den Verantwortlichen den jeweiligen Fall an.
   - Prueft den signierten Link.
   - Prueft Entra ID Login ueber App Service Authentication.
   - Prueft, ob der angemeldete Benutzer zu den Verantwortlichen des Falls gehoert.
   - Bietet Aktionen zum Erneuern, Aufschieben oder Loeschen des alten Secrets.

Die wichtigsten unterstuetzenden Systeme sind:

- **Microsoft Graph** fuer App Registration Daten, User Lookup, Secret-Erstellung, Secret-Loeschung und Mailversand.
- **Cosmos DB** als Fall- und Audit-Speicher.
- **Key Vault** fuer produktive Secrets wie den Link-Signing-Key.
- **Internes REST-System** fuer die Zuordnung von `serviceManagementReference` zu Verantwortlichen.
- **Bitwarden Send** fuer die einmalige oder kurzlebige Uebergabe des neu erzeugten Secrets.

Version 1 erneuert nur **Client Secrets** automatisch. Zertifikate werden erkannt und im Fall angezeigt, aber nicht automatisch erneuert.

## 2. Laufzeitablauf des Automation Runbooks

Der Einstiegspunkt ist:

```text
credential_renewal.runbook_scan.main
```

Beim Start passiert Folgendes:

1. Die Konfiguration wird aus Environment Variables geladen.
2. Ueber Managed Identity wird ein Microsoft Graph Token geholt.
3. Der Graph Client ruft alle App Registrations ab.
4. Fuer jede App Registration werden diese Felder gelesen:
   - `id`
   - `appId`
   - `displayName`
   - `serviceManagementReference`
   - `passwordCredentials`
   - `keyCredentials`
5. Die Funktion `expiring_credentials()` prueft alle Secrets und Zertifikate.
6. Relevant sind Credentials, deren `endDateTime` zwischen jetzt und `EXPIRY_WINDOW_DAYS` liegt.
7. Fuer jedes betroffene Credential wird ein Fall verarbeitet.

Falls eine betroffene App Registration keine `serviceManagementReference` hat, kann sie nicht gegen das interne System gemappt werden. Der Fehler wird geloggt, und das Runbook verarbeitet die naechste App weiter.

## 3. Interne Systemabfrage

Das Runbook nutzt `serviceManagementReference` als internes App-Kuerzel und ruft das interne System so auf:

```http
GET /applications/{serviceManagementReference}/responsibles
Accept: application/json
```

Erwartetes Beispiel:

```json
{
  "applicationCode": "PAY",
  "businessService": "Payments",
  "environment": "Production",
  "criticality": "High",
  "responsibles": [
    {
      "email": "owner.one@example.com",
      "role": "Application Owner"
    },
    {
      "upn": "owner.two@example.com",
      "role": "Technical Owner"
    }
  ]
}
```

Die Verantwortlichen muessen per `email` oder `upn` geliefert werden. Anzeigenamen sind nicht geeignet, weil sie in Entra ID nicht eindeutig sein muessen.

## 4. Entra ID User Lookup

Fuer jede verantwortliche Person wird Microsoft Graph gefragt:

```text
mail eq '{email}' or userPrincipalName eq '{email}'
```

Nur eindeutige Treffer werden als verantwortliche Benutzer in Cosmos DB gespeichert. Falls kein Benutzer oder mehrere Benutzer gefunden werden, wird diese Person nicht als gueltiger Responsible User in den Fall uebernommen.

## 5. Cosmos DB Case-Erstellung

Fuer jedes expiring Credential wird eine stabile `case_id` erzeugt. Die ID basiert auf:

- Application Object ID
- Credential Key ID
- Credential Ablaufdatum
- Credential Typ

Dadurch ist der Scan idempotent. Wenn das Runbook mehrfach laeuft, wird derselbe Fall aktualisiert statt mehrfach angelegt.

Ein Fall enthaelt unter anderem:

- Azure App Metadaten
- Altes Credential mit `keyId`, Typ und Ablaufdatum
- Interne Metadaten aus dem internen System
- Verantwortliche Benutzer
- Status
- Link-Ablaufdatum
- Entscheidungshistorie
- Audit Events
- Neue Secret-Metadaten nach Renewal
- Bitwarden Send Metadaten

Das neue Secret selbst wird niemals in Cosmos DB gespeichert.

## 6. Benachrichtigung und Unique Link

Wenn ein Fall neu ist oder noch keine Mail verschickt wurde, erzeugt das Runbook einen signierten Link:

```text
https://credential-renewal.example.com/cases/{caseId}?token={signedToken}
```

Der Link ist **nicht** single-use. Er kann mehrfach aufgerufen werden, solange das alte Credential noch nicht abgelaufen ist.

Die Sicherheit basiert auf mehreren Ebenen:

1. Der Link enthaelt einen signierten Token.
2. Der Token ist an die `case_id` gebunden.
3. Der Token laeuft mit dem alten Credential ab.
4. Die Web App erzwingt Entra ID Login.
5. Die Web App erlaubt nur Responsible Users des Falls.

Die Mail wird ueber Microsoft Graph aus der konfigurierten Shared Mailbox gesendet.

## 7. Web App Ablauf

Die Web App ist eine FastAPI App:

```text
credential_renewal.web_app:app
```

Beim Aufruf eines Falls:

1. Die App liest `caseId` aus der URL.
2. Die App liest `token` aus der Query.
3. Der Token wird kryptografisch validiert.
4. Der Benutzer muss per App Service Authentication angemeldet sein.
5. Der Benutzer wird aus dem `x-ms-client-principal` Header gelesen.
6. Die App prueft, ob die Benutzer-Mail in den Responsible Users des Falls steht.
7. Wenn alles passt, wird die Fallseite angezeigt.

Die Seite zeigt:

- Case ID
- Status
- App ID
- Service Management Reference
- Credential Typ
- Alte Credential Key ID
- Ablaufdatum
- Entscheidungsfenster
- Bitwarden Send Link, falls bereits erneuert wurde

## 8. Aktion: Secret erneuern

Der Button **Renew secret** ist nur fuer Client Secrets verfuegbar.

Beim Klick passiert:

1. Die Web App laedt den Fall aus Cosmos DB.
2. Sie prueft, ob der Fall noch editierbar ist.
3. Sie prueft, ob das alte Credential ein Secret ist.
4. Microsoft Graph `addPassword` wird aufgerufen.
5. Graph erstellt ein neues Client Secret.
6. Graph liefert `secretText` zurueck.
7. `secretText` wird sofort an Bitwarden Send uebergeben.
8. Cosmos DB speichert nur Metadaten des neuen Secrets.
9. Der Status wird `renewed_pending_old_secret_removal`.

Wichtig: Microsoft Graph gibt `secretText` nur ein einziges Mal zurueck. Es gibt keine Moeglichkeit, diesen Wert spaeter erneut abzurufen. Deshalb darf das Secret nicht in Logs, Cosmos DB, Mails oder Audit Events landen.

## 9. Aktion: Altes Secret loeschen

Das alte Secret wird bei einer Erneuerung **nicht** automatisch geloescht.

Erst nachdem ein neues Secret erzeugt wurde, erscheint der Button **Delete old secret**. Beim Klick zeigt der Browser eine Bestaetigung:

```text
This will delete the old client secret. Systems still using it can fail immediately. Continue?
```

Nur nach Bestaetigung ruft die Web App Microsoft Graph `removePassword` mit der alten `keyId` auf. Danach wird der Status:

```text
renewed_old_secret_removed
```

Dieser Schritt ist bewusst getrennt, damit Applikationsteams zuerst das neue Secret in ihren Systemen ausrollen koennen.

## 10. Aktion: Nicht erneuern

Der Button **Do not renew** setzt:

```text
defer_until = jetzt + 30 Tage
```

Der Status wird:

```text
deferred
```

Die Entscheidung bleibt innerhalb des Entscheidungsfensters aenderbar, solange das alte Credential noch nicht abgelaufen ist.

## 11. Deployment Checkliste

### 11.1 Azure Ressourcen

Erstelle oder waehle:

- Resource Group
- Azure Automation Account
- Azure App Service Plan
- Azure App Service fuer die FastAPI Web App
- Cosmos DB Account
- Cosmos DB Database
- Cosmos DB Container
- Key Vault
- Shared Mailbox
- Optional: Application Insights und Log Analytics

Empfohlene Cosmos DB Struktur:

```text
Database: credential-renewal
Container: credential-renewal-cases
Partition key: /caseId
```

### 11.2 Managed Identities

Aktiviere Managed Identity fuer:

- Automation Account
- Web App

Empfehlung: Verwende getrennte Identitaeten. Das Runbook braucht andere Rechte als die Web App.

### 11.3 Microsoft Graph Permissions

Noetige Graph Permissions:

- `Application.Read.All` fuer den Scan.
- `User.Read.All` fuer Entra ID User Lookup.
- `Mail.Send` fuer Mailversand aus der Shared Mailbox.
- `Application.ReadWrite.OwnedBy` oder `Application.ReadWrite.All` fuer Secret-Erstellung und Secret-Loeschung.

Alle Permissions brauchen Admin Consent.

Wenn moeglich, ist `Application.ReadWrite.OwnedBy` sicherer als `Application.ReadWrite.All`, setzt aber voraus, dass die verwendete Identity Owner der betroffenen App Registrations ist.

### 11.4 Cosmos DB Rechte

Die Managed Identities brauchen Zugriff auf den Cosmos DB Container.

Mindestens benoetigt:

- Cases lesen
- Cases schreiben
- Cases upserten

### 11.5 Key Vault

Lege einen Signing Key an, z. B.:

```text
credential-renewal-link-signing-key
```

Die Web App und das Runbook muessen das Secret lesen duerfen.

App Settings:

```bash
KEY_VAULT_URL="https://your-vault.vault.azure.net/"
LINK_SIGNING_KEY_SECRET_NAME="credential-renewal-link-signing-key"
```

Alternativ fuer lokale Tests:

```bash
LINK_SIGNING_KEY="local-development-signing-key"
```

### 11.6 Web App Settings

Setze mindestens:

```bash
TENANT_ID="00000000-0000-0000-0000-000000000000"
EXPIRY_WINDOW_DAYS="30"
GRAPH_BASE_URL="https://graph.microsoft.com/v1.0"
INTERNAL_API_BASE_URL="https://internal-api.example.com"
COSMOS_ACCOUNT_URL="https://cosmos-account.documents.azure.com:443/"
COSMOS_DATABASE="credential-renewal"
COSMOS_CONTAINER="credential-renewal-cases"
WEBAPP_PUBLIC_BASE_URL="https://your-webapp.azurewebsites.net"
MAIL_SHARED_MAILBOX="credential-renewal@example.com"
BITWARDEN_MODE="send"
KEY_VAULT_URL="https://your-vault.vault.azure.net/"
LINK_SIGNING_KEY_SECRET_NAME="credential-renewal-link-signing-key"
```

### 11.7 Web App Startup Command

Setze im App Service folgenden Startup Command:

```bash
python -m uvicorn credential_renewal.web_app:app --host 0.0.0.0 --port 8000
```

Die Datei `requirements.txt` liegt im Repository Root. Azure App Service installiert dadurch die Python Dependencies beim Deployment.

### 11.8 App Service Authentication

Aktiviere Authentication im Azure App Service:

1. App Service oeffnen.
2. **Authentication** auswaehlen.
3. Microsoft Entra ID Provider hinzufuegen.
4. Zugriff fuer nicht authentifizierte Benutzer blockieren.
5. Fuer Webseiten ist ein Login Redirect sinnvoll.

Die Web App prueft danach zusaetzlich im Code, ob der eingeloggte Benutzer Responsible User des jeweiligen Falls ist.

### 11.9 Bitwarden

Die Web App nutzt den Bitwarden CLI Client ueber `BitwardenSendClient`.

Produktiv muss sichergestellt sein:

- Bitwarden CLI ist in der Web App Umgebung verfuegbar.
- Die Authentifizierung ist Enterprise-konform automatisiert.
- `bw send create` darf verwendet werden.
- Sends sind kurzlebig.
- Zugriff ist limitiert, idealerweise einmalig.
- Fehler beim Erstellen eines Sends werden ueber Monitoring sichtbar.

Falls Bitwarden Send nach der Graph Secret-Erstellung fehlschlaegt, ist das kritisch: Graph liefert `secretText` nur einmal. In diesem Fall muss der Credential-Wechsel kontrolliert wiederholt oder manuell behandelt werden.

### 11.10 Automation Runbook

Fuer das Runbook:

1. Python Runtime im Automation Account vorbereiten.
2. Projektdateien bereitstellen.
3. Dependencies aus `requirements.txt` bereitstellen.
4. Managed Identity aktivieren.
5. Environment Variables oder Automation Variables setzen.
6. Entry Point auf `credential_renewal.runbook_scan.main` legen.
7. Schedule erstellen, z. B. einmal taeglich.

Das Runbook ist idempotent. Ein wiederholter Lauf aktualisiert bestehende Faelle statt Duplikate zu erzeugen.

## 12. Smoke Test

Empfohlener Testablauf:

1. Test App Registration erstellen.
2. Ein Secret mit baldiger Ablaufzeit hinterlegen.
3. `serviceManagementReference` setzen.
4. Internes REST-System so konfigurieren, dass es fuer diese Reference Verantwortliche liefert.
5. Sicherstellen, dass die Verantwortlichen in Entra ID gefunden werden.
6. Runbook manuell starten.
7. Cosmos DB Case pruefen.
8. Mailzustellung pruefen.
9. Web App Link oeffnen.
10. Entra ID Login pruefen.
11. **Renew secret** klicken.
12. Bitwarden Send Link pruefen.
13. Sicherstellen, dass das alte Secret noch existiert.
14. **Delete old secret** klicken und Confirm Dialog bestaetigen.
15. In Entra ID pruefen, dass das alte Secret entfernt wurde.

## 13. Monitoring und Betrieb

Ueberwache:

- Automation Job Status
- Runbook Exceptions
- Cosmos DB Fehler und Throttling
- Microsoft Graph 401/403/429/5xx Antworten
- Interne API Fehler
- Mailversandfehler
- Bitwarden Send Fehler
- Web App 401/403/500 Raten

Typische Fehler:

- `serviceManagementReference` fehlt.
- Internes System liefert keine Verantwortlichen.
- Verantwortliche koennen in Entra ID nicht eindeutig gefunden werden.
- Graph Permission fehlt.
- Web App Managed Identity hat keinen Key Vault Zugriff.
- Bitwarden CLI ist nicht installiert oder nicht authentifiziert.
- Cosmos DB Rechte fehlen.

## 14. Sicherheitsnotizen

- Secret-Werte duerfen niemals gespeichert werden.
- Secret-Werte duerfen niemals geloggt werden.
- Secret-Werte duerfen niemals per Mail verschickt werden.
- Cosmos DB speichert nur Metadaten.
- Der Web App Link ist wiederverwendbar, aber signiert und zeitlich begrenzt.
- Entra ID Login ist immer erforderlich.
- Zusaetzlich muss der Benutzer Responsible User des Falls sein.
- Das alte Secret wird erst nach expliziter Bestaetigung geloescht.
- Audit Events dokumentieren Scan, Mailversand, Renewal, Deferral und Loeschung.

## 15. Wichtige Grenzen von Version 1

- Zertifikate werden erkannt, aber nicht automatisch erneuert.
- Die automatische Bitwarden Send Erstellung setzt voraus, dass die Web App Umgebung Bitwarden CLI und Authentifizierung korrekt bereitstellt.
- Die interne REST API muss bereits existieren oder separat implementiert werden.
- Graph Permissions muessen tenant-seitig sauber genehmigt werden.
- Fuer sehr grosse Tenants muss Graph Throttling beobachtet werden, insbesondere beim Abruf von `keyCredentials`.
