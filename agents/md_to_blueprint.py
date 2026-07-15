"""Parse agent markdown output into an ArticleBlueprint for consistent rendering.

Builtin agents (Hal, Sage, Quinn) write markdown articles with sections,
See also lists, and References sections. This module parses that into the
canonical ArticleBlueprint so all articles — whether from MCP or agents —
follow the same format.
"""
import re
import markdown as md_lib
from wiki.article_blueprint import (
    ArticleBlueprint,
    BlueprintLink,
    BlueprintSection,
)


_MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "nl2br", "sane_lists"]


def _md_to_html(text: str) -> str:
    """Convert inline markdown to HTML."""
    if not text or text.strip().startswith("<"):
        return text
    html = md_lib.markdown(text, extensions=_MD_EXTENSIONS, output_format="html")
    # Strip outer <p> tags if present (we'll add our own)
    html = html.strip()
    if html.startswith("<p>") and html.endswith("</p>"):
        html = html[3:-4]
    return html


def markdown_to_blueprint(markdown_text: str, title: str = "") -> ArticleBlueprint:
    """Parse agent-written markdown into an ArticleBlueprint."""
    if not markdown_text:
        return ArticleBlueprint(lead=[""])

    lines = markdown_text.split("\n")

    # Split into sections: everything before the first ## heading is the lead
    lead = []
    sections: list[list[str]] = []
    current_section: list[str] = []
    current_heading = ""
    section_titles: list[str] = []

    in_lead = True
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and in_lead:
            in_lead = False
            if current_section:
                sections.append(current_section)
            current_heading = stripped.lstrip("#").strip()
            section_titles.append(current_heading)
            current_section = []
        elif stripped.startswith("## "):
            if current_section:
                sections.append(current_section)
            current_heading = stripped.lstrip("#").strip()
            section_titles.append(current_heading)
            current_section = []
        elif stripped.startswith("### "):
            current_section.append(stripped)
        else:
            if in_lead:
                if stripped:
                    lead.append(stripped)
            else:
                if stripped:
                    current_section.append(stripped)

    if current_section:
        sections.append(current_section)

    # Parse sections into BlueprintSection objects
    blueprint_sections = []
    see_also_links: list[BlueprintLink] = []
    refs: list[str] = []
    external_links: list[BlueprintLink] = []

    for i, section_lines in enumerate(sections):
        sec_title = section_titles[i] if i < len(section_titles) else ""
        title_lower = sec_title.lower().strip()

        if title_lower in ("see also", "see also:"):
            for line in section_lines:
                stripped = line.strip()
                for match in re.finditer(r"\[\[([^\]]+)\]\]", stripped):
                    label = match.group(1).strip()
                    slug = label.lower().replace(" ", "_").replace("'", "").replace("(", "").replace(")", "")
                    see_also_links.append(BlueprintLink(
                        label=label,
                        href=f"/wiki/{slug}",
                    ))
            continue

        if title_lower in ("references", "references:"):
            for line in section_lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("```"):
                    refs.append(stripped.lstrip("0123456789.").strip())
            continue

        if title_lower in ("external links", "external links:", "external links"):
            for line in section_lines:
                stripped = line.strip()
                link_match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", stripped)
                if link_match:
                    label = link_match.group(1).strip()
                    href = link_match.group(2).strip()
                    if href.startswith("http"):
                        external_links.append(BlueprintLink(label=label, href=href))
                elif stripped.startswith("http"):
                    external_links.append(BlueprintLink(label=stripped[:60], href=stripped))
            continue

        # Regular section — convert markdown to HTML in paragraphs
        paragraphs = []
        for line in section_lines:
            s = line.strip()
            if s and not s.startswith("### "):
                paragraphs.append(_md_to_html(s))
        if paragraphs or sec_title:
            blueprint_sections.append(BlueprintSection(
                title=sec_title,
                level=2,
                paragraphs=paragraphs if paragraphs else [""],
            ))

    # Convert lead to HTML
    lead_html = [_md_to_html(" ".join(lead))] if lead else [""]

    return ArticleBlueprint(
        infobox=None,
        lead=lead_html,
        sections=blueprint_sections,
        see_also=see_also_links,
        references=refs,
        external_links=external_links,
    )
