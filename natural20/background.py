"""
Background support for 5e 2014 player characters.

A Background provides skill proficiencies, tool proficiencies,
language options, a background feature, and starting equipment.
"""

from natural20.serializable_object import SerializableObject


class Background(SerializableObject):
    """Represents a 5e background loaded from YAML.

    Fields (from YAML):
      name: Display name.
      label: Short label for UI.
      description: Flavor text.
      skill_proficiencies: List of skill names (proficient by default).
      tool_proficiencies: List of tool kit names.
      languages: Optional list of fixed languages.
      languages_pool: Pool of languages the player may choose from.
      language_count: Total languages granted (including fixed).
      language_choice_count: How many the player may choose from the pool.
      feature: Dict with ``name`` and ``description`` for the background feature.
      equipment: List of starting equipment items.
    """

    def __init__(self, data: dict):
        self.name = data.get('name', '')
        self.label = data.get('label', self.name)
        self.description = data.get('description', '')
        self.skill_proficiencies: list[str] = list(data.get('skill_proficiencies', []))
        self.tool_proficiencies: list[str] = list(data.get('tool_proficiencies', []))
        self.languages: list[str] = list(data.get('languages', []))
        self.languages_pool: list[str] = list(data.get('languages_pool', []))
        self.language_count: int = int(data.get('language_count', 0))
        self.language_choice_count: int = int(data.get('language_choice_count', 0))
        self.feature: dict = data.get('feature', {})
        self.equipment: list = list(data.get('equipment', []))
        self._raw = data

    # -- Convenience accessors ------------------------------------------------

    def get_feature_name(self) -> str:
        return self.feature.get('name', '') if self.feature else ''

    def get_feature_description(self) -> str:
        return self.feature.get('description', '') if self.feature else ''

    def has_language_choices(self) -> bool:
        return self.language_choice_count > 0 and bool(self.languages_pool)

    def to_dict(self) -> dict:
        """Serialize back to a plain dict (for YAML save / JSON API)."""
        return {
            'name': self.name,
            'label': self.label,
            'description': self.description,
            'skill_proficiencies': self.skill_proficiencies,
            'tool_proficiencies': self.tool_proficiencies,
            'languages': self.languages,
            'languages_pool': self.languages_pool,
            'language_count': self.language_count,
            'language_choice_count': self.language_choice_count,
            'feature': self.feature,
            'equipment': self.equipment,
        }

    @classmethod
    def from_yaml(cls, data: dict) -> 'Background':
        return cls(data)


# De-serialization hook for Session save/load.
def _deserialize_background(data):
    if isinstance(data, Background):
        return data
    if isinstance(data, dict):
        return Background(data)
    return data
