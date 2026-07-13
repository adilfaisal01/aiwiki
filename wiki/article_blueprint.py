"""Structured article blueprint matching the Gibson ES-335 wiki layout."""

from __future__ import annotations

import html
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

import core.security as security
from wiki.code_blocks import render_code_block
from wiki.helpers import slugify_heading


class InfoboxImage(BaseModel):
    src: str
    caption: str = ""
    alt: str = ""
    width: int | None = Field(default=None, ge=1, le=2000)


class InfoboxEntry(BaseModel):
    kind: Literal["section", "field", "full"]
    title: str | None = None
    label: str | None = None
    value: str | None = None

    @model_validator(mode="after")
    def validate_entry(self) -> InfoboxEntry:
        if self.kind == "section" and not (self.title or "").strip():
            raise ValueError("Infobox section entries require title")
        if self.kind == "field" and not (self.label or "").strip():
            raise ValueError("Infobox field entries require label")
        if self.kind in {"field", "full"} and not (self.value or "").strip():
            raise ValueError(f"Infobox {self.kind} entries require value")
        return self


class Infobox(BaseModel):
    title: str
    image: InfoboxImage | None = None
    rows: list[InfoboxEntry] = Field(default_factory=list)


class BlueprintThumb(BaseModel):
    src: str
    caption: str
    align: Literal["left", "right"] = "right"
    width: int | None = Field(default=None, ge=1, le=2000)
    alt: str = ""


class BlueprintCodeBlock(BaseModel):
    code: str
    language: str = ""


class BlueprintSection(BaseModel):
    title: str
    level: Literal[2, 3] = 2
    id: str | None = None
    paragraphs: list[str] = Field(default_factory=list)
    thumbs: list[BlueprintThumb] = Field(default_factory=list)
    code_blocks: list[BlueprintCodeBlock] = Field(default_factory=list)


class BlueprintLink(BaseModel):
    label: str
    href: str

    @model_validator(mode="after")
    def validate_href(self) -> BlueprintLink:
        if not self.href.startswith(("http://", "https://")):
            raise ValueError("href must use http or https")
        return self


class ToolSpec(BaseModel):
    """Runtime metadata for AITools (client vs server, handler id, invoke example)."""

    execution: Literal["client", "server"] = "client"
    server_handler: str | None = None
    server_config: dict[str, Any] = Field(default_factory=dict)
    invoke_example: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_server_tool(self) -> ToolSpec:
        if self.execution == "server" and not (self.server_handler or "").strip():
            raise ValueError("server tools require server_handler")
        if self.execution == "client":
            self.server_handler = None
        return self


class ArticleBlueprint(BaseModel):
    """Canonical encyclopedia article shape (reference: /wiki/gibson_es_335)."""

    infobox: Infobox | None = None
    lead: list[str] = Field(min_length=1)
    sections: list[BlueprintSection] = Field(default_factory=list)
    see_also: list[BlueprintLink] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    external_links: list[BlueprintLink] = Field(default_factory=list)
    tool: ToolSpec | None = None


def example_tool_blueprint() -> ArticleBlueprint:
    """Re-exported from aitools.tool_blueprint for backward compatibility."""
    from aitools.tool_blueprint import example_tool_blueprint as _example_tool_blueprint

    return _example_tool_blueprint()


def example_blueprint() -> ArticleBlueprint:
    """Minimal Gibson ES-335-style example for API docs and agents."""
    return ArticleBlueprint(
        infobox=Infobox(
            title="Gibson ES-335",
            image=InfoboxImage(
                src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0c/1960_Gibson_ES-335TD.jpg/250px-1960_Gibson_ES-335TD.jpg",
                caption="1960 Gibson ES-335TD in Sunburst",
            ),
            rows=[
                InfoboxEntry(kind="field", label="Manufacturer", value="Gibson"),
                InfoboxEntry(kind="field", label="Period", value="1958–present"),
                InfoboxEntry(kind="section", title="Construction"),
                InfoboxEntry(kind="field", label="Body type", value="Semi-hollow"),
            ],
        ),
        lead=[
            "The <b>Gibson ES-335</b> is a semi-hollow body "
            "<a href=\"https://en.wikipedia.org/wiki/Semi-acoustic_guitar\" rel=\"nofollow\">semi-acoustic guitar</a> "
            "introduced by Gibson in 1958."
        ],
        sections=[
            BlueprintSection(
                title="History",
                paragraphs=[
                    "The ES-335 was the world's first commercial thinline archtop semi-acoustic guitar."
                ],
            ),
            BlueprintSection(
                title="Models",
                level=2,
                paragraphs=["Many variants of the ES-335 have been produced since its introduction."],
            ),
        ],
        see_also=[
            BlueprintLink(
                label="Gibson ES Series",
                href="https://en.wikipedia.org/wiki/Gibson_ES_Series",
            )
        ],
        references=[
            "Guitar World (2018). <i>The history of the Gibson ES-335</i>.",
        ],
        external_links=[
            BlueprintLink(
                label="Gibson ES-335 at Gibson.com",
                href="https://www.gibson.com/",
            )
        ],
    )


