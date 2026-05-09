"""
CG-pilot agent service.

Uses the OpenAI Responses API for the chatbot LLM while keeping project
retrieval grounded in the existing CodeGuardian index and read-only local
file tools constrained to the selected project root.
"""

from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from server.models.route_schemas import CGPilotMessage, CGPilotToolUse, SourceRef

logger = logging.getLogger("codeguardian.cg_pilot")

_SKIP_DIRS = {
    ".git",
    ".codeguardian",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "coverage",
    "chroma_data",
}
_TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".css",
    ".html",
    ".sql",
}
_MAX_READ_CHARS = 18_000
_MAX_SEARCH_RESULTS = 30
_DOC_KEYWORDS = {"readme", "docs", "documentation", "design", "guide", "manual"}


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

    async def chat(
        self,
        project_id: str,
        project_path: str,
        message: str,
        conversation_history: list[CGPilotMessage] | None = None,
    ) -> tuple[str, list[SourceRef], list[CGPilotToolUse]]:
        logger.info(
            "💬 CG-pilot chat starting: project=%s, message='%s'", project_id, message
        )
        tools = self._tool_definitions()

        instructions = (
            "You are CG-pilot, CodeGuardian's project copilot. Your core principle: YOU MUST USE TOOLS. Never answer from memory.\\n\\n"
            "MANDATORY WORKFLOW for every question:\\n"
            "1. search_index(query='<question topic>') - Find relevant indexed code\\n"
            "2. list_files(directory='<relevant_dir>') or glob_files(pattern='<pattern>') - Explore structure\\n"
            "3. read_file(path='<file_path>') - Read specific source files with content\\n"
            "4. search_files(query='<term>', pattern='*') - Find specific patterns in source files\\n\\n"
            "CRITICAL RULES:\\n"
            "- Always use search_index first for any question about the codebase.\\n"
            "- Read file contents before making claims about implementation details.\\n"
            "- Cite the exact file paths and line numbers provided in tool outputs.\\n"
            "- If search_index returns 0 results, use list_files/glob_files to explore manually.\\n"
            "- Do not guess variable names or architectures. Verify everything."
        )

        messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
        for msg in conversation_history or []:
            msg_dict = msg if isinstance(msg, dict) else {"role": msg.role, "content": msg.content}
            messages.append({"role": msg_dict["role"], "content": msg_dict["content"]})
        
        messages.append({"role": "user", "content": message})

        tools_used: list[CGPilotToolUse] = []
        sources: list[SourceRef] = []
        seen_chunks: set[str] = set()

        for round_idx in range(self._max_tool_rounds):
            logger.debug(f"CG-pilot round {round_idx + 1}/{self._max_tool_rounds}")
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
            except Exception as e:
                logger.error("❌ OpenAI API error in CG-pilot: %s", e)
                return f"Error communicating with LLM API: {e}", sources, tools_used

            response_message = response.choices[0].message
            
            # Prepare message to append (strip None fields to avoid validation errors on some NIM models)
            msg_to_append = {"role": response_message.role, "content": response_message.content or ""}
            if response_message.tool_calls:
                msg_to_append["tool_calls"] = [
                    {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in response_message.tool_calls
                ]
            messages.append(msg_to_append)

            tool_calls = response_message.tool_calls
            if not tool_calls:
                break

            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                fn_args_str = tool_call.function.arguments
                
                try:
                    import json
                    args = json.loads(fn_args_str)
                except Exception as e:
                    logger.warning("Failed to parse tool arguments for %s: %s", fn_name, e)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"error": f"Invalid JSON arguments: {e}"})
                    })
                    continue
                    
                logger.info("🔧 Calling tool: %s(%s)", fn_name, args)
                tool_output, new_sources, tool_summary = await self._run_tool(
                    fn_name, args, project_id, project_path, seen_chunks
                )
                
                sources.extend(new_sources)
                tools_used.append(
                    CGPilotToolUse(
                        name=fn_name,
                        summary=tool_summary
                    )
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_output)
                })

        final_answer = response_message.content or ""
        if not final_answer.strip() and len(messages) > 1:
            final_answer = "I've explored the codebase but exceeded my maximum processing steps. Please try asking a more specific question, or ask me about what I've discovered so far."
            
        return final_answer.strip(), sources, tools_used

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
                                "description": "Natural language search query about the codebase"
                            },
                            "top_k": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                                "default": 5
                            }
                        },
                        "required": ["query"],
                        "additionalProperties": False
                    }
                }
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
                                "description": "Relative directory path (default: '.')"
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "additionalProperties": False
                    }
                }
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
                                "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.tsx')"
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": ["pattern"],
                        "additionalProperties": False
                    }
                }
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
                                "description": "Text to search for"
                            },
                            "pattern": {
                                "type": "string",
                                "description": "File glob pattern (default: '*')"
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 30
                            }
                        },
                        "required": ["query"],
                        "additionalProperties": False
                    }
                }
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
                                "description": "Relative path to file from project root"
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Starting line number (optional)"
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "Ending line number (optional)"
                            }
                        },
                        "required": ["path"],
                        "additionalProperties": False
                    }
                }
            }
        ]

    def _field(self, item: Any, name: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)


    async def _run_tool(self, fn_name: str, args: dict, project_id: str, project_path: str, seen_chunks: set[str]) -> tuple[dict, list[SourceRef], str]:
        sources: list[SourceRef] = []
        try:
            if fn_name == "search_index":
                query = args.get("query", "")
                top_k = args.get("top_k", 5)
                results = await self._vector_service.search(project_id, query, top_k)
                for res in results:
                    sources.append(SourceRef(
                        file_path=res.get("file_path", ""),
                        start_line=res.get("start_line"),
                        end_line=res.get("end_line"),
                        chunk_type="chunk",
                        relevance_score=1.0
                    ))
                return {"results": results, "summary": f"retrieved {len(results)} chunks"}, sources, f"retrieved {len(results)} chunks"
            elif fn_name == "list_files":
                directory = args.get("directory", ".")
                limit = args.get("limit", 100)
                import os
                full_dir = os.path.join(project_path, directory)
                entries = []
                if os.path.exists(full_dir):
                    for idx, entry in enumerate(os.listdir(full_dir)):
                        if idx >= limit: break
                        entries.append({"path": entry})
                return {"entries": entries}, sources, f"listed {len(entries)} entries"
            elif fn_name == "read_file":
                path = args.get("path")
                import os
                full_path = os.path.join(project_path, path)
                if os.path.exists(full_path):
                    with open(full_path, "r") as f:
                        lines = f.readlines()
                    start = args.get("start_line", 1)
                    end = args.get("end_line", min(start + 200, len(lines)))
                    content = "".join(lines[start-1:end])
                    sources.append(SourceRef(
                        file_path=path,
                        start_line=start,
                        end_line=end,
                        chunk_type="file_read",
                        relevance_score=1.0
                    ))
                    return {"file_path": path, "content": content}, sources, f"read {path}:{start}-{end}"
                return {"error": "file not found"}, sources, "file not found"
            elif fn_name == "glob_files":
                pattern = args.get("pattern", "*")
                import glob
                import os
                full_pattern = os.path.join(project_path, pattern)
                files = glob.glob(full_pattern, recursive=True)[:args.get("limit", 100)]
                entries = [{"path": os.path.relpath(f, project_path)} for f in files]
                return {"entries": entries}, sources, f"found {len(entries)} files"
            elif fn_name == "search_files":
                query = args.get("query")
                import subprocess
                res = subprocess.run(["grep", "-rn", query, project_path], capture_output=True, text=True)
                lines = res.stdout.splitlines()[:args.get("limit", 30)]
                return {"results": lines}, sources, f"found {len(lines)} matches"
            else:
                return {"error": f"Unknown tool {fn_name}"}, sources, "unknown tool"
        except Exception as e:
            return {"error": str(e)}, sources, "tool error"
