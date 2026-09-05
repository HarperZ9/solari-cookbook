"""Optional Index adapter. Analyze only explicitly selected source files."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile


def _sources(root, files):
    if not files or len(files) > 64:
        raise ValueError("Select between 1 and 64 owned source files")
    sources = {}
    for name in files:
        relative = PurePosixPath(name.replace("\\", "/"))
        if (relative.is_absolute() or PureWindowsPath(name).drive
                or ".." in relative.parts or relative.suffix != ".py"):
            raise ValueError("Source allowlist requires relative Python file paths")
        path = root.joinpath(*relative.parts)
        if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
            raise ValueError("Symlinked sources are not allowed")
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError("Source must be a file inside the supplied root")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Source exceeds the 2 MiB inspection limit")
        if str(relative) in sources:
            raise ValueError("Source allowlist contains duplicates")
        sources[str(relative)] = path.read_bytes()
    return sources


def inspect_sources(root: Path, files: list[str], query: str) -> dict:
    """Use installed Index without vendoring or scanning the wider workspace.

    Index remains an external FSL-1.1-MIT dependency. This adapter neither
    executes sources nor sends their contents to a model or remote service.
    """
    sources = _sources(Path(root).resolve(strict=True), files)
    try:
        from index_graph.symbols import build_symbol_navigator, find_definitions, find_references
    except ImportError as error:
        raise RuntimeError("Source inspection needs the optional index-graph package") from error
    try:
        package_version = version("index-graph")
    except PackageNotFoundError:
        package_version = "unknown"
    with tempfile.TemporaryDirectory(prefix="rd-lab-index-") as temporary:
        staging = Path(temporary)
        for name, content in sources.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        graph, _ = build_symbol_navigator(staging, repo_name="rd-lab-selected-source")
        return {"schema": "rd-lab.inspection/v1", "tool": "index-graph",
                "distribution_version": package_version,
                "source_files": list(sources), "query": query,
                "definitions": find_definitions(graph, query),
                "references": find_references(graph, query),
                "limitations": ["Static source navigation, not runtime behavior or repair correctness.",
                                "Distribution metadata may lag an editable installation."]}
