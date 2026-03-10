# Configuration Examples

This document provides ready-to-use configuration examples for different use cases.

## Quick Start Configuration

Minimal `.env` file to get started:

```bash
# Required
GROQ_API_KEY=your_api_key_here

# That's it! All other settings use sensible defaults
```

## Development Environment

Configuration for active development with fast iteration:

```bash
# API Key
GROQ_API_KEY=your_api_key_here

# Fast model for quick feedback
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.5
DOC_LLM_MAX_TOKENS=512

# Lower quality threshold to document more code
DOC_QUALITY_THRESHOLD=50.0

# Faster processing
DOC_BATCH_SIZE=20
DOC_MAX_RETRIES=2
DOC_RETRY_DELAY=1.0

# Disable caching for fresh results
DOC_ENABLE_CACHING=false
```

## Production Environment

Configuration for high-quality production documentation:

```bash
# API Key
GROQ_API_KEY=your_api_key_here

# Best model for quality
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.1
DOC_LLM_MAX_TOKENS=2048

# High quality threshold
DOC_QUALITY_THRESHOLD=85.0

# Conservative processing
DOC_BATCH_SIZE=5
DOC_MAX_RETRIES=3
DOC_RETRY_DELAY=3.0

# Enable caching
DOC_ENABLE_CACHING=true
DOC_CACHE_TTL_HOURS=48
```

## Large Codebase

Configuration optimized for processing large projects:

```bash
# API Key
GROQ_API_KEY=your_api_key_here

# Balanced model
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.3
DOC_LLM_MAX_TOKENS=1024

# Standard threshold
DOC_QUALITY_THRESHOLD=70.0

# Larger batches for efficiency
DOC_BATCH_SIZE=25
DOC_MAX_RETRIES=3
DOC_RETRY_DELAY=2.0

# Aggressive caching
DOC_ENABLE_CACHING=true
DOC_CACHE_TTL_HOURS=72

# Increased timeouts
INDEXING_TIMEOUT_MINUTES=60
QUERY_TIMEOUT_SECONDS=30
```

## Rate-Limited Environment

Configuration when dealing with API rate limits:

```bash
# API Key
GROQ_API_KEY=your_api_key_here

# Standard model
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.3
DOC_LLM_MAX_TOKENS=1024

# Standard threshold
DOC_QUALITY_THRESHOLD=70.0

# Small batches to avoid rate limits
DOC_BATCH_SIZE=3
DOC_MAX_RETRIES=5
DOC_RETRY_DELAY=5.0

# Enable caching to reduce API calls
DOC_ENABLE_CACHING=true
DOC_CACHE_TTL_HOURS=168  # 1 week
```

## CI/CD Pipeline

Configuration for automated documentation in CI/CD:

```bash
# API Key (from secrets)
GROQ_API_KEY=${GROQ_API_KEY_SECRET}

# Fast model for CI
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.3
DOC_LLM_MAX_TOKENS=1024

# Moderate threshold
DOC_QUALITY_THRESHOLD=60.0

# Fast processing
DOC_BATCH_SIZE=15
DOC_MAX_RETRIES=2
DOC_RETRY_DELAY=2.0

# Disable caching in CI
DOC_ENABLE_CACHING=false

# Strict timeouts
INDEXING_TIMEOUT_MINUTES=15
QUERY_TIMEOUT_SECONDS=10
```

## Memory-Constrained Environment

Configuration for systems with limited memory:

```bash
# API Key
GROQ_API_KEY=your_api_key_here

# Standard model
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.3
DOC_LLM_MAX_TOKENS=1024

# Standard threshold
DOC_QUALITY_THRESHOLD=70.0

# Small batches to reduce memory usage
DOC_BATCH_SIZE=3
DOC_MAX_RETRIES=3
DOC_RETRY_DELAY=2.0

# Disable caching to save memory
DOC_ENABLE_CACHING=false

# Reduced memory limits
MAX_MEMORY_INDEXING_GB=2
MAX_MEMORY_QUERY_GB=1

# Smaller chunks
MIN_CHUNK_TOKENS=50
MAX_CHUNK_TOKENS=300
OVERLAP_TOKENS=25
```

## Testing Environment

Configuration for running tests:

```bash
# API Key (can use test key)
GROQ_API_KEY=test_api_key

# Fast model for tests
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.5
DOC_LLM_MAX_TOKENS=512

# Low threshold for test coverage
DOC_QUALITY_THRESHOLD=30.0

# Fast processing
DOC_BATCH_SIZE=10
DOC_MAX_RETRIES=1
DOC_RETRY_DELAY=0.5

# Disable caching in tests
DOC_ENABLE_CACHING=false

# Short timeouts
INDEXING_TIMEOUT_MINUTES=5
QUERY_TIMEOUT_SECONDS=5
```

## Complete Configuration Template

Full `.env` template with all available options:

