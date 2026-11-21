"""Send the committed sample HTML to the isolated Vercel test project."""
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY = "PXYQ/liebian-actions-lab"
TEAM_ID = "team_16kEqgHGciCuUillcswqPeqE"
PROJECT_ID = "prj_MpbG3VsbT5wUdK40aMTtAVrdHUgi"
PROJECT_NAME = "liebian-actions-lab"
PREVIEW_VIEWER_GITHUB_LOGIN = "dajuwu01-glitch"
SITE = f"{PROJECT_NAME}.vercel.app"
DEPLOYMENT_ID = re.compile(r"dpl_[A-Za-z0-9]{12,80}")
HOSTNAME = re.compile(r"[a-z0-9-]+\.vercel\.app")


def api(origin, path, token, body=None, *, method=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = Request(origin + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except HTTPError as error:
        # Provider responses can contain user-supplied data. Log only the status.
        raise RuntimeError(f"{origin} returned HTTP {error.code}") from None


def vercel(path, body=None, *, method=None):
    return api("https://api.vercel.com", f"{path}?teamId={TEAM_ID}",
               os.environ["VERCEL_LAB_TOKEN"], body, method=method)


def checked_deployment(identifier):
    if not DEPLOYMENT_ID.fullmatch(identifier):
        raise ValueError("Enter the dpl_ preview ID shown in Actions.")
    deployment = vercel(f"/v13/deployments/{identifier}")
    project_id = deployment.get("projectId") or (deployment.get("project") or {}).get("id")
    if project_id != PROJECT_ID or deployment.get("id") != identifier:
        raise ValueError("The deployment does not belong to the test project.")
    return deployment


def submitted_page(event):
    run = event["workflow_run"]
    sha = run["head_sha"]
    if (
        event["action"] != "completed"
        or run["event"] != "push"
        or run["conclusion"] != "success"
        or run["head_repository"]["id"] != event["repository"]["id"]
        or not run["head_branch"].startswith("content/")
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
    ):
        raise ValueError("Expected a successful same-repository page edit.")
    file = api(
        "https://api.github.com",
        f"/repos/{REPOSITORY}/contents/index.html?ref={sha}",
        os.environ["GH_TOKEN"],
    )
    if file["type"] != "file" or file["encoding"] != "base64" or file["size"] > 65536:
        raise ValueError("Expected a normal index.html up to 64 KiB.")
    page = base64.b64decode(file["content"])
    if len(page) != file["size"] or not page:
        raise ValueError("The submitted page is empty or incomplete.")
    page.decode("utf-8")
    return sha, page


def wait_until_ready(identifier, target):
    for attempt in range(36):
        deployment = checked_deployment(identifier)
        status = deployment["readyState"]
        if status in {"ERROR", "CANCELED", "BLOCKED"} or deployment.get("aliasError"):
            raise RuntimeError(f"Deployment {identifier} failed ({status}).")
        if status == "READY" and deployment.get("target") != target:
            raise RuntimeError("Vercel returned an unexpected deployment target.")
        if status == "READY" and (target is None or SITE in deployment.get("alias", [])):
            return deployment
        if attempt < 35:
            time.sleep(5)
    raise RuntimeError(f"Deployment {identifier} did not become ready in time.")


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    if os.environ["GITHUB_REPOSITORY"] != REPOSITORY or os.environ["GITHUB_REF"] != "refs/heads/main":
        raise ValueError("Run the deployment from the test repository's main branch.")
    if not os.environ.get("VERCEL_LAB_TOKEN"):
        raise ValueError("The vercel-lab environment is missing VERCEL_LAB_TOKEN.")

    request = {"name": PROJECT_NAME, "project": PROJECT_ID}
    event_name = os.environ["GITHUB_EVENT_NAME"]
    preview_viewer_email = None
    if event_name == "workflow_run":
        sha, page = submitted_page(event)
        actor = event["workflow_run"]["actor"]["login"]
        if actor.casefold() == PREVIEW_VIEWER_GITHUB_LOGIN:
            preview_viewer_email = os.environ.get("VERCEL_LAB_PREVIEW_VIEWER_EMAIL", "").strip()
            if not preview_viewer_email:
                raise ValueError("The vercel-lab environment is missing VERCEL_LAB_PREVIEW_VIEWER_EMAIL.")
        request["files"] = [
            {"file": "index.html", "encoding": "base64", "data": base64.b64encode(page).decode()}
        ]
        request["meta"] = {"labSourceSha": sha, "labContentSha256": hashlib.sha256(page).hexdigest()}
        target = None
        title = "Preview ready"
        notes = [f"- Source commit: `{sha}`"]
    elif event_name == "workflow_dispatch":
        preview_id = event["inputs"]["preview_id"].strip()
        preview = checked_deployment(preview_id)
        if preview.get("target") is not None or preview["readyState"] != "READY":
            raise ValueError("Choose a READY preview from this test project.")
        request.update(deploymentId=preview_id, target="production")
        target = "production"
        title = "Test site published"
        notes = [f"- Approved preview: `{preview_id}`", f"- Test site: https://{SITE}"]
    else:
        raise ValueError("Unknown workflow trigger.")

    created = vercel("/v13/deployments", request)
    deployment = wait_until_ready(created["id"], target)
    hostname = deployment["url"]
    if not HOSTNAME.fullmatch(hostname):
        raise RuntimeError("The deployment did not return a Vercel hostname.")
    summary = [
        f"## {title}",
        f"- URL: https://{hostname}",
        f"- Deployment ID: `{created['id']}`",
        *notes,
    ]
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        output.write("\n".join(summary) + "\n")
        if preview_viewer_email:
            try:
                vercel(
                    f"/aliases/{hostname}/protection-bypass",
                    {"scope": {"email": preview_viewer_email, "access": "granted"}},
                    method="PATCH",
                )
            except (RuntimeError, URLError, TimeoutError, json.JSONDecodeError):
                output.write("- Preview access: automatic sharing failed.\n")
                raise
            output.write("- Preview access: granted to the configured operator.\n")
    print(f"{title}: {created['id']}")


if __name__ == "__main__":
    main()
