# CodeGuardian Context-YAML Implementation Plan

## Executive Summary

This document describes a fundamental architectural shift in CodeGuardian's code intelligence system. The current vector embedding-based indexing approach is to be replaced with a self-documenting context management system that leverages Large Language Models to generate and maintain `.context.yaml` files in each directory of a codebase.

The new approach eliminates the need for chunking code into vectors, avoids constant re-indexing as codebases evolve, and provides more meaningful, human-understandable context for the QnA system. The system will automatically analyze directories, generate descriptions, and track changes through git integration, creating a growing knowledge base that evolves alongside the codebase.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Proposed Solution](#proposed-solution)
3. [Architecture Overview](#architecture-overview)
4. [YAML Schema Specification](#yaml-schema-specification)
5. [Component Design](#component-design)
6. [Implementation Phases](#implementation-phases)
7. [Trigger Mechanisms](#trigger-mechanisms)
8. [Retrieval System](#retrieval-system)
9. [Data Flow Diagrams](#data-flow-diagrams)
10. [Configuration](#configuration)
11. [Code Removal/Refactoring](#code-removal-and-refactoring)
12. [Testing Strategy](#testing-strategy)
13. [Migration Path](#migration-path)
14. [Future Considerations](#future-considerations)

---

## Problem Statement

### Limitations of Vector-Based Indexing

The current CodeGuardian implementation uses vector embeddings to index codebases:

1. **Loss of Context**: Code chunks lose their relationship to surrounding files and directories. A function extracted from its module loses the context of why it exists.

2. **Frequent Rechunking**: As codebases evolve through the SDLC, the same chunk boundaries become invalid, requiring complete re-indexing.

3. **No Git Integration**: Vector chunks don't track the history of changes. There's no understanding of what changed, when, and why.

4. **Bloat and Noise**: Everything gets indexed—boilerplate, generated code, tests, dependencies—without prioritization.

5. **Hard to Debug**: When retrieval fails, it's difficult to understand why. The "black box" nature of vector similarity makes troubleshooting difficult.

6. **No Human Readability**: Vector embeddings are not human-readable or editable. Users cannot fine-tune or correct the index.

### The Core Insight

Not all code is equally worth indexing. Core business logic, API interfaces, and configuration schemas are valuable. Generated code, build artifacts, and boilerplate are noise. Rather than fighting with chunk boundaries, we should capture the *intent* and *purpose* of directories and files through LLM analysis.

---

## Proposed Solution

### Paradigm Shift: From Searchable Vectors to Self-Documenting Context

Instead of chunking code into vectors, we will:

1. **Analyze directories** with an LLM to understand their purpose and contents
2. **Generate `.context.yaml`** files in each directory describing:
   - What the directory contains and its purpose
   - What each file does and its type
   - What subdirectories exist and their purposes
   - Key APIs or exports from important files
3. **Track changes** through git integration:
   - Recent commits affecting the directory
   - Staged changes (uncommitted)
   - Unstaged changes (working directory)
   - File renames, moves, and deletions
4. **Auto-commit** the context YAML files alongside the code changes
5. **Retrieve context** by searching YAML files and feeding relevant sections to the QnA LLM

### Why This Works Better

| Vector Chunking | Context YAML |
|-----------------|--------------|
| Lose file relationships | Preserve directory structure |
| Lose intent/context | LLM explains purpose |
| Fragments git history | Git-integrated by design |
| Needs full reindex | Incrementally updated |
| Bloated retrieval | Targeted, focused |
| Hard to debug | Human-readable/editable |

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CODEGUARDIAN ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐              ┌──────────────────────────────────┐    │
│  │   GIT LAYER     │              │       CONTEXT MANAGEMENT         │    │
│  │                 │              │                                  │    │
│  │  ┌───────────┐  │              │  ┌────────────────────────────┐ │    │
│  │  │Local Hooks│◀─┼──────────────┼──│  Context Service            │ │    │
│  │  └───────────┘  │              │  │  - analyze_directory()     │ │    │
│  │  ┌───────────┐  │              │  │  - update_on_changes()     │ │    │
│  │  │GitHub     │◀─┼──────────────┼──│  - read_context()           │ │    │
│  │  │Webhook    │  │              │  │  - delete_context()        │ │    │
│  │  └───────────┘  │              │  │  - search_contexts()       │ │    │
│  │  ┌───────────┐  │              │  └────────────────────────────┘ │    │
│  │  │Git Service│  │              │           │                     │    │
│  │  └───────────┘  │              │           ▼                     │    │
│  └────────┬────────┘              │  ┌────────────────────────────┐ │    │
│           │                        │  │   Context YAML Files       │ │    │
│           │                        │  │   (per directory)          │ │    │
│           │                        │  │   .context.yaml            │ │    │
│           ▼                        │  └────────────────────────────┘ │    │
│  ┌─────────────────┐              └──────────────────────────────────┘    │
│  │  LLM CLIENT     │                             │                        │
│  │  (NVIDIA NIM)   │                             ▼                        │
│  └─────────────────┘              ┌──────────────────────────────────┐    │
│           │                       │       RETRIEVAL SYSTEM          │    │
│           └───────────────────────│  - search_contexts()           │    │
│                                   │  - retrieve_relevant()        │    │
│                                   │  - build_context_prompt()     │    │
│                                   └──────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
project-root/
├── .context.yaml                 # Root directory context (optional)
├── src/
│   ├── .context.yaml            # Generated: src/ directory context
│   ├── api/
│   │   ├── .context.yaml        # Generated: api/ directory context
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── models/
│   │   ├── .context.yaml
│   │   └── user.py
│   └── utils/
│       ├── .context.yaml
│       └── helpers.py
├── tests/
│   ├── .context.yaml
│   └── test_routes.py
└── ... more directories ...
```

---

## YAML Schema Specification

### File Structure

Each `.context.yaml` file follows this schema:

```yaml
# Required: The directory path this file describes (relative to repo root)
directory: src/api

# Required: A description of what this directory contains and its purpose
description: |
  REST API layer handling HTTP requests and responses.
  Contains FastAPI route handlers, Pydantic schemas for validation,
  and middleware components for authentication and logging.
  This is the primary entry point for all client-facing APIs.

# Optional: List of files in this directory with their purposes
files:
  - name: routes.py
    purpose: FastAPI route definitions and endpoint handlers
    type: api
    key_apis:
      - create_user
      - get_user
      - update_user
      - delete_user

  - name: schemas.py
    purpose: Pydantic models for request/response validation
    type: schema
    key_apis:
      - UserCreate
      - UserResponse
      - UserUpdate

  - name: middleware.py
    purpose: Authentication and logging middleware components
    type: middleware
    key_apis:
      - auth_middleware
      - logging_middleware

# Optional: List of subdirectories with their purposes
subdirectories:
  - name: v1
    purpose: API version 1 endpoints (deprecated, use v2)

  - name: v2
    purpose: Current API version 2 endpoints with improved schema

  - name: internal
    purpose: Internal helper modules not exposed as public API

# Optional: Track changes to this directory over time
changes:
  # Committed changes (from git history)
  recent:
    - commit: abc123def456
      message: "Added pagination to user list endpoint"
      files: [routes.py]
      date: "2025-01-15T10:30:00Z"
      author: john@example.com

    - commit: def456abc789
      message: "Refactored auth middleware for better performance"
      files: [middleware.py, schemas.py]
      date: "2025-01-10T14:22:00Z"
      author: jane@example.com

  # Uncommitted staged changes
  staged:
    - file: routes.py
      description: "Added rate limiting to create_user endpoint"
      diff: "..."

  # Uncommitted unstaged changes
  unstaged:
    - file: schemas.py
      description: "Modified email validation regex"

  # File changes (renames, moves, deletions)
  file_changes:
    - type: renamed
      from: auth.py
      to: authentication.py
      commit: ghi789jkl012

    - type: removed
      file: legacy.py
      commit: mno345pqr678
      note: "Removed deprecated authentication handler"
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `directory` | string | Yes | Relative path from repo root |
| `description` | string | Yes | Multi-line description of directory purpose |
| `files` | array | No | List of files with metadata |
| `files[].name` | string | Yes | File name (not full path) |
| `files[].purpose` | string | Yes | What the file does |
| `files[].type` | string | Yes | Type: api, schema, util, test, model, middleware, config, etc. |
| `files[].key_apis` | array | No | Key functions/classes/exports |
| `subdirectories` | array | No | List of subdirectories |
| `subdirectories[].name` | string | Yes | Subdirectory name |
| `subdirectories[].purpose` | string | Yes | Purpose of subdirectory |
| `changes` | object | No | Change tracking |
| `changes.recent` | array | No | Last N committed changes |
| `changes.staged` | array | No | Currently staged changes |
| `changes.unstaged` | array | No | Unstaged working directory changes |
| `changes.file_changes` | array | No | Renames, moves, deletions |

---

## Component Design

### 1. Data Models

**File**: `server/models/context_models.py`

```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class FileEntry:
    """Represents a file within a directory context."""
    name: str
    purpose: str
    type: str  # api, schema, util, test, model, middleware, config, etc.
    key_apis: list[str] = field(default_factory=list)


@dataclass
class SubdirectoryEntry:
    """Represents a subdirectory within a directory context."""
    name: str
    purpose: str


@dataclass
class RecentChange:
    """Represents a committed change to this directory."""
    commit: str
    message: str
    files: list[str]
    date: str
    author: str


@dataclass
class UncommittedChange:
    """Represents an uncommitted change (staged or unstaged)."""
    file: str
    description: str
    diff: Optional[str] = None


@dataclass
class FileChange:
    """Represents a file rename, move, or deletion."""
    type: str  # renamed, moved, removed
    from_path: Optional[str] = None
    to_path: Optional[str] = None
    file: Optional[str] = None
    commit: Optional[str] = None
    note: Optional[str] = None


@dataclass
class DirectoryContext:
    """Complete context for a directory."""
    directory: str
    description: str
    files: list[FileEntry] = field(default_factory=list)
    subdirectories: list[SubdirectoryEntry] = field(default_factory=list)
    changes: dict[str, list] = field(default_factory=dict)

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        pass

    @classmethod
    def from_yaml(cls, yaml_str: str, path: str) -> "DirectoryContext":
        """Deserialize from YAML string."""
        pass
```

### 2. Context Service

**File**: `server/services/context_service.py`

The Context Service is the core component for managing `.context.yaml` files.

```python
class ContextService:
    """Service for managing directory context YAML files."""

    def __init__(self, llm_client: LLMClient, git_service: GitService):
        self.llm = llm_client
        self.git = git_service


    async def analyze_directory(self, dir_path: str, repo_path: str) -> DirectoryContext:
        """
        Analyze a directory and generate its context YAML.
        
        Process:
        1. List all files and subdirectories
        2. Get git history for the directory (last N commits)
        3. Optionally read a sample of file contents for context
        4. Prompt LLM to generate directory description and file metadata
        5. Create and write .context.yaml
        
        Returns:
            DirectoryContext object
        """
        pass


    async def update_on_changes(
        self,
        dir_path: str,
        repo_path: str,
        changes: dict
    ) -> DirectoryContext:
        """
        Update an existing context file with new changes.
        
        Process:
        1. Read existing .context.yaml
        2. Get git diff for changed files in this directory
        3. Get staged/unstaged file lists
        4. Prompt LLM to append to changes section
        5. Write updated .context.yaml
        6. Auto-commit the changes
        
        Returns:
            Updated DirectoryContext object
        """
        pass


    async def read_context(self, dir_path: str) -> Optional[DirectoryContext]:
        """
        Read and parse an existing .context.yaml file.
        
        Returns:
            DirectoryContext or None if file doesn't exist
        """
        pass


    async def delete_context(self, dir_path: str) -> bool:
        """
        Remove .context.yaml when a directory is deleted.
        
        Returns:
            True if deleted, False if file didn't exist
        """
        pass


    def search_contexts(
        self,
        query: str,
        repo_path: str,
        max_results: int = 5
    ) -> list[ContextSearchResult]:
        """
        Search for relevant context files.
        
        Uses hybrid approach:
        - Path-based matching (exact or prefix)
        - Keyword search in descriptions and purposes
        
        Returns:
            List of matching context files with relevance scores
        """
        pass


    async def _generate_initial_context(
        self,
        dir_path: str,
        files: list[str],
        subdirs: list[str],
        git_history: list[CommitInfo]
    ) -> DirectoryContext:
        """Internal: Call LLM to generate initial context."""
        pass


    async def _generate_update(
        self,
        existing: DirectoryContext,
        new_changes: dict
    ) -> DirectoryContext:
        """Internal: Call LLM to update existing context."""
        pass


    async def _auto_commit(self, dir_path: str, context: DirectoryContext) -> str:
        """
        Auto-commit the .context.yaml file.
        
        Uses git add + git commit with appropriate message.
        
        Returns:
            Commit SHA of the auto-commit
        """
        pass
```

### 3. Git Service Extensions

**File**: `server/services/git_service.py` (extend existing)

New methods to add to the existing GitService:

```python
class GitService:
    # ... existing methods ...

    async def get_directory_history(
        self,
        dir_path: str,
        limit: int = 10
    ) -> list[CommitInfo]:
        """
        Get commits that touched files in a specific directory.
        
        Args:
            dir_path: Relative path to directory
            limit: Maximum number of commits to return
        
        Returns:
            List of CommitInfo objects for the directory
        """
        pass


    async def get_staged_files(self, repo_path: str) -> list[str]:
        """
        Get list of staged files in the repository.
        
        Returns:
            List of file paths that are staged
        """
        pass


    async def get_unstaged_files(self, repo_path: str) -> list[str]:
        """
        Get list of unstaged modified files in the repository.
        
        Returns:
            List of file paths that have uncommitted changes
        """
        pass


    async def get_directory_diff(self, dir_path: str) -> str:
        """
        Get combined diff for all changes in a directory.
        
        Returns:
            Unified diff string for the directory
        """
        pass


    async def get_file_renames(self, repo_path: str) -> list[dict]:
        """
        Detect file renames and moves since last context update.
        
        Returns:
            List of dicts with type, from, to
        """
        pass
```

### 4. Retrieval Service

**File**: `server/services/retrieval_service.py`

```python
@dataclass
class ContextSnippet:
    """A relevant snippet from a context file."""
    directory: str
    section: str  # description, files, subdirectories, changes
    content: str
    relevance_score: float


class RetrievalService:
    """Service for retrieving relevant context for queries."""

    def __init__(self, context_service: ContextService):
        self.context = context_service


    async def retrieve_for_query(
        self,
        query: str,
        repo_path: str,
        max_contexts: int = 5
    ) -> list[ContextSnippet]:
        """
        Retrieve relevant context snippets for a user query.
        
        Process:
        1. Search for relevant context.yaml files
        2. Extract relevant sections (description, files matching query)
        3. Rank by relevance
        4. Return top N snippets
        
        Returns:
            List of ContextSnippet objects
        """
        pass


    async def build_context_prompt(
        self,
        query: str,
        repo_path: str
    ) -> str:
        """
        Build a prompt context for the QnA LLM.
        
        Combines relevant context snippets into a prompt format
        that the LLM can use to answer the user's question.
        
        Returns:
            Formatted prompt string
        """
        pass


    def _search_by_path(self, query: str, repo_path: str) -> list[str]:
        """Find context files by path matching."""
        pass


    def _search_by_keywords(self, query: str, repo_path: str) -> list[tuple[str, float]]:
        """Find context files by keyword search."""
        pass


    def _extract_relevant_sections(
        self,
        context: DirectoryContext,
        query: str
    ) -> list[ContextSnippet]:
        """Extract sections relevant to the query."""
        pass
```

### 5. Trigger Handlers

#### Local Git Hooks

**File**: `cgctl/commands/hooks.py` (new command)

Installable git hooks that trigger context updates:

```python
# .git/hooks/pre-commit (generated)
#!/bin/bash
# Pre-commit hook - analyze staged changes

STAGED_FILES=$(git diff --cached --name-only)
for file in $STAGED_FILES; do
    dir=$(dirname "$file")
    curl -X POST "http://localhost:8742/api/context/update" \
        -H "Content-Type: application/json" \
        -d "{\"repo_path\": \"$PWD\", \"directory\": \"$dir\", \"change_type\": \"staged\"}"
done
```

```python
# .git/hooks/post-commit (generated)
#!/bin/bash
# Post-commit hook - analyze newly committed changes

COMMIT_FILES=$(git diff-tree --no-commit-id -r --name-only HEAD)
for file in $COMMIT_FILES; do
    dir=$(dirname "$file")
    curl -X POST "http://localhost:8742/api/context/update" \
        -H "Content-Type: application/json" \
        -d "{\"repo_path\": \"$PWD\", \"directory\": \"$dir\", \"change_type\": \"committed\"}"
done
```

#### GitHub Webhook Handler

**File**: `server/routes/review.py` (enhance existing)

```python
@router.post("/webhook")
async def github_webhook(request: Request, app: FastAPI):
    """
    Handle GitHub webhook events.
    
    Currently handles:
    - pull_request: Logged, manual trigger for review
    - push: NEW - Trigger context updates
    """
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")

    if event_type == "push":
        # Get list of changed files from payload
        # Group by directory
        # Trigger context update for each affected directory
        # Auto-commit updated YAMLs
        
        for commit in payload.get("commits", []):
            for file_path in commit.get("added", []) + commit.get("modified", []):
                dir_path = os.path.dirname(file_path)
                await context_service.update_on_changes(
                    dir_path=dir_path,
                    repo_path=repo_path,
                    changes={"type": "committed", "commit": commit}
                )
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1)

**Objective**: Create the data models and basic YAML read/write functionality.

**Tasks**:

1. Create `server/models/context_models.py`
   - Define all dataclasses: FileEntry, SubdirectoryEntry, RecentChange, UncommittedChange, FileChange, DirectoryContext
   - Implement `to_yaml()` and `from_yaml()` methods
   - Add YAML serialization/deserialization

2. Create `server/services/context_service.py` (stub)
   - Initialize with LLM client and git service
   - Implement basic `read_context()` method
   - Implement `delete_context()` method

3. Create basic YAML file in a test directory
   - Manually create a `.context.yaml` file
   - Verify it can be parsed correctly

4. Add type hints and validation

**Deliverables**:
- `server/models/context_models.py` module
- `server/services/context_service.py` with basic read/write
- Working YAML parsing test

**Testing**:
- Unit tests for YAML serialization/deserialization
- Test with various valid and invalid YAML inputs

---

### Phase 2: LLM Integration (Week 1-2)

**Objective**: Connect the LLM to generate and update context YAMLs.

**Tasks**:

1. Design prompt templates for context generation
   - Initial analysis prompt
   - Update prompt for changes

2. Implement `analyze_directory()` in ContextService
   - List files and subdirectories
   - Get git history for directory
   - Call LLM with file list and history
   - Parse LLM response into DirectoryContext

3. Implement `update_on_changes()` in ContextService
   - Read existing context
   - Get new changes (staged/unstaged/committed)
   - Call LLM to append changes
   - Write updated context

4. Add configuration for prompt templates
   - Temperature, max tokens settings
   - Retry logic for LLM failures

5. Handle edge cases
   - Empty directories
   - Directories with only subdirectories
   - Directories with many files (batch LLM calls)

**Deliverables**:
- Working `analyze_directory()` method
- Working `update_on_changes()` method
- Prompt templates in config or as constants

**Testing**:
- Run on sample directories
- Verify output quality (review YAML files)
- Test with various directory structures

---

### Phase 3: Git Integration (Week 2)

**Objective**: Extend GitService to support directory-level operations.

**Tasks**:

1. Implement `get_directory_history()`
   - Use GitPython to get commits for a directory
   - Limit to last N commits
   - Return as list of CommitInfo

2. Implement `get_staged_files()`
   - Use `git diff --cached --name-only`
   - Return list of staged file paths

3. Implement `get_unstaged_files()`
   - Use `git diff --name-only`
   - Return list of unstaged file paths

4. Implement `get_directory_diff()`
   - Get diff for all files in a directory
   - Combine into unified diff string

5. Implement `get_file_renames()`
   - Compare current state with last known state
   - Detect renames and moves

6. Update ContextService to use these new methods

**Deliverables**:
- Extended GitService with directory methods
- Integrated with ContextService
- Auto-commit functionality

**Testing**:
- Test on various git states (clean, staged, unstaged)
- Test with different branch histories
- Test auto-commit functionality

---

### Phase 4: Triggers (Week 2-3)

**Objective**: Implement trigger mechanisms for both local and remote scenarios.

**Tasks**:

1. Create hook installation command
   - `cgctl hooks install` command
   - Generate pre-commit and post-commit hooks
   - Support uninstall: `cgctl hooks uninstall`

2. Enhance webhook handler
   - Add push event handling
   - Group changed files by directory
   - Trigger context updates

3. Create API endpoint for manual triggers
   - POST `/api/context/update`
   - GET `/api/context/{directory}`
   - DELETE `/api/context/{directory}`

4. Add auto-commit logic
   - Stage .context.yaml files
   - Create commit with appropriate message
   - Handle merge conflicts gracefully

5. Add error handling
   - What if LLM fails?
   - What if git commit fails?
   - Retry logic

**Deliverables**:
- `cgctl hooks` command
- Enhanced webhook handler
- API endpoints for context management
- Auto-commit working

**Testing**:
- Full local commit → update → commit flow
- Webhook push → update flow
- Error scenarios

---

### Phase 5: Retrieval (Week 3)

**Objective**: Implement the retrieval system for QnA.

**Tasks**:

1. Create `server/services/retrieval_service.py`

2. Implement `search_contexts()`
   - Path-based matching
   - Keyword search in descriptions

3. Implement `retrieve_for_query()`
   - Find relevant context files
   - Extract relevant sections
   - Rank by relevance

4. Implement `build_context_prompt()`
   - Format context for LLM consumption
   - Include instructions for using context

5. Integrate with QnA flow
   - Modify `server/routes/qa.py`
   - Add context retrieval to prompt

6. Optimize retrieval
   - Caching of context files
   - Index for faster searching

**Deliverables**:
- Working RetrievalService
- Integrated with QnA
- Working query → context flow

**Testing**:
- Test various query types
- Verify relevant contexts returned
- Verify QnA uses context correctly

---

### Phase 6: Cleanup (Week 3-4)

**Objective**: Remove vector embedding code and finalize.

**Tasks**:

1. Remove embedding service
   - Delete `server/services/embedding_service.py`
   - Remove from imports in other files

2. Remove ChromaDB integration
   - Remove ChromaDB from requirements.txt
   - Remove ChromaDB imports and usage
   - Delete `chroma_data/` if exists

3. Remove Supabase vector storage
   - Remove vector-related Supabase code
   - Keep Supabase for other uses if applicable

4. Remove indexing routes
   - Modify `server/routes/indexing.py`
   - Remove chunking logic
   - Keep file discovery if needed for context

5. Update configuration
   - Remove embedding-related config in `server/config.py`
   - Add context-yaml related config

6. Update requirements.txt
   - Remove chromadb
   - Keep gitpython (needed for git integration)

7. Update documentation
   - Update README with new approach
   - Update API documentation

**Deliverables**:
- Clean codebase without vector logic
- Updated configuration
- Updated documentation

**Testing**:
- Verify no ChromaDB references remain
- Verify app starts without embedding dependencies
- Verify all features still work

---

## Trigger Mechanisms

### 1. Local Git Hooks

**Installation Flow**:

```
User runs: cgctl hooks install
           │
           ▼
┌─────────────────────────┐
│ Generate pre-commit     │
│ and post-commit hooks  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Write to .git/hooks/   │
│ (with executable perms)│
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Hooks installed        │
│ successfully           │
└─────────────────────────┘
```

**Pre-Commit Flow**:

```
User runs: git commit -m "..."
          │
          ▼
┌─────────────────────────┐
│ pre-commit hook fires  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Get staged files       │
│ git diff --cached      │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Group by directory     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ For each affected dir: │
│ 1. Get current context │
│ 2. Get staged changes  │
│ 3. Update .context.yaml│
│ 4. Stage the YAML     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ git commit proceeds    │
│ (includes YAML changes)│
└─────────────────────────┘
```

**Post-Commit Flow**:

```
User runs: git push
          │
          ▼
┌─────────────────────────┐
│ post-commit hook fires │
│ (after successful commit)│
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Get committed files    │
│ git diff-tree --name-only│
│ HEAD~1..HEAD           │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Group by directory     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ For each affected dir: │
│ 1. Get current context │
│ 2. Get commit changes  │
│ 3. Update .context.yaml│
│ 4. Auto-commit YAML    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Done (background)      │
└─────────────────────────┘
```

### 2. GitHub Webhook

**Push Event Flow**:

```
GitHub receives push
        │
        ▼
┌─────────────────────────┐
│ Send webhook to        │
│ CodeGuardian server   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Validate webhook       │
│ (HMAC signature)       │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Parse payload          │
│ - commits[]            │
│ - changed files        │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ For each commit:       │
│   For each changed file│
│     Get directory      │
│     Trigger update     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ ContextService         │
│ update_on_changes()   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Auto-commit .context   │
│ yaml files             │
└─────────────────────────┘
```

### 3. Manual Trigger

Users can also manually trigger context updates:

```bash
# Update specific directory
curl -X POST "http://localhost:8742/api/context/update" \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/path/to/repo", "directory": "src/api"}'

# Force re-analyze entire directory
curl -X POST "http://localhost:8742/api/context/analyze" \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/path/to/repo", "directory": "src/api"}'
```

---

## Retrieval System

### Retrieval Flow

```
User asks: "How does authentication work in this codebase?"
            │
            ▼
┌─────────────────────────┐
│ QnA handler receives   │
│ question               │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ RetrievalService       │
│ retrieve_for_query()  │
└────────────┬────────────┘
             │
      ┌──────┴──────┐
      │             │
      ▼             ▼
┌───────────┐ ┌─────────────┐
│Path-based │ │ Keyword     │
│ matching  │ │ search      │
└─────┬─────┘ └──────┬──────┘
      │              │
      └──────┬───────┘
             │
             ▼
┌─────────────────────────┐
│ Combine results        │
│ and rank by relevance  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Extract relevant       │
│ sections from YAMLs   │
│ - description          │
│ - relevant files       │
│ - recent changes       │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Build context prompt   │
│ for QnA LLM            │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Call QnA LLM with      │
│ question + context     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Return answer to user  │
└─────────────────────────┘
```

### Example Context Prompt

When user asks "How does authentication work?", the prompt sent to QnA LLM might include:

```
=== CONTEXT FROM CODEBASE ===

## Directory: src/auth

Description:
Authentication and authorization layer. Contains JWT token handling,
user session management, password hashing, and role-based access control.
This is the core security component for the entire application.

Files:
- auth.py: Main authentication handler, login/logout, JWT generation (type: api)
- middleware.py: Auth middleware for request validation (type: middleware)
- utils.py: Password hashing (bcrypt) and token validation utilities (type: util)
- models.py: User, Role, Permission Pydantic models (type: schema)

Key APIs:
- authenticate_user(), generate_jwt_token(), verify_token()
- require_permissions(), get_current_user()

Recent Changes:
- commit abc123: "Added refresh token support"
- commit def456: "Implemented role-based access control"

=== END CONTEXT ===

Question: How does authentication work in this codebase?

Provide a detailed explanation using the context above.
```

---

## Data Flow Diagrams

### Initial Indexing Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     INITIAL DIRECTORY INDEXING                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Start: User triggers initial index or first query on directory        │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. ContextService.analyze_directory(dir_path, repo_path)        │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 2. List files in directory                                      │   │
│  │    - os.listdir()                                              │   │
│  │    - Filter by supported extensions                            │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 3. List subdirectories                                         │   │
│  │    - os.listdir() filter dirs                                 │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 4. GitService.get_directory_history(dir_path)                 │   │
│  │    - Last 10 commits touching this directory                  │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 5. Build prompt for LLM:                                      │   │
│  │    Directory: {dir_path}                                      │   │
│  │    Files: {file_list}                                         │   │
│  │    Subdirs: {subdir_list}                                     │   │
│  │    History: {git_history}                                     │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 6. Call LLM (NVIDIA NIM)                                       │   │
│  │    - Model: qwen/qwen3-coder-480b-a35b-instruct              │   │
│  │    - System: Prompt template                                   │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 7. Parse LLM response into DirectoryContext                   │   │
│  │    - Extract description, files, subdirs                       │   │
│  │    - Validate required fields                                  │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 8. Write .context.yaml to directory                            │   │
│  │    - directory_path/.context.yaml                              │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 9. Auto-commit .context.yaml                                  │   │
│  │    - git add .context.yaml                                    │   │
│  │    - git commit -m "Add context for {dir_path}"              │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│                          Done                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Change Update Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     CHANGE UPDATE FLOW                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Trigger: Git hook fires OR webhook received                           │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. Determine change type (staged/unstaged/committed)           │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 2. Get list of affected directories                             │   │
│  │    - Parse changed files                                       │   │
│  │    - Extract unique directories                                 │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 3. For each affected directory:                                │   │
│  │                                                                         │
│  │    3a. Read existing .context.yaml                            │   │
│  │        - Load DirectoryContext                                 │   │
│  │                                                                  │   │
│  │    3b. Get changes for this directory                         │   │
│  │        - git diff (staged/unstaged)                            │   │
│  │        - git log (recent commits)                              │   │
│  │        - detect renames/moves                                  │   │
│  │                                                                  │   │
│  │    3c. Build update prompt                                    │   │
│  │        - Include existing context                             │   │
│  │        - Include new changes                                   │   │
│  │                                                                  │   │
│  │    3d. Call LLM to generate update                            │   │
│  │        - Append to changes.recent                             │   │
│  │        - Add to changes.staged/unstaged                        │   │
│  │        - Update file_changes for renames                      │   │
│  │                                                                  │   │
│  │    3e. Write updated .context.yaml                            │   │
│  │                                                                  │   │
│  │    3f. Auto-commit updated .context.yaml                      │   │
│  │        - git add .context.yaml                                 │   │
│  │        - git commit -m "Update context for {dir}"             │   │
│  │                                                                  │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                        │
│                               ▼                                        │
│                          Done                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### New Configuration Options

**File**: `server/config.py`

```python
# Context YAML Settings
context_yaml_enabled: bool = True
context_yaml_filename: str = ".context.yaml"
context_max_recent_changes: int = 20  # Keep last 20 commits in history
context_auto_commit: bool = True  # Auto-commit updated YAMLs

# LLM Context Generation
context_llm_model: str = "qwen/qwen3-coder-480b-a35b-instruct"
context_llm_temperature: float = 0.3  # Lower for more consistent output
context_llm_max_tokens: int = 2048

# Trigger Settings
hooks_install_path: str = ".git/hooks"
webhook_enabled: bool = True

# Retrieval Settings
retrieval_max_contexts: int = 5  # Max YAMLs to include in prompt
retrieval_max_snippets: int = 10  # Max snippets per context
```

### Removed Configuration

The following configuration options should be removed:

```python
# REMOVE:
nvidia_embed_model: str = "nvidia/nv-embedqa-e5-v5"  # No longer needed
chromadb_persist_dir: str = "./chroma_data"  # Remove ChromaDB
# Supabase vector - remove vector-related, keep for other uses
```

---

## Code Removal and Refactoring

### Files to Delete

| File | Reason |
|------|--------|
| `server/services/embedding_service.py` | No longer needed |
| `src/embedding_generator.py` | Legacy client-side code |
| `src/vector_store.py` | Legacy client-side code |
| `src/text_chunker.py` | No more chunking |

### Files to Modify

| File | Changes |
|------|---------|
| `server/routes/indexing.py` | Remove embedding logic, keep file discovery |
| `server/config.py` | Remove embedding config, add context config |
| `server/app.py` | Update imports, remove embedding initialization |
| `requirements.txt` | Remove chromadb, keep gitpython |

### Updated Import Structure

```python
# Before (with embeddings)
from server.services.embedding_service import EmbeddingService
from server.services.vector_service import VectorService

# After (context-based)
from server.services.context_service import ContextService
from server.services.retrieval_service import RetrievalService
```

---

## Testing Strategy

### Unit Tests

1. **Context Models**
   - Test YAML serialization/deserialization
   - Test validation of required fields
   - Test edge cases (empty values, special characters)

2. **Git Service Extensions**
   - Test directory history retrieval
   - Test staged/unstaged file detection
   - Test rename detection

3. **Context Service**
   - Test file read/write operations
   - Test search functionality

### Integration Tests

1. **Full Indexing Flow**
   - Create test directory with files
   - Run analyze_directory()
   - Verify .context.yaml created correctly
   - Verify auto-commit

2. **Change Update Flow**
   - Make changes to directory
   - Trigger update
   - Verify changes section updated
   - Verify auto-commit

3. **Retrieval Flow**
   - Index multiple directories
   - Query with various search terms
   - Verify relevant contexts returned

### End-to-End Tests

1. **Git Hook Flow**
   - Install hooks
   - Make commit
   - Verify context updated
   - Verify auto-commit

2. **Webhook Flow**
   - Send push event
   - Verify context updated
   - Verify auto-commit

3. **QnA with Context**
   - Index directory
   - Ask question about directory
   - Verify answer uses context

---

## Migration Path

### For Existing Users

1. **New installations**: Start with context-yaml by default
2. **Existing installations**:
   - Optional: Delete `chroma_data/` directory
   - Optional: Remove embedding settings from config
   - First query will trigger initial context generation

### Backward Compatibility

The system should be designed to work without any existing vector index. The context-yaml system is self-contained and doesn't depend on the old embedding system.

---

## Future Considerations

### Potential Enhancements (Out of Scope)

1. **Cross-directory context**: Track relationships between directories
2. **Code graph integration**: Link with existing knowledge graph
3. **Team sharing**: Store context in shared location (future Supabase use)
4. **Selective indexing**: Allow users to exclude directories
5. **Manual edits**: Allow users to manually edit .context.yaml files (with LLM merge)
6. **Bulk reanalysis**: Periodically refresh all context files

### Performance Considerations

1. **Rate limiting**: Handle LLM rate limits with retry and backoff
2. **Batching**: Batch multiple directories for initial indexing
3. **Caching**: Cache parsed YAML files to avoid repeated disk I/O
4. **Async processing**: All operations should be non-blocking

### Error Handling

1. **LLM failures**: Retry with exponential backoff, fallback to basic description
2. **Git failures**: Log error, skip auto-commit, notify user
3. **File write failures**: Log error, notify user, allow manual resolution

---

## Summary

This plan describes a comprehensive implementation of a context-yaml based code intelligence system that:

1. **Eliminates vector embeddings** - No more chunking and embedding code
2. **Uses LLM analysis** - Generates meaningful directory descriptions
3. **Integrates with git** - Tracks changes through commit history
4. **Auto-commits** - Seamlessly updates .context.yaml files
5. **Provides targeted retrieval** - Returns relevant context for queries
6. **Scales with the codebase** - No need for re-indexing, context evolves naturally

The implementation is divided into 6 phases over approximately 3-4 weeks, with clear deliverables and testing strategies at each phase.

---

*Document Version: 1.0*
*Last Updated: May 2026*