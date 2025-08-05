class SerializableObject:
    """
    Base class for objects that can be serialized to and from YAML.
    """
    def serialize(self) -> dict:
        def resolve_value(attr, value):
            if isinstance(value, list):
                return [resolve_value(attr, item) for item in value]
            elif isinstance(value, dict):
                return {k: resolve_value(f"{attr}.{k}", v) for k, v in value.items()}
            elif hasattr(value, 'to_dict'):
                return value.to_dict()
            elif isinstance(value, str):
                return value
            elif isinstance(value, int):
                return value
            elif isinstance(value, float):
                return value
            elif isinstance(value, bool):
                return value
            elif value is None:
                return None
            else:
                raise ValueError(f"Unsupported type for serialization: {attr}: {type(value)}")

        output_dict = {}
        for attr in self.__dict__:
            # skip private attributes and methods
            if attr.startswith('_') or callable(getattr(self, attr)):
                continue

            if self.__dict__[attr] is None:
                continue
            output_dict[attr] = resolve_value(attr, self.__dict__[attr])
        return output_dict

    def to_yaml(self) -> str:
        """
        Convert the serialized object to a YAML string.
        """
        import yaml
        return yaml.dump(self.serialize(), default_flow_style=False, sort_keys=False)

    @classmethod
    def deserialize(cls, data):
        """
        Deserialize the object from a dictionary.
        """
        for attr, value in data.items():
            if isinstance(value, str):
                setattr(cls, attr, value)
        return cls