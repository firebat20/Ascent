import logging
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FS:
    def __init__(self, root_dir: Path | str = ".") -> None:
        self.root = Path(root_dir).resolve()
        self.base = self.root / "base"
        self.menv = self.root / "menv"
        self.sd = self.root / "sd"

    def clean(self) -> None:
        """Remove build artifacts from previous runs.

        Call this explicitly before starting a build rather than relying on
        constructor side-effects, so that importing or instantiating FS for
        testing or scripting is safe.
        """
        for d in (self.base, self.menv, self.sd):
            shutil.rmtree(d, ignore_errors=True)
        for element in self.root.glob("*.zip"):
            try:
                element.unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Could not remove {element}: {e}")

    def createSDEnv(self) -> None:
        shutil.rmtree(self.sd, ignore_errors=True)
        self.sd.mkdir(parents=True, exist_ok=True)

    def createModuleEnv(self, module: dict[str, Any]) -> None:
        shutil.rmtree(self.menv, ignore_errors=True)
        self.menv.mkdir(parents=True, exist_ok=True)
        src = self.base / module["repo"]
        if src.exists():
            shutil.copytree(src, self.menv, dirs_exist_ok=True)
        else:
            raise FileNotFoundError(f"Module base source does not exist: {src}")

    def finishModule(self) -> None:
        self._copy_to_sd()
        shutil.rmtree(self.menv, ignore_errors=True)

    def executeStep(self, module: dict[str, Any], step: dict[str, Any]) -> None:
        name = step.get("name")
        args = step.get("arguments", [])
        expected_args = {
            "extract": 1,
            "create_dir": 1,
            "create_file": 2,
            "replace_content": 3,
            "delete": 1,
            "copy": 2,
            "move": 2,
        }

        if name not in expected_args:
            raise ValueError(f"[{module.get('repo')}] Unknown step action: '{name}'")
        if len(args) != expected_args[name]:
            raise ValueError(
                f"[{module.get('repo')}] Step '{name}' expected {expected_args[name]} arguments, got {len(args)}"
            )

        if name == "extract":
            self._extract(args[0])
        elif name == "create_dir":
            self._create_dir(args[0])
        elif name == "create_file":
            self._create_file(args[0], args[1])
        elif name == "replace_content":
            self._replace_file_content(args[0], args[1], args[2])
        elif name == "delete":
            self._delete(args[0])
        elif name == "copy":
            self._copy(args[0], args[1])
        elif name == "move":
            self._move(args[0], args[1])

    def _resolve_menv_path(self, rel_path: str) -> Path:
        """Resolve a relative path inside menv, rejecting traversal or absolute paths."""
        if Path(rel_path).is_absolute():
            raise ValueError(f"Absolute path not allowed in module environment: {rel_path}")
        base = self.menv.resolve()
        target = (base / rel_path).resolve()
        if not target.is_relative_to(base):
            raise ValueError(f"Path escapes module environment: {rel_path}")
        return target

    def _glob_menv(self, pattern: str) -> list[Path]:
        """Glob relative to menv while ensuring all matches stay inside menv."""
        if Path(pattern).is_absolute():
            raise ValueError(f"Absolute path not allowed in glob pattern: {pattern}")
        base = self.menv.resolve()
        matches: list[Path] = []
        for match in self.menv.glob(pattern):
            resolved = match.resolve()
            if not resolved.is_relative_to(base):
                raise ValueError(f"Glob match escapes module environment: {match}")
            matches.append(resolved)
        return matches

    def _extract(self, source: str) -> None:
        try:
            pattern = re.compile(source)
        except re.error as e:
            raise ValueError(f"Invalid archive regex pattern '{source}': {e}") from e

        archives = [
            entry
            for entry in self.menv.iterdir()
            if entry.is_file() and pattern.search(entry.name)
        ]
        if not archives:
            raise FileNotFoundError(f"No archive matching '{source}' found to extract in {self.menv}")

        for archive_path in archives:
            if not zipfile.is_zipfile(archive_path):
                raise ValueError(
                    f"Unsupported archive format: {archive_path.name}. Only .zip files are supported."
                )
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                for member in zip_ref.infolist():
                    if self._is_unsafe_zip_path(self.menv, member.filename):
                        raise ValueError(f"Blocked unsafe path in {archive_path.name}: {member.filename}")
                zip_ref.extractall(self.menv)
            archive_path.unlink(missing_ok=True)

    def _is_unsafe_zip_path(self, base_dir: Path, member: str) -> bool:
        base = base_dir.resolve()
        target = (base / member).resolve()
        return not target.is_relative_to(base)

    def _remove_path(self, path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink(missing_ok=True)

    def _delete(self, source: str) -> None:
        full = self._resolve_menv_path(source)
        if full.exists():
            self._remove_path(full)
        else:
            for match in self._glob_menv(source):
                self._remove_path(match)

    def _copy_matches(self, matches: list[Path], target_path: Path, source_label: str, dest_label: str) -> None:
        if len(matches) > 1:
            if target_path.exists() and not target_path.is_dir():
                raise ValueError(
                    f"Multiple sources matched '{source_label}' for non-directory destination '{dest_label}'"
                )
            if not target_path.exists():
                raise ValueError(
                    f"Multiple sources matched '{source_label}'; destination '{dest_label}' must be an existing directory"
                )

        for element in matches:
            if element.is_dir():
                if target_path.exists() and not target_path.is_dir():
                    raise FileExistsError(f"Destination exists and is not a directory: {target_path}")
                target_path.mkdir(parents=True, exist_ok=True)
                shutil.copytree(element, target_path, dirs_exist_ok=True)
            else:
                if target_path.is_dir():
                    dest_file = target_path / element.name
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_file = target_path
                shutil.copy2(element, dest_file)

    def _copy(self, source: str, dest: str) -> None:
        matches = self._glob_menv(source)
        if not matches:
            raise FileNotFoundError(f"Copy source '{source}' matched no files in {self.menv}")
        target_path = self._resolve_menv_path(dest)
        self._copy_matches(matches, target_path, source, dest)

    def _move(self, source: str, dest: str) -> None:
        matches = self._glob_menv(source)
        if not matches:
            raise FileNotFoundError(f"Move source '{source}' matched no files in {self.menv}")
        target_path = self._resolve_menv_path(dest)

        for element in matches:
            if target_path == element:
                return
            if element.is_dir() and target_path.is_relative_to(element):
                raise ValueError(f"Cannot move directory '{source}' into itself ('{dest}')")

        self._copy_matches(matches, target_path, source, dest)
        for element in matches:
            self._remove_path(element)

    def _create_dir(self, source: str) -> None:
        self._resolve_menv_path(source).mkdir(parents=True, exist_ok=True)

    def _create_file(self, source: str, content: str) -> None:
        file_path = self._resolve_menv_path(source)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def _replace_file_content(self, source: str, search: str, replace: str) -> None:
        if not search:
            raise ValueError("Search string for replace_content cannot be empty")
        file_path = self._resolve_menv_path(source)
        if not file_path.is_file():
            raise FileNotFoundError(f"Target file for replacement not found: {file_path}")

        data = file_path.read_text(encoding="utf-8")
        if search not in data:
            logger.warning(f"Replace target '{search}' not found in {source}. File unchanged.")
            return

        data = data.replace(search, replace)
        file_path.write_text(data, encoding="utf-8")

    def _copy_to_sd(self) -> None:
        if self.menv.exists():
            shutil.copytree(self.menv, self.sd, dirs_exist_ok=True)

    def createAscentFile(self, releaseVersion: str, packageName: str) -> None:
        ascent_dir = self.sd / "atmosphere"
        ascent_dir.mkdir(parents=True, exist_ok=True)
        (ascent_dir / "ASCENT").write_text(f"{releaseVersion} - {packageName}", encoding="utf-8")
