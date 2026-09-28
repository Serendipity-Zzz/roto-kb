from .app import create_app

__all__ = ["create_app"]

def __getattr__(name: str):
    if name == "app":
        from .app import app as _app
        return _app
    raise AttributeError(name)
