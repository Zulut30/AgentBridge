from pathlib import Path


class ProjectContext:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def exists(self) -> bool:
        return self.root.exists() and self.root.is_dir()

    def describe(self) -> str:
        return f"Root: {self.root}"

