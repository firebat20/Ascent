import argparse
import json
import logging
import os
import shutil
from pathlib import Path

from fs import FS
from gh import GH

logging.basicConfig(format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("ascent")
logger.setLevel(logging.INFO)

if __name__ == "__main__":
    # Anchor CWD to the script's own directory so relative paths always resolve
    # correctly regardless of where the script is invoked from.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(description="eXploitz's Ascent build script.")
    parser.add_argument("-gt", "--githubToken", default=os.environ.get("GITHUB_TOKEN"),
                        help="GitHub Token (defaults to $GITHUB_TOKEN)")
    parser.add_argument("-v", "--version", default=os.environ.get("RELEASE_VERSION"),
                        help="Override release version (defaults to $RELEASE_VERSION or version.json)")
    parser.add_argument("-p", "--package", default=None,
                        help="Build a specific package only (e.g. minimal, normal, advanced)")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip downloading assets if already present in base/")
    args = parser.parse_args()

    if not args.githubToken and not args.skip_download:
        parser.error("A GitHub token is required. Pass -gt/--githubToken or set GITHUB_TOKEN.")

    # Load version
    if args.version:
        releaseVersion = args.version
    else:
        with open("./version.json", "r", encoding="utf-8") as f:
            version = json.load(f)
            releaseVersion = version["releaseVersion"]

    # Load settings
    with open("./settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)

    # Filter packages
    packages_to_build = [
        p for p in settings.get("packages", [])
        if p.get("active", False) and (args.package is None or p["name"] == args.package)
    ]

    if not packages_to_build:
        raise SystemExit(
            f"No active packages found to build" + (f" for '{args.package}'" if args.package else "")
        )

    # Deduplicate modules across target packages while preserving order
    neededModules = list(dict.fromkeys(
        module
        for package in packages_to_build
        for module in package.get("modules", [])
    ))

    # Validate that every referenced module exists in moduleList
    for name in neededModules:
        if name not in settings.get("moduleList", {}):
            raise SystemExit(f"Package references unknown module: {name}")

    sdcard = FS()
    if not args.skip_download:
        sdcard.clean()
        github = GH(args.githubToken, base_dir=sdcard.base)
        for i in neededModules:
            module = settings["moduleList"][i]
            if not github.downloadReleaseAssets(module):
                raise SystemExit(f"Failed to download assets for: {module['repo']}")
    else:
        logger.info("Skipping asset download (--skip-download enabled)")

    for package in packages_to_build:
        pkg_name = package["name"]
        logger.info(f"[{pkg_name}] Creating package")
        sdcard.createSDEnv()

        for i in package["modules"]:
            module = settings["moduleList"][i]
            logger.info(f"[{pkg_name}][{module['repo']}] Creating module env")
            sdcard.createModuleEnv(module)
            for step in module.get("steps", []):
                logger.info(f"[{pkg_name}][{module['repo']}] Executing step: {step['name']}")
                sdcard.executeStep(module, step)

            logger.info(f"[{pkg_name}][{module['repo']}] Moving MENV to SD")
            sdcard.finishModule()

        # Validate that files were actually written to the SD environment
        if not any(Path("./sd").iterdir()):
            raise SystemExit(f"[{pkg_name}] SD card environment is empty. Aborting ZIP creation.")

        logger.info(f"[{pkg_name}] All modules processed.")
        logger.info(f"[{pkg_name}] Creating ASCENT file in atmosphere folder")
        sdcard.createAscentFile(releaseVersion, pkg_name)
        archive_name = f"ascent-{pkg_name}_v{releaseVersion}"
        logger.info(f"[{pkg_name}] Creating ZIP: {archive_name}.zip")
        try:
            shutil.make_archive(archive_name, "zip", "./sd")
        except OSError:
            logger.exception(f"[{pkg_name}] Failed to create ZIP archive")
            raise SystemExit(f"ZIP creation failed for package: {pkg_name}")

    logger.info("Build completed successfully.")
