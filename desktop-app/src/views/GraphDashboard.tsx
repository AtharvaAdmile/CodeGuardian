import { useEffect, useRef, useState, useMemo } from 'react';
import * as d3 from 'd3';
import { useProject } from '../App';
import ActionsPane from '../components/ActionsPane';

interface FileNode {
    id: string; // full relative path
    name: string;
    path: string;
    size: number;
    type: 'file' | 'directory';
    x?: number;
    y?: number;
    fx?: number | null;
    fy?: number | null;
}

interface FileLink {
    source: string | FileNode;
    target: string | FileNode;
}

export default function GraphDashboard() {
    const { projectPath } = useProject();
    const svgRef = useRef<SVGSVGElement>(null);
    const wrapperRef = useRef<HTMLDivElement>(null);

    const [files, setFiles] = useState<any[]>([]);
    const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
    const [loading, setLoading] = useState(true);

    // Load data
    useEffect(() => {
        if (!projectPath) return;

        const loadFiles = async () => {
            setLoading(true);
            try {
                // Get all files
                const fileList = await window.cgctl.listFiles(projectPath);
                setFiles(fileList);
            } catch (e) {
                console.error("Failed to list files", e);
            } finally {
                setLoading(false);
            }
        };

        loadFiles();
    }, [projectPath]);

    // Graph Data Construction
    const graphData = useMemo(() => {
        if (files.length === 0) return { nodes: [], links: [] };

        const nodesMap = new Map<string, FileNode>();
        const links: FileLink[] = [];

        // Create Root Node
        const rootNode: FileNode = { id: '.', name: 'Root', path: '.', size: 0, type: 'directory' };
        nodesMap.set('.', rootNode);

        files.forEach(file => {
            // Ensure node exists
            if (!nodesMap.has(file.path)) {
                nodesMap.set(file.path, { ...file, id: file.path });
            }

            // Determine parent
            const parts = file.path.split('/');
            if (parts.length > 1) {
                const parentPath = parts.slice(0, -1).join('/');
                // Ensure parent exists (directories might be implicit in list if listFiles returned files only, current implementation returns both but let's be safe)
                if (!nodesMap.has(parentPath)) {
                    // Create implicit directory node if missing (though our improved walker should find them)
                    const name = parts[parts.length - 2];
                    nodesMap.set(parentPath, { id: parentPath, name, path: parentPath, size: 0, type: 'directory' });
                    // Link parent's parent... (recurse?)
                    // For simplicity, assuming our walker is good.
                    // But we do need to link this node to its parent.
                }

                links.push({ source: parentPath, target: file.path });
            } else {
                // Child of root
                links.push({ source: '.', target: file.path });
            }
        });

        return { nodes: Array.from(nodesMap.values()), links };
    }, [files]);

    // D3 Simulation
    useEffect(() => {
        if (!svgRef.current || !wrapperRef.current || graphData.nodes.length === 0) return;

        const width = wrapperRef.current.clientWidth;
        const height = wrapperRef.current.clientHeight;

        const svg = d3.select(svgRef.current);
        svg.selectAll("*").remove(); // Clear previous

        const g = svg.append("g");

        // Zoom capability
        const zoom = d3.zoom<SVGSVGElement, unknown>()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {
                g.attr("transform", event.transform);
            });

        svg.call(zoom);

        // Disable default dblclick-to-zoom and add reset functionality
        svg.on("dblclick.zoom", null);
        svg.on("dblclick", (event) => {
            // Only trigger if clicking directly on the canvas background
            if (event.target === svg.node()) {
                svg.transition()
                    .duration(750)
                    .ease(d3.easeCubicInOut)
                    .call(zoom.transform, d3.zoomIdentity);
            }
        });

        // Simulation
        const simulation = d3.forceSimulation<FileNode>(graphData.nodes)
            .force("link", d3.forceLink<FileNode, FileLink>(graphData.links).id(d => d.id).distance(120))
            .force("charge", d3.forceManyBody().strength(-400))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide<FileNode>().radius(d => {
                const nodeRadius = d.type === 'directory' ? 20 : 3 + Math.min(10, Math.sqrt(d.size || 0) * 0.1);
                return nodeRadius + 25; // Adjusted padding for smaller folder nodes
            }).iterations(2));


        // Render Links
        const link = g.append("g")
            .attr("stroke", "#333")
            .attr("stroke-opacity", 0.6)
            .selectAll("line")
            .data(graphData.links)
            .join("line");

        // Render Nodes
        const node = g.append("g")
            .selectAll("circle")
            .data(graphData.nodes)
            .join("circle")
            .attr("r", d => d.type === 'directory' ? 48 : 3 + Math.min(10, Math.sqrt(d.size || 0) * 0.1))
            .attr("fill", d => {
                if (d.type === 'directory') return "#4a90e2"; // Blue folders
                if (d.name.endsWith('.ts') || d.name.endsWith('.tsx')) return "#2f74c0"; // TS blue
                if (d.name.endsWith('.css')) return "#c6538c"; // Pink CSS
                return "#888"; // Grey others
            })
            .attr("stroke", "#fff")
            .attr("stroke-width", d => d.type === 'directory' ? 2 : 0.5)
            .style("cursor", "pointer")
            .style("opacity", d => d.type === 'directory' ? 0.9 : 1)
            .on("click", (event, d) => {
                event.stopPropagation();
                setSelectedFile(d);
            })
            .call(d3.drag<any, any>()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended)
            );

        // Labels
        const label = g.append("g")
            .selectAll("text")
            .data(graphData.nodes)
            .join("text")
            .text(d => d.name)
            .attr("font-family", "monospace")
            .attr("font-size", d => {
                const baseSize = d.type === 'directory' ? 14 : 7;
                const scale = Math.min(2, Math.sqrt(d.size || 0) * 0.05);
                return baseSize + scale;
            })
            .attr("text-anchor", "middle")
            .attr("dy", d => {
                if (d.type === 'directory') return 5; // Center vertically inside node
                const nodeRadius = 3 + Math.min(10, Math.sqrt(d.size || 0) * 0.1);
                return nodeRadius + 12; // Position below file node
            })
            .attr("fill", d => d.type === 'directory' ? "#fff" : "#ccc")
            .attr("font-weight", d => d.type === 'directory' ? "700" : "normal")
            .style("pointer-events", "none")
            .style("opacity", d => d.type === 'directory' ? 1 : 0.8);

        node.append("title").text(d => d.path);

        simulation.on("tick", () => {
            link
                .attr("x1", d => (d.source as FileNode).x!)
                .attr("y1", d => (d.source as FileNode).y!)
                .attr("x2", d => (d.target as FileNode).x!)
                .attr("y2", d => (d.target as FileNode).y!);

            node
                .attr("cx", d => d.x!)
                .attr("cy", d => d.y!);

            label
                .attr("x", d => d.x!)
                .attr("y", d => d.y!);
        });

        function dragstarted(event: any) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event: any) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event: any) {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }

        // Cleanup
        return () => {
            simulation.stop();
        };

    }, [graphData]);

    // Handle background click to deselect
    const handleBackgroundClick = () => {
        setSelectedFile(null);
    };

    return (
        <div className="graph-dashboard" ref={wrapperRef} onClick={handleBackgroundClick}>
            {loading && <div className="loading-overlay">Loading Project Graph...</div>}

            <svg ref={svgRef} width="100%" height="100%"></svg>

            {selectedFile && (
                <div className="selected-file-overlay">
                    <span className="icon">{selectedFile.type === 'directory' ? '📁' : '📄'}</span>
                    <span className="name" style={{ fontWeight: 600 }}>{selectedFile.name}</span>
                    <span className="path">{selectedFile.path}</span>
                </div>
            )}

            {projectPath && (
                <ActionsPane
                    selectedFile={selectedFile}
                    projectPath={projectPath}
                />
            )}
        </div>
    );
}
