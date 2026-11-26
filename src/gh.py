import logging
import pathlib
import re
import shutil
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from github import Auth, Github, GithubException
from github.GitRelease import GitRelease
from github.GitReleaseAsset import GitReleaseAsset
from github.Repository import Repository

logger = logging.getLogger(__name__)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip the Authorization header when redirecting to a different host.

    GitHub's asset download API (api.github.com) redirects to a signed S3 URL.
    Without this handler, urllib forwards the Authorization header to the
    storage backend, leaking the token to a third-party host.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            original_host = urlparse(req.full_url).netloc.lower()
            new_host = urlparse(new_req.full_url).netloc.lower()
            if original_host != new_host:
                new_req.remove_header("Authorization")
        return new_req


def find_latest_stable_release(repo: Repository) -> GitRelease | None:
    """Return the latest non-prerelease, non-draft release, or None."""
    # Fast-path: query the latest release endpoint directly (1 API call)
    try:
        latest = repo.get_latest_release()
        if not latest.prerelease and not latest.draft:
            return latest
    except GithubException as e:
        if e.status != 404:
            raise

    # Fallback: iterate releases if get_latest_release() 404s (e.g. only prereleases exist)
    for release in repo.get_releases():
        if not release.prerelease and not release.draft:
            return release
    return None


class GH:
    def __init__(self, gh_token: str, base_dir: pathlib.Path | str = "base") -> None:
        self.token = gh_token
        self.base_dir = pathlib.Path(base_dir)
        auth = Auth.Token(self.token)
        self.github = Github(auth=auth)
        self._opener = urllib.request.build_opener(_SafeRedirectHandler)

    def downloadReleaseAssets(self, module: dict[str, Any]) -> bool:
        try:
            ghRepo = self.github.get_repo(module["repo"])
            ghLatestRelease = find_latest_stable_release(ghRepo)
        except GithubException as e:
            if e.status in (403, 429):
                logger.error(f"GitHub API rate limit exceeded while accessing {module['repo']}")
            else:
                logger.exception(f"Unable to get release for repository: {module['repo']}")
            return False

        if ghLatestRelease is None:
            logger.warning(f"No stable release found for: {module['repo']}")
            return False

        logger.info(f"[{module['repo']}] Using stable release: {ghLatestRelease.tag_name}")

        dest_dir = self.base_dir / module["repo"]
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            assets = list(ghLatestRelease.get_assets())
        except GithubException as e:
            if e.status in (403, 429):
                logger.error(f"GitHub API rate limit exceeded while listing assets for {module['repo']}")
            else:
                logger.exception(f"Unable to list assets for: {module['repo']}")
            return False

        downloaded_files: list[pathlib.Path] = []
        for asset in assets:
            if any(re.search(pattern, asset.name) for pattern in module["regex"]):
                logger.info(f"[{module['repo']}] Downloading: {asset.name}")
                dest_file = dest_dir / asset.name
                try:
                    self._download_asset(asset, dest_file)
                except (urllib.error.URLError, OSError):
                    logger.exception(f"[{module['repo']}] Failed to download: {asset.name}")
                    for path in downloaded_files:
                        path.unlink(missing_ok=True)
                    return False
                downloaded_files.append(dest_file)

        if not downloaded_files:
            logger.error(f"No asset matched {module['regex']} for: {module['repo']}")
            return False

        return True

    def _download_asset(self, asset: GitReleaseAsset, dest: pathlib.Path) -> None:
        request = urllib.request.Request(
            asset.url,
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/octet-stream",
            },
        )
        temp_dest = dest.with_suffix(dest.suffix + ".part")
        try:
            with self._opener.open(request, timeout=120) as response, open(temp_dest, "wb") as out:
                shutil.copyfileobj(response, out)
            temp_dest.replace(dest)
        except Exception:
            if temp_dest.exists():
                temp_dest.unlink(missing_ok=True)
            raise
