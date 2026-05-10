"""
Compliance Agent — tool-calling agentic loop for codebase compliance scanning.

For each selected check type, the agent runs an independent ReAct-style loop:
    Plan -> Act (tool call) -> Observe -> Decide -> repeat -> Finalize

Each step is streamed to the UI via SSE for real-time visibility.

Check types:
    secrets          — hardcoded API keys, tokens, passwords
    pii              — personally identifiable information identifiers
    gdpr             — GDPR-sensitive fields (email, phone, address)
    hipaa            — HIPAA-protected health information
    dangerous_funcs  — eval, exec, subprocess, os.system
    sql_injection    — f-string / string interpolation in SQL queries
"""

from __future__ import annotations

import glob as glob_module
import json
import logging
import os
import subprocess
from typing import Any

from openai import AsyncOpenAI

from server.models.route_schemas import ComplianceFinding, ComplianceStep

logger = logging.getLogger("codeguardian.agents.compliance")

_FINALIZE_TOOL = "finalize_check"

_CHECK_REGISTRY: dict[str, dict] = {}


def _register_check(check_id: str, name: str, description: str, category: str, default_severity: str):
    _CHECK_REGISTRY[check_id] = {
        "id": check_id, "name": name, "description": description,
        "category": category, "default_severity": default_severity,
    }


_register_check("secrets", "Secrets & Credentials", "Hardcoded API keys, tokens, passwords, private keys", "security", "critical")
_register_check("pii", "PII Detection", "Social Security Numbers, credit card data", "privacy", "high")
_register_check("gdpr", "GDPR Compliance", "Personal data fields: email, phone, address, DOB", "privacy", "medium")
_register_check("hipaa", "HIPAA Compliance", "Protected health information: patient data, medical records", "regulatory", "critical")
_register_check("dangerous_funcs", "Dangerous Functions", "eval, exec, os.system, subprocess usage", "security", "critical")
_register_check("sql_injection", "SQL Injection", "f-string / interpolation in database queries", "security", "high")

_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", "chroma_data", ".codeguardian", ".egg-info",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def get_available_checks() -> list[dict]:
    return list(_CHECK_REGISTRY.values())


_CHECK_PROMPTS: dict[str, str] = {
    "secrets": (
        "You are checking for hardcoded secrets, credentials, and sensitive tokens in the codebase.\n"
        "Look for:\n"
        "- API keys, API secrets, access tokens, auth tokens\n"
        "- Hardcoded passwords, passphrases\n"
        "- Private keys (PEM blocks, SSH keys)\n"
        "- Bearer tokens, JWT tokens\n"
        "- Connection strings containing credentials\n\n"
        "Use record_finding() for each violation you discover.\n"
        "Search in: .env files, configuration files, Python/JS source files, YAML/JSON configs, CI files, docker-compose files."
    ),
    "pii": (
        "You are checking for Personally Identifiable Information (PII) in the codebase.\n"
        "Look for:\n"
        "- Social Security Number (SSN) references or patterns\n"
        "- Credit card data references (credit_card, card_number, CVV)\n"
        "- Variable names suggesting PII storage\n\n"
        "Use record_finding() for each violation.\n"
        "Search in: source code, configuration files, log statements, database schemas, API payloads."
    ),
    "gdpr": (
        "You are checking for GDPR-sensitive personal data fields in the codebase.\n"
        "Look for:\n"
        "- Email addresses (user_email, email_address)\n"
        "- Phone numbers (phone_number, mobile)\n"
        "- Date of birth (date_of_birth, dob)\n"
        "- Home addresses (home_address, street_address)\n"
        "- Any variable names suggesting personal data storage\n\n"
        "Use record_finding() for each violation.\n"
        "Search in: source code, database models, API schemas, form definitions, log statements."
    ),
    "hipaa": (
        "You are checking for HIPAA-protected health information (PHI) in the codebase.\n"
        "Look for:\n"
        "- Patient identifiers (patient_id, patientID)\n"
        "- Medical record references (medical_record, health_record)\n"
        "- Diagnosis data (diagnosis, condition, symptom)\n"
        "- Prescription data (prescription, medication)\n"
        "- Any variable names suggesting health data storage\n\n"
        "Use record_finding() for each violation.\n"
        "Search in: source code, database models, API schemas, form definitions."
    ),
    "dangerous_funcs": (
        "You are checking for dangerous function usage in the codebase.\n"
        "Look for:\n"
        "- eval() calls — code injection risk\n"
        "- exec() calls — code injection risk\n"
        "- os.system() calls — shell injection risk\n"
        "- subprocess.call() with shell=True — shell injection risk\n"
        "- subprocess.Popen() — shell injection risk\n"
        "- Any use of exec, compile, __import__ with dynamic input\n\n"
        "Use record_finding() for each violation.\n"
        "Search in: Python source files, shell scripts, build scripts."
    ),
    "sql_injection": (
        "You are checking for SQL injection vulnerabilities in the codebase.\n"
        "Look for:\n"
        "- f-strings used in SQL queries (e.g., f\"SELECT * FROM {{table}}\")\n"
        "- String concatenation in SQL queries\n"
        "- .format() used in SQL query strings\n"
        "- % interpolation in SQL query strings\n"
        "- Raw string building for SQL without parameterization\n\n"
        "Use record_finding() for each violation.\n"
        "Search in: Python source files, JS/TS source files, SQL files, ORM usage."
    ),
}


