import importlib.metadata
import pathlib

def _get_version():
    # Check pyproject.toml in case local editable install
    try:
        import tomllib
        
        # Locate pyproject.toml relative to this file (src/depot/__init__.py)
        pyproject_path = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                return data.get("project", {}).get("version", "unknown")
    except Exception:
        pass
    
    # Fallback to version at last install time
    try:
        return importlib.metadata.version("depot")
    except importlib.metadata.PackageNotFoundError:
        pass

    return "unknown"

__version__ = _get_version()
