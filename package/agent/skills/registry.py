from package.agent.skills.contracts import Skill


class SkillRegistry:
    def __init__(self, skills: list[Skill] | None = None) -> None:
        self._skills = {skill.name: skill for skill in skills or []}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {name}") from exc

    def all(self) -> tuple[Skill, ...]:
        return tuple(self._skills.values())