_CHECK_SUGGESTIONS: dict[str, str] = {
    "secrets": "Store secrets in environment variables or a secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager). Never hardcode credentials.",
    "pii": "Avoid storing or logging plaintext PII. Use encryption, masking, or tokenization.",
    "gdpr": "Ensure GDPR compliance: mask or encrypt personal data fields, avoid storing raw personal data in logs.",
    "hipaa": "PHI must be encrypted at rest and in transit. Ensure HIPAA compliance with access controls and audit trails.",
    "dangerous_funcs": "Use safer alternatives (e.g., subprocess.run with shell=False, ast.literal_eval instead of eval).",
    "sql_injection": "Use parameterised queries (?, %s) or an ORM instead of string building. Never interpolate user input into SQL.",
}


class ComplianceAgent:
    """
    Tool-calling agent that runs compliance checks one at a time.

    For each selected check type, the agent:
    1. Receives a system prompt describing what to look for
    2. Explores the codebase using tool calls (list_files, read_file, etc.)
    3. Records findings via record_finding() tool
    4. Calls finalize_check() when done with that check

    Steps are yielded via step_callback for SSE streaming to the UI.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tool_rounds: int = 20,
        step_callback=None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
        self._model = model
        self._max_tool_rounds = max(1, max_tool_rounds)
        self._step_callback = step_callback

    async def close(self) -> None:
        await self._client.close()

    def _build_system_prompt(self, check_type: str) -> str:
        check_info = _CHECK_REGISTRY.get(check_type, {})
        check_prompt = _CHECK_PROMPTS.get(check_type, "Check for compliance violations in the codebase.")

        return (
            "You are a compliance violation detection agent running a thorough codebase scan.\n\n"
            f"CHECK: {check_info.get('name', check_type)}\n"
            f"DESCRIPTION: {check_info.get('description', '')}\n"
            f"CATEGORY: {check_info.get('category', 'security')}\n"
            f"DEFAULT SEVERITY: {check_info.get('default_severity', 'medium')}\n\n"
            f"{check_prompt}\n\n"
            "RULES:\n"
            "1. You MUST work in an agentic loop: Plan -> Act -> Observe -> Decide -> repeat.\n"
            "2. You MUST call a tool to gather information whenever you need it.\n"
            '3. When you find a violation, call record_finding() immediately.\n'
            '4. When you are DONE checking, call finalize_check().\n'
            "5. You MUST NOT produce a final answer as plain text. Always use finalize_check().\n"
            "6. Be THOROUGH — search in multiple directories, read relevant files, explore config directories.\n"
            "7. Always tell the user what you're doing alongside your tool calls.\n\n"
            "YOUR TOOLS:\n"
            "- list_files(directory) — list files in a directory\n"
            "- read_file(path, start_line, end_line) — read a specific file's content\n"
            "- glob_files(pattern, limit) — find files by glob pattern\n"
            "- grep_files(query, pattern, limit) — search for text in files\n"
            "- record_finding(file_path, line, severity, message, snippet) — record a violation\n"
            "- finalize_check() — Call this ONLY when you are done with the check\n\n"
            "CRITICAL:\n"
            "- If a tool returns empty results, try a different search approach.\n"
            "- Don't give up after one search. Explore the codebase structure first.\n"
            "  Use list_files('.') at the root, then drill into relevant directories.\n"
            "- Look at configuration files (.env, .yaml, .json) as well as source code.\n"
            "- Be specific about severity: critical, high, medium, or low.\n"
            "- Include the relevant code snippet when recording a finding.\n"
            f"Project path: {{project_path}}"
        )

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files and directories at a path. Use to explore the project structure.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Directory path (default: '.')",
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
                    "name": "read_file",
                    "description": "Read a file's content. Use to examine specific files for violations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative path to file from project root",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Starting line number (optional, 1-indexed)",
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
                    "name": "glob_files",
                    "description": "Find files matching a glob pattern (e.g., '**/*.py', '**/*.env', '**/*config*'). Use to locate specific file types.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Glob pattern (e.g., '**/*.py', '**/*.env')",
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
                    "name": "grep_files",
                    "description": "Search for text patterns in files. Use to find specific functions, variables, or patterns across the codebase.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Text or regex pattern to search for",
                            },
                            "pattern": {
                                "type": "string",
                                "description": "File glob pattern to narrow search (default: '*')",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 50,
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
                    "name": "record_finding",
                    "description": "Record a compliance violation finding. Call this whenever you discover a violation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Relative path to the file with the violation",
                            },
                            "line": {
                                "type": "integer",
                                "description": "Line number where the violation was found",
                            },
                            "severity": {
                                "type": "string",
                                "enum": ["critical", "high", "medium", "low"],
                                "description": "Severity of the violation",
                            },
                            "message": {
                                "type": "string",
                                "description": "Description of the violation",
                            },
                            "snippet": {
                                "type": "string",
                                "description": "The relevant code snippet (max 200 chars)",
                            },
                        },
                        "required": ["file_path", "line", "severity", "message"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": _FINALIZE_TOOL,
                    "description": "Call this ONLY when you have thoroughly checked the codebase for this check type and are ready to move on. Do NOT call this after just one tool call.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "Brief summary of what you found for this check",
                            },
                        },
                        "required": ["summary"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def _field(self, item: Any, name: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    async def _run_tool(
        self,
        fn_name: str,
        args: dict,
        project_path: str,
    ) -> tuple[dict, str]:
        try:
            if fn_name == "list_files":
                directory = args.get("directory", ".")
                limit = args.get("limit", 100)
                full_dir = os.path.join(project_path, directory)
                entries = []
                if os.path.exists(full_dir) and os.path.isdir(full_dir):
                    for idx, entry in enumerate(sorted(os.listdir(full_dir))):
                        if idx >= limit:
                            break
                        full_entry = os.path.join(full_dir, entry)
                        is_dir = os.path.isdir(full_entry)
                        if is_dir and entry in _SKIP_DIRS:
                            continue
                        entries.append({"name": entry, "type": "directory" if is_dir else "file"})
                summary = f"listed {len(entries)} entries in {directory}"
                return {"entries": entries, "summary": summary}, summary

            elif fn_name == "read_file":
                path = args.get("path")
                full_path = os.path.join(project_path, path)
                if not os.path.exists(full_path):
                    return {"error": f"file not found: {path}"}, "file not found"
                with open(full_path, "r", errors="replace") as f:
                    lines = f.readlines()
                start = args.get("start_line", 1)
                end = args.get("end_line", min(start + 200, len(lines)))
                content = "".join(lines[start - 1 : end])
                summary = f"read {path}:{start}-{end} ({end - start + 1} lines)"
                return {
                    "file_path": path,
                    "content": content,
                    "total_lines": len(lines),
                    "summary": summary,
                }, summary

            elif fn_name == "glob_files":
                pattern = args.get("pattern", "*")
                limit = args.get("limit", 100)
                full_pattern = os.path.join(project_path, pattern)
                matches = glob_module.glob(full_pattern, recursive=True)[:limit]
                entries = [{"path": os.path.relpath(f, project_path)} for f in matches]
                summary = f"found {len(entries)} files matching {pattern}"
                return {"entries": entries, "summary": summary}, summary

            elif fn_name == "grep_files":
                query = args.get("query")
                file_pattern = args.get("pattern", "*")
                limit = args.get("limit", 50)
                try:
                    res = subprocess.run(
                        ["grep", "-rn", "--include", file_pattern, query, project_path],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    lines = [l for l in res.stdout.splitlines() if l.strip()][:limit]
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    # Fallback: use Python grep
                    lines = []
                    for root, dirs, fnames in os.walk(project_path):
                        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                        for fname in fnames:
                            fpath = os.path.join(root, fname)
                            try:
                                with open(fpath, "r", errors="replace") as f:
                                    for i, line in enumerate(f, 1):
                                        if query.lower() in line.lower():
                                            rel = os.path.relpath(fpath, project_path)
                                            lines.append(f"{rel}:{i}:{line.rstrip()[:200]}")
                                            if len(lines) >= limit:
                                                break
                            except Exception:
                                pass
                            if len(lines) >= limit:
                                break
                summary = f"found {len(lines)} matches for '{query}'"
                return {"results": lines, "summary": summary}, summary

            elif fn_name == "record_finding":
                return {
                    "recorded": True,
                    "finding": {
                        "file_path": args.get("file_path"),
                        "line": args.get("line", 0),
                        "severity": args.get("severity", "medium"),
                        "message": args.get("message"),
                        "snippet": args.get("snippet", ""),
                    },
                    "summary": f"recorded finding: {args.get('message', '')[:80]}",
                }, f"recorded finding at {args.get('file_path')}:{args.get('line')}"

            else:
                return {"error": f"Unknown tool {fn_name}"}, "unknown tool"

        except Exception as e:
            return {"error": str(e)}, "tool error"

    async def _emit_step(self, step: ComplianceStep) -> None:
        if self._step_callback:
            await self._step_callback(step)

    async def run_check(
        self,
        check_type: str,
        project_id: str,
        project_path: str,
        round_offset: int = 0,
    ) -> tuple[list[ComplianceFinding], list[ComplianceStep], int]:
        """
        Run a single compliance check type.

        Returns:
            (findings, steps, rounds_used)
        """
        tools = self._tool_definitions()
        system_prompt = self._build_system_prompt(check_type).format(project_path=project_path)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Run the {_CHECK_REGISTRY.get(check_type, {}).get('name', check_type)} check "
                    f"on the codebase at {project_path}. "
                    "Explore the project structure, find relevant files, read them, "
                    "and record any violations you discover. "
                    "Call finalize_check() when you are done."
                ),
            },
        ]

        all_findings: list[ComplianceFinding] = []
        steps: list[ComplianceStep] = []
        final_summary = ""
        rounds_used = 0

        for round_idx in range(self._max_tool_rounds):
            round_num = round_idx + 1
            rounds_used = round_num

            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.1,
                )
            except Exception as e:
                logger.error("Compliance agent LLM error for %s: %s", check_type, e)
                await self._emit_step(ComplianceStep(
                    round=round_num + round_offset,
                    action="observation",
                    check_type=check_type,
                    message=f"LLM API error: {e}",
                    findings=[],
                ))
                break

            response_message = response.choices[0].message
            assistant_content = response_message.content or ""
            tool_calls = response_message.tool_calls

            # Check if model called finalize_check
            if tool_calls:
                for tc in tool_calls:
                    if tc.function.name == _FINALIZE_TOOL:
                        try:
                            args = json.loads(tc.function.arguments)
                            final_summary = args.get("summary", "").strip()
                        except Exception:
                            final_summary = assistant_content.strip()
                        steps.append(ComplianceStep(
                            round=round_num + round_offset,
                            action="check_complete",
                            check_type=check_type,
                            message=final_summary or f"Completed {check_type} check",
                            findings=list(all_findings),
                        ))
                        await self._emit_step(steps[-1])
                        logger.info("Compliance check '%s' completed: %d findings", check_type, len(all_findings))
                        return all_findings, steps, rounds_used

            # Capture narration
            if assistant_content.strip():
                action = "plan" if tool_calls else "observation"
                step = ComplianceStep(
                    round=round_num + round_offset,
                    action=action,
                    check_type=check_type,
                    message=assistant_content,
                    findings=[],
                )
                steps.append(step)
                await self._emit_step(step)

            # Append assistant message to context
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

            # No tool calls -> re-prompt
            if not tool_calls:
                messages.append({
                    "role": "user",
                    "content": (
                        "If you need more information to find violations, call a tool "
                        "(list_files, read_file, glob_files, grep_files, record_finding). "
                        "If you are done checking, call finalize_check(). "
                        "Do NOT just talk — use tools."
                    ),
                })
                continue

            # Process each tool call
            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                if fn_name == _FINALIZE_TOOL:
                    continue
                fn_args_str = tool_call.function.arguments

                try:
                    args = json.loads(fn_args_str)
                except Exception as e:
                    logger.warning("Failed to parse tool arguments for %s: %s", fn_name, e)
                    tool_content = json.dumps({"error": f"Invalid JSON arguments: {e}"})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_content,
                    })
                    continue

                logger.info("Compliance agent tool call: %s(%s)", fn_name, {k: v for k, v in args.items() if k != "content"})

                tool_output, tool_summary = await self._run_tool(
                    fn_name, args, project_path
                )

                if fn_name == "record_finding":
                    suggestion = _CHECK_SUGGESTIONS.get(check_type, "")
                    finding = ComplianceFinding(
                        file_path=args.get("file_path", ""),
                        line=args.get("line", 0),
                        severity=args.get("severity", "medium"),
                        check_type=check_type,
                        category=_CHECK_REGISTRY.get(check_type, {}).get("category", "security"),
                        message=args.get("message", ""),
                        snippet=args.get("snippet", ""),
                        suggestion=suggestion,
                    )
                    all_findings.append(finding)
                    step = ComplianceStep(
                        round=round_num + round_offset,
                        action="finding",
                        check_type=check_type,
                        tool_name=fn_name,
                        tool_summary=tool_summary,
                        message=args.get("message", ""),
                        findings=[finding],
                    )
                    steps.append(step)
                    await self._emit_step(step)
                else:
                    step = ComplianceStep(
                        round=round_num + round_offset,
                        action="tool_call",
                        check_type=check_type,
                        tool_name=fn_name,
                        tool_summary=tool_summary,
                        message=assistant_content[:200] if assistant_content else "",
                        findings=[],
                    )
                    steps.append(step)
                    await self._emit_step(step)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_output),
                })

        # Exhausted rounds without finalize -> force complete
        if not final_summary:
            final_summary = f"Exhausted {self._max_tool_rounds} rounds. Found {len(all_findings)} violation(s)."
        step = ComplianceStep(
            round=rounds_used + round_offset,
            action="check_complete",
            check_type=check_type,
            message=final_summary,
            findings=list(all_findings),
        )
        steps.append(step)
        await self._emit_step(step)

        return all_findings, steps, rounds_used

    async def run_all(
        self,
        project_id: str,
        project_path: str,
        selected_checks: list[str] | None = None,
    ) -> tuple[list[ComplianceFinding], list[ComplianceStep], dict[str, str]]:
        """
        Run all selected compliance checks sequentially.

        Returns:
            (all_findings, all_steps, check_summaries)
        """
        if selected_checks is None:
            selected_checks = list(_CHECK_REGISTRY.keys())

        all_findings: list[ComplianceFinding] = []
        all_steps: list[ComplianceStep] = []
        check_summaries: dict[str, str] = {}
        total_rounds = 0

        # Emit a plan step indicating which checks will run
        plan_step = ComplianceStep(
            round=1,
            action="plan",
            check_type="_overall",
            message=f"Starting compliance scan with {len(selected_checks)} check(s): {', '.join(selected_checks)}",
            findings=[],
        )
        all_steps.append(plan_step)
        await self._emit_step(plan_step)
        total_rounds += 1

        for i, check_type in enumerate(selected_checks):
            check_name = _CHECK_REGISTRY.get(check_type, {}).get("name", check_type)

            # Emit check start step
            start_step = ComplianceStep(
                round=total_rounds + 1,
                action="plan",
                check_type=check_type,
                message=f"Starting check: {check_name}",
                findings=[],
            )
            all_steps.append(start_step)
            await self._emit_step(start_step)
            total_rounds += 1

            findings, steps, used = await self.run_check(
                check_type=check_type,
                project_id=project_id,
                project_path=project_path,
                round_offset=total_rounds,
            )

            all_findings.extend(findings)
            all_steps.extend(steps)
            total_rounds += used

            # Extract summary from the last step
            for s in reversed(steps):
                if s.action == "check_complete":
                    check_summaries[check_type] = s.message
                    break

        # Emit final step
        final_step = ComplianceStep(
            round=total_rounds + 1,
            action="final",
            check_type="_overall",
            message=f"Compliance scan complete. Found {len(all_findings)} violation(s) across {len(selected_checks)} check(s).",
            findings=list(all_findings),
        )
        all_steps.append(final_step)
        await self._emit_step(final_step)

        return all_findings, all_steps, check_summaries