```bash
# ============================================
# REQUIRED CONFIGURATION
# ============================================

GROQ_API_KEY=your_api_key_here

# ============================================
# DOCUMENTATION GENERATOR
# ============================================

# LLM Configuration
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.3
DOC_LLM_MAX_TOKENS=1024

# Quality and Processing
DOC_QUALITY_THRESHOLD=70.0
DOC_BATCH_SIZE=10

# Retry Configuration
DOC_MAX_RETRIES=3
DOC_RETRY_DELAY=2.0

# Caching
DOC_ENABLE_CACHING=true
DOC_CACHE_TTL_HOURS=24

# ============================================
# EMBEDDING CONFIGURATION
# ============================================

EMBEDDING_BATCH_SIZE=32
EMBEDDING_MAX_RETRIES=3

# ============================================
# CHUNKING CONFIGURATION
# ============================================

MIN_CHUNK_TOKENS=100
MAX_CHUNK_TOKENS=500
OVERLAP_TOKENS=50

# ============================================
# RETRIEVAL CONFIGURATION
# ============================================

INITIAL_RETRIEVAL_COUNT=10
FINAL_RESULT_COUNT=5

# ============================================
# VECTOR STORE CONFIGURATION
# ============================================

CHROMA_PERSIST_DIR=./chroma_data
VECTORSTORE_MAX_RETRIES=3

# ============================================
# LLM CONFIGURATION (Q&A)
# ============================================

LLM_MODEL_NAME=llama-3.1-8b-instant
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.7
LLM_STREAM=true

# ============================================
# CONVERSATION CONFIGURATION
# ============================================

MAX_HISTORY_MESSAGES=10

# ============================================
# PERFORMANCE CONFIGURATION
# ============================================

QUERY_TIMEOUT_SECONDS=10
INDEXING_TIMEOUT_MINUTES=30
```

## Docker Environment Variables

For Docker deployments, use this `docker-compose.yml`:

```yaml
version: '3.8'

services:
  codebase-qa:
    build: .
    ports:
      - "8501:8501"
    environment:
      # Required
      - GROQ_API_KEY=${GROQ_API_KEY}
      
      # Documentation Generator
      - DOC_LLM_MODEL=llama-3.1-8b-instant
      - DOC_LLM_TEMPERATURE=0.3
      - DOC_LLM_MAX_TOKENS=1024
      - DOC_QUALITY_THRESHOLD=70.0
      - DOC_BATCH_SIZE=10
      - DOC_MAX_RETRIES=3
      - DOC_RETRY_DELAY=2.0
      - DOC_ENABLE_CACHING=true
      - DOC_CACHE_TTL_HOURS=24
      
      # Vector Store
      - CHROMA_PERSIST_DIR=/app/data/chroma
      
    volumes:
      - ./data:/app/data
      - ./src:/app/src:ro
```

## Environment-Specific Configurations

### Local Development

```bash
# .env.local
GROQ_API_KEY=your_dev_api_key
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_QUALITY_THRESHOLD=50.0
DOC_ENABLE_CACHING=false
```

### Staging

```bash
# .env.staging
GROQ_API_KEY=your_staging_api_key
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_QUALITY_THRESHOLD=70.0
DOC_ENABLE_CACHING=true
DOC_CACHE_TTL_HOURS=24
```

### Production

```bash
# .env.production
GROQ_API_KEY=your_prod_api_key
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_QUALITY_THRESHOLD=85.0
DOC_ENABLE_CACHING=true
DOC_CACHE_TTL_HOURS=72
DOC_BATCH_SIZE=5
```

## Loading Environment-Specific Configs

```python
import os
from dotenv import load_dotenv

# Load environment-specific config
env = os.getenv('ENVIRONMENT', 'local')
load_dotenv(f'.env.{env}')

# Or load with override
load_dotenv('.env')  # Base config
load_dotenv(f'.env.{env}', override=True)  # Environment-specific overrides
```

## Programmatic Configuration

Override configuration in code:

```python
from config import get_config

config = get_config()

# Override for specific use case
config.documentation.llm_model = "llama-3.1-8b-instant"
config.documentation.batch_size = 20
config.documentation.quality_threshold = 50.0

# Use modified config
orchestrator = DocumentationOrchestrator(
    analysis_agent=AnalysisAgent(config),
    context_agent=ContextAgent(config),
    documentation_agent=DocumentationAgent(config),
    review_manager=ReviewManager()
)
```

## Validation

Validate your configuration:

```python
from config import get_config

config = get_config()
is_valid, error_message = config.validate()

if not is_valid:
    print(f"Configuration error: {error_message}")
    exit(1)

# Print configuration summary
import json
print(json.dumps(config.get_summary(), indent=2))
```

---

**Note**: Always keep your `.env` file secure and never commit it to version control. Add it to `.gitignore`:

```bash
# .gitignore
.env
.env.*
!.env.example
```
