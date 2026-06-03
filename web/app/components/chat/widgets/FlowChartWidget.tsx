"use client";

import { useMemo, useState } from "react";
import {
  ReactFlow, Background, Controls,
  type Edge as RFEdge, type Node as RFNode,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { summarizeFlowChart } from "./synthesize";
import type {
  FlowChartEdge, FlowChartHint, FlowChartNode, WidgetSelectHandler,
} from "./types";


// Local editable shapes — same as the on-the-wire types but lets us track
// drafted rows the user hasn't filled yet.
type EditableNode = FlowChartNode;
type EditableEdge = FlowChartEdge;


function cloneNodes(nodes: FlowChartNode[]): EditableNode[] {
  return nodes.map(n => ({ ...n, questions: [...(n.questions ?? [])] }));
}

function cloneEdges(edges: FlowChartEdge[]): EditableEdge[] {
  return edges.map(e => ({ ...e }));
}


/**
 * Auto-layout the nodes in a horizontal row so the canvas always shows
 * something usable on first render, regardless of how many constructs the
 * tool suggested. The user can drag-rearrange after — xyflow tracks
 * position locally; we don't persist it because the schema's `nodes` shape
 * only carries label + questions, not layout.
 */
function nodesToReactFlow(nodes: EditableNode[]): RFNode[] {
  const SPACING_X = 200;
  return nodes.map((n, i) => ({
    id: n.id,
    position: { x: i * SPACING_X, y: 0 },
    data: { label: `${n.label || "(unnamed)"}${
      n.questions.length ? ` · ${n.questions.length} items` : ""
    }` },
    // Light styling so the visual matches the chat aesthetic without
    // pulling in extra CSS.
    style: {
      background: "#f5f3ff",
      border: "1px solid #c4b5fd",
      borderRadius: 8,
      padding: 8,
      fontSize: 12,
    },
  }));
}


function edgesToReactFlow(edges: EditableEdge[]): RFEdge[] {
  return edges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.hypothesis || undefined,
    // Negative paths get a dashed visual + red tint so direction is readable
    // even without opening the edit panel. Positive stays the default.
    animated: e.effect_type === "negative",
    style: e.effect_type === "negative"
      ? { stroke: "#dc2626", strokeDasharray: "5 5" }
      : undefined,
    labelStyle: { fontSize: 10 },
  }));
}


