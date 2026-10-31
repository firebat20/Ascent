import pathlib
import shutil
import urllib.request
from github import Github
import re
import logging

class GH():
    def __init__(self, ghToken):
        self.token = ghToken
        self.github = Github(self.token)

    def downloadReleaseAssets(self, module):
        try:
            ghRepo = self.github.get_repo(module["repo"])
        except Exception:
            logging.exception(f"Unable to get: {module['repo']}")
            return False

        releases = ghRepo.get_releases()
        if releases.totalCount == 0:
            logging.warning(f"No available release for: {module['repo']}")
            return False

        # Find the latest stable release (skip pre-releases and drafts)
        ghLatestRelease = None
        for release in releases:
            if not release.prerelease and not release.draft:
                ghLatestRelease = release
                logging.info(f"[{module['repo']}] Using stable release: {release.tag_name}")
                break

        if ghLatestRelease is None:
            logging.warning(f"No stable release found for: {module['repo']}")
            return False

        fpath = f"./base/{module['repo']}/"
        pathlib.Path(fpath).mkdir(parents=True, exist_ok=True)

        downloaded = 0
        for asset in ghLatestRelease.get_assets():
            if any(re.search(pattern, asset.name) for pattern in module["regex"]):
                logging.info(f"[{module['repo']}] Downloading: {asset.name}")
                try:
                    self.__downloadAsset(asset, f"{fpath}{asset.name}")
                except Exception:
                    logging.exception(f"[{module['repo']}] Failed to download: {asset.name}")
                    return False
                downloaded += 1

        if downloaded == 0:
            logging.error(f"No asset matched {module['regex']} for: {module['repo']}")
            return False

        return True

    def __downloadAsset(self, asset, dest):
        # Use the API asset URL so private release assets download with auth;
        # urllib follows the signed redirect to the storage backend.
        request = urllib.request.Request(
            asset.url,
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/octet-stream",
            },
        )
        with urllib.request.urlopen(request) as response, open(dest, "wb") as out:
            shutil.copyfileobj(response, out)
