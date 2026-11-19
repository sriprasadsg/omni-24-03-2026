"""What each cloud log connector reads and how its records become SIEM events (Wave 3; see log_connectors).

Sources: entra_id (sign-ins and directory audits), m365, aws_cloudtrail, google_workspace (the names migration 039 gave
the descriptive library rules). Every ``fetch_*`` takes the connector's settings (secret decrypted), its cursor (ISO time of the newest record already
read, per stream) and the current time, and returns (events, new cursor). Events have the siem_pipeline shape:
source, action, outcome, user, srcIp, host, message, timestamp and a ``key`` unique per record, so a record read twice
(cursors overlap by design) is stored once. Errors raise SourceError with the provider's HTTP status, never a secret.

* entra  - Microsoft Graph auditLogs/signIns (needs Entra ID P1 or P2) and auditLogs/directoryAudits;
           permission AuditLog.Read.All (application), admin consent.
* m365   - Office 365 Management Activity API, content types Audit.AzureActiveDirectory, Audit.Exchange,
           Audit.SharePoint, Audit.General; permission ActivityFeed.Read (Office 365 Management APIs).
* aws    - CloudTrail LookupEvents (management events, read-only key with cloudtrail:LookupEvents), per region.
* google - Admin SDK Reports API, applications login and admin; a service account with domain-wide delegation for
           https://www.googleapis.com/auth/admin.reports.audit.readonly, acting as an admin.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"
MANAGE = "https://manage.office.com/api/v1.0"
GOOGLE_REPORTS = "https://admin.googleapis.com/admin/reports/v1/activity/users/all/applications"
M365_TYPES = ("Audit.AzureActiveDirectory", "Audit.Exchange", "Audit.SharePoint", "Audit.General")
FIRST_LOOK = timedelta(hours=24)  # how far back a new connector starts
MAX_PAGES = 20
TIMEOUT = 30.0

Event = Dict[str, Any]
Cursor = Dict[str, str]


class SourceError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _client(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, **kw)


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _since(cursor: Cursor, stream: str, now: datetime, limit: Optional[timedelta] = None) -> datetime:
    start = datetime.fromisoformat(cursor[stream].replace("Z", "+00:00")) if cursor.get(stream) else now - FIRST_LOOK
    return max(start, now - limit) if limit else start


def _refused(provider: str, r: httpx.Response) -> SourceError:
    hints = {400: "the request was refused", 401: "the credentials were refused", 403: "the app lacks a permission or licence",
             404: "not found", 429: "rate limited; the next run continues"}
    return SourceError(f"{provider} answered HTTP {r.status_code}: {hints.get(r.status_code, 'an error')}")


def _event(source: str, key: str, action: str, outcome: str, ts: Optional[str], user: Optional[str] = None,
           ip: Optional[str] = None, host: Optional[str] = None, message: str = "", **extra: Any) -> Event:
    return {"source": source, "key": f"{source}|{key}", "action": action, "outcome": outcome, "timestamp": ts,
            "user": (user or None), "srcIp": ip or None, "host": host, "message": message[:500], **extra}


# ------------------------------------------------------------------------------------------------ Microsoft (both)

async def ms_token(cfg: Dict[str, Any], scope: str) -> str:
    async with _client() as c:
        r = await c.post(f"https://login.microsoftonline.com/{cfg['azureTenantId']}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": cfg["clientId"], "client_secret": cfg["secret"], "scope": scope})
    if r.status_code != 200:
        raise SourceError(f"Entra refused the app's credentials (HTTP {r.status_code}); check the ids and the secret")
    return r.json()["access_token"]


def entra_signin(s: Dict[str, Any]) -> Event:
    status = s.get("status") or {}
    failed = (status.get("errorCode") or 0) != 0
    loc = s.get("location") or {}
    return _event("entra_id", f"signin|{s['id']}", "login_failed" if failed else "login_success", "failure" if failed else "success",
                  s.get("createdDateTime"), s.get("userPrincipalName"), s.get("ipAddress"), s.get("appDisplayName"),
                  f"Entra sign-in to {s.get('appDisplayName')}: {status.get('failureReason') or 'success'}",
                  country=loc.get("countryOrRegion"), risk=s.get("riskLevelDuringSignIn"), clientApp=s.get("clientAppUsed"))


ENTRA_AUDIT_ACTIONS = {"Add member to role": "admin_role_add", "Add eligible member to role": "admin_role_add",
                       "Add user": "account_created", "Delete user": "account_deleted", "Reset user password": "password_reset",
                       "Disable account": "account_disabled", "Add service principal credentials": "app_credential_added",
                       "Consent to application": "app_consent"}


def entra_audit(a: Dict[str, Any]) -> Event:
    by = (a.get("initiatedBy") or {})
    actor = (by.get("user") or {}).get("userPrincipalName") or (by.get("app") or {}).get("displayName")
    target = next((t.get("userPrincipalName") or t.get("displayName") for t in a.get("targetResources") or []), None)
    ok = (a.get("result") or "success") == "success"
    return _event("entra_id", f"audit|{a['id']}", ENTRA_AUDIT_ACTIONS.get(a.get("activityDisplayName"), "directory_change"),
                  "success" if ok else "failure", a.get("activityDateTime"), actor,
                  ((by.get("user") or {}).get("ipAddress")), None, f"{a.get('activityDisplayName')}: {target or ''}".strip(": "),
                  target=target, operation=a.get("activityDisplayName"))


async def _graph_pages(token: str, url: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    async with _client(headers={"Authorization": f"Bearer {token}"}) as c:
        for _ in range(MAX_PAGES):
            r = await c.get(url)
            if r.status_code != 200:
                raise _refused("Microsoft Graph", r)
            body = r.json()
            rows += body.get("value") or []
            url = body.get("@odata.nextLink")
            if not url:
                break
    return rows


async def fetch_entra(cfg: Dict[str, Any], cursor: Cursor, now: datetime) -> Tuple[List[Event], Cursor]:
    token = await ms_token(cfg, "https://graph.microsoft.com/.default")
    out, cursor = [], dict(cursor)
    for stream, path, field, norm in (("signIns", "auditLogs/signIns", "createdDateTime", entra_signin),
                                      ("directoryAudits", "auditLogs/directoryAudits", "activityDateTime", entra_audit)):
        since = _iso(_since(cursor, stream, now))
        rows = await _graph_pages(token, f"{GRAPH}/{path}?$filter={field} ge {since}&$top=500")
        out += [norm(r) for r in rows if r.get("id")]
        cursor[stream] = max([since, *(r.get(field) or "" for r in rows)])
    return out, cursor


M365_ACTIONS = {"UserLoginFailed": "login_failed", "UserLoggedIn": "login_success", "New-InboxRule": "mail_rule_created",
                "Set-InboxRule": "mail_rule_created", "Set-Mailbox": "mailbox_changed", "Add-MailboxPermission": "mailbox_permission_added",
                "FileDeleted": "file_deleted", "FileDownloaded": "file_downloaded", "SharingSet": "sharing_changed",
                "AnonymousLinkCreated": "anonymous_link_created", "Add member to role.": "admin_role_add"}


def m365_record(r: Dict[str, Any]) -> Event:
    op = r.get("Operation") or ""
    action = M365_ACTIONS.get(op, "activity")
    failed = action == "login_failed" or str(r.get("ResultStatus") or "").lower() in ("failed", "failure")
    params = {p.get("Name"): p.get("Value") for p in r.get("Parameters") or [] if isinstance(p, dict)}
    forwards = any(params.get(k) for k in ("ForwardTo", "ForwardAsAttachmentTo", "RedirectTo", "ForwardingSmtpAddress"))
    ts = r.get("CreationTime")
    return _event("m365", r.get("Id") or f"{ts}|{op}|{r.get('UserId')}", "mail_forward_rule" if forwards else action,
                  "failure" if failed else "success", f"{ts}Z" if ts and not ts.endswith("Z") and "+" not in ts else ts,
                  r.get("UserId"), r.get("ClientIP") or r.get("ActorIpAddress"), r.get("Workload"),
                  f"Microsoft 365 {r.get('Workload') or ''} {op}: {r.get('ObjectId') or ''}".strip(), operation=op)


async def fetch_m365(cfg: Dict[str, Any], cursor: Cursor, now: datetime) -> Tuple[List[Event], Cursor]:
    token = await ms_token(cfg, "https://manage.office.com/.default")
    base, out, cursor = f"{MANAGE}/{cfg['azureTenantId']}/activity/feed", [], dict(cursor)
    async with _client(headers={"Authorization": f"Bearer {token}"}) as c:
        for kind in M365_TYPES:
            if not cursor.get(f"{kind}:on"):
                r = await c.post(f"{base}/subscriptions/start", params={"contentType": kind})
                if r.status_code not in (200, 400):  # 400 = already subscribed (AF20024)
                    raise _refused("Office 365 Management API", r)
                cursor[f"{kind}:on"] = "yes"
            start = _since(cursor, kind, now, limit=timedelta(hours=23, minutes=55))  # the API lists at most 24 hours
            url, params = f"{base}/subscriptions/content", {"contentType": kind, "startTime": _iso(start), "endTime": _iso(now)}
            newest = start
            for _ in range(MAX_PAGES):
                r = await c.get(url, params=params)
                if r.status_code != 200:
                    raise _refused("Office 365 Management API", r)
                for blob in r.json() or []:
                    got = await c.get(blob["contentUri"])
                    if got.status_code != 200:
                        raise _refused("Office 365 Management API", got)
                    out += [m365_record(x) for x in got.json() or []]
                    created = blob.get("contentCreated")
                    if created:
                        newest = max(newest, datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(timezone.utc))
                url, params = r.headers.get("NextPageUri"), None
                if not url:
                    break
            cursor[kind] = _iso(newest)
    return out, cursor


# ------------------------------------------------------------------------------------------------ AWS

AWS_ACTIONS = {"StopLogging": "log_disabled", "DeleteTrail": "log_disabled", "UpdateTrail": "log_changed",
               "CreateUser": "account_created", "DeleteUser": "account_deleted", "CreateAccessKey": "access_key_created",
               "AttachUserPolicy": "policy_attached", "AttachRolePolicy": "policy_attached", "AttachGroupPolicy": "policy_attached",
               "PutUserPolicy": "policy_attached", "AuthorizeSecurityGroupIngress": "firewall_opened", "DeleteBucketPolicy": "bucket_policy_deleted",
               "PutBucketPublicAccessBlock": "bucket_access_changed", "DisableKey": "kms_key_disabled", "ScheduleKeyDeletion": "kms_key_deleted"}


def aws_event(e: Dict[str, Any], region: str) -> Event:
    detail = json.loads(e.get("CloudTrailEvent") or "{}")
    name = e.get("EventName") or detail.get("eventName") or ""
    ident = detail.get("userIdentity") or {}
    login = (detail.get("responseElements") or {}).get("ConsoleLogin")
    failed = login == "Failure" or bool(detail.get("errorCode"))
    action = ("login_failed" if login == "Failure" else "login_success") if name == "ConsoleLogin" else AWS_ACTIONS.get(name, "activity")
    ts = e.get("EventTime")
    ts = ts.isoformat() if isinstance(ts, datetime) else (ts or detail.get("eventTime"))
    return _event("aws_cloudtrail", e.get("EventId") or detail.get("eventID"), action, "failure" if failed else "success", ts,
                  e.get("Username") or ident.get("userName") or ident.get("arn"), detail.get("sourceIPAddress"), region,
                  f"AWS {detail.get('eventSource', '')} {name}{(': ' + detail['errorCode']) if detail.get('errorCode') else ''}",
                  operation=name, rootUser=ident.get("type") == "Root", region=region)


def _aws_lookup(cfg: Dict[str, Any], region: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """CloudTrail LookupEvents for one region (boto3, run in a thread); at most MAX_PAGES pages of 50."""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    client = boto3.client("cloudtrail", region_name=region, aws_access_key_id=cfg["accessKeyId"], aws_secret_access_key=cfg["secret"])
    rows, token = [], None
    try:
        for _ in range(MAX_PAGES):
            page = client.lookup_events(StartTime=start, EndTime=end, MaxResults=50, **({"NextToken": token} if token else {}))
            rows += page.get("Events") or []
            token = page.get("NextToken")
            if not token:
                break
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "error")
        raise SourceError(f"AWS CloudTrail refused the request in {region} ({code}); check the key and cloudtrail:LookupEvents")
    except BotoCoreError as exc:
        raise SourceError(f"AWS CloudTrail could not be reached in {region} ({type(exc).__name__})")
    return rows


async def fetch_aws(cfg: Dict[str, Any], cursor: Cursor, now: datetime) -> Tuple[List[Event], Cursor]:
    out, cursor = [], dict(cursor)
    for region in cfg["regions"]:
        start = _since(cursor, region, now)
        rows = await asyncio.to_thread(_aws_lookup, cfg, region, start, now)
        out += [aws_event(r, region) for r in rows]
        cursor[region] = _iso(max([start, *(r["EventTime"] for r in rows if isinstance(r.get("EventTime"), datetime))]))
    return out, cursor


# ------------------------------------------------------------------------------------------------ Google Workspace

GOOGLE_ACTIONS = {"login_failure": "login_failed", "login_success": "login_success", "suspicious_login": "login_suspicious",
                  "login_challenge": "login_challenge", "ASSIGN_ROLE": "admin_role_add", "CREATE_USER": "account_created",
                  "DELETE_USER": "account_deleted", "CHANGE_PASSWORD": "password_reset", "GRANT_ADMIN_PRIVILEGE": "admin_role_add"}


def google_activity(a: Dict[str, Any], app: str) -> List[Event]:
    ident, out = a.get("id") or {}, []
    for i, e in enumerate(a.get("events") or []):
        name = e.get("name") or ""
        action = GOOGLE_ACTIONS.get(name, "activity" if app == "login" else "directory_change")
        out.append(_event("google_workspace", f"{app}|{ident.get('uniqueQualifier')}|{ident.get('time')}|{i}", action,
                          "failure" if action == "login_failed" else "success", ident.get("time"),
                          (a.get("actor") or {}).get("email"), a.get("ipAddress"), None, f"Google Workspace {app} {name}", operation=name, app=app))
    return out


def _google_token(cfg: Dict[str, Any]) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    try:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(cfg["secret"]), scopes=["https://www.googleapis.com/auth/admin.reports.audit.readonly"], subject=cfg["adminEmail"])
        creds.refresh(Request())
    except Exception as exc:  # google-auth raises several types; never echo the key
        raise SourceError(f"Google refused the service account ({type(exc).__name__}); check domain-wide delegation and the admin email")
    return creds.token


async def fetch_google(cfg: Dict[str, Any], cursor: Cursor, now: datetime) -> Tuple[List[Event], Cursor]:
    token = await asyncio.to_thread(_google_token, cfg)
    out, cursor = [], dict(cursor)
    async with _client(headers={"Authorization": f"Bearer {token}"}) as c:
        for app in ("login", "admin"):
            since, newest, params = _iso(_since(cursor, app, now)), None, None
            params = {"startTime": since, "maxResults": 1000}
            for _ in range(MAX_PAGES):
                r = await c.get(f"{GOOGLE_REPORTS}/{app}", params=params)
                if r.status_code != 200:
                    raise _refused("Google Reports API", r)
                body = r.json()
                for a in body.get("items") or []:
                    out += google_activity(a, app)
                    newest = max(newest or since, (a.get("id") or {}).get("time") or since)
                if not body.get("nextPageToken"):
                    break
                params = {"startTime": since, "maxResults": 1000, "pageToken": body["nextPageToken"]}
            cursor[app] = newest or since
    return out, cursor


FETCH = {"entra": fetch_entra, "m365": fetch_m365, "aws": fetch_aws, "google": fetch_google}
