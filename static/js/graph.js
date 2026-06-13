/* ── DocRAG graph.js — D3 force-directed knowledge graph ─────────────────── */
(function () {
  "use strict";

  const loadBtn       = document.getElementById("load-graph-btn");
  const container     = document.getElementById("graph-container");
  const placeholder   = container.querySelector(".graph-placeholder");

  if (!loadBtn) return;

  loadBtn.addEventListener("click", () => {
    loadBtn.disabled = true;
    loadBtn.textContent = "Loading…";
    placeholder && (placeholder.textContent = "Fetching graph data…");

    fetch("/graph")
      .then(r => r.json())
      .then(data => {
        loadBtn.textContent = "Refresh";
        loadBtn.disabled = false;
        if (data.error) {
          placeholder && (placeholder.textContent = "Error: " + data.error);
          return;
        }
        if (!data.nodes || data.nodes.length === 0) {
          placeholder && (placeholder.textContent = "No graph data yet — index some documents first.");
          return;
        }
        renderGraph(data);
      })
      .catch(err => {
        loadBtn.disabled = false;
        loadBtn.textContent = "Retry";
        placeholder && (placeholder.textContent = "Failed: " + err);
      });
  });

  function renderGraph({ nodes, edges }) {
    container.innerHTML = "";

    const W = container.clientWidth  || 900;
    const H = container.clientHeight || 500;

    const svg = d3.select(container)
      .append("svg")
      .attr("id", "graph-svg")
      .attr("viewBox", [0, 0, W, H]);

    // ── Zoom layer ──────────────────────────────────────────────────────────
    const g = svg.append("g");
    svg.call(d3.zoom()
      .scaleExtent([0.1, 6])
      .on("zoom", e => g.attr("transform", e.transform))
    );

    // ── Arrow marker ────────────────────────────────────────────────────────
    svg.append("defs").append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 18).attr("refY", 0)
      .attr("markerWidth", 6).attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", "#3a4060");

    // ── Force simulation ────────────────────────────────────────────────────
    const sim = d3.forceSimulation(nodes)
      .force("link",   d3.forceLink(edges).id(d => d.id).distance(90).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("collide", d3.forceCollide(22));

    // ── Edges ────────────────────────────────────────────────────────────────
    const link = g.append("g")
      .selectAll("line")
      .data(edges)
      .join("line")
      .attr("stroke", "#2a2e45")
      .attr("stroke-width", 1.5)
      .attr("marker-end", "url(#arrow)");

    // ── Edge labels ──────────────────────────────────────────────────────────
    const edgeLabel = g.append("g")
      .selectAll("text")
      .data(edges.filter(e => e.relation || e.keyword))
      .join("text")
      .attr("font-size", "8px")
      .attr("fill", "#4a5070")
      .attr("text-anchor", "middle")
      .text(d => (d.relation || d.keyword || "").slice(0, 20));

    // ── Nodes ────────────────────────────────────────────────────────────────
    const colorScale = d3.scaleOrdinal()
      .domain(["entity", "concept", "HEADING", "TABLE", "default"])
      .range(["#6c8eff", "#a78bfa", "#34d399", "#fbbf24", "#7a84a0"]);

    const node = g.append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag",  (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end",   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    node.append("circle")
      .attr("r", d => Math.max(7, Math.min(18, (d.degree || 1) * 2.5)))
      .attr("fill", d => colorScale(d.entity_type || d.type || "default"))
      .attr("stroke", "#0d0f14")
      .attr("stroke-width", 1.5)
      .attr("fill-opacity", 0.88);

    node.append("text")
      .attr("dy", "0.35em")
      .attr("x", d => Math.max(8, Math.min(19, (d.degree || 1) * 2.5)) + 4)
      .attr("font-size", "9px")
      .attr("fill", "#c0c8e0")
      .text(d => (d.id || d.entity || "").slice(0, 28));

    // ── Tooltip ──────────────────────────────────────────────────────────────
    const tip = d3.select(container)
      .append("div")
      .style("position", "absolute").style("pointer-events", "none")
      .style("background", "#1b1f2b").style("border", "1px solid #252a38")
      .style("border-radius", "8px").style("padding", "8px 12px")
      .style("font-size", "11px").style("color", "#e2e6f0")
      .style("display", "none").style("max-width", "240px");

    node.on("mouseenter", (e, d) => {
      const lines = [
        `<b>${d.id || d.entity || "node"}</b>`,
        d.entity_type ? `Type: ${d.entity_type}` : "",
        d.description ? d.description.slice(0, 120) + "…" : "",
      ].filter(Boolean).join("<br/>");
      tip.html(lines).style("display", "block")
         .style("left", (e.offsetX + 12) + "px").style("top", (e.offsetY - 10) + "px");
    }).on("mousemove", e => {
      tip.style("left", (e.offsetX + 12) + "px").style("top", (e.offsetY - 10) + "px");
    }).on("mouseleave", () => tip.style("display", "none"));

    // ── Tick ─────────────────────────────────────────────────────────────────
    sim.on("tick", () => {
      link
        .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      edgeLabel
        .attr("x", d => ((d.source.x || 0) + (d.target.x || 0)) / 2)
        .attr("y", d => ((d.source.y || 0) + (d.target.y || 0)) / 2);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });
  }
})();
