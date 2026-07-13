"""Tool-specific blueprint helpers (infobox fields, examples)."""

from __future__ import annotations

from wiki.article_blueprint import (
    ArticleBlueprint,
    BlueprintCodeBlock,
    BlueprintSection,
    Infobox,
    InfoboxEntry,
    InfoboxImage,
    ToolSpec,
)

QBRAIN_AUTHOR = "QuBrain"
TOOL_INFOBOX_MADE_BY_LABEL = "Made by"


def tool_made_by_row(made_by: str = QBRAIN_AUTHOR) -> InfoboxEntry:
    return InfoboxEntry(kind="field", label=TOOL_INFOBOX_MADE_BY_LABEL, value=made_by)


def web_search_tool_blueprint() -> ArticleBlueprint:
    """Server-side web search tool (DuckDuckGo)."""
    return ArticleBlueprint(
        infobox=Infobox(
            title="Web Search",
            image=InfoboxImage(
                src="https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/DuckDuckGo_icon.svg/120px-DuckDuckGo_icon.svg.png",
                caption="Web search via DuckDuckGo",
                alt="Search icon",
            ),
            rows=[
                InfoboxEntry(kind="field", label="Runtime", value="Server-side (AIWiki)"),
                InfoboxEntry(kind="field", label="Input", value="JSON: query, optional limit"),
                InfoboxEntry(kind="field", label="Output", value="Ranked web results"),
                InfoboxEntry(kind="field", label="Provider", value="DuckDuckGo"),
                tool_made_by_row(),
            ],
        ),
        lead=[
            "Searches the public web and returns ranked results. "
            "Invoke with a JSON body; AIWiki runs the search on the server and returns structured results.",
        ],
        sections=[
            BlueprintSection(
                title="Example response",
                code_blocks=[
                    BlueprintCodeBlock(
                        code=(
                            '{\n'
                            '  "execution": "server",\n'
                            '  "result": {\n'
                            '    "query": "FastAPI tutorial",\n'
                            '    "count": 2,\n'
                            '    "results": [\n'
                            '      {"title": "...", "url": "https://...", "snippet": "..."}\n'
                            '    ]\n'
                            '  }\n'
                            '}'
                        ),
                        language="json",
                    )
                ],
            ),
        ],
        tool=ToolSpec(
            execution="server",
            server_handler="web_search",
            server_config={"provider": "duckduckgo"},
            invoke_example={"query": "FastAPI web framework", "limit": 5},
        ),
    )


def example_tool_blueprint() -> ArticleBlueprint:
    """Minimal tool page example with infobox, Made by, optional image, and code block."""
    return ArticleBlueprint(
        infobox=Infobox(
            title="Text Uppercase",
            image=InfoboxImage(
                src="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Crystal_Clear_app_fonts.svg/120px-Crystal_Clear_app_fonts.svg.png",
                caption="Text transformation utility",
                alt="Font icon",
            ),
            rows=[
                InfoboxEntry(kind="field", label="Runtime", value="Client-side"),
                InfoboxEntry(kind="field", label="Language", value="Python"),
                InfoboxEntry(kind="field", label="Input", value="Plain text"),
                InfoboxEntry(kind="field", label="Output", value="Uppercase text"),
                tool_made_by_row(),
            ],
        ),
        lead=[
            "Converts input text to uppercase. Fetch this tool via the invoke API and run it locally.",
        ],
        sections=[
            BlueprintSection(
                title="Implementation",
                code_blocks=[
                    BlueprintCodeBlock(
                        code=(
                            'def run(text: str) -> str:\n'
                            '    """Return uppercase text."""\n'
                            "    return text.upper()"
                        ),
                        language="python",
                    )
                ],
            ),
        ],
        tool=ToolSpec(execution="client"),
    )
