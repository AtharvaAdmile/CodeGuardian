# CodeGuardian

AI-powered institutional memory for codebases. CLI-first tool that preserves and surfaces engineering context.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Initialize project
cgctl init

# Index codebase
cgctl index

# Ask questions
cgctl ask "What does the authentication module do?"

# Fix code with AI agent
cgctl fix "fix the null check in utils.py"
```

## Configuration

Create a `.env` file with:

```bash
GOOGLE_API_KEY=your_gemini_api_key
SUPABASE_URL=https://cwsmzhneuykyojnwzufz.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

## Architecture

- **CLI**: Typer + Rich for beautiful terminal output
- **Database**: Supabase (PostgreSQL + pgvector)
- **LLM**: Google Gemini with Universal Caller pattern
- **Agent**: OpenSWE-style autonomous code agent
