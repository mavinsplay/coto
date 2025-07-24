__all__ = ["get_bool_env"]


def get_bool_env(value):
    enabled_values = ("true", "t", "yes", "y", "1")
    return value.lower() in enabled_values
