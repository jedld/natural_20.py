from natural20.action import Action


def _ref(value):
    """Entity -> entity_uid; lists recurse; other non-plain values -> str."""
    if hasattr(value, 'entity_uid'):
        return value.entity_uid
    if isinstance(value, (list, tuple)):
        return [_ref(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class ActionRecord(Action):
    """Saved stand-in for a ``battle_log`` action whose class has no YAML
    form. Keeps what log readers use: actor, target, type and description."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.action_class = None
        self.description = None

    @staticmethod
    def from_action(action):
        record = ActionRecord(None, getattr(action, 'source', None), getattr(action, 'action_type', None))
        record.target = getattr(action, 'target', None)
        record.action_class = f"{type(action).__module__}.{type(action).__qualname__}"
        record.legendary_action = bool(getattr(action, 'legendary_action', False))
        try:
            record.description = str(action)
        except Exception:
            record.description = record.action_type
        return record

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'action_class': self.action_class,
            'source': _ref(self.source),
            'target': _ref(self.target),
            'description': self.description,
            'legendary_action': bool(self.legendary_action),
        }

    @staticmethod
    def from_dict(data):
        record = ActionRecord(data.get('session'), data.get('source'), data.get('action_type'))
        record.target = data.get('target')
        record.action_class = data.get('action_class')
        record.description = data.get('description')
        record.legendary_action = bool(data.get('legendary_action'))
        return record

    def __str__(self):
        return self.description or str(self.action_type)

    def __repr__(self):
        return self.__str__()
