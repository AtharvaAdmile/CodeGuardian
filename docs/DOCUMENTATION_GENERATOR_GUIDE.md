# Smart Code Documentation Generator - Detailed Guide

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Configuration Reference](#configuration-reference)
4. [Usage Examples](#usage-examples)
5. [Export Format Examples](#export-format-examples)
6. [Advanced Features](#advanced-features)
7. [Error Handling & Recovery](#error-handling--recovery)
8. [Best Practices](#best-practices)
9. [Performance Tuning](#performance-tuning)
10. [FAQ](#faq)

## Overview

The Smart Code Documentation Generator is a multi-agent AI system that automatically generates comprehensive documentation for Python and JavaScript/TypeScript codebases. It uses a sophisticated workflow involving analysis, context understanding, and intelligent generation.

### Key Benefits

- **Time Savings**: Automate documentation for hundreds of functions in minutes
- **Consistency**: Maintain consistent documentation style across your codebase
- **Quality**: AI-generated documentation includes descriptions, parameters, returns, and examples
- **Context-Aware**: Understands code relationships and dependencies
- **Flexible**: Multiple export formats to fit your workflow

### Supported Languages

| Language | File Extensions | Documentation Format |
|----------|----------------|---------------------|
| Python | `.py` | Google-style docstrings |
| JavaScript | `.js`, `.jsx` | JSDoc comments |
| TypeScript | `.ts`, `.tsx` | JSDoc comments |

## Architecture

### Multi-Agent Workflow

```
┌─────────────────┐
│  File Selection │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Analysis Agent  │ ← Identifies documentation gaps
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Context Agent  │ ← Understands relationships
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│Documentation    │ ← Generates documentation
│     Agent       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Review Manager  │ ← Human review & approval
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Export Module  │ ← Exports in chosen format
└─────────────────┘
```

### Agent Responsibilities

#### 1. Analysis Agent
- Parses source files using AST
- Extracts code elements (functions, classes, methods)
- Evaluates existing documentation quality (0-100 score)
- Identifies elements below quality threshold

**Quality Score Breakdown:**
- Docstring/JSDoc present: 40 points
- Description complete: 20 points
- Parameters documented: 20 points
- Return value documented: 10 points
- Usage examples included: 10 points

#### 2. Context Agent
- Analyzes imports and module dependencies
- Identifies function calls within implementations
- Detects class inheritance and composition
- Queries vector store for similar code
- Builds dependency graph for processing order

#### 3. Documentation Agent
- Generates documentation using Groq LLM
- Processes elements in dependency order
- Applies language-specific templates
- Includes context from dependencies
- Ensures consistency and quality

#### 4. Review Manager
- Stores generated documentation
- Tracks approval status
- Enables filtering and search
- Manages edit workflow

#### 5. Export Module
- Formats documentation for target format
- Handles file generation
- Creates backups
- Provides export summaries

## Configuration Reference

### Complete Configuration Options

All configuration can be set via environment variables in `.env`:

```bash
# ============================================
# DOCUMENTATION GENERATOR CONFIGURATION
# ============================================

# LLM Model Selection
# Options: llama-3.1-8b-instant (recommended), llama-3.1-8b-instant (faster)
DOC_LLM_MODEL=llama-3.1-8b-instant

# LLM Temperature (0.0 - 1.0)
# Lower = more deterministic, Higher = more creative
# Recommended: 0.1-0.3 for documentation
DOC_LLM_TEMPERATURE=0.3

# Maximum tokens per documentation generation
# Increase for longer, more detailed documentation
DOC_LLM_MAX_TOKENS=1024

# Quality Threshold (0.0 - 100.0)
# Elements below this score are considered to have gaps
# Lower = more elements documented, Higher = only poor docs
DOC_QUALITY_THRESHOLD=70.0

# Retry Configuration
# Number of retry attempts for failed LLM calls
DOC_MAX_RETRIES=3

# Delay between retries (seconds)
# Uses exponential backoff: delay, delay*2, delay*4
DOC_RETRY_DELAY=2.0

# Batch Processing
# Number of elements to process in parallel
# Higher = faster but more memory, Lower = slower but safer
DOC_BATCH_SIZE=10

# Caching
# Enable caching of LLM responses
DOC_ENABLE_CACHING=true

# Cache time-to-live (hours)
# How long to keep cached responses
DOC_CACHE_TTL_HOURS=24
```

### Configuration Profiles

#### Fast Processing (Less Accurate)
```bash
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.5
DOC_LLM_MAX_TOKENS=512
DOC_BATCH_SIZE=20
```

#### Balanced (Recommended)
```bash
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.3
DOC_LLM_MAX_TOKENS=1024
DOC_BATCH_SIZE=10
```

#### High Quality (Slower)
```bash
DOC_LLM_MODEL=llama-3.1-8b-instant
DOC_LLM_TEMPERATURE=0.1
DOC_LLM_MAX_TOKENS=2048
DOC_BATCH_SIZE=5
```

## Usage Examples

### Example 1: Document a Single Module

```python
# Document a specific Python module
from src.documentation.orchestrator import DocumentationOrchestrator

# Initialize orchestrator
orchestrator = DocumentationOrchestrator(
    analysis_agent=analysis_agent,
    context_agent=context_agent,
    documentation_agent=doc_agent,
    review_manager=review_manager
)

# Generate documentation
session = orchestrator.generate_documentation(
    file_paths=['src/utils/helpers.py'],
    progress_callback=lambda stage, pct: print(f"{stage}: {pct}%")
)

# Review results
print(f"Session ID: {session.session_id}")
print(f"Elements with gaps: {session.gap_report.elements_with_gaps}")
print(f"Documentation items: {len(session.documentation_items)}")
```

### Example 2: Document Entire Project

```python
import os
from pathlib import Path

# Find all Python files in project
def find_python_files(directory):
    files = []
    for root, dirs, filenames in os.walk(directory):
        # Skip virtual environments and caches
        dirs[:] = [d for d in dirs if d not in ['.venv', '__pycache__', 'node_modules']]
        for filename in filenames:
            if filename.endswith('.py'):
                files.append(os.path.join(root, filename))
    return files

# Document all files
project_files = find_python_files('src/')
session = orchestrator.generate_documentation(
    file_paths=project_files,
    progress_callback=lambda stage, pct: print(f"{stage}: {pct}%")
)
```

### Example 3: Filter and Review Documentation

```python
from src.documentation.review_manager import ReviewManager

review_manager = ReviewManager()

# Get all pending items
pending_items = review_manager.get_items_for_review(
    session_id=session.session_id,
    filter_by={'approval_status': 'pending'}
)

# Get items for specific file
file_items = review_manager.get_items_for_review(
    session_id=session.session_id,
    filter_by={'file_path': 'src/utils/helpers.py'}
)

# Get items by element type
function_items = review_manager.get_items_for_review(
    session_id=session.session_id,
    filter_by={'element_type': 'function'}
)

# Approve an item
review_manager.update_approval_status(
    session_id=session.session_id,
    element_id='func_123',
    status='approved'
)

# Edit and approve
review_manager.update_approval_status(
    session_id=session.session_id,
    element_id='func_456',
    status='edited',
    edited_doc='"""Custom edited documentation."""'
)
```

### Example 4: Export in Multiple Formats

```python
from src.documentation.export.export_module import ExportModule

export_module = ExportModule(docstring_writer, markdown_writer, html_writer)

# Get approved items
approved = review_manager.get_approved_items(session.session_id)

# Export as inline docstrings
inline_result = export_module.export_documentation(
    items=approved,
    export_format='inline',
    output_path='./src_documented'
)

# Export as markdown
markdown_result = export_module.export_documentation(
    items=approved,
    export_format='markdown',
    output_path='./docs/api'
)

# Export as HTML
html_result = export_module.export_documentation(
    items=approved,
    export_format='html',
    output_path='./docs/html'
)

print(f"Inline: {inline_result.elements_exported} elements")
print(f"Markdown: {len(markdown_result.output_files)} files")
print(f"HTML: {len(html_result.output_files)} files")
```

### Example 5: Custom Progress Tracking

```python
import time
from datetime import datetime

class ProgressTracker:
    def __init__(self):
        self.start_time = None
        self.current_stage = None
        
    def callback(self, stage, progress_percent):
        if self.start_time is None:
            self.start_time = time.time()
        
        if stage != self.current_stage:
            self.current_stage = stage
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Stage: {stage}")
        
        elapsed = time.time() - self.start_time
        print(f"  Progress: {progress_percent:.1f}% (Elapsed: {elapsed:.1f}s)", end='\r')

tracker = ProgressTracker()
session = orchestrator.generate_documentation(
    file_paths=project_files,
    progress_callback=tracker.callback
)
```

## Export Format Examples

### Python: Google-Style Docstrings

**Input Code:**
```python
def process_data(data, threshold=0.5, normalize=True):
    if normalize:
        data = data / data.max()
    return data[data > threshold]
```

**Generated Documentation:**
```python
def process_data(data, threshold=0.5, normalize=True):
    """Process and filter data based on threshold value.
    
    This function optionally normalizes the input data and then filters
    it to return only values above the specified threshold. Normalization
    divides all values by the maximum value in the dataset.
    
    Args:
        data (numpy.ndarray): Input data array to process.
        threshold (float, optional): Minimum value threshold for filtering.
            Values below this threshold are excluded. Defaults to 0.5.
        normalize (bool, optional): Whether to normalize data before filtering.
            If True, divides all values by the maximum. Defaults to True.
    
    Returns:
        numpy.ndarray: Filtered data array containing only values above threshold.
    
    Example:
        >>> import numpy as np
        >>> data = np.array([0.1, 0.5, 0.8, 1.0])
        >>> result = process_data(data, threshold=0.6)
        >>> print(result)
        [0.8 1.0]
    
    Note:
        If normalize is True and data.max() is 0, this will raise a
        division by zero error.
    """
    if normalize:
        data = data / data.max()
    return data[data > threshold]
```

### JavaScript: JSDoc Comments

**Input Code:**
```javascript
function fetchUserData(userId, options) {
    const url = `${API_BASE}/users/${userId}`;
    return fetch(url, options).then(res => res.json());
}
```

**Generated Documentation:**
```javascript
/**
 * Fetch user data from the API by user ID.
 * 
 * Makes an HTTP request to retrieve user information from the API endpoint.
 * The response is automatically parsed as JSON and returned as a Promise.
 * 
 * @param {string|number} userId - The unique identifier of the user to fetch.
 * @param {Object} [options={}] - Optional fetch configuration object.
 * @param {string} [options.method='GET'] - HTTP method to use.
 * @param {Object} [options.headers] - Additional headers to include.
 * @param {AbortSignal} [options.signal] - AbortSignal for request cancellation.
 * 
 * @returns {Promise<Object>} A promise that resolves to the user data object.
 * 
 * @throws {Error} If the network request fails or returns non-OK status.
 * 
 * @example
 * // Fetch user with ID 123
 * fetchUserData(123)
 *   .then(user => console.log(user.name))
 *   .catch(err => console.error('Failed to fetch user:', err));
 * 
 * @example
 * // Fetch with custom headers
 * fetchUserData(456, {
 *   headers: { 'Authorization': 'Bearer token123' }
 * }).then(user => console.log(user));
 */
function fetchUserData(userId, options) {
    const url = `${API_BASE}/users/${userId}`;
    return fetch(url, options).then(res => res.json());
}
```

### TypeScript: JSDoc with Type Information

**Input Code:**
```typescript
interface User {
    id: number;
    name: string;
    email: string;
}

function validateUser(user: User): boolean {
    return user.email.includes('@') && user.name.length > 0;
}
```

**Generated Documentation:**
```typescript
interface User {
    id: number;
    name: string;
    email: string;
}

/**
 * Validate user object for required fields and format.
 * 
 * Performs basic validation on a user object to ensure it has a valid
 * email address (contains '@') and a non-empty name. This is typically
 * used before saving user data or processing user input.
 * 
 * @param {User} user - The user object to validate.
 * @param {number} user.id - User's unique identifier.
 * @param {string} user.name - User's display name.
 * @param {string} user.email - User's email address.
 * 
 * @returns {boolean} True if user is valid, false otherwise.
 * 
 * @example
 * const user: User = {
 *   id: 1,
 *   name: 'John Doe',
 *   email: 'john@example.com'
 * };
 * 
 * if (validateUser(user)) {
 *   console.log('User is valid');
 * } else {
 *   console.log('Invalid user data');
 * }
 * 
 * @see {@link User} for the user interface definition
 */
function validateUser(user: User): boolean {
    return user.email.includes('@') && user.name.length > 0;
}
```

## Advanced Features

### 1. Dependency-Aware Documentation

The system processes code elements in dependency order:

```python
# File: utils.py
def calculate_distance(p1, p2):
    # Will be documented first
    pass

def find_nearest(point, points):
    # Will be documented second (depends on calculate_distance)
    for p in points:
        dist = calculate_distance(point, p)
    pass
```

The documentation for `find_nearest` will reference `calculate_distance`:

```python
def find_nearest(point, points):
    """Find the nearest point from a list of points.
    
    Uses the calculate_distance function to compute distances between
    the target point and each point in the list, returning the closest one.
    
    Args:
        point (tuple): Target point coordinates (x, y).
        points (list): List of point tuples to search.
    
    Returns:
        tuple: The nearest point from the list.
    
    See Also:
        calculate_distance: Used to compute point distances.
    """
```

### 2. Context from Similar Code

The system uses vector similarity to find related code:

```python
# If you have similar functions elsewhere:
def cosine_similarity(v1, v2):
    """Calculate cosine similarity..."""
    pass

# The new function will reference this pattern:
def euclidean_distance(v1, v2):
    """Calculate Euclidean distance between two vectors.
    
    Similar to cosine_similarity, this function measures the distance
    between two vectors, but uses Euclidean (L2) distance instead of
    cosine similarity.
    """
    pass
```

### 3. Batch Processing with Progress

Process large codebases efficiently:

```python
# Process in batches with progress updates
def batch_process_project(root_dir, batch_size=50):
    all_files = find_python_files(root_dir)
    
    for i in range(0, len(all_files), batch_size):
        batch = all_files[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{len(all_files)//batch_size + 1}")
        
        session = orchestrator.generate_documentation(
            file_paths=batch,
            progress_callback=lambda s, p: print(f"  {s}: {p:.0f}%")
        )
        
        # Auto-approve high-confidence items
        for item in session.documentation_items:
            if item.confidence_score > 0.9:
                review_manager.update_approval_status(
                    session.session_id,
                    item.element_id,
                    'approved'
                )
```

### 4. Custom Quality Thresholds

Adjust quality thresholds per project:

```python
from src.documentation.gap_detector import GapDetector

# Strict threshold for production code
production_detector = GapDetector(quality_threshold=85.0)

# Lenient threshold for experimental code
experimental_detector = GapDetector(quality_threshold=50.0)
```

### 5. Incremental Documentation

Document only changed files:

```python
import subprocess

def get_changed_files():
    """Get files changed in current git branch."""
    result = subprocess.run(
        ['git', 'diff', '--name-only', 'main'],
        capture_output=True,
        text=True
    )
    return [f for f in result.stdout.split('\n') if f.endswith('.py')]

# Document only changed files
changed_files = get_changed_files()
session = orchestrator.generate_documentation(file_paths=changed_files)
```

## Error Handling & Recovery

### Error Types and Solutions

#### 1. Parsing Errors

**Error Message:**
```
ParsingError: Failed to parse src/broken.py:45
SyntaxError: invalid syntax
```

**Solution:**
```python
# Fix syntax error in source file
# Then retry specific file
session = orchestrator.generate_documentation(
    file_paths=['src/broken.py']
)
```

#### 2. API Rate Limiting

**Error Message:**
```
RateLimitError: Rate limit exceeded for API
Retry after: 60 seconds
```

**Solution:**
```bash
# Increase retry delay
DOC_RETRY_DELAY=5.0

# Reduce batch size
DOC_BATCH_SIZE=3
```

Or wait and retry:
```python
import time

try:
    session = orchestrator.generate_documentation(file_paths=files)
except RateLimitError as e:
    print(f"Rate limited. Waiting {e.retry_after} seconds...")
    time.sleep(e.retry_after)
    session = orchestrator.generate_documentation(file_paths=files)
```

#### 3. Context Analysis Failures

**Error Message:**
```
ContextError: Cannot resolve dependency for function 'process_data'
Missing import: 'numpy'
```

**Solution:**
```python
# Ensure all dependencies are installed
pip install numpy

# Or mark element for manual documentation
review_manager.update_approval_status(
    session_id=session.session_id,
    element_id='process_data',
    status='rejected'  # Will skip this element
)
```

#### 4. Export Permission Errors

**Error Message:**
```
PermissionError: Cannot write to /usr/local/docs
Permission denied
```

**Solution:**
```python
# Use writable directory
export_module.export_documentation(
    items=approved,
    export_format='markdown',
    output_path='./docs'  # Use local directory
)

# Or fix permissions
# chmod 755 /usr/local/docs
```

### Retry Strategies

#### Automatic Retry with Exponential Backoff

```python
# Configured in .env
DOC_MAX_RETRIES=3
DOC_RETRY_DELAY=2.0

# Retry schedule:
# Attempt 1: immediate
# Attempt 2: after 2 seconds
# Attempt 3: after 4 seconds
# Attempt 4: after 8 seconds
```

#### Manual Retry for Failed Elements

```python
# Get failed elements from session
failed_elements = [
    item.element_id 
    for item in session.documentation_items 
    if item.confidence_score == 0
]

# Retry specific elements
for element_id in failed_elements:
    try:
        # Re-generate documentation for this element
        item = doc_agent.generate_for_element(
            element=get_element_by_id(element_id),
            context=context_map.element_contexts[element_id],
            previously_documented={}
        )
        print(f"✓ Retry successful for {element_id}")
    except Exception as e:
        print(f"✗ Retry failed for {element_id}: {e}")
```

## Best Practices

### 1. Pre-Documentation Checklist

Before running documentation generation:

- [ ] Ensure code compiles/runs without errors
- [ ] Fix any syntax errors
- [ ] Install all dependencies
- [ ] Index codebase in vector store (for better context)
- [ ] Set appropriate quality threshold
- [ ] Configure output directory with write permissions

### 2. Quality Review Guidelines

When reviewing generated documentation:

- **Check Accuracy**: Verify parameter types and descriptions
- **Verify Examples**: Ensure code examples are correct and runnable
- **Review Tone**: Maintain consistent voice across documentation
- **Add Context**: Include domain-specific knowledge the AI might miss
- **Fix Errors**: Edit any incorrect or misleading information

### 3. Export Strategy

Choose the right export format for your use case:

| Format | Best For | Pros | Cons |
|--------|----------|------|------|
| Inline | Active development | Integrated with code | Modifies source files |
| Markdown | Documentation sites | Readable, portable | Separate from code |
| HTML | Public documentation | Professional, searchable | Requires hosting |

### 4. Incremental Workflow

For large projects, use an incremental approach:

```python
# Week 1: Core modules
core_files = ['src/core/', 'src/models/']
session1 = orchestrator.generate_documentation(file_paths=core_files)

# Week 2: Utilities
util_files = ['src/utils/', 'src/helpers/']
session2 = orchestrator.generate_documentation(file_paths=util_files)

# Week 3: API layer
api_files = ['src/api/', 'src/routes/']
session3 = orchestrator.generate_documentation(file_paths=api_files)
```

### 5. Version Control Integration

Track documentation changes:

```bash
# Create documentation branch
git checkout -b docs/auto-generated

# Generate and export documentation
python generate_docs.py

# Review changes
git diff

# Commit approved documentation
git add src/
git commit -m "docs: Add AI-generated documentation"

# Create pull request for review
git push origin docs/auto-generated
```

## Performance Tuning

### Optimization Strategies

#### 1. Batch Size Tuning

```python
# Test different batch sizes
batch_sizes = [5, 10, 20, 50]
results = {}

for batch_size in batch_sizes:
    config.documentation.batch_size = batch_size
    start = time.time()
    session = orchestrator.generate_documentation(file_paths=test_files)
    elapsed = time.time() - start
    results[batch_size] = elapsed
    print(f"Batch size {batch_size}: {elapsed:.2f}s")

# Use optimal batch size
optimal_batch_size = min(results, key=results.get)
```

#### 2. Caching Strategy

```python
# Enable caching for repeated runs
config.documentation.enable_caching = True
config.documentation.cache_ttl_hours = 24

# First run: ~10 minutes
session1 = orchestrator.generate_documentation(file_paths=files)

# Second run with same files: ~2 minutes (cached)
session2 = orchestrator.generate_documentation(file_paths=files)
```

#### 3. Parallel Processing

```python
from concurrent.futures import ThreadPoolExecutor

def process_file_batch(files):
    return orchestrator.generate_documentation(file_paths=files)

# Split files into chunks
file_chunks = [files[i:i+10] for i in range(0, len(files), 10)]

# Process chunks in parallel
with ThreadPoolExecutor(max_workers=4) as executor:
    sessions = list(executor.map(process_file_batch, file_chunks))
```

### Performance Benchmarks

Typical performance on a modern machine:

| Project Size | Files | Elements | Time (Balanced) | Time (Fast) |
|--------------|-------|----------|-----------------|-------------|
| Small | 10 | 50 | 2-3 min | 1-2 min |
| Medium | 50 | 250 | 10-15 min | 5-8 min |
| Large | 200 | 1000 | 40-60 min | 20-30 min |
| Very Large | 500+ | 2500+ | 2-3 hours | 1-1.5 hours |

## FAQ

### General Questions

**Q: Does this replace human-written documentation?**

A: No, it's a tool to accelerate documentation creation. Human review and editing are essential for accuracy and context.

**Q: What languages are supported?**

A: Currently Python, JavaScript, and TypeScript. More languages can be added by extending the parser and template engine.

**Q: Can I customize the documentation style?**

A: Yes, you can modify templates in `src/documentation/template_engine.py` to match your style guide.

**Q: Is my code sent to external servers?**

A: Yes, code snippets are sent to Groq's API for documentation generation. Review their privacy policy if you have concerns.

### Technical Questions

**Q: How does the quality score work?**

A: It's calculated based on presence and completeness of documentation elements:
- Docstring exists: 40 points
- Description: 20 points
- Parameters: 20 points
- Return value: 10 points
- Examples: 10 points

**Q: What happens with circular dependencies?**

A: The system detects circular dependencies and processes elements in alphabetical order within the cycle.

**Q: Can I use a different LLM?**

A: The system is designed for Groq's API. To use other LLMs, you'd need to modify `DocumentationAgent` to support different API formats.

**Q: How accurate is the generated documentation?**

A: Accuracy depends on code clarity and context. Typical accuracy is 85-95% for well-structured code. Always review before publishing.

### Troubleshooting Questions

**Q: Why is generation so slow?**

A: Check your batch size, network connection, and API rate limits. Try the "Fast Processing" configuration profile.

**Q: Why are some elements skipped?**

A: Elements may be skipped if they have quality scores above the threshold, parsing fails, or they're excluded by filters.

**Q: Can I resume a failed session?**

A: Yes, use the session ID to retry failed elements individually through the review interface.

**Q: How do I handle large files?**

A: Large files are automatically chunked. If issues persist, consider splitting the file or increasing timeout limits.

---

**Last Updated**: November 2025  
**Version**: 1.0.0  
**For Support**: Open an issue on GitHub or consult the main README.md
