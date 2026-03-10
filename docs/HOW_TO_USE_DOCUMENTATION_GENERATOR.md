# How to Use the Documentation Generator

## ✅ Good News: The Documentation Generator is Working!

I've tested the documentation generator and it's working correctly. Here's how to use it:

## Step-by-Step Guide

### 1. Start the Application

```bash
# Make sure you're in the project directory
cd /Users/atharvahanumantadmile/Documents/CG_2

# Activate virtual environment
source .venv/bin/activate

# Run Streamlit
streamlit run main.py
```

### 2. Navigate to Documentation Generator Tab

- Open the application in your browser (usually http://localhost:8501)
- Click on the **"📝 Documentation Generator"** tab at the top

### 3. Select Files for Documentation

You have two options:

#### Option A: Select Entire Project
1. Check the box **"Select entire project"**
2. This will automatically select all Python, JavaScript, and TypeScript files
3. Click **"✅ Confirm Selection"** button

#### Option B: Select Individual Files
1. Browse the file tree displayed
2. Check the boxes next to files you want to document
3. Click **"✅ Confirm Selection"** button

### 4. Start Documentation Generation

After confirming your selection:
1. You'll see a summary showing:
   - Number of selected files
   - Breakdown by language (Python, JavaScript, TypeScript)
   - Estimated processing time
2. Click the **"🚀 Start Documentation Generation"** button
3. Wait for the process to complete (progress will be shown)

### 5. Review Generated Documentation

Once generation completes:
1. You'll automatically move to the **Review** stage
2. Review each generated documentation item:
   - See the original code
   - See the generated documentation
   - Approve, reject, or edit each item
3. Use filters to find specific items:
   - Filter by approval status
   - Filter by language
   - Filter by element type (function, class, method)

### 6. Export Documentation

After approving documentation:
1. Click the **"📦 Export"** tab
2. Choose your export format:
   - **Inline**: Inserts docstrings directly into source files
   - **Markdown**: Creates markdown documentation files
   - **HTML**: Generates an HTML documentation website
3. Configure export options
4. Click **"Export Documentation"**

## Important Notes

### Vector Store (Optional but Recommended)

The documentation generator works better if you index your codebase first:

1. Go to the **"Codebase Indexing"** tab
2. Select your project directory
3. Click **"Index Codebase"**
4. Wait for indexing to complete

This helps the AI understand your code context better, but it's **not required** for basic documentation generation.

### Quality Threshold

The system only documents code elements with quality scores below 70 (by default). This means:
- Well-documented code is skipped
- Poorly documented or undocumented code is processed

You can adjust this in `.env`:
```bash
# Document more code (lower threshold)
DOC_QUALITY_THRESHOLD=50.0

# Document only very poor code (higher threshold)
DOC_QUALITY_THRESHOLD=85.0
```

### Supported File Types

- **Python**: `.py` files → Google-style docstrings
- **JavaScript**: `.js`, `.jsx` files → JSDoc comments
- **TypeScript**: `.ts`, `.tsx` files → JSDoc comments

## Test Results

I've verified the system works by generating documentation for a test file:

```python
# Test file with 5 code elements
def calculate_sum(a, b):
    return a + b

def multiply_numbers(x, y):
    result = x * y
    return result

class Calculator:
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b
```

**Results:**
- ✅ All 5 elements documented successfully
- ✅ Generated proper docstrings with descriptions, parameters, returns, and examples
- ✅ Processing time: ~20 seconds
- ✅ No errors

## Troubleshooting

### "Documentation Generator not available"

This error means the orchestrator failed to initialize. Check:
1. Is `GROQ_API_KEY` set in `.env`?
2. Is the API key valid?
3. Restart the Streamlit application

### "No files selected"

Make sure to:
1. Check file checkboxes OR check "Select entire project"
2. Click **"✅ Confirm Selection"** button
3. Then click **"🚀 Start Documentation Generation"**

### Slow Performance

If generation is slow:
1. Use faster model in `.env`:
   ```bash
   DOC_LLM_MODEL=llama-3.1-8b-instant
   ```
2. Reduce batch size:
   ```bash
   DOC_BATCH_SIZE=5
   ```
3. Process fewer files at once

### Vector Store Warnings

You may see warnings like:
```
Collection codebase_collection does not exist
```

This is normal if you haven't indexed your codebase yet. The documentation generator will still work, but without context from similar code. To fix:
1. Go to "Codebase Indexing" tab
2. Index your project
3. Then use the documentation generator

## Example Workflow

Here's a complete example workflow:

1. **Start Application**
   ```bash
   streamlit run main.py
   ```

2. **Index Codebase** (Optional but recommended)
   - Go to "Codebase Indexing" tab
   - Select project directory
   - Click "Index Codebase"
   - Wait for completion

3. **Generate Documentation**
   - Go to "Documentation Generator" tab
   - Check "Select entire project"
   - Click "✅ Confirm Selection"
   - Click "🚀 Start Documentation Generation"
   - Wait for completion (~15 seconds per file)

4. **Review Documentation**
   - Review each generated item
   - Approve good documentation
   - Edit or reject poor documentation
   - Use filters to navigate

5. **Export Documentation**
   - Go to "Export" tab
   - Choose format (inline, markdown, or HTML)
   - Configure options
   - Click "Export Documentation"

## Need Help?

- Check the main [README.md](README.md) for detailed documentation
- See [DOCUMENTATION_GENERATOR_GUIDE.md](DOCUMENTATION_GENERATOR_GUIDE.md) for advanced usage
- Review [docs/troubleshooting.md](docs/troubleshooting.md) for common issues
- Check [docs/quick-reference.md](docs/quick-reference.md) for quick commands

---

**The documentation generator is ready to use! Just follow the steps above and you'll be generating documentation in minutes.**
