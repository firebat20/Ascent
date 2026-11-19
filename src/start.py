import argparse
import json
import logging
import os
import shutil

from fs import FS
from gh import GH

logging.basicConfig(format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logging.getLogger().setLevel(logging.INFO)

if __name__ == '__main__':
    # Anchor CWD to the script's own directory so relative paths always resolve
    # correctly regardless of where the script is invoked from.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(description="eXploitz's Ascent build script.")
    requiredNamed = parser.add_argument_group('Options required to build a release candidate')
    requiredNamed.add_argument('-gt', '--githubToken', default=os.environ.get('GITHUB_TOKEN'),
                               help='Github Token (defaults to $GITHUB_TOKEN)')
    args = parser.parse_args()

    if not args.githubToken:
        parser.error("A GitHub token is required. Pass -gt/--githubToken or set GITHUB_TOKEN.")

    sdcard = FS()
    sdcard.clean()
    github = GH(args.githubToken)

    with open('./settings.json', 'r') as f:
        settings = json.load(f)

    with open('./version.json', 'r') as f:
        version = json.load(f)
        releaseVersion = version['releaseVersion']

    # Deduplicate modules across active packages while preserving order
    neededModules = list(dict.fromkeys(
        module
        for package in settings["packages"] if package["active"]
        for module in package["modules"]
    ))

    # Validate that every referenced module exists in moduleList
    for name in neededModules:
        if name not in settings["moduleList"]:
            raise SystemExit(f"Package references unknown module: {name}")

    for i in neededModules:
        module = settings["moduleList"][i]
        if not github.downloadReleaseAssets(module):
            raise SystemExit(f"Failed to download assets for: {module['repo']}")

    for package in settings["packages"]:
        if package["active"]:
            logging.info(f"[{package['name']}] Creating package")
            sdcard.createSDEnv()

            for i in package["modules"]:
                module = settings["moduleList"][i]
                logging.info(f"[{package['name']}][{module['repo']}] Creating module env")
                sdcard.createModuleEnv(module)
                for step in module["steps"]:
                    logging.info(f"[{package['name']}][{module['repo']}] Executing step: {step['name']}")
                    sdcard.executeStep(module, step)

                logging.info(f"[{package['name']}][{module['repo']}] Moving MENV to SD")
                sdcard.finishModule()

            logging.info(f"[{package['name']}] All modules processed.")
            logging.info(f"[{package['name']}] Creating ASCENT file in atmosphere folder")
            sdcard.createAscentFile(releaseVersion, package['name'])
            logging.info(f"[{package['name']}] Creating ZIP")
            try:
                shutil.make_archive(f"ascent-{package['name']}_v{releaseVersion}", 'zip', "./sd")
            except OSError:
                logging.exception(f"[{package['name']}] Failed to create ZIP archive")
                raise SystemExit(f"ZIP creation failed for package: {package['name']}")
