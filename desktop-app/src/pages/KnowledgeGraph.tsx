import { useEffect, useRef, useState, useMemo } from "react";
import * as d3 from "d3";
import { Search, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { useProjectContext } from "../App";
import { analyzeProjectDependencies } from "../lib/api";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";

interface FileNode {
  id: string;
  name: string;
  path: string;
  size: number;
  type: "file" | "directory";
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

interface FileLink {
  source: string | FileNode;
  target: string | FileNode;
  type?: string;
}

const COLORS = {
  accent: { blue: "#3B82F6" },
  border: "#1E2D4A",
  text: { secondary: "#94A3B8", muted: "#64748B" },
};

const CODE_EXTENSIONS = new Set([
  ".py", ".js", ".jsx", ".ts", ".tsx",
  ".css", ".scss", ".less",
  ".json", ".yaml", ".yml", ".toml",
  ".html", ".htm",
  ".c", ".cpp", ".h", ".hpp",
  ".java", ".kt", ".kts",
  ".rs", ".go", ".rb",
  ".vue", ".svelte",
  ".sql",
]);

function getExtension(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx >= 0 ? name.slice(idx) : "";
}

export default function KnowledgeGraph() {
  const { projectPath } = useProjectContext();
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const [files, setFiles] = useState<FileNode[]>([]);
  const [dependencyLinks, setDependencyLinks] = useState<FileLink[]>([]);
  const [collapsedDirs, setCollapsedDirs] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<FileNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (!projectPath) return;

    const loadFiles = async () => {
      setLoading(true);
      try {
        const fileList = await window.cgctl.listFiles(projectPath);
        const mapped: FileNode[] = fileList.map((f: any) => ({
          id: f.path,
          name: f.name,
          path: f.path,
          size: f.size,
          type: f.type,
        }));

        const dirs = mapped.filter((f) => f.type === "directory");
        const codeFiles = mapped.filter(
          (f) => f.type === "file" && CODE_EXTENSIONS.has(getExtension(f.name))
        );

        const ancestorPaths = new Set<string>();
        codeFiles.forEach((f) => {
          const parts = f.path.split("/");
          for (let i = 1; i < parts.length; i++) {
            ancestorPaths.add(parts.slice(0, i).join("/"));
          }
        });

        const keptDirs = dirs.filter((d) => ancestorPaths.has(d.path));

        setFiles([...codeFiles, ...keptDirs]);
        setCollapsedDirs(new Set(keptDirs.filter((d) => d.path !== ".").map((d) => d.path)));

        const depGraph = await analyzeProjectDependencies(projectPath);
        if (depGraph && depGraph.links) {
          setDependencyLinks(depGraph.links as FileLink[]);
        }
      } catch (e) {
        console.error("Failed to list files or dependencies", e);
      } finally {
        setLoading(false);
      }
    };

    loadFiles();
  }, [projectPath]);

  const graphData = useMemo(() => {
    if (files.length === 0) return { nodes: [] as FileNode[], links: [] as FileLink[] };

    const nodesMap = new Map<string, FileNode>();
    const links: FileLink[] = [];

    const rootNode: FileNode = { id: ".", name: "Root", path: ".", size: 0, type: "directory" };
    nodesMap.set(".", rootNode);

    files.forEach((file) => {
      if (!nodesMap.has(file.path)) {
        nodesMap.set(file.path, { ...file, id: file.path });
      }

      const parts = file.path.split("/");
      if (parts.length > 1) {
        const parentPath = parts.slice(0, -1).join("/");
        if (!nodesMap.has(parentPath)) {
          const name = parts[parts.length - 2];
          nodesMap.set(parentPath, { id: parentPath, name, path: parentPath, size: 0, type: "directory" });
        }
        links.push({ source: parentPath, target: file.path });
      } else {
        links.push({ source: ".", target: file.path });
      }
    });

    dependencyLinks.forEach((dep) => {
      const srcId = typeof dep.source === "string" ? dep.source : (dep.source as FileNode).id;
      const tgtId = typeof dep.target === "string" ? dep.target : (dep.target as FileNode).id;
      if (nodesMap.has(srcId) && nodesMap.has(tgtId)) {
        links.push({ source: srcId, target: tgtId, type: "dependency" });
      }
    });

    const allNodes = Array.from(nodesMap.values());

    if (collapsedDirs.size > 0) {
      const isHidden = (node: FileNode) => {
        if (node.path === ".") return false;
        const parts = node.path.split("/");
        for (let i = 1; i < parts.length; i++) {
          const ancestorPath = parts.slice(0, i).join("/");
          if (ancestorPath !== node.path && collapsedDirs.has(ancestorPath)) return true;
        }
        return false;
      };

      const visibleNodes = allNodes.filter((n) => !isHidden(n));
      const visibleIds = new Set(visibleNodes.map((n) => n.id));
      const visibleLinks = links.filter(
        (l) =>
          visibleIds.has(typeof l.source === "string" ? l.source : (l.source as FileNode).id) &&
          visibleIds.has(typeof l.target === "string" ? l.target : (l.target as FileNode).id)
      );

      return { nodes: visibleNodes, links: visibleLinks };
    }

    return { nodes: allNodes, links };
  }, [files, dependencyLinks, collapsedDirs]);

  useEffect(() => {
    if (!svgRef.current || !wrapperRef.current || graphData.nodes.length === 0) return;

    const width = wrapperRef.current.clientWidth;
    const height = wrapperRef.current.clientHeight;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const g = svg.append("g");

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });

    svg.call(zoom);
    svg.on("dblclick.zoom", null);

    const simulation = d3.forceSimulation<FileNode>(graphData.nodes)
      .force("link", d3.forceLink<FileNode, FileLink>(graphData.links).id((d) => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide<FileNode>().radius((d) => {
        const nodeRadius = d.type === "directory" ? 20 : 5 + Math.min(10, Math.sqrt(d.size || 0) * 0.5);
        return nodeRadius + 10;
      }).iterations(2));

    const link = g.append("g")
      .selectAll("line")
      .data(graphData.links)
      .join("line")
      .attr("stroke", (d) => d.type === "dependency" ? COLORS.accent.blue : COLORS.border)
      .attr("stroke-opacity", 0.3)
      .attr("stroke-width", 1);

    const node = g.append("g")
      .selectAll("circle")
      .data(graphData.nodes)
      .join("circle")
      .attr("r", (d) => d.type === "directory" ? 15 : 5 + Math.min(10, Math.sqrt(d.size || 0) * 0.5))
      .attr("fill", (d) => d.type === "directory" ? COLORS.accent.blue : COLORS.text.muted)
      .attr("stroke", (d) =>
        d.type === "directory" && collapsedDirs.has(d.path) ? COLORS.accent.blue : "#fff"
      )
      .attr("stroke-width", (d) =>
        d.type === "directory" && collapsedDirs.has(d.path) ? 2 : 1
      )
      .attr("stroke-dasharray", (d) =>
        d.type === "directory" && collapsedDirs.has(d.path) ? "4,2" : "none"
      )
      .style("cursor", "pointer")
      .on("click", (event, d) => {
        event.stopPropagation();
        if (d.type === "directory") {
          setCollapsedDirs((prev) => {
            const next = new Set(prev);
            if (next.has(d.path)) {
              next.delete(d.path);
            } else {
              next.add(d.path);
            }
            return next;
          });
        } else {
          setSelectedNode(d);
        }
      });

    const label = g.append("g")
      .selectAll("text")
      .data(graphData.nodes)
      .join("text")
      .text((d) => d.name)
      .attr("font-family", "monospace")
      .attr("font-size", "10px")
      .attr("text-anchor", "middle")
      .attr("dy", (d) => {
        const nodeRadius = d.type === "directory" ? 15 : 5 + Math.min(10, Math.sqrt(d.size || 0) * 0.5);
        return nodeRadius + 12;
      })
      .attr("fill", COLORS.text.secondary)
      .style("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as FileNode).x!)
        .attr("y1", (d) => (d.source as FileNode).y!)
        .attr("x2", (d) => (d.target as FileNode).x!)
        .attr("y2", (d) => (d.target as FileNode).y!);

      node
        .attr("cx", (d) => d.x!)
        .attr("cy", (d) => d.y!);

      label
        .attr("x", (d) => d.x!)
        .attr("y", (d) => d.y!);
    });

    return () => {
      simulation.stop();
    };
  }, [graphData]);

  const handleSearch = () => {
    if (!searchQuery.trim()) return;
    const found = graphData.nodes.find(
      (n) => n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
             n.path.toLowerCase().includes(searchQuery.toLowerCase())
    );
    if (found) {
      setSelectedNode(found);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="relative h-full">
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
        <div className="bg-bg-secondary border border-border rounded-lg p-2 flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search files..."
            className="bg-bg-tertiary border-none rounded px-3 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none w-48"
          />
          <button className="p-1.5 hover:bg-bg-hover rounded">
            <Search className="w-4 h-4 text-text-muted" />
          </button>
        </div>

        <div className="bg-bg-secondary border border-border rounded-lg p-2 space-y-2">
          <button className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
            <ZoomIn className="w-4 h-4" />
            <span>Zoom In</span>
          </button>
          <button className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
            <ZoomOut className="w-4 h-4" />
            <span>Zoom Out</span>
          </button>
          <button className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
            <Maximize2 className="w-4 h-4" />
            <span>Reset</span>
          </button>
        </div>
      </div>

      <div ref={wrapperRef} className="h-full bg-bg-primary">
        <svg ref={svgRef} width="100%" height="100%" />
      </div>

      {selectedNode && (
        <div className="absolute top-4 right-4 w-72 bg-bg-secondary border border-border rounded-xl p-4 z-10">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold">Node Details</h3>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-text-muted hover:text-text-primary"
            >
              ×
            </button>
          </div>
          <div className="space-y-2 text-sm">
            <div>
              <span className="text-text-muted">Name:</span>
              <span className="ml-2 text-text-primary">{selectedNode.name}</span>
            </div>
            <div>
              <span className="text-text-muted">Path:</span>
              <span className="ml-2 text-text-primary font-mono text-xs">{selectedNode.path}</span>
            </div>
            <div>
              <span className="text-text-muted">Type:</span>
              <span className="ml-2 text-text-primary">{selectedNode.type}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
