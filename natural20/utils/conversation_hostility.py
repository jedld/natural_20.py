"""Shared LLM prompt hints for NPC hostility escalation during conversation."""

HOSTILITY_ESCALATION_HINT = (
    "If the situation escalates and your character would attack (for example you are "
    "a guard who caught a thief, or you draw steel), include [GO_HOSTILE] in your "
    "response; the server will make you hostile and may trigger combat. "
    "Omit [GO_HOSTILE] if you only warn, negotiate, stay silent, or look away."
)
