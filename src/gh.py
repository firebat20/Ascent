import logging
import pathlib
import re
import shutil
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from github import Github, GithubException
from github.GitRelease import GitRelease
from github.Repository import Repository


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip the Authorization header when redirecting to a different host.

    GitHub's asset download API (api.github.com) redirects to a signed S3 URL.
    Without this handler, urllib forwards the Authorization header to the
    storage backend, leaking the token to a third-party host.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            original_host = urlparse(req.full_url).netloc
            new_host = urlparse(new_req.full_url).netloc
            if original_host != new_host:
                new_req.remove_header("Authorization")
        return new_req


def find_latest_stable_release(repo: Repository) -> Optional[GitRelease]:
    """Return the latest non-prerelease, non-draft release, or None."""
    releases = repo.get_releases()
    if releases.totalCount == 0:
        return None
    for release in releases:
        if not release.prerelease and not release.draft:
            return release
    return None


class GH:
    def __init__(self, gh_token: str):
        self.token = gh_token
        self.github = Github(self.token)

    def downloadReleaseAssets(self, module: dict) -> bool:
        try:
            ghRepo = self.github.get_repo(module["repo"])
        except GithubException:
            logging.exception(f"Unable to get: {module['repo']}")
            return False

        ghLatestRelease = find_latest_stable_release(ghRepo)

        if ghLatestRelease is None:
            logging.warning(f"No stable release found for: {module['repo']}")
            return False

        logging.info(f"[{module['repo']}] Using stable release: {ghLatestRelease.tag_name}")

        fpath = f"./base/{module['repo']}/"
        pathlib.Path(fpath).mkdir(parents=True, exist_ok=True)

        downloaded = 0
        for asset in ghLatestRelease.get_assets():
            if any(re.search(pattern, asset.name) for pattern in module["regex"]):
                logging.info(f"[{module['repo']}] Downloading: {asset.name}")
                try:
                    self.__downloadAsset(asset, f"{fpath}{asset.name}")
                except (urllib.error.URLError, OSError):
                    logging.exception(f"[{module['repo']}] Failed to download: {asset.name}")
                    return False
                downloaded += 1

        if downloaded == 0:
            logging.error(f"No asset matched {module['regex']} for: {module['repo']}")
            return False

        return True

    def __downloadAsset(self, asset, dest: str) -> None:
        opener = urllib.request.build_opener(_SafeRedirectHandler)
        request = urllib.request.Request(
            asset.url,
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/octet-stream",
            },
        )
        with opener.open(request) as response, open(dest, "wb") as out:
            shutil.copyfileobj(response, out)
