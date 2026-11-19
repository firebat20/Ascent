import glob
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any


class FS:
    def __init__(self) -> None:
        pass

    def clean(self) -> None:
        """Remove build artifacts from previous runs.

        Call this explicitly before starting a build rather than relying on
        constructor side-effects, so that importing or instantiating FS for
        testing or scripting is safe.
        """
        shutil.rmtree("./base", ignore_errors=True)
        shutil.rmtree("./menv", ignore_errors=True)
        shutil.rmtree("./sd", ignore_errors=True)
        for element in glob.glob("./*.zip"):
            os.remove(element)

    def createSDEnv(self) -> None:
        shutil.rmtree("./sd", ignore_errors=True)
        Path("./sd").mkdir(parents=True, exist_ok=True)

    def createModuleEnv(self, module: dict[str, Any]) -> None:
        shutil.rmtree("./menv", ignore_errors=True)
        Path("./menv").mkdir(parents=True, exist_ok=True)
        shutil.copytree(f"./base/{module['repo']}", "./menv/", dirs_exist_ok=True)

    def finishModule(self) -> None:
        self.__copyToSD()
        shutil.rmtree("./menv", ignore_errors=True)

    def executeStep(self, module: dict[str, Any], step: dict[str, Any]) -> None:
        name = step["name"]
        args = step["arguments"]

        if name == "extract":
            self.__extract(args[0])
        elif name == "create_dir":
            self.__createDir(args[0])
        elif name == "create_file":
            self.__createFile(args[0], args[1])
        elif name == "replace_content":
            self.__replaceFileContent(args[0], args[1], args[2])
        elif name == "delete":
            self.__delete(args[0])
        elif name == "copy":
            self.__copy(args[0], args[1])
        elif name == "move":
            self.__copy(args[0], args[1])
            self.__delete(args[0])
        else:
            logging.warning(f"Unknown step: {name}")

    def __extract(self, source: str) -> None:
        path = "./menv/"
        for filename in os.listdir(path):
            if re.search(source, filename):
                assetPath = f"./menv/{filename}"
                if zipfile.is_zipfile(assetPath):
                    with zipfile.ZipFile(assetPath, 'r') as zip_ref:
                        for member in zip_ref.infolist():
                            if self.__isUnsafeZipPath(path, member.filename):
                                raise ValueError(f"Blocked unsafe path in {filename}: {member.filename}")
                        zip_ref.extractall(path)
                else:
                    raise ValueError(
                        f"Unsupported archive format: {filename}. Only .zip files are supported."
                    )
                self.__delete(filename)

    def __isUnsafeZipPath(self, baseDir: str, member: str) -> bool:
        base = os.path.realpath(baseDir)
        target = os.path.realpath(os.path.join(base, member))
        try:
            return os.path.commonpath([base, target]) != base
        except ValueError:
            return True

    def __delete(self, source: str) -> None:
        full = f"./menv/{source}"
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
        elif os.path.exists(full):
            os.remove(full)

    def __copy(self, source: str, dest: str) -> None:
        for element in glob.glob(f"./menv/{source}"):
            if os.path.isdir(element):
                shutil.copytree(element, f"./menv/{dest}", dirs_exist_ok=True)
            elif os.path.exists(element):
                shutil.copy(element, f"./menv/{dest}")
            break  # Only process the first glob match

    def __createDir(self, source: str) -> None:
        Path(f"./menv/{source}").mkdir(parents=True, exist_ok=True)

    def __createFile(self, source: str, content: str) -> None:
        with open(f"./menv/{source}", "w") as f:
            f.write(content)

    def __replaceFileContent(self, source: str, search: str, replace: str) -> None:
        with open(f"./menv/{source}", "rt") as fin:
            data = fin.read()
        data = data.replace(search, replace)
        with open(f"./menv/{source}", "wt") as fout:
            fout.write(data)

    def __copyToSD(self) -> None:
        shutil.copytree("./menv", "./sd/", dirs_exist_ok=True)

    def createAscentFile(self, releaseVersion: str, packageName: str) -> None:
        Path("./sd/atmosphere").mkdir(parents=True, exist_ok=True)
        with open("./sd/atmosphere/ASCENT", "w") as f:
            f.write(f"{releaseVersion} - {packageName}")
