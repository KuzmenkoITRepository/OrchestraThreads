"""Scaffold a new agent directory from the bundled template."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScaffoldOptions:
    display_name: str | None = None
    backend_type: str = "example"
    template: str = "agent"
    force: bool = False


class _ScaffoldInputs:
    default_template_name = "agent"
    default_backend_type = "example"

    @staticmethod
    def normalized_template_name(template_name: str) -> str:
        return (
            str(template_name or _ScaffoldInputs.default_template_name).strip()
            or _ScaffoldInputs.default_template_name
        )

    @staticmethod
    def display_name(slug: str, options: ScaffoldOptions) -> str:
        return options.display_name or slug.replace("_", " ").title()

    @staticmethod
    def backend_type(options: ScaffoldOptions) -> str:
        return str(options.backend_type).strip() or _ScaffoldInputs.default_backend_type

    @staticmethod
    def normalized_slug(slug: str) -> str:
        normalized = str(slug).strip()
        if not normalized:
            raise ValueError("slug is required")
        return normalized

    @staticmethod
    def target_root(output_dir: str | Path) -> Path:
        return Path(output_dir).expanduser().resolve()

    @staticmethod
    def ensure_target_root(target_root: Path, *, force: bool) -> None:
        if target_root.exists() and any(target_root.iterdir()) and not force:
            raise ValueError(
                f"target directory already exists and is not empty: {target_root}",
            )
        target_root.mkdir(parents=True, exist_ok=True)


class _TemplateRenderer:
    skipped_template_parts = frozenset(("__pycache__", "agent_runtime"))

    @staticmethod
    def template_root(template_name: str = "agent") -> Path:
        normalized = _ScaffoldInputs.normalized_template_name(template_name)
        root = Path(__file__).resolve().parent / "templates" / normalized
        if not root.exists() or not root.is_dir():
            raise ValueError(f"unknown template: {normalized}")
        return root

    @staticmethod
    def build_replacements(slug: str, options: ScaffoldOptions) -> dict[str, str]:
        return {
            "__AGENT_SLUG__": slug,
            "__AGENT_DISPLAY_NAME__": _ScaffoldInputs.display_name(slug, options),
            "__BACKEND_TYPE__": _ScaffoldInputs.backend_type(options),
        }

    @classmethod
    def copy_template(
        cls, template_root: Path, target_root: Path, replacements: dict[str, str]
    ) -> None:
        for source in template_root.rglob("*"):
            if cls._should_skip(source):
                continue

            cls._copy_file(
                source=source,
                target_root=target_root,
                template_root=template_root,
                replacements=replacements,
            )

    @staticmethod
    def _should_skip(source: Path) -> bool:
        if source.is_dir() or source.suffix == ".pyc":
            return True
        return any(part in _TemplateRenderer.skipped_template_parts for part in source.parts)

    @staticmethod
    def _copy_file(
        *,
        source: Path,
        target_root: Path,
        template_root: Path,
        replacements: dict[str, str],
    ) -> None:
        target = target_root / source.relative_to(template_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = _TemplateRenderer._render_text(source, replacements)
        target.write_text(rendered, encoding="utf-8")

    @staticmethod
    def _render_text(source: Path, replacements: dict[str, str]) -> str:
        text = source.read_text(encoding="utf-8")
        for placeholder, replacement in replacements.items():
            text = text.replace(placeholder, replacement)
        return text


def scaffold_agent(
    *,
    slug: str,
    output_dir: str | Path,
    options: ScaffoldOptions | None = None,
) -> Path:
    """Create a new agent directory from the bundled template."""
    normalized_slug = _ScaffoldInputs.normalized_slug(slug)
    resolved_options = options or ScaffoldOptions()
    target_root = _ScaffoldInputs.target_root(output_dir)
    _ScaffoldInputs.ensure_target_root(target_root, force=resolved_options.force)
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
        default="agent",
        choices=["agent", "agent_mux", "opencode"],
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