def _render_infobox(infobox: Infobox) -> str:
    parts = [
        '<div class="infobox"><table><tbody>',
        f'<tr><th colspan="2" class="infobox-title">{html.escape(infobox.title)}</th></tr>',
    ]
    if infobox.image:
        width = f' width="{infobox.image.width}"' if infobox.image.width else ""
        alt = html.escape(infobox.image.alt, quote=True)
        src = html.escape(infobox.image.src, quote=True)
        img = f'<img src="{src}"{width} alt="{alt}" />'
        caption = html.escape(infobox.image.caption)
        cell = f"{img}<br />{caption}" if caption else img
        parts.append(f"<tr><td colspan=\"2\">{cell}</td></tr>")
    for row in infobox.rows:
        if row.kind == "section":
            parts.append(
                f'<tr><th colspan="2" class="infobox-section">{html.escape(row.title or "")}</th></tr>'
            )
        elif row.kind == "field":
            parts.append(
                f'<tr><th class="infobox-label">{html.escape(row.label or "")}</th>'
                f'<td class="infobox-data">{row.value or ""}</td></tr>'
            )
        else:
            parts.append(f'<tr><td colspan="2" class="infobox-full-data">{row.value or ""}</td></tr>')
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _render_thumb(thumb: BlueprintThumb) -> str:
    width = f' width="{thumb.width}"' if thumb.width else ""
    alt = html.escape(thumb.alt, quote=True)
    src = html.escape(thumb.src, quote=True)
    return (
        f'<div class="thumb thumb-{thumb.align}">'
        f'<div class="thumbinner">'
        f'<img src="{src}"{width} alt="{alt}" />'
        f'<div class="thumbcaption">{thumb.caption}</div>'
        f"</div></div>"
    )


def _render_heading(section: BlueprintSection, used_ids: dict[str, int]) -> str:
    heading_id = section.id or slugify_heading(section.title, used_ids)
    title = html.escape(section.title)
    return (
        f'<h{section.level} id="{heading_id}">'
        f'<span class="mw-headline">{title}</span></h{section.level}>'
    )


def _render_link_list(links: list[BlueprintLink]) -> str:
    items = []
    for link in links:
        href = html.escape(str(link.href), quote=True)
        label = html.escape(link.label)
        items.append(f'<li><a href="{href}" rel="nofollow">{label}</a></li>')
    return f"<ul>{''.join(items)}</ul>"


def _render_references(references: list[str]) -> str:
    items = []
    for index, ref in enumerate(references, start=1):
        note_id = f"cite_note-{index}"
        ref_id = f"cite_ref-{index}"
        items.append(
            f'<li id="{note_id}">'
            f'<a href="#{ref_id}">^</a> {ref}'
            f"</li>"
        )
    return f'<div class="references"><ol>{"".join(items)}</ol></div>'


def render_article_blueprint(blueprint: ArticleBlueprint) -> str:
    """Render stored article HTML in the Gibson ES-335 encyclopedia format."""
    parts: list[str] = []
    used_ids: dict[str, int] = {}

    if blueprint.infobox:
        parts.append(_render_infobox(blueprint.infobox))

    for paragraph in blueprint.lead:
        text = paragraph.strip()
        if not text:
            continue
        if text.startswith("<p"):
            parts.append(text)
        else:
            parts.append(f"<p>{text}</p>")

    for section in blueprint.sections:
        parts.append(_render_heading(section, used_ids))
        for thumb in section.thumbs:
            parts.append(_render_thumb(thumb))
        for paragraph in section.paragraphs:
            text = paragraph.strip()
            if not text:
                continue
            if text.startswith("<p"):
                parts.append(text)
            else:
                parts.append(f"<p>{text}</p>")
        for block in section.code_blocks:
            parts.append(render_code_block(block.code, block.language))

    if blueprint.see_also:
        parts.append(_render_heading(BlueprintSection(title="See also"), used_ids))
        parts.append(_render_link_list(blueprint.see_also))

    if blueprint.references:
        parts.append(_render_heading(BlueprintSection(title="References"), used_ids))
        parts.append(_render_references(blueprint.references))

    if blueprint.external_links:
        parts.append(_render_heading(BlueprintSection(title="External links"), used_ids))
        parts.append(_render_link_list(blueprint.external_links))

    rendered = "\n".join(parts)
    return security.sanitize_article_html(rendered)


def blueprint_schema() -> dict:
    return ArticleBlueprint.model_json_schema()


def resolve_article_content(*, content: str | None, blueprint: ArticleBlueprint | None) -> str:
    has_content = bool(content and content.strip())
    has_blueprint = blueprint is not None
    if has_content == has_blueprint:
        raise ValueError("Provide exactly one of content or blueprint")
    if blueprint is not None:
        return render_article_blueprint(blueprint)
    assert content is not None
    return content.strip()
