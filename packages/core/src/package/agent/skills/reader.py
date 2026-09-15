import asyncio
from dataclasses import dataclass, field
from pathlib import Path


SKILL_SEPARATOR = "-----------------------------------------------------"
SKILL_FILENAME = "SKILL.md"


@dataclass(frozen=True, slots=True)
class FileSkill:
    name: str
    description: str
    path: Path
    _reader: "SkillReader" = field(repr=False, compare=False)

    async def load(self) -> str:
        return await self._reader.load_body(self.path)


class SkillReader:
    """Discovers skill metadata eagerly and loads instructions only on demand."""

    def discover(self, root: Path) -> tuple[FileSkill, ...]:
        if not root.exists():
            raise FileNotFoundError(f"Skill directory does not exist: {root}")
        skills = [self.read(path) for path in sorted(root.glob(f"*/{SKILL_FILENAME}"))]
        return tuple(skills)

    def read(self, path: Path) -> FileSkill:
        metadata = self._read_metadata(path)
        return FileSkill(
            name=metadata["name"],
            description=metadata["description"],
            path=path,
            _reader=self,
        )

    async def load_body(self, path: Path) -> str:
        return await asyncio.to_thread(self._read_body, path)

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, str]:
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline().strip()
            if first != SKILL_SEPARATOR:
                raise ValueError(f"Skill file must start with {SKILL_SEPARATOR!r}: {path}")

            metadata: dict[str, str] = {}
            for raw_line in handle:
                line = raw_line.strip()
                if line == SKILL_SEPARATOR:
                    break
                if not line:
                    continue
                key, separator, value = line.partition(":")
                if not separator:
                    raise ValueError(
                        f"Invalid skill metadata line {line!r} in {path}; expected 'key: value'"
                    )
                normalized_key = key.strip().casefold()
                if normalized_key not in {"name", "description"}:
                    raise ValueError(f"Unsupported skill metadata field {key.strip()!r} in {path}")
                normalized_value = value.strip()
                if not normalized_value:
                    raise ValueError(
                        f"Skill metadata field {normalized_key!r} cannot be empty in {path}"
                    )
                metadata[normalized_key] = normalized_value
            else:
                raise ValueError(f"Skill metadata closing separator not found: {path}")

        missing = {"name", "description"} - metadata.keys()
        if missing:
            raise ValueError(
                f"Skill metadata missing required fields {sorted(missing)!r} in {path}"
            )
        return metadata

    @staticmethod
    def _read_body(path: Path) -> str:
        with path.open("r", encoding="utf-8") as handle:
            if handle.readline().strip() != SKILL_SEPARATOR:
                raise ValueError(f"Invalid skill header: {path}")
            for raw_line in handle:
                if raw_line.strip() == SKILL_SEPARATOR:
                    break
            else:
                raise ValueError(f"Skill metadata closing separator not found: {path}")
            body = handle.read().strip()

        if not body:
            raise ValueError(f"Skill body cannot be empty: {path}")
        return body
