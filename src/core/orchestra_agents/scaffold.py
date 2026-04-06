"""Scaffold a new agent directory from the bundled template."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

_LOG = logging.getLogger(__name__)

DEFAULT_TEMPLATE_NAME = "agent"


@dataclass(frozen=True)
class ScaffoldOptions:
    display_name: str | None = None
    backend_type: str = "example"
    template: str = DEFAULT_TEMPLATE_NAME
    force: bool = False


class _TemplateRenderer:
    @staticmethod
    def template_root(template_name: str = DEFAULT_TEMPLATE_NAME) -> Path:
        normalized = str(template_name or DEFAULT_TEMPLATE_NAME).strip() or DEFAULT_TEMPLATE_NAME
        root = Path(__file__).resolve().parent / "templates" / normalized
        if not root.exists() or not root.is_dir():
            raise ValueError(f"unknown template: {normalized}")
        return root

    @staticmethod
    def build_replacements(slug: str, options: ScaffoldOptions) -> dict[str, str]:
        return {
            "__AGENT_SLUG__": slug,
            "__AGENT_DISPLAY_NAME__": options.display_name or slug.replace("_", " ").title(),
            "__BACKEND_TYPE__": str(options.backend_type).strip() or "example",
        }

    @classmethod
    def copy_template(
        cls, template_root: Path, target_root: Path, replacements: dict[str, str]
    ) -> None:
        for source in template_root.rglob("*"):
            if source.is_dir() or "__pycache__" in source.parts or source.suffix == ".pyc":
                continue
            target = target_root / source.relative_to(template_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            text = source.read_text(encoding="utf-8")
            for placeholder, replacement in replacements.items():
                text = text.replace(placeholder, replacement)
            target.write_text(text, encoding="utf-8")


def scaffold_agent(
    *,
    slug: str,
    output_dir: str | Path,
    options: ScaffoldOptions | None = None,
) -> Path:
    """Create a new agent directory from the bundled template."""
    normalized_slug = str(slug).strip()
    if not normalized_slug:
        raise ValueError("slug is required")
    resolved_options = options or ScaffoldOptions()
    target_root = Path(output_dir).expanduser().resolve()
    if target_root.exists() and any(target_root.iterdir()) and not resolved_options.force:
        raise ValueError(f"target directory already exists and is not empty: {target_root}")
    target_root.mkdir(parents=True, exist_ok=True)
    replacements = _TemplateRenderer.build_replacements(normalized_slug, resolved_options)
    _TemplateRenderer.copy_template(
        _TemplateRenderer.template_root(resolved_options.template),
        target_root,
        replacements,
    )
    return target_root


def _build_arg_parser() -> argparse.ArgumentParser:
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
    args = _build_arg_parser().parse_args()
    result = scaffold_agent(
        slug=args.slug,
        output_dir=args.output_dir,
        options=ScaffoldOptions(
            display_name=args.display_name,
            backend_type=args.backend_type,
            template=args.template,
            force=args.force,
        ),
    )
    _LOG.info("Scaffolded agent at %s", result)


if __name__ == "__main__":
    main()
