# UI Screenshots

This directory contains screenshots of the Smart Code Documentation Generator UI workflow.

## Required Screenshots

To complete the documentation, please add the following screenshots:

### 1. File Selection Interface
**Filename:** `file-selection.png`

**What to capture:**
- The file tree view with checkboxes
- "Select entire project" option
- File count summary (Python: X, JavaScript: Y)
- Estimated processing time
- "Start Documentation" button

**How to capture:**
1. Navigate to "Documentation Generator" tab
2. Select a few files from different directories
3. Take screenshot of the entire interface

---

### 2. Progress Tracking
**Filename:** `progress-tracking.png`

**What to capture:**
- Current stage indicator (Analysis, Context, Generation, or Review)
- Progress bar showing percentage
- Current file being processed
- Element count (processed / total)
- Stage completion checkmarks

**How to capture:**
1. Start documentation generation
2. Wait until progress is around 40-60%
3. Take screenshot showing active progress

---

### 3. Review Interface
**Filename:** `review-interface.png`

**What to capture:**
- Filter options (status, language, element type, file path)
- Side-by-side view of:
  - Original code
  - Existing documentation (if any)
  - Generated documentation
- Action buttons (Approve, Reject, Edit)
- Review progress indicator

**How to capture:**
1. Navigate to Review tab after generation completes
2. Select an interesting code element (function with parameters)
3. Take screenshot showing the full review interface

---

### 4. Export Interface
**Filename:** `export-interface.png`

**What to capture:**
- Format selection radio buttons (inline, markdown, HTML)
- Output directory input field
- Export options checkboxes
- Export button
- Export summary (if available)

**How to capture:**
1. Navigate to Export tab
2. Select a format and configure options
3. Take screenshot before or after export

---

### 5. Complete Workflow
**Filename:** `complete-workflow.png`

**What to capture:**
- Overview showing all tabs/stages
- Navigation between stages
- Overall application layout

**How to capture:**
1. Take a full-window screenshot showing the main interface
2. Ensure all major UI elements are visible

---

## Screenshot Guidelines

### Technical Requirements
- **Format:** PNG (preferred) or JPG
- **Resolution:** Minimum 1920x1080 for desktop views
- **File Size:** Keep under 2MB per image
- **Quality:** High quality, no compression artifacts

### Content Guidelines
- Use realistic but non-sensitive code examples
- Ensure text is readable (no tiny fonts)
- Show meaningful data (not empty states)
- Include relevant UI elements and labels
- Avoid personal information or API keys

### Naming Convention
- Use lowercase with hyphens: `file-selection.png`
- Be descriptive: `review-interface-with-filters.png`
- Add variants if needed: `export-markdown-format.png`

## Adding Screenshots

1. **Capture screenshots** following the guidelines above

2. **Save to this directory:**
```bash
docs/screenshots/file-selection.png
docs/screenshots/progress-tracking.png
docs/screenshots/review-interface.png
docs/screenshots/export-interface.png
```

3. **Optimize images** (optional but recommended):
```bash
# Install optimization tools
brew install optipng jpegoptim  # macOS
sudo apt install optipng jpegoptim  # Linux

# Optimize PNG files
optipng -o7 docs/screenshots/*.png

# Or use online tools like TinyPNG
```

4. **Verify references** in documentation:
   - Check `README.md` for image links
   - Ensure paths are correct
   - Test that images display properly

## Current Status

- [ ] file-selection.png
- [ ] progress-tracking.png
- [ ] review-interface.png
- [ ] export-interface.png
- [ ] complete-workflow.png

## Alternative: Placeholder Images

If screenshots are not yet available, you can create placeholder images:

```bash
# Create placeholder images (requires ImageMagick)
convert -size 1920x1080 xc:lightgray -pointsize 72 -draw "text 600,540 'File Selection Interface'" docs/screenshots/file-selection.png
convert -size 1920x1080 xc:lightgray -pointsize 72 -draw "text 600,540 'Progress Tracking'" docs/screenshots/progress-tracking.png
convert -size 1920x1080 xc:lightgray -pointsize 72 -draw "text 600,540 'Review Interface'" docs/screenshots/review-interface.png
convert -size 1920x1080 xc:lightgray -pointsize 72 -draw "text 600,540 'Export Interface'" docs/screenshots/export-interface.png
```

Or use online placeholder services:
```markdown
![File Selection](https://via.placeholder.com/1920x1080/cccccc/000000?text=File+Selection+Interface)
```

---

**Note:** Screenshots should be updated whenever the UI changes significantly to keep documentation accurate and helpful.