export function FlowChartWidget({
  hint,
  onSelect,
  disabled,
}: {
  hint: FlowChartHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  const [nodes, setNodes] = useState<EditableNode[]>(
    () => cloneNodes(hint.initial_nodes));
  const [edges, setEdges] = useState<EditableEdge[]>(
    () => cloneEdges(hint.initial_edges));

  const rfNodes = useMemo(() => nodesToReactFlow(nodes), [nodes]);
  const rfEdges = useMemo(() => edgesToReactFlow(edges), [edges]);

  // --- Node ops ---
  const addNode = () => {
    const id = `new_${Date.now()}_${nodes.length}`;
    setNodes([...nodes, { id, label: "", questions: [] }]);
  };
  const removeNode = (id: string) => {
    // Cascade-remove any edges touching this node so the canvas doesn't
    // ship dangling references on Confirm.
    setNodes(nodes.filter(n => n.id !== id));
    setEdges(edges.filter(e => e.source !== id && e.target !== id));
  };
  const editNodeLabel = (id: string, label: string) => {
    setNodes(nodes.map(n => n.id === id ? { ...n, label } : n));
  };
  const addQuestion = (nodeId: string) => {
    setNodes(nodes.map(n => n.id === nodeId
      ? { ...n, questions: [...n.questions, ""] }
      : n));
  };
  const editQuestion = (nodeId: string, idx: number, text: string) => {
    setNodes(nodes.map(n => n.id === nodeId
      ? { ...n, questions: n.questions.map((q, i) => i === idx ? text : q) }
      : n));
  };
  const removeQuestion = (nodeId: string, idx: number) => {
    setNodes(nodes.map(n => n.id === nodeId
      ? { ...n, questions: n.questions.filter((_, i) => i !== idx) }
      : n));
  };

  // --- Edge ops ---
  const addEdge = () => {
    const id = `H${Date.now()}`;
    const firstNodeId = nodes[0]?.id ?? "";
    const secondNodeId = nodes[1]?.id ?? firstNodeId;
    setEdges([...edges, {
      id, source: firstNodeId, target: secondNodeId,
      hypothesis: "", effect_type: "positive",
    }]);
  };
  const removeEdge = (id: string) => {
    setEdges(edges.filter(e => e.id !== id));
  };
  const editEdgeField = <K extends keyof EditableEdge>(
    id: string, field: K, value: EditableEdge[K],
  ) => {
    setEdges(edges.map(e => e.id === id ? { ...e, [field]: value } : e));
  };

  const reset = () => {
    setNodes(cloneNodes(hint.initial_nodes));
    setEdges(cloneEdges(hint.initial_edges));
  };

  const confirm = () => {
    // Strip empty constructs/items defensively so the M3 extractor doesn't
    // see ghost rows from the user clicking Add but never typing.
    const cleanNodes: FlowChartNode[] = nodes
      .filter(n => n.label.trim())
      .map(n => ({
        id: n.id,
        label: n.label.trim(),
        questions: n.questions.map(q => q.trim()).filter(Boolean),
      }));
    const validIds = new Set(cleanNodes.map(n => n.id));
    const cleanEdges: FlowChartEdge[] = edges
      .filter(e => validIds.has(e.source) && validIds.has(e.target))
      .map(e => ({
        id: e.id,
        source: e.source,
        target: e.target,
        hypothesis: e.hypothesis.trim(),
        effect_type: e.effect_type,
      }));
    const payload = { nodes: cleanNodes, edges: cleanEdges };
    onSelect(
      hint.field_name,
      JSON.stringify(payload),
      summarizeFlowChart(cleanNodes, cleanEdges, hint.field_name),
    );
  };

  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-white p-3"
      data-testid={`flow-chart-${hint.field_name}`}
    >
      <div className="text-xs font-semibold text-gray-700 mb-2">{hint.title}</div>

      <div className="rounded-md border border-gray-200 bg-gray-50"
           style={{ height: 240 }}>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodesDraggable
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {/* Constructs — editable label + per-construct Likert items. */}
      <div className="mt-3 space-y-2">
        <div className="text-xs font-semibold text-gray-700">Constructs</div>
        {nodes.map(n => (
          <div key={n.id}
               className="rounded-md border border-gray-200 bg-gray-50 p-2">
            <div className="flex items-center gap-2">
              {disabled ? (
                <span className="text-sm text-gray-900 flex-1 font-medium">
                  {n.label || "(unnamed)"}
                </span>
              ) : (
                <input
                  type="text"
                  className="text-sm text-gray-900 flex-1 bg-transparent outline-none border-b border-transparent focus:border-purple-400 font-medium"
                  value={n.label}
                  onChange={e => editNodeLabel(n.id, e.target.value)}
                  placeholder="Construct name…"
                  data-testid={`flow-node-${n.id}-label`}
                />
              )}
              {!disabled && (
                <button
                  type="button"
                  className="text-gray-400 hover:text-red-500"
                  onClick={() => removeNode(n.id)}
                  data-testid={`flow-node-${n.id}-remove`}
                >
                  ✕
                </button>
              )}
            </div>

            <div className="ml-4 mt-1 space-y-1">
              {n.questions.map((q, i) => (
                <div key={`${n.id}_q${i}`}
                     className="flex items-center gap-2 text-xs text-gray-600">
                  {disabled ? (
                    <span className="flex-1">• {q}</span>
                  ) : (
                    <>
                      <span>•</span>
                      <input
                        type="text"
                        className="flex-1 bg-transparent outline-none border-b border-transparent focus:border-purple-400"
                        value={q}
                        onChange={e => editQuestion(n.id, i, e.target.value)}
                        data-testid={`flow-node-${n.id}-q${i}-input`}
                      />
                      <button
                        type="button"
                        className="text-gray-300 hover:text-red-500"
                        onClick={() => removeQuestion(n.id, i)}
                        data-testid={`flow-node-${n.id}-q${i}-remove`}
                      >
                        ✕
                      </button>
                    </>
                  )}
                </div>
              ))}
              {!disabled && (
                <button
                  type="button"
                  className="text-xs text-gray-500 border border-dashed border-gray-300 rounded px-2 py-0.5 hover:bg-purple-50"
                  onClick={() => addQuestion(n.id)}
                  data-testid={`flow-node-${n.id}-add-question`}
                >
                  + Item
                </button>
              )}
            </div>
          </div>
        ))}
        {!disabled && (
          <button
            type="button"
            className="w-full text-sm text-gray-500 border border-dashed border-gray-300 rounded-md py-1.5 hover:bg-purple-50 hover:border-purple-400"
            onClick={addNode}
            data-testid="flow-chart-add-node"
          >
            + Add construct
          </button>
        )}
      </div>

      {/* Hypothesis paths — source/target dropdowns + hypothesis text + effect. */}
      <div className="mt-3 space-y-2">
        <div className="text-xs font-semibold text-gray-700">Hypothesis paths</div>
        {edges.map(e => (
          <div key={e.id}
               className="rounded-md border border-gray-200 bg-gray-50 p-2 space-y-1">
            <div className="flex items-center gap-2 text-xs">
              {disabled ? (
                <span className="text-gray-700 flex-1">
                  {(nodes.find(n => n.id === e.source)?.label) || e.source}
                  {" → "}
                  {(nodes.find(n => n.id === e.target)?.label) || e.target}
                </span>
              ) : (
                <>
                  <select
                    className="text-xs border border-gray-300 rounded px-1 py-0.5"
                    value={e.source}
                    onChange={ev => editEdgeField(e.id, "source", ev.target.value)}
                    data-testid={`flow-edge-${e.id}-source`}
                  >
                    {/* Number-prefix keeps the picker text distinct from the
                        bare construct label input above — `getByDisplayValue
                        ("TL")` should resolve uniquely to the label input,
                        not also match the select's selected option text. */}
                    {nodes.map((n, i) => (
                      <option key={n.id} value={n.id}>{`${i + 1}. ${n.label || "(unnamed)"}`}</option>
                    ))}
                  </select>
                  <span className="text-gray-500">→</span>
                  <select
                    className="text-xs border border-gray-300 rounded px-1 py-0.5"
                    value={e.target}
                    onChange={ev => editEdgeField(e.id, "target", ev.target.value)}
                    data-testid={`flow-edge-${e.id}-target`}
                  >
                    {nodes.map((n, i) => (
                      <option key={n.id} value={n.id}>{`${i + 1}. ${n.label || "(unnamed)"}`}</option>
                    ))}
                  </select>
                  <select
                    className="text-xs border border-gray-300 rounded px-1 py-0.5"
                    value={e.effect_type}
                    onChange={ev => editEdgeField(
                      e.id, "effect_type",
                      ev.target.value as "positive" | "negative",
                    )}
                    data-testid={`flow-edge-${e.id}-effect`}
                  >
                    <option value="positive">positive</option>
                    <option value="negative">negative</option>
                  </select>
                  <button
                    type="button"
                    className="ml-auto text-gray-400 hover:text-red-500"
                    onClick={() => removeEdge(e.id)}
                    data-testid={`flow-edge-${e.id}-remove`}
                  >
                    ✕
                  </button>
                </>
              )}
            </div>
            {disabled ? (
              <div className="text-xs text-gray-600">{e.hypothesis}</div>
            ) : (
              <input
                type="text"
                className="w-full text-xs text-gray-700 bg-transparent outline-none border-b border-gray-200 focus:border-purple-400"
                value={e.hypothesis}
                onChange={ev => editEdgeField(e.id, "hypothesis", ev.target.value)}
                placeholder="Hypothesis statement (e.g. H1: A positively affects B)"
                data-testid={`flow-edge-${e.id}-hypothesis`}
              />
            )}
          </div>
        ))}
        {!disabled && (
          <button
            type="button"
            className="w-full text-sm text-gray-500 border border-dashed border-gray-300 rounded-md py-1.5 hover:bg-purple-50 hover:border-purple-400"
            onClick={addEdge}
            data-testid="flow-chart-add-edge"
          >
            + Add path
          </button>
        )}
      </div>

      {!disabled && (
        <div className="flex gap-2 mt-3 justify-end">
          <button
            type="button"
            className="text-xs text-gray-600 border border-gray-200 rounded-md px-3 py-1 hover:bg-gray-50"
            onClick={reset}
            data-testid="flow-chart-reset"
          >
            {hint.reset_label ?? "Reset to suggested"}
          </button>
          <button
            type="button"
            className="text-xs font-medium text-white bg-purple-600 border border-purple-600 rounded-md px-3 py-1 hover:bg-purple-700"
            onClick={confirm}
            data-testid="flow-chart-confirm"
          >
            {hint.confirm_label ?? "Confirm"}
          </button>
        </div>
      )}
    </div>
  );
}
