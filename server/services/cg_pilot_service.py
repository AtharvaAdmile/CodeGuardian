"""
CG-pilot agent service.

Uses the OpenAI Responses API for the chatbot LLM while keeping project
retrieval grounded in the existing CodeGuardian index and read-only local
file tools constrained to the selected project root.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
from typing import Any

from openai import AsyncOpenAI

from server.models.route_schemas import (
    CGPilotMessage,
    CGPilotStep,
    CGPilotToolUse,
    SourceRef,
)

logger = logging.getLogger("codeguardian.cg_pilot")

_FINAL_ANSWER_TOOL = "final_answer"



class CGPilotService:
    """Agentic project chat backed by OpenAI and CodeGuardian retrieval."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        embedding_service,
        vector_service,
        max_tool_rounds: int = 6,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
        self._model = model
        self._embedding_service = embedding_service
        self._vector_service = vector_service
        self._max_tool_rounds = max(1, max_tool_rounds)

    async def close(self) -> None:
        """Close the OpenAI client."""
        await self._client.close()

    # ── System prompt ─────────────────────────────────────────────────────

    def _build_instructions(self) -> str:
        return (
            "You are CG-pilot, CodeGuardian's project copilot.\n\n"
            "RULES:\n"
            "1. You MUST work in an agentic loop: Plan -> Act -> Observe -> Decide -> repeat.\n"
            "2. You MUST call a tool to gather information whenever you need it.\n"
            '3. When you have ENOUGH context to fully answer, call final_answer(message="...").\n'
            "4. You MUST NEVER produce a final answer as plain text. Always use final_answer().\n"
            "5. You MUST NOT answer after just one tool call. Minimum 2-3 rounds.\n"
            "6. Always tell the user what you're doing alongside your tool calls.\n\n"
            "YOUR TOOLS:\n"
            "- search_index(query) — semantic search over indexed code\n"
            "- read_file(path) — read a specific file's content\n"
            "- list_files(directory) — list files in a directory\n"
            "- glob_files(pattern) — find files by glob pattern\n"
            "- search_files(query) — grep for text in files\n"
            "- final_answer(message) — Call this ONLY when you are ready to answer\n\n"
            "ANSWER QUALITY — Your final_answer must be comprehensive:\n"
            "- Start with a concise high-level summary of what you found.\n"
            "- Structure long answers with sections (headings, bullet points).\n"
            "- Cite specific file paths and line numbers for every claim.\n"
            "- Include short code snippets inline when relevant.\n"
            "- Describe how things connect — architecture, data flow, dependencies.\n"
            "- If asked about the project, cover: purpose, tech stack, directory layout, key modules.\n"
            "- Be thorough — don't just list file names, explain what each does.\n"
            "- Use markdown for readability (headings, code blocks, lists).\n\n"
            "CRITICAL: If a tool returns empty results, try a different tool or query.\n"
            "Do NOT give up after one search. Explore the codebase structure.\n"
            "Search for README, index files, entry points, and configuration files."
        )

    # ── Main chat entry point ─────────────────────────────────────────────

    async def chat(
        self,
        project_id: str,
        project_path: str,
        message: str,
        conversation_history: list[CGPilotMessage] | None = None,
        file_context: dict | None = None,
    ) -> tuple[str, list[SourceRef], list[CGPilotToolUse], list[CGPilotStep]]:
        logger.info(
            "💬 CG-pilot chat starting: project=%s, message='%s'", project_id, message
        )
        tools = self._tool_definitions()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_instructions()}
        ]
        for msg in conversation_history or []:
            msg_dict = (
                msg
                if isinstance(msg, dict)
                else {"role": msg.role, "content": msg.content}
            )
            messages.append(
                {"role": msg_dict["role"], "content": msg_dict["content"]}
            )

        # ── Inject optional file context ──────────────────────────────
        user_content = message
        if file_context:
            file_path = file_context.get("file_path", "")
            if file_path:
                full_path = os.path.join(project_path, file_path)
                if os.path.isfile(full_path):
                    try:
                        with open(full_path, "r") as f:
                            file_content = f.read()
                        user_content = (
                            f"The user has attached this file as additional context:\n\n"
                            f"```\n{file_path}\n{file_content}\n```\n\n"
                            f"---\n\n{message}"
                        )
                        logger.info(
                            "📎 Attached file context: %s (%d chars)",
                            file_path,
                            len(file_content),
                        )
                    except Exception as e:
                        logger.warning("Failed to read attached file %s: %s", file_path, e)

        messages.append({"role": "user", "content": user_content})

        tools_used: list[CGPilotToolUse] = []
        sources: list[SourceRef] = []
        steps: list[CGPilotStep] = []
        seen_chunks: set[str] = set()

        final_answer: str | None = None
        last_content = ""

        for round_idx in range(self._max_tool_rounds):
            round_num = round_idx + 1
            logger.debug(f"CG-pilot round {round_num}/{self._max_tool_rounds}")

            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
            except Exception as e:
                logger.error("❌ OpenAI API error in CG-pilot: %s", e)
                return (
                    f"Error communicating with LLM API: {e}",
                    sources,
                    tools_used,
                    steps,
                )

            response_message = response.choices[0].message
            assistant_content = response_message.content or ""
            last_content = assistant_content
            tool_calls = response_message.tool_calls

            # ── Check if model called final_answer ────────────────────
            if tool_calls:
                for tc in tool_calls:
                    if tc.function.name == _FINAL_ANSWER_TOOL:
                        try:
                            args = json.loads(tc.function.arguments)
                            final_answer = args.get("message", "").strip()
                        except Exception:
                            final_answer = ""
                        if not final_answer:
                            final_answer = assistant_content.strip()
                        steps.append(
                            CGPilotStep(
                                round=round_num,
                                action="final",
                                message=final_answer[:200],
                            )
                        )
                        logger.info(
                            "✅ CG-pilot final_answer (%d chars)", len(final_answer)
                        )
                        return final_answer, sources, tools_used, steps

            # ── Capture narration for plan/observation ────────────────
            if assistant_content.strip():
                action = "plan" if tool_calls else "observation"
                steps.append(
                    CGPilotStep(
                        round=round_num,
                        action=action,
                        message=assistant_content,
                    )
                )

            # ── Append assistant message to context ───────────────────
            msg_to_append: dict[str, Any] = {
                "role": response_message.role,
                "content": assistant_content,
            }
            if tool_calls:
                msg_to_append["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(msg_to_append)

            # ── No tool calls at all → re-prompt ──────────────────────
            if not tool_calls:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "If you need more information to answer the user's question, "
                            "call a tool (search_index, read_file, list_files, glob_files, "
                            "or search_files). If you are ready to answer, call "
                            "final_answer(). Describe what you're doing alongside "
                            "your tool calls. Do NOT just talk about what you'll do."
                        ),
                    }
                )
                continue

            # ── Process each information-gathering tool call ──────────
            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                if fn_name == _FINAL_ANSWER_TOOL:
                    continue  # already handled above
                fn_args_str = tool_call.function.arguments

                try:
                    args = json.loads(fn_args_str)
                except Exception as e:
                    logger.warning(
                        "Failed to parse tool arguments for %s: %s", fn_name, e
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {"error": f"Invalid JSON arguments: {e}"}
                            ),
                        }
                    )
                    continue

                logger.info("🔧 Calling tool: %s(%s)", fn_name, args)
                tool_output, new_sources, tool_summary = await self._run_tool(
                    fn_name, args, project_id, project_path, seen_chunks
                )

                sources.extend(new_sources)
                tools_used.append(
                    CGPilotToolUse(name=fn_name, summary=tool_summary)
                )

                steps.append(
                    CGPilotStep(
                        round=round_num,
                        action="tool_call",
                        tool_name=fn_name,
                        tool_summary=tool_summary,
                    )
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_output),
                    }
                )

        # ── Exhausted rounds without final_answer ─────────────────────
        if not final_answer:
            final_answer = (
                last_content.strip()
                or "I explored the codebase but ran out of processing steps. "
                "Try asking a more specific question."
            )
        steps.append(
            CGPilotStep(
                round=round_num,
                action="final",
                message=final_answer[:200],
            )
        )
        return final_answer.strip(), sources, tools_used, steps

    # ── Tool definitions ──────────────────────────────────────────────────

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_index",
                    "description": "REQUIRED FIRST STEP. Semantic search over indexed code chunks. Use this to find relevant files and code for any question. Returns code snippets with file paths and line numbers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language search query about the codebase",
                            },
                            "top_k": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files and directories. Use after search_index to explore structure and find related files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Relative directory path (default: '.')",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "glob_files",
                    "description": "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts'). Use to locate specific file types.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.tsx')",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                            },
                        },
                        "required": ["pattern"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Grep-style search for text in files. Use to find specific functions, classes, or patterns.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Text to search for",
                            },
                            "pattern": {
                                "type": "string",
                                "description": "File glob pattern (default: '*')",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 30,
                            },
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file's content. Use this to examine specific code after finding relevant files via search_index. Returns lines with numbers for citation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative path to file from project root",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Starting line number (optional)",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "Ending line number (optional)",
                            },
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": _FINAL_ANSWER_TOOL,
                    "description": "Call this ONLY when you have gathered enough information to fully answer the user. Provide your complete answer as the 'message' parameter with specific file:line citations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Your complete answer with file path citations",
                            }
                        },
                        "required": ["message"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def _field(self, item: Any, name: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    # ── Tool runner ───────────────────────────────────────────────────────

    async def _run_tool(
        self,
        fn_name: str,
        args: dict,
        project_id: str,
        project_path: str,
        seen_chunks: set[str],
    ) -> tuple[dict, list[SourceRef], str]:
        sources: list[SourceRef] = []

        try:
            if fn_name == "search_index":
                query = args.get("query", "")
                top_k = args.get("top_k", 5)
                results = await self._vector_service.search(
                    project_id, query, top_k
                )
                for res in results:
                    sources.append(
                        SourceRef(
                            file_path=res.get("file_path", ""),
                            start_line=res.get("start_line"),
                            end_line=res.get("end_line"),
                            chunk_type="chunk",
                            relevance_score=1.0,
                        )
                    )
                summary = f"retrieved {len(results)} chunks"
                return {
                    "results": results,
                    "summary": summary,
                    "next_steps": "Use read_file() on the files above to see actual implementation details.",
                }, sources, summary

            elif fn_name == "list_files":
                directory = args.get("directory", ".")
                limit = args.get("limit", 100)
                full_dir = os.path.join(project_path, directory)
                entries = []
                if os.path.exists(full_dir):
                    for idx, entry in enumerate(os.listdir(full_dir)):
                        if idx >= limit:
                            break
                        entries.append({"path": entry})
                summary = f"listed {len(entries)} entries"
                return {
                    "entries": entries,
                    "summary": summary,
                    "next_steps": "Use read_file() to examine relevant files found above, or search_files() to find specific patterns.",
                }, sources, summary

            elif fn_name == "read_file":
                path = args.get("path")
                full_path = os.path.join(project_path, path)
                if os.path.exists(full_path):
                    with open(full_path, "r") as f:
                        lines = f.readlines()
                    start = args.get("start_line", 1)
                    end = args.get(
                        "end_line", min(start + 200, len(lines))
                    )
                    content = "".join(lines[start - 1 : end])
                    sources.append(
                        SourceRef(
                            file_path=path,
                            start_line=start,
                            end_line=end,
                            chunk_type="file_read",
                            relevance_score=1.0,
                        )
                    )
                    summary = f"read {path}:{start}-{end}"
                    return {
                        "file_path": path,
                        "content": content,
                        "summary": summary,
                        "next_steps": "Review the content above. Search for related patterns with search_files() or read additional files to confirm understanding.",
                    }, sources, summary
                return {
                    "error": "file not found",
                    "next_steps": "Try list_files() or glob_files() to find the correct file path.",
                }, sources, "file not found"

            elif fn_name == "glob_files":
                pattern = args.get("pattern", "*")
                full_pattern = os.path.join(project_path, pattern)
                files = glob.glob(full_pattern, recursive=True)[
                    : args.get("limit", 100)
                ]
                entries = [
                    {"path": os.path.relpath(f, project_path)} for f in files
                ]
                summary = f"found {len(entries)} files"
                return {
                    "entries": entries,
                    "summary": summary,
                    "next_steps": "Use read_file() to examine relevant files from the results above.",
                }, sources, summary

            elif fn_name == "search_files":
                query = args.get("query")
                res = subprocess.run(
                    ["grep", "-rn", query, project_path],
                    capture_output=True,
                    text=True,
                )
                lines = res.stdout.splitlines()[: args.get("limit", 30)]
                summary = f"found {len(lines)} matches"
                return {
                    "results": lines,
                    "summary": summary,
                    "next_steps": "Use read_file() on the matching files to examine the relevant code sections.",
                }, sources, summary

            else:
                return {
                    "error": f"Unknown tool {fn_name}"
                }, sources, "unknown tool"

        except Exception as e:
            return {"error": str(e)}, sources, "tool error"
