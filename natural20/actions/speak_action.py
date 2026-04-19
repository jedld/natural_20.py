from natural20.action import Action


class SpeakAction(Action):
    """
    A free action that allows an entity to speak to nearby entities.
    Speaking does not consume any action economy resources (action, bonus action, movement).
    In D&D 5e, speaking is considered a free action that can be done on your turn.
    """

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts or {})
        self.message = opts.get('message', '') if opts else ''
        self.language = opts.get('language', 'common') if opts else 'common'
        self.targets = opts.get('targets', None) if opts else None
        self.distance_ft = opts.get('distance_ft', 30) if opts else 30

    @staticmethod
    def can(entity, battle, options=None):
        """Speaking is always available if the entity can speak (is conversable)."""
        if not entity.conversable():
            return False
        return True

    def __repr__(self) -> str:
        if self.targets:
            target_names = ", ".join(getattr(t, 'name', str(t)) for t in self.targets)
            return f"Speak(to {target_names}: \"{self.message[:30]}{'...' if len(self.message) > 30 else ''}\")"
        return f"Speak(\"{self.message[:30]}{'...' if len(self.message) > 30 else ''}\")"

    def build_map(self):
        return self

    @staticmethod
    def build(session, source, opts=None):
        action = SpeakAction(session, source, "speak", opts)
        return action.build_map()

    def resolve(self, session, map, opts=None):
        if opts is None:
            opts = {}
        self.result = [{
            "source": self.source,
            "type": "speak",
            "message": self.message,
            "language": self.language,
            "targets": self.targets,
            "distance_ft": self.distance_ft,
            "map": map,
            "battle": opts.get("battle"),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None and battle is not None:
            session = battle.session
        if item["type"] == "speak":
            source = item["source"]
            message = item["message"]
            language = item.get("language", "common")
            targets = item.get("targets")
            distance_ft = item.get("distance_ft", 30)

            # Use the entity's send_conversation method to broadcast
            processed = source.send_conversation(
                message, distance_ft=distance_ft, targets=targets, language=language
            )

            if session:
                session.event_manager.received_event({
                    "source": source,
                    "event": "speak",
                    "message": message,
                    "language": language,
                    "targets": targets,
                    "processed_conversations": processed,
                })
            # Speaking is a free action - no resource consumption
