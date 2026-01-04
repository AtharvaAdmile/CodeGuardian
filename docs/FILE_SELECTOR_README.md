# File Selector Component

## Overview
The File Selector UI component provides a Streamlit interface for selecting files to document in the Smart Code Documentation Generator.

## Implementation Details

### Location
- **Main Component:** `src/documentation/ui/file_selector.py`
- **Package Init:** `src/documentation/ui/__init__.py`

### Features Implemented

✅ **File Tree Display** (Requirement 1.1)
- Hierarchical tree view of project structure
- Expandable directories
- Clean visual organization

✅ **Individual File Selection** (Requirement 1.2)
- Checkbox for each supported file
- Supports: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`
- Automatic filtering of unsupported files

✅ **Directory Selection** (Requirement 1.3)
- Recursive file discovery in subdirectories
- Excludes common build/cache directories

✅ **Select Entire Project** (Requirement 1.4)
- Single checkbox to select all supported files
- Automatically finds all files in project

✅ **Selection Summary** (Requirement 1.5)
- Count of selected files by language
- Estimated processing time calculation
- Visual metrics display

### Key Classes

#### `FileSelector`
Main UI component class with methods:
- `render()` - Display the file selection interface
- `_build_file_tree()` - Build hierarchical file structure
- `_render_file_tree()` - Recursively render tree with checkboxes
- `_get_all_supported_files()` - Find all supported files
- `_count_files_by_language()` - Count files by programming language
- `_calculate_estimated_time()` - Estimate processing time
- `reset_selection()` - Clear selection state

#### `FileSelectionResult`
Data class containing:
- `selected_files` - List of selected file paths
- `files_by_language` - Dictionary of language counts
- `estimated_time_minutes` - Estimated processing time

### Configuration

**Supported Extensions:**
```python
SUPPORTED_EXTENSIONS = {
    'Python': ['.py'],
    'JavaScript': ['.js', '.jsx'],
    'TypeScript': ['.ts', '.tsx']
}
```

**Excluded Directories:**
- `__pycache__`, `node_modules`, `.git`, `.venv`, `venv`
- `env`, `.env`, `dist`, `build`, `.next`, `.nuxt`
- `coverage`, `.pytest_cache`, `.mypy_cache`, `.tox`

**Time Estimation:**
- 15 seconds per file (configurable via `ESTIMATED_TIME_PER_FILE`)

## Testing

### Demo Script
Run the standalone demo:
```bash
streamlit run test_file_selector_demo.py
```

### Integration Example
See `documentation_integration_example.py` for workflow integration example.

## Usage Example

```python
from src.documentation.ui.file_selector import FileSelector

# Initialize file selector
file_selector = FileSelector(root_path=".")

# Render in Streamlit app
result = file_selector.render()

# Process result
if result:
    print(f"Selected {len(result.selected_files)} files")
    print(f"Estimated time: {result.estimated_time_minutes:.1f} minutes")
    
    # Pass to documentation orchestrator
    orchestrator.generate_documentation(
        file_paths=result.selected_files,
        progress_callback=progress_callback
    )
```

## Session State Management

The component uses Streamlit session state to maintain:
- `selected_files` - Set of selected file paths
- `select_all_project` - Boolean for "select all" state

## Requirements Mapping

| Requirement | Implementation |
|-------------|----------------|
| 1.1 - File selection interface with tree view | `_build_file_tree()`, `_render_file_tree()` |
| 1.2 - Accept Python and JS/TS files | `SUPPORTED_EXTENSIONS` |
| 1.3 - Include files in subdirectories | `_get_all_supported_files()` with `os.walk()` |
| 1.4 - Select entire project option | `select_all_project` checkbox |
| 1.5 - Display count and estimated time | `_count_files_by_language()`, `_calculate_estimated_time()` |

## Next Steps

This component is ready for integration into the main Streamlit app (task 20). It can be used alongside:
- Progress View (task 17)
- Review View (task 18)
- Export View (task 19)
