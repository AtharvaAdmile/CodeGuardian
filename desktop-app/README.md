# CodeGuardian Desktop

A modern Electron + React + Vite desktop application that provides a stunning graphical interface for the CodeGuardian codebase intelligence platform.

## Features

### 🗺️ Interactive Codebase Graph
- **Force-Directed Visualization** - Explore your entire codebase as an interactive node graph
- **Zoom & Pan** - Navigate your project with smooth D3.js-powered interactions
- **Double-Click to Reset** - Quickly re-center and rescale the view with a double-click on the canvas
- **Smart Node Sizing** - Folders are prominently displayed with labels inside, files are sized by their byte count

### 🎛️ Action Sidebar
A persistent floating sidebar provides quick access to per-file analysis tools:

- ❤️ **File Health** - Tech debt score combining cyclomatic complexity (via Radon) and git churn
- 🛡️ **Compliance Scanner** - Detects PII exposure, hardcoded secrets, and dangerous function usage
- 👥 **Code Experts** - Identifies file owners with recency-weighted scoring from git history
- 📜 **Git History** - View commit history for files or specific lines

### 📊 Results Pane
- **Slide-in Panel** - Appears from the left when an action is triggered
- **Smart Grouping** - Compliance violations are automatically bundled by message and severity
- **Line Ranges** - Grouped issues display formatted line ranges (e.g., "Lines 130, 132-136, 140")

### ✨ UI/UX Polish
- **Selected File Overlay** - A pill-shaped indicator at the bottom shows the currently selected file or folder
- **Dark Mode** - Premium dark theme with glassmorphism and subtle animations
- **Responsive Layout** - Adapts to window resizing with proper constraints

## Prerequisites

- Node.js 18+
- npm or yarn
- Python 3.9+ (for the CodeGuardian MCP server)
- `cgctl` installed and accessible from terminal

## Installation

```bash
# Navigate to desktop-app directory
cd desktop-app

# Install dependencies
npm install

# Start development mode
npm run dev
```

## Development

```bash
# Run in development mode (hot reload for Vite, auto-recompile for Electron)
npm run dev

# Type check the entire project
npm run typecheck

# Build for production
npm run build

# Build Electron package (macOS, Windows, Linux)
npm run build:electron
```

## Project Structure

```
desktop-app/
├── electron/                 # Electron main process
│   ├── main.ts              # Main process entry, IPC handlers
│   └── preload.ts           # Preload script (secure IPC bridge)
├── src/                     # React application (Vite)
│   ├── components/
│   │   └── ActionsPane.tsx  # Sidebar + Results pane
│   ├── views/
│   │   └── GraphDashboard.tsx # Force-directed graph view
│   ├── App.tsx              # Main application & routing
│   └── index.css            # Global styles & design tokens
├── package.json
├── tsconfig.json            # TypeScript config for React
├── tsconfig.electron.json   # TypeScript config for Electron
└── vite.config.ts           # Vite build configuration
```

## How It Works

The application uses Electron's IPC (Inter-Process Communication) to execute CodeGuardian's MCP tools directly:

1. **Renderer Process** (React) - Handles the UI and user interactions
2. **Main Process** (Node.js) - Spawns Python to execute MCP tool functions
3. **Preload Script** - Securely exposes `window.cgctl` API to the renderer

### Example Flow
```
User clicks "File Health" → React calls window.cgctl.getFileHealth()
→ IPC message to main.ts → Spawns Python with mcp_server function
→ Returns JSON result → React updates UI
```

## Configuration

Ensure your CodeGuardian project is properly set up:

1. Initialize with `cgctl init <project-path>`
2. Index the codebase with `cgctl index <project-path>`
3. (Optional) Populate `runtime_stats.json` from your CI/CD pipeline for production telemetry

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Reset Graph View | Double-click on canvas |
| Close Results Pane | Click "×" or click same action button |

## License

MIT
