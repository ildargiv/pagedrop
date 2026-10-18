"""Publish a folder as a GitHub Pages site and wait until the URL is live.

Usage:
    python publish.py ./my-site --repo my-site --description "Landing for a coffee shop"
    python publish.py ./my-site --repo my-site --update            # push changes to an existing site
    python publish.py ./my-site --repo my-site --domain example.com  # custom domain

Auth (first match wins; the token is never printed):
    1. GITHUB_TOKEN or GH_TOKEN environment variable
    2. `gh auth token` (GitHub CLI)
    3. the git credential helper (e.g. Git Credential Manager) for github.com

Only the Python standard library and git are required.
The last line of output is a JSON summary: {"url": ..., "repo": ..., "status": ...}.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def fail(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    print(json.dumps({"status": "error", "error": msg}))
    sys.exit(1)


# ---------- auth ----------

def get_token() -> str:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    if shutil.which("gh"):
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, env=env)
    fields = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    if fields.get("password"):
        return fields["password"]
    fail("No GitHub credentials found. Set GITHUB_TOKEN, run `gh auth login`, "
         "or sign in to GitHub once with git (e.g. `git push` to any repo).")


def api(token: str, method: str, path: str, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "pagedrop"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"message": raw.decode(errors="replace")}


# ---------- git ----------

def git(args, cwd: Path, token: str = None, check=True):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:
        # Pass the token through env-based git config, so it never appears in argv or in .git/config
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"})
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        fail(f"git {' '.join(args)} failed: {r.stderr.strip()[-400:]}")
    return r


def commit_all(site: Path, login: str, message: str) -> bool:
    git(["add", "-A"], site)
    if not git(["status", "--porcelain"], site).stdout.strip():
        return False
    ident = []
    if not git(["config", "user.email"], site, check=False).stdout.strip():
        ident = ["-c", f"user.name={login}", "-c", f"user.email={login}@users.noreply.github.com"]
    git([*ident, "commit", "-q", "-m", message], site)
    return True


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description="Publish a folder to GitHub Pages")
    ap.add_argument("dir", help="folder with index.html")
    ap.add_argument("--repo", required=True, help="repository name; the site URL is <user>.github.io/<repo>/")
    ap.add_argument("--description", default="", help="repository description")
    ap.add_argument("--update", action="store_true", help="publish changes to an existing repository")
    ap.add_argument("--domain", help="custom domain, e.g. example.com or www.example.com")
    ap.add_argument("--private", action="store_true", help="private repo (Pages on private repos needs a paid plan)")
    ap.add_argument("--message", default=None, help="commit message")
    ap.add_argument("--timeout", type=int, default=300, help="seconds to wait for the site to go live")
    args = ap.parse_args()

    site = Path(args.dir).resolve()
    if not (site / "index.html").exists():
        fail(f"{site} has no index.html")
    if not shutil.which("git"):
        fail("git is not installed")

    token = get_token()
    st, me = api(token, "GET", "/user")
    if st != 200:
        fail(f"GitHub rejected the credentials: {me.get('message')}")
    login = me["login"]
    full = f"{login}/{args.repo}"
    remote = f"https://github.com/{full}.git"

    st, repo = api(token, "GET", f"/repos/{full}")
    exists = st == 200
    if exists and not args.update:
        fail(f"Repository {full} already exists. Use --update to publish changes to it, or pick another --repo.")
    if not exists and args.update:
        fail(f"Repository {full} does not exist, so there is nothing to update. Drop --update to create it.")

    # Files GitHub Pages needs
    (site / ".nojekyll").touch()  # serve files as-is, no Jekyll processing
    if args.domain:
        (site / "CNAME").write_text(args.domain.strip() + "\n", encoding="utf-8")

    if not exists:
        print(f"Creating {full}...")
        homepage = f"https://{args.domain}/" if args.domain else f"https://{login}.github.io/{args.repo}/"
        st, repo = api(token, "POST", "/user/repos", {
            "name": args.repo, "description": args.description[:350], "homepage": homepage,
            "private": args.private, "has_wiki": False})
        if st != 201:
            fail(f"Could not create the repository: {repo.get('message')} {repo.get('errors', '')}")

    branch = "main"
    if not (site / ".git").exists():
        git(["init", "-q", "-b", branch], site)
    current = git(["remote", "get-url", "origin"], site, check=False)
    if current.returncode != 0:
        git(["remote", "add", "origin", remote], site)
    elif current.stdout.strip().removesuffix(".git").rstrip("/").lower() != remote.removesuffix(".git").lower():
        fail(f"This folder already pushes to {current.stdout.strip()}. "
             f"Publish from a separate folder, or change its origin yourself.")

    if exists:
        branch = repo.get("default_branch", "main")
        # Fresh local folder for an existing site: keep the remote history
        if git(["rev-parse", "--verify", "HEAD"], site, check=False).returncode != 0:
            git(["fetch", "-q", "origin", branch], site, token)
            git(["reset", "-q", "--soft", f"origin/{branch}"], site)
        git(["checkout", "-q", "-B", branch], site, check=False)

    changed = commit_all(site, login, args.message or ("Update site" if exists else "Publish site"))
    if exists and not changed:
        print("No changes to publish.")
    print("Pushing...")
    git(["push", "-q", "-u", "origin", branch], site, token)

    st, pages = api(token, "GET", f"/repos/{full}/pages")
    if st == 404:
        print("Enabling GitHub Pages...")
        st, pages = api(token, "POST", f"/repos/{full}/pages", {"source": {"branch": branch, "path": "/"}})
        if st not in (201, 409):
            fail(f"Could not enable Pages: {pages.get('message')}")
    if args.domain:
        api(token, "PUT", f"/repos/{full}/pages", {"cname": args.domain.strip()})

    url = f"https://{args.domain.strip()}/" if args.domain else f"https://{login}.github.io/{args.repo}/"
    print("Waiting for the build", end="", flush=True)
    deadline = time.time() + args.timeout
    head = git(["rev-parse", "HEAD"], site).stdout.strip()
    status = "pending"
    while time.time() < deadline:
        st, build = api(token, "GET", f"/repos/{full}/pages/builds/latest")
        if st == 200 and build.get("status") == "errored":
            status = "build_error"
            break
        if st == 200 and build.get("status") == "built" and build.get("commit") == head:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=20) as r:
                    if r.status == 200:
                        status = "live"
                        break
            except (urllib.error.URLError, OSError):
                pass
        print(".", end="", flush=True)
        time.sleep(8)
    print()

    if status == "live":
        print(f"Live: {url}")
    elif status == "build_error":
        print(f"GitHub Pages reported a build error. Check https://github.com/{full}/actions")
    else:
        print(f"Pushed, but not live yet after {args.timeout}s. It usually appears within a few minutes: {url}")
    if args.domain:
        apex = args.domain.count(".") == 1
        print("DNS for the custom domain:")
        if apex:
            print("  A     @    185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153")
        else:
            print(f"  CNAME {args.domain.split('.')[0]}  {login}.github.io")
    print(json.dumps({"status": status, "url": url, "repo": f"https://github.com/{full}"}))


if __name__ == "__main__":
    main()
