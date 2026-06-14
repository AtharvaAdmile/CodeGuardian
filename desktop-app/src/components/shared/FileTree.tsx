import { useState } from "react";
import type { FileNode } from "../../lib/types";

interface FileTreeProps {
  files: FileNode[];
  onFileSelect?: (file: FileNode) => void;
  selectedPath?: string;
}

function FileTreeNode({
  node,
  isLast,
  prefix,
  depth = 0,
  onFileSelect,
  selectedPath,
}: {
  node: FileNode;
  isLast: boolean;
  prefix: string;
  depth?: number;
  onFileSelect?: (file: FileNode) => void;
  selectedPath?: string;
}) {
  const [isExpanded, setIsExpanded] = useState(depth < 2);
  const isSelected = selectedPath === node.path;

  const connector = isLast ? "└── " : "├── ";
  const childPrefix = prefix + (isLast ? "    " : "│   ");

  return (
    <div>
      <div
        className={`flex items-baseline font-mono text-[12px] leading-6 cursor-pointer transition-colors select-none ${
          isSelected
            ? "bg-secondary text-on-secondary"
            : "hover:bg-surface-container-high"
        }`}
        onClick={() => {
          if (node.type === "directory") setIsExpanded(!isExpanded);
          else onFileSelect?.(node);
        }}
      >
        <span
          className={`shrink-0 whitespace-pre ${
            isSelected ? "text-on-secondary/50" : "text-on-surface-variant/40"
          }`}
        >
          {prefix}{connector}
        </span>
        <span
          className={
            isSelected
              ? "font-bold"
              : node.type === "directory"
              ? "text-primary"
              : "text-on-surface"
          }
        >
          {node.name}
          {node.type === "directory" && "/"}
        </span>
      </div>
      {node.type === "directory" &&
        isExpanded &&
        node.children?.map((child, i) => (
          <FileTreeNode
            key={child.id}
            node={child}
            isLast={i === node.children!.length - 1}
            prefix={childPrefix}
            depth={depth + 1}
            onFileSelect={onFileSelect}
            selectedPath={selectedPath}
          />
        ))}
    </div>
  );
}

export function FileTree({ files, onFileSelect, selectedPath }: FileTreeProps) {
  return (
    <div className="font-mono text-[12px] leading-6">
      <div className="text-secondary select-none">.</div>
      {files.map((file, i) => (
        <FileTreeNode
          key={file.id}
          node={file}
          isLast={i === files.length - 1}
          prefix=""
          depth={0}
          onFileSelect={onFileSelect}
          selectedPath={selectedPath}
        />
      ))}
    </div>
  );
}
