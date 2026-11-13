"""Dispatch guardian-close. This process does not scan, freeze, or seal.

The token is read from the environment and is never placed on the command
line or written to the status file. HTTP 204 only means GitHub accepted the
request. A missing run, a skipped job, a rejected token, or a timeout is a
non-zero result.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

API = "https://api.github.com"
WORKFLOW = "guardian-close.yml"
DEFAULT_STATUS = Path("/var/lib/mrbot/guardian_dispatch/last.json")


class DispatchError(RuntimeError):
    def __init__(self, result: str, detail: str, http_status: int | None = None):
        super().__init__(detail)
        self.result = result
        self.detail = detail
        self.http_status = http_status


def dispatch_guardian_close(
    *,
    token: str,
    repo: str,
    workflow: str = WORKFLOW,
    ref: str = "main",
    status_path: Path = DEFAULT_STATUS,
    timeout_sec: float = 20.0,
    transport: Callable[..., tuple[int, Any]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    lock: bool = True,
) -> dict:
    """Start one workflow run and record a durable status object."""
    status_path = Path(status_path)
    if lock:
        busy = _acquire(status_path)
        if busy is not None:
            _write_status(status_path, busy, token)
            return busy
    recorded = datetime.now(timezone.utc).replace(microsecond=0)
    result: dict
    try:
        result = _dispatch(
            token=token,
            repo=repo,
            workflow=workflow,
            ref=ref,
            timeout_sec=timeout_sec,
            transport=transport or _urllib_transport,
            sleep=sleep,
            monotonic=monotonic,
            started=recorded,
        )
    except DispatchError as exc:
        result = _status(exc.result, exc.detail, http_status=exc.http_status, recorded_at=recorded)
    _write_status(status_path, result, token)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispatch the Guardian close workflow")
    parser.parse_args(argv)
    token = os.environ.get("GUARDIAN_DISPATCH_TOKEN", "").strip()
    repo = os.environ.get("GUARDIAN_DISPATCH_REPO", "SONVODAI/scanner-ga-chien-clean").strip()
    workflow = os.environ.get("GUARDIAN_DISPATCH_WORKFLOW", WORKFLOW).strip()
    ref = os.environ.get("GUARDIAN_DISPATCH_REF", "main").strip()
    status = Path(os.environ.get("GUARDIAN_DISPATCH_STATUS", str(DEFAULT_STATUS)))
    timeout = float(os.environ.get("GUARDIAN_DISPATCH_TIMEOUT_SEC", "20"))
    if not token:
        body = _status("TOKEN_REJECTED", "GUARDIAN_DISPATCH_TOKEN is empty")
        _write_status(status, body, "")
        return _exit_code(body)
    body = dispatch_guardian_close(
        token=token,
        repo=repo,
        workflow=workflow,
        ref=ref,
        status_path=status,
        timeout_sec=timeout,
    )
    return _exit_code(body)


def _dispatch(*, token, repo, workflow, ref, timeout_sec, transport, sleep, monotonic, started) -> dict:
    owner, name = _repo(repo)
    url = f"{API}/repos/{owner}/{name}/actions/workflows/{workflow}/dispatches"
    status, _payload = transport(
        "POST",
        url,
        {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"},
        {"ref": ref},
    )
    if status in {401, 403}:
        raise DispatchError("TOKEN_REJECTED", f"HTTP {status}", status)
    if status != 204:
        raise DispatchError("DISPATCH_FAILED", f"HTTP {status}", status)
    deadline = monotonic() + max(0.0, float(timeout_sec))
    runs_url = f"{API}/repos/{owner}/{name}/actions/workflows/{workflow}/runs?event=workflow_dispatch&per_page=10"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    while True:
        run_status, runs = transport("GET", runs_url, headers, None)
        if run_status in {401, 403}:
            raise DispatchError("TOKEN_REJECTED", f"HTTP {run_status}", run_status)
        if run_status != 200:
            raise DispatchError("DISPATCH_FAILED", f"HTTP {run_status}", run_status)
        match = _matching_run(runs, started)
        if match is not None:
            job_status, jobs = transport("GET", match["jobs_url"], headers, None)
            if job_status in {401, 403}:
                raise DispatchError("TOKEN_REJECTED", f"HTTP {job_status}", job_status)
            if job_status != 200:
                raise DispatchError("DISPATCH_FAILED", f"HTTP {job_status}", job_status)
            verdict = _job_verdict(jobs)
            if verdict == "skipped":
                raise DispatchError("SKIPPED_JOB", "guardian job skipped", 204)
            if verdict == "started":
                return _status(
                    "DISPATCH_ACCEPTED",
                    "run queued",
                    http_status=204,
                    run_id=match["id"],
                    run_url=match["url"],
                    recorded_at=started,
                )
        if monotonic() >= deadline:
            if match is None:
                raise DispatchError("MISSING_RUN", "workflow run did not appear", 204)
            raise DispatchError("TIMEOUT", "job state was not visible before timeout", 204)
        sleep(min(1.0, max(0.0, deadline - monotonic())))


def _matching_run(payload: Any, started: datetime) -> dict | None:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None
    floor = started.timestamp() - 5
    chosen = None
    for run in runs:
        if not isinstance(run, dict) or run.get("event") not in {None, "workflow_dispatch"}:
            continue
        created = _timestamp(run.get("created_at"))
        if created is None or created < floor:
            continue
        if chosen is None or created >= chosen["created"]:
            chosen = {
                "id": run.get("id"),
                "url": run.get("html_url") or "",
                "jobs_url": run.get("jobs_url") or "",
                "created": created,
            }
    if chosen is None or not chosen["jobs_url"]:
        return None
    return chosen


def _job_verdict(payload: Any) -> str:
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list) or not jobs:
        return "pending"
    guardian = [job for job in jobs if isinstance(job, dict) and str(job.get("name") or "") == "guardian"]
    selected = guardian or [job for job in jobs if isinstance(job, dict)]
    if any(str(job.get("conclusion") or "") == "skipped" for job in selected):
        return "skipped"
    if any(str(job.get("status") or "") in {"queued", "in_progress", "waiting", "pending"} for job in selected):
        return "started"
    if any(str(job.get("status") or "") == "completed" and str(job.get("conclusion") or "") not in {"skipped", ""} for job in selected):
        return "started"
    return "pending"


def _urllib_transport(method: str, url: str, headers: dict, body: dict | None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            parsed: Any = json.loads(raw) if raw else {}
            return int(response.status), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"message": raw[:200]}
        return int(exc.code), parsed


def _acquire(status_path: Path) -> dict | None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = status_path.with_suffix(".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return _status("DISPATCH_BUSY", "another dispatch holds the lock")
    # The lock must outlive this function. The process exits after main, which
    # releases it. Keep the descriptor open by parking it on the module.
    _LOCKS.append(fd)
    return None


def _write_status(path: Path, body: dict, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = json.dumps(_redact(body, token), ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(safe, encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _redact(value, token: str):
    if isinstance(value, dict):
        return {key: _redact(item, token) for key, item in value.items() if key != "token"}
    if isinstance(value, list):
        return [_redact(item, token) for item in value]
    if isinstance(value, str) and token and token in value:
        return value.replace(token, "[REDACTED]")
    return value


def _status(result: str, detail: str, **extra) -> dict:
    body = {
        "result": result,
        "detail": detail,
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    for key, value in extra.items():
        if isinstance(value, datetime):
            value = value.astimezone(timezone.utc).isoformat()
        if value is not None:
            body[key] = value
    return body


def _exit_code(body: dict) -> int:
    return {
        "DISPATCH_ACCEPTED": 0,
        "TOKEN_REJECTED": 2,
        "MISSING_RUN": 3,
        "SKIPPED_JOB": 4,
        "TIMEOUT": 5,
        "DISPATCH_BUSY": 6,
    }.get(str(body.get("result")), 1)


def _repo(value: str) -> tuple[str, str]:
    owner, _sep, name = value.partition("/")
    if not owner or not name or "/" in name:
        raise DispatchError("DISPATCH_FAILED", "GUARDIAN_DISPATCH_REPO must be owner/name")
    return owner, name


def _timestamp(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


_LOCKS: list[int] = []


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DispatchError as exc:
        sys.stderr.write(exc.detail + "\n")
        raise SystemExit(_exit_code({"result": exc.result})) from exc
