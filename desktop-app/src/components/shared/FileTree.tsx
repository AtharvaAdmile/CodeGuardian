import { useState } from "react";
import { ChevronRight, File, Folder, FolderOpen } from "lucide-react";
import { getHealthColor } from "../../lib/constants";
import type { FileNode } from "../../lib/types";

interface FileTreeProps {
  files: FileNode[];
  onFileSelect?: (file: FileNode) => void;
  selectedPath?: string;
}

interface FileTreeNodeProps {
  node: FileNode;
  depth: number;
  onFileSelect?: (file: FileNode) => void;
  selectedPath?: string;
}

function FileTreeNode({ node, depth, onFileSelect, selectedPath }: FileTreeNodeProps) {
  const [isExpanded, setIsExpanded] = useState(depth < 2);
  const isSelected = selectedPath === node.path;

  const handleClick = () => {
    if (node.type === "directory") {
      setIsExpanded(!isExpanded);
    } else {
      onFileSelect?.(node);
    }
  };

  const Icon = node.type === "directory"
    ? (isExpanded ? FolderOpen : Folder)
    : File;

  const healthColor = node.health !== undefined ? getHealthColor(node.health) : null;

  return (
    <div>
      <div
        className={`
          flex items-center gap-1.5 py-1 px-2 cursor-pointer rounded
          ${isSelected ? "bg-accent-blue/20 text-accent-blue" : "hover:bg-bg-hover text-text-primary"}
        `}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={handleClick}
      >
        {node.type === "directory" && (
          <ChevronRight
            className={`w-3 h-3 text-text-muted transition-transform ${isExpanded ? "rotate-90" : ""}`}
          />
        )}
        <Icon className="w-4 h-4 text-text-muted" />
        <span className="text-sm truncate flex-1">{node.name}</span>
        {node.type === "file" && healthColor && (
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: healthColor }}
          />
        )}
      </div>
      {node.type === "directory" && isExpanded && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              onFileSelect={onFileSelect}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function FileTree({ files, onFileSelect, selectedPath }: FileTreeProps) {
  return (
    <div className="font-mono text-sm">
      {files.map((file) => (
        <FileTreeNode
          key={file.id}
          node={file}
          depth={0}
          onFileSelect={onFileSelect}
          selectedPath={selectedPath}
        />
      ))}
    </div>
  );
}
