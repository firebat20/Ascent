#!/usr/bin/env python3

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from github import Auth, Github, GithubException
from gh import find_latest_stable_release

logging.basicConfig(format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("version_tracker")
logger.setLevel(logging.INFO)

SCRIPT_DIR = Path(__file__).parent.resolve()


class VersionTracker:
    def __init__(self, github_token: str):
        self.github = Github(auth=Auth.Token(github_token))
        self.version_file = SCRIPT_DIR / "last_component_versions.json"

    def get_current_versions(self, settings: dict[str, Any], previous_versions: dict) -> dict[str, dict]:
        """Get current versions of all components with fallback to previous versions on error."""
        versions: dict[str, dict] = {}

        for module_name, module_config in settings.get("moduleList", {}).items():
            repo_name = module_config["repo"]
            try:
                repo = self.github.get_repo(repo_name)
                latest_release = find_latest_stable_release(repo)

                if latest_release is not None:
                    versions[module_name] = {
                        "version": latest_release.tag_name,
                        "published_at": (
                            latest_release.published_at.isoformat()
                            if latest_release.published_at
                            else datetime.now().isoformat()
                        ),
                        "repo": repo_name,
                        "url": latest_release.html_url,
                    }
                else:
                    # Fallback to latest commit without computing totalCount
                    try:
                        latest_commit = repo.get_commits()[0]
                        versions[module_name] = {
                            "version": f"commit-{latest_commit.sha[:7]}",
                            "published_at": latest_commit.commit.author.date.isoformat(),
                            "repo": repo_name,
                            "url": latest_commit.html_url,
                        }
                    except (IndexError, GithubException):
                        versions[module_name] = previous_versions.get(
                            module_name,
                            {
                                "version": "unknown",
                                "published_at": datetime.now().isoformat(),
                                "repo": repo_name,
                                "url": f"https://github.com/{repo_name}",
                            },
                        )

            except GithubException as e:
                logger.warning(f"Failed to get version for {module_name} ({repo_name}): {e}")
                versions[module_name] = previous_versions.get(
                    module_name,
                    {
                        "version": "unknown",
                        "published_at": datetime.now().isoformat(),
                        "repo": repo_name,
                        "url": f"https://github.com/{repo_name}",
                    },
                )

        return versions

    def load_previous_versions(self) -> dict:
        """Load previous version information."""
        if not self.version_file.exists():
            return {}

        try:
            return json.loads(self.version_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load previous versions: {e}")
            return {}

    def save_current_versions(self, versions: dict) -> None:
        """Save current versions for next comparison."""
        try:
            self.version_file.write_text(json.dumps(versions, indent=2), encoding="utf-8")
            logger.info(f"Saved current versions to {self.version_file}")
        except OSError as e:
            logger.error(f"Failed to save versions: {e}")

    def find_updates(self, current_versions: dict, previous_versions: dict) -> dict[str, list]:
        """Find what components have been updated."""
        updates: dict[str, list] = {
            "new": [],
            "updated": [],
            "unchanged": [],
        }

        for module_name, current_info in current_versions.items():
            if module_name not in previous_versions:
                updates["new"].append({
                    "name": module_name,
                    "version": current_info["version"],
                    "repo": current_info["repo"],
                    "url": current_info["url"],
                })
            elif previous_versions[module_name]["version"] != current_info["version"]:
                updates["updated"].append({
                    "name": module_name,
                    "old_version": previous_versions[module_name]["version"],
                    "new_version": current_info["version"],
                    "repo": current_info["repo"],
                    "url": current_info["url"],
                })
            else:
                updates["unchanged"].append({
                    "name": module_name,
                    "version": current_info["version"],
                    "repo": current_info["repo"],
                })

        return updates

    def generate_changelog(
        self,
        settings: dict[str, Any],
        updates: dict[str, list],
        release_version: str | None = None,
    ) -> str:
        """Generate a focused changelog based on actual updates."""
        if not release_version:
            version_path = SCRIPT_DIR / "version.json"
            try:
                version_data = json.loads(version_path.read_text(encoding="utf-8"))
                release_version = version_data.get("releaseVersion", "unknown")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load version.json: {e}, using fallback")
                release_version = settings.get("releaseVersion", "unknown")

        current_date = datetime.now().strftime("%Y-%m-%d")

        notes = [
            f"# Ascent v{release_version}",
            f"*Released on {current_date}*",
            "",
            f"![Downloads](https://img.shields.io/github/downloads/exploitz86/Ascent/v{release_version}/total)",
            "",
        ]

        # Show what's been updated
        if updates["updated"] or updates["new"]:
            notes.extend(["## 🚀 What's Updated", ""])

            if updates["updated"]:
                notes.append("### Updated Components")
                for item in updates["updated"]:
                    notes.append(
                        f"- **{item['name']}**: `{item['old_version']}` → [`{item['new_version']}`]({item['url']}) - {item['repo']}"
                    )
                notes.append("")

            if updates["new"]:
                notes.append("### New Components")
                for item in updates["new"]:
                    notes.append(f"- **{item['name']}**: [`{item['version']}`]({item['url']}) - {item['repo']}")
                notes.append("")
        else:
            notes.extend([
                "## 📦 Package Update",
                "",
                "This release contains the same component versions as the previous release, but may include:",
                "- Build script improvements",
                "- Configuration updates",
                "- Package structure optimizations",
                "",
            ])

        # Package information
        notes.extend(["## 📋 Available Packages", ""])

        for package in settings.get("packages", []):
            if package.get("active", False):
                component_count = len(package.get("modules", []))
                notes.append(f"- **{package['name'].title()}**: {component_count} components")

        notes.extend([
            "",
            "## 📥 Installation",
            "",
            "1. Download the appropriate package for your setup",
            "2. Extract to the root of your Switch SD card",
            "3. Boot CFW using your preferred method",
            "",
            "## ⚠️ Important",
            "",
            "- Always backup your NAND before updating CFW",
            "- This is an automated build from the latest component releases",
            "",
            "<details>",
            "<summary>📦 Complete Component List (Click to expand)</summary>",
            "",
        ])

        all_components = updates["updated"] + updates["new"] + updates["unchanged"]
        all_components.sort(key=lambda x: x["name"])

        for item in all_components:
            version = item.get("new_version", item.get("version", "unknown"))
            notes.append(f"- **{item['name']}**: `{version}` - {item['repo']}")

        notes.extend([
            "",
            "</details>",
            "",
            "---",
            f"*Generated automatically by [Ascent](https://github.com/exploitz86/Ascent) on {current_date}*",
        ])

        return "\n".join(notes)


def main() -> int:
    # Anchor CWD to the script's own directory
    os.chdir(SCRIPT_DIR)

    parser = argparse.ArgumentParser(description="Generate changelog based on component updates")
    parser.add_argument("-gt", "--github-token", default=os.environ.get("GITHUB_TOKEN"),
                        help="GitHub Token (defaults to $GITHUB_TOKEN)")
    parser.add_argument("-v", "--version", default=os.environ.get("RELEASE_VERSION"),
                        help="Override release version (defaults to $RELEASE_VERSION or version.json)")
    parser.add_argument("-o", "--output", default="changelog.md", help="Output file")

    args = parser.parse_args()

    if not args.github_token:
        parser.error("A GitHub token is required. Pass -gt/--github-token or set GITHUB_TOKEN.")

    # Load settings
    try:
        settings = json.loads(Path("./settings.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load settings.json: {e}")
        return 1

    tracker = VersionTracker(args.github_token)

    # Load previous versions first so we can fall back on errors
    logger.info("Loading previous component versions...")
    previous_versions = tracker.load_previous_versions()

    # Get current versions
    logger.info("Fetching current component versions...")
    current_versions = tracker.get_current_versions(settings, previous_versions)

    # Find updates
    updates = tracker.find_updates(current_versions, previous_versions)

    logger.info(
        f"Found {len(updates['updated'])} updated, {len(updates['new'])} new, "
        f"{len(updates['unchanged'])} unchanged components"
    )

    # Generate changelog
    changelog = tracker.generate_changelog(settings, updates, release_version=args.version)

    # Save changelog
    try:
        Path(args.output).write_text(changelog, encoding="utf-8")
        logger.info(f"Changelog saved to {args.output}")
    except OSError as e:
        logger.error(f"Failed to save changelog: {e}")
        return 1

    # Save current versions for next time
    tracker.save_current_versions(current_versions)

    return 0


if __name__ == "__main__":
    exit(main())
