/**
 * Causation graph for a single workflow.
 * Visualizes Event N -> Activity N, Event N -> Delay N,
 * Activity N -> Event N+1, Delay N -> Event N+1.
 */
import { useMemo, useEffect } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import dagre from 'dagre';
import { colorFor } from '../utils/colors';
import 'reactflow/dist/style.css';

const NODE_WIDTH = 140;
const NODE_HEIGHT = 36;

function getLayoutedElements(nodes, edges, direction = 'LR') {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction, nodesep: 40, ranksep: 60 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
      sourcePosition: direction === 'LR' ? 'right' : 'bottom',
      targetPosition: direction === 'LR' ? 'left' : 'top',
    };
  });

  return { nodes: layoutedNodes, edges };
}

function statusColor(status) {
  if (!status) return 'var(--fg)';
  const s = (status || '').toLowerCase().replace(' ', '_');
  if (s === 'completed') return 'var(--green)';
  if (s === 'failed') return 'var(--red)';
  if (s === 'in_progress' || s === 'running') return 'var(--blue)';
  if (s === 'pending' || s === 'retrying') return 'var(--yellow)';
  return 'var(--fg)';
}

export default function CausationGraph({ events = [], activities = [], delays = [], onNodeClick }) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    const eventByNum = new Map();
    const activityByNum = new Map();
    const delayByNum = new Map();

    (events || []).forEach((e) => {
      const n = e.event_number ?? e.workflow_version;
      if (n != null) eventByNum.set(n, e);
    });
    (activities || []).forEach((a) => {
      const n = a.event_number;
      if (n != null) activityByNum.set(n, a);
    });
    (delays || []).forEach((d) => {
      const n = d.event_number ?? d.event_version;
      if (n != null) delayByNum.set(n, d);
    });

    const allNums = new Set([
      ...eventByNum.keys(),
      ...activityByNum.keys(),
      ...delayByNum.keys(),
    ]);
    const sortedNums = [...allNums].sort((a, b) => a - b);

    const nodes = [];
    const edges = [];

    sortedNums.forEach((n) => {
      const ev = eventByNum.get(n);
      const act = activityByNum.get(n);
      const del = delayByNum.get(n);

      if (ev) {
        const eventType = ev.body?.type || ev.event_type || 'Event';
        const color = colorFor(eventType) || 'var(--cyan)';
        nodes.push({
          id: `event-${n}`,
          type: 'default',
          data: {
            label: (
              <span style={{ color }}>
                Event #{n}
                {eventType && eventType !== 'Event' && (
                  <span style={{ opacity: 0.8, marginLeft: 4 }}>({eventType})</span>
                )}
              </span>
            ),
          },
          style: {
            borderColor: color,
            backgroundColor: 'var(--bg)',
            color: 'var(--fg)',
          },
        });
      }

      if (act) {
        const color = statusColor(act.status);
        nodes.push({
          id: `activity-${n}`,
          type: 'default',
          data: {
            label: (
              <span style={{ color }}>
                Activity #{n}
                <span style={{ opacity: 0.8, marginLeft: 4 }}>({act.status})</span>
              </span>
            ),
          },
          style: {
            borderColor: color,
            backgroundColor: 'var(--bg)',
            color: 'var(--fg)',
          },
        });
      }

      if (del) {
        nodes.push({
          id: `delay-${n}`,
          type: 'default',
          data: {
            label: (
              <span style={{ color: 'var(--yellow)' }}>
                Delay #{n}
              </span>
            ),
          },
          style: {
            borderColor: 'var(--yellow)',
            backgroundColor: 'var(--bg)',
            color: 'var(--fg)',
          },
        });
      }

      // Event N -> Activity N
      if (ev && act) {
        edges.push({
          id: `e${n}-a${n}`,
          source: `event-${n}`,
          target: `activity-${n}`,
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: 'var(--green)', strokeWidth: 1.5 },
        });
      }

      // Event N -> Delay N
      if (ev && del) {
        edges.push({
          id: `e${n}-d${n}`,
          source: `event-${n}`,
          target: `delay-${n}`,
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: 'var(--yellow)', strokeWidth: 1.5 },
        });
      }

      // Activity N -> Event N+1
      const nextEv = eventByNum.get(n + 1);
      if (act && nextEv) {
        edges.push({
          id: `a${n}-e${n + 1}`,
          source: `activity-${n}`,
          target: `event-${n + 1}`,
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: 'var(--cyan)', strokeWidth: 1.5 },
        });
      }

      // Delay N -> Event N+1
      if (del && nextEv) {
        edges.push({
          id: `d${n}-e${n + 1}`,
          source: `delay-${n}`,
          target: `event-${n + 1}`,
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: 'var(--cyan)', strokeWidth: 1.5 },
        });
      }
    });

    if (nodes.length === 0) {
      return { nodes: [], edges: [] };
    }

    return getLayoutedElements(nodes, edges, 'LR');
  }, [events, activities, delays]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data changes
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  if (initialNodes.length === 0) {
    return (
      <div className="causation-graph-empty">
        <p>no events, activities, or delays to display</p>
      </div>
    );
  }

  return (
    <div className="causation-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="var(--muted)" gap={12} />
        <Controls className="causation-graph-controls" />
        <MiniMap
          nodeColor={(node) => {
            const m = node.style?.borderColor;
            return m || 'var(--green)';
          }}
          maskColor="rgba(0,0,0,0.8)"
        />
      </ReactFlow>
    </div>
  );
}
