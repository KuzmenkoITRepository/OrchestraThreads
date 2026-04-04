"""Scaffold a new agent directory from the bundled template."""

from __future__ import annotations

import argparse
from pathlib import Path

PLACEHOLDERS = {
    "__AGENT_SLUG__": "",
    "__AGENT_DISPLAY_NAME__": "",
    "__BACKEND_TYPE__": "example",
}
DEFAULT_TEMPLATE_NAME = "agent"


def _template_root(template_name: str = DEFAULT_TEMPLATE_NAME) -> Path:
    normalized = str(template_name or DEFAULT_TEMPLATE_NAME).strip() or DEFAULT_TEMPLATE_NAME
    root = Path(__file__).resolve().parent / "templates" / normalized
    if not root.exists() or not root.is_dir():
        raise ValueError(f"unknown template: {normalized}")
    return root


def scaffold_agent(
    *,
    slug: str,
    output_dir: str | Path,
    display_name: str | None = None,
    backend_type: str = "example",
    template: str = DEFAULT_TEMPLATE_NAME,
    force: bool = False,
) -> Path:
    normalized_slug = str(slug).strip()
    if not normalized_slug:
        raise ValueError("slug is required")
    target_root = Path(output_dir).expanduser().resolve()
    if target_root.exists() and any(target_root.iterdir()) and not force:
        raise ValueError(f"target directory already exists and is not empty: {target_root}")
    target_root.mkdir(parents=True, exist_ok=True)

    replacements = dict(PLACEHOLDERS)
    replacements["__AGENT_SLUG__"] = normalized_slug
    replacements["__AGENT_DISPLAY_NAME__"] = (
        display_name or normalized_slug.replace("_", " ").title()
    )
    replacements["__BACKEND_TYPE__"] = str(backend_type).strip() or "example"

    template_root = _template_root(template)
    for source_path in template_root.rglob("*"):
        if source_path.is_dir():
            continue
        if "__pycache__" in source_path.parts or source_path.suffix == ".pyc":
            continue
        relative_path = source_path.relative_to(template_root)
        target_path = target_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        text = source_path.read_text(encoding="utf-8")
        for placeholder, replacement in replacements.items():
            text = text.replace(placeholder, replacement)
        target_path.write_text(text, encoding="utf-8")
    return target_root


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold a new Orchestra agent directory.")
    parser.add_argument("--slug", required=True, help="Agent slug, for example coding_agent.")
    parser.add_argument(
        "--output-dir", required=True, help="Where to write the new agent directory."
    )
    parser.add_argument("--display-name", help="Optional human-friendly display name.")
    parser.add_argument(
        "--backend-type", default="example", help="Backend type written into manifest and runtime."
    )
    parser.add_argument(
        "--template",
        default=DEFAULT_TEMPLATE_NAME,
        choices=["agent", "agent_mux"],
        help="Template root under src/core/orchestra_agents/templates.",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing non-empty directory."
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    path = scaffold_agent(
        slug=args.slug,
        output_dir=args.output_dir,
        display_name=args.display_name,
        backend_type=args.backend_type,
        template=args.template,
        force=args.force,
    )
    print(path)


if __name__ == "__main__":
    main()
