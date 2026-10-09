// Isometric house scene (adapted from the villa-energy panel): grid pole, the PowerHub at the meter, and,
// when the user has them, one local-production node (an icon per source) and a garage with an EV. Pure SVG, back to front.

type V = [number, number, number];
const S = 32, CX = 288, CY = 262;
// isometric projection: x runs right-down, y left-down, z up
const P = ([x, y, z]: V): [number, number] => [CX + (x - y) * 0.866 * S, CY + (x + y) * 0.5 * S - z * S];
const pts = (vs: V[]) => vs.map((v) => P(v).join(",")).join(" ");
const path = (vs: V[]) => vs.map((v, i) => `${i ? "L" : "M"}${P(v).join(",")}`).join(" ");

const C = { sun: "#f5b301", grid: "#7c8cff", batt: "#2ec27e", house: "#3daee9", ev: "#c061cb", inv: "#f5a524" };

import type { Source } from "./App";

// SMIL ignores CSS, so honour prefers-reduced-motion here: dashes stay, frozen
const REDUCED = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

// one wire segment: dashes run in the flow direction, faster for bigger flows
function Wire({ route, w, max, color }: { route: V[]; w: number | null; max: number; color: string }) {
  const kw = Math.abs(w ?? 0), active = kw > 0.03;
  const d = path((w ?? 0) < 0 ? [...route].reverse() : route);
  const width = active ? 3 + 3.5 * Math.sqrt(Math.min(1, kw / Math.max(max, 1e-9))) : 0;
  const dur = Math.max(0.5, 3 - Math.log10(Math.max(kw * 1000, 1)) * 0.6);
  const [a, b] = [P(route[0]), P(route[route.length - 1])];
  return (
    <g>
      {/* the cable itself, visible also when nothing flows: light sheath + dark core + end connectors */}
      <path d={d} fill="none" stroke="#e9eef5" strokeWidth={7.5} strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} fill="none" stroke={active ? color : "#4a5262"} strokeOpacity={active ? 0.45 : 1} strokeWidth={4.5}
        strokeLinecap="round" strokeLinejoin="round" />
      {[a, b].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={3.6} fill="#4a5262" stroke="#e9eef5" strokeWidth={1.5} />)}
      {active && (
        <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="7 9">
          {!REDUCED && <animate attributeName="stroke-dashoffset" from="16" to="0" dur={`${dur}s`} repeatCount="indefinite" />}
        </path>
      )}
    </g>
  );
}

function Tag({ at, title, value, sub, color, align = "middle" }:
  { at: V; title: string; value: string; sub?: string; color: string; align?: "start" | "middle" | "end" }) {
  const [x, y] = P(at);
  return (
    <g transform={`translate(${x},${y})`} className="hs-tag" textAnchor={align}>
      <text className="hs-title" y={0}>{title}</text>
      <text className="hs-value" y={20} style={{ fill: color }}>{value}</text>
      {sub && <text className="hs-sub" y={36}>{sub}</text>}
    </g>
  );
}

// Wire values in kW, + along the route as written; null = not measured, so the cable is drawn but nothing flows.
export type HouseValues = {
  live: boolean; grid: number | null; house: number | null; inv: number | null; ev: number | null;
  sources: Source[]; hasEv: boolean; soc: number | null;  // sources: the production node's, no v2g
  text: { grid: string; gridSub: string; house: string; inv: string; invSub: string; ev: string; evSub: string };
  labels: { grid: string; house: string; inverter: string; ev: string; powerhub: string };
  ariaLabel: string;
};

// axis-aligned box seen from the front-right: front face (y = y1), right face (x = x1), top (z = z1)
function box(x0: number, x1: number, y0: number, y1: number, z0: number, z1: number, front: string, side: string, top: string) {
  return <g>
    <polygon points={pts([[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]])} fill={side} />
    <polygon points={pts([[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]])} fill={front} />
    <polygon points={pts([[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])} fill={top} />
  </g>;
}

function tree(x: number, y: number) {
  const [tx, ty] = P([x, y, 0]);
  return <g key={`${x},${y}`}><rect x={tx - 2} y={ty - 26} width={4} height={26} rx={2} fill="#7a5a3a" />
    <ellipse cx={tx} cy={ty - 44} rx={15} ry={24} fill="#22b07d" /><ellipse cx={tx - 4} cy={ty - 50} rx={7} ry={11} fill="#3ccf96" opacity={0.6} /></g>;
}

// small symbols drawn on the inverter's face
function Sun({ x, y }: { x: number; y: number }) {
  return <g stroke={C.sun} strokeWidth={1.6} strokeLinecap="round"><circle cx={x} cy={y} r={3.6} fill={C.sun} />
    {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => { const r = (a * Math.PI) / 180;
      return <line key={a} x1={x + 5.5 * Math.cos(r)} y1={y + 5.5 * Math.sin(r)} x2={x + 8 * Math.cos(r)} y2={y + 8 * Math.sin(r)} />; })}</g>;
}
function Battery({ x, y, soc }: { x: number; y: number; soc: number | null }) {
  const lvl = Math.max(0, Math.min(100, soc ?? 60)) / 100;
  return <g><rect x={x - 5} y={y - 8} width={10} height={16} rx={2} fill="none" stroke={C.batt} strokeWidth={1.6} />
    <rect x={x - 2.5} y={y - 10.5} width={5} height={2.5} rx={1} fill={C.batt} />
    <rect x={x - 3} y={y + 6 - 12 * lvl} width={6} height={12 * lvl} fill={C.batt} /></g>;
}

function Wind({ x, y }: { x: number; y: number }) {
  return <g stroke="#9fb4ff" strokeWidth={1.6} strokeLinecap="round"><line x1={x} y1={y} x2={x} y2={y + 9} />
    {[-90, 30, 150].map((a) => { const r = (a * Math.PI) / 180; return <line key={a} x1={x} y1={y} x2={x + 8 * Math.cos(r)} y2={y + 8 * Math.sin(r)} />; })}</g>;
}
function Generator({ x, y }: { x: number; y: number }) {
  return <g><rect x={x - 7} y={y - 5} width={14} height={10} rx={2} fill="none" stroke="#e5484d" strokeWidth={1.6} />
    <text x={x} y={y + 3.5} textAnchor="middle" fontSize={8} fontWeight={700} fill="#e5484d">G</text></g>;
}
function Bolt({ x, y }: { x: number; y: number }) {
  return <path d={`M${x + 1} ${y - 8} L${x - 4} ${y + 1} H${x} L${x - 1} ${y + 8} L${x + 4} ${y - 1} H${x} Z`} fill="#c3ccd8" />;
}
// one icon per source on the node's face: up to two per row, smaller when there are several
function Icons({ sources, soc }: { sources: Source[]; soc: number | null }) {
  const one = sources.length === 1;
  return <>{sources.map((s, i) => {
    const [x, y] = one ? P([5.1, 4.04, 1.1]) : P([4.82 + (i % 2) * 0.56, 4.04, 1.5 - Math.floor(i / 2) * 0.42]);
    const icon = s === "solar" ? <Sun x={0} y={0} /> : s === "battery" ? <Battery x={0} y={0} soc={soc} />
      : s === "wind" ? <Wind x={0} y={0} /> : s === "generator" ? <Generator x={0} y={0} /> : <Bolt x={0} y={0} />;
    return <g key={s} transform={`translate(${x},${y + (one ? 4 : 0)}) scale(${one ? 1 : 0.72})`}>{icon}</g>;
  })}</>;
}

export default function House({ v }: { v: HouseValues }) {
  const hasInv = v.sources.length > 0;
  const max = Math.max(1e-9, ...[v.grid, v.house, v.inv, v.ev].map((x) => Math.abs(x ?? 0)));
  const W = 4.04; // wire plane, just in front of the front wall
  return (
    <svg viewBox={v.hasEv ? "0 105 600 410" : "90 105 510 410"} className="house-scene" role="img" aria-label={v.ariaLabel}>
      <defs>
        <linearGradient id="hs-wall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f4f7fb" /><stop offset="100%" stopColor="#dde4ee" />
        </linearGradient>
        <radialGradient id="hs-ground" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--me-accent)" stopOpacity="0.16" /><stop offset="100%" stopColor="var(--me-accent)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx={P([2, 3, 0])[0]} cy={P([2, 3, 0])[1]} rx={270} ry={120} fill="url(#hs-ground)" />
      <polygon points={pts([[v.hasEv ? -5.2 : -1.6, -0.4, 0], [8.6, -0.4, 0], [8.6, 5.8, 0], [v.hasEv ? -5.2 : -1.6, 5.8, 0]])} className="hs-plot" />
      {v.hasEv ? <>{tree(-5, 0.6)}{tree(-4.4, -0.2)}</> : tree(-1.2, 0.2)}

      {/* grid pole behind the house, right */}
      <line x1={P([8.2, 0.6, 0])[0]} y1={P([8.2, 0.6, 0])[1]} x2={P([8.2, 0.6, 4.6])[0]} y2={P([8.2, 0.6, 4.6])[1]} stroke="#7a5a3a" strokeWidth={5} strokeLinecap="round" />
      <line x1={P([8.2, 0.1, 4.3])[0]} y1={P([8.2, 0.1, 4.3])[1]} x2={P([8.2, 1.1, 4.3])[0]} y2={P([8.2, 1.1, 4.3])[1]} stroke="#7a5a3a" strokeWidth={4} strokeLinecap="round" />
      {v.hasEv && <g>
        <polygon points={pts([[-4, 4, 0], [0, 4, 0], [0, 4, 2.4], [-4, 4, 2.4]])} fill="url(#hs-wall)" stroke="#c3ccd8" />
        <polygon points={pts([[-3.5, 4, 0], [-0.6, 4, 0], [-0.6, 4, 1.95], [-3.5, 4, 1.95]])} fill="#2a3240" />
        <polygon points={pts([[-4.3, 4.45, 2.35], [0.1, 4.45, 2.35], [0.1, 2.2, 3.35], [-4.3, 2.2, 3.35]])} className="hs-roof" />
        <clipPath id="hs-garage-door"><polygon points={pts([[-3.5, 4, 0], [-0.6, 4, 0], [-0.6, 4, 1.95], [-3.5, 4, 1.95]])} /></clipPath>
        <g clipPath="url(#hs-garage-door)">
          {box(-2.95, -2.6, 3.15, 3.6, 0.0, 0.36, "#1c1f26", "#14161b", "#2a2f38")}
          {box(-1.5, -1.15, 3.15, 3.6, 0.0, 0.36, "#1c1f26", "#14161b", "#2a2f38")}
          {box(-3.0, -1.1, 1.0, 3.85, 0.2, 0.7, "#d63f44", "#b93a3e", "#f06a6e")}
          {box(-2.85, -1.25, 1.4, 3.0, 0.7, 1.2, "#9fd3f2", "#b93a3e", "#e5484d")}
          <polygon points={pts([[-2.4, 3.86, 0.28], [-1.7, 3.86, 0.28], [-1.7, 3.86, 0.42], [-2.4, 3.86, 0.42]])} fill="#2b2f37" />
          <polygon points={pts([[-2.9, 3.86, 0.48], [-2.5, 3.86, 0.48], [-2.5, 3.86, 0.6], [-2.9, 3.86, 0.6]])} fill="#fff3c4" />
          <polygon points={pts([[-1.6, 3.86, 0.48], [-1.2, 3.86, 0.48], [-1.2, 3.86, 0.6], [-1.6, 3.86, 0.6]])} fill="#fff3c4" />
        </g>
        <polygon points={pts([[-0.55, W, 0.9], [-0.15, W, 0.9], [-0.15, W, 1.5], [-0.55, W, 1.5]])} fill="#3a4250" />
      </g>}

      {/* house body: side wall with gable, front wall, windows, door, roof */}
      <polygon points={pts([[6, 0, 0], [6, 4, 0], [6, 4, 3], [6, 2, 5], [6, 0, 3]])} fill="#c9d3e0" stroke="#b7c2d1" />
      <polygon points={pts([[0, 4, 0], [6, 4, 0], [6, 4, 3], [0, 4, 3]])} fill="url(#hs-wall)" stroke="#c3ccd8" />
      {[[0.45, 1.05], [2.7, 3.3]].map(([a, b], i) => (
        <polygon key={i} points={pts([[a, 4, 1.25], [b, 4, 1.25], [b, 4, 2.3], [a, 4, 2.3]])} className="hs-window" />
      ))}
      <polygon points={pts([[1.4, 4, 0], [2.3, 4, 0], [2.3, 4, 2.0], [1.4, 4, 2.0]])} fill="#8a6a4a" />
      <polygon points={pts([[1.25, 4.5, 0], [2.45, 4.5, 0], [2.45, 4.5, 0.18], [1.25, 4.5, 0.18]])} fill="#cfd6df" />
      {[0.9, 2.3].map((y0, i) => (
        <polygon key={i} points={pts([[6, y0, 1.25], [6, y0 + 0.8, 1.25], [6, y0 + 0.8, 2.2], [6, y0, 2.2]])} className="hs-window side" />
      ))}
      <polygon points={pts([[-0.35, 2, 5], [6.35, 2, 5], [6.35, -0.5, 2.85], [-0.35, -0.5, 2.85]])} className="hs-roof back" />
      <polygon points={pts([[6.35, 2, 5], [6.35, -0.5, 2.85], [6.35, -0.5, 2.7], [6.35, 2, 4.85]])} fill="#1d2027" />
      <polygon points={pts([[-0.35, 4.5, 2.85], [6.35, 4.5, 2.85], [6.35, 2, 5], [-0.35, 2, 5]])} className="hs-roof" />
      <polygon points={pts([[6.35, 4.5, 2.85], [6.35, 4.5, 2.7], [6.35, 2, 4.85], [6.35, 2, 5]])} fill="#1d2027" />

      {/* the PowerHub at the meter: everything behind it is "house" to the grid */}
      <polygon points={pts([[3.45, W, 1.6], [4.15, W, 1.6], [4.15, W, 2.35], [3.45, W, 2.35]])} fill="#f8fafc" stroke="#aab4c3">
        <title>{v.labels.powerhub}</title></polygon>
      <circle cx={P([3.8, W, 1.8])[0]} cy={P([3.8, W, 1.8])[1]} r={2.2} fill={v.live ? "#2ec27e" : "#9aa4b2"} />
      {/* one node for every local source: the grid meter can't tell them apart */}
      {hasInv && <g>
        <polygon points={pts([[4.55, W, 0.45], [5.65, W, 0.45], [5.65, W, 1.75], [4.55, W, 1.75]])} fill="#f8fafc" stroke="#aab4c3" />
        <Icons sources={v.sources} soc={v.soc} />
      </g>}
      {tree(7.6, 3.4)}

      {/* flows: only grid import/export is measured by the PowerHub; the rest when the user picked sensors */}
      <Wire route={[[8.2, 0.6, 4.3], [6.03, 1.0, 2.6], [6.03, W, 2.6], [4.15, W, 2.6], [4.15, W, 2.2]]} w={v.grid} max={max} color={C.grid} />
      <Wire route={[[3.45, W, 1.75], [3.38, W, 1.75], [3.38, W, 1.0], [2.36, W, 1.0]]} w={v.house} max={max} color={C.house} />
      {hasInv && <Wire route={[[4.55, W, 1.55], [4.35, W, 1.55], [4.35, W, 1.8], [4.15, W, 1.8]]} w={v.inv} max={max} color={C.inv} />}
      {v.hasEv && <Wire route={[[3.6, W, 1.6], [3.6, W, 0.12], [-0.35, W, 0.12], [-0.35, W, 0.9]]} w={v.ev} max={max} color={C.ev} />}

      <Tag at={[8.4, 0.6, 6.4]} title={v.labels.grid} value={v.text.grid} sub={v.text.gridSub} color={C.grid} />
      <Tag at={[2.4, 5.6, -0.7]} title={v.labels.house} value={v.text.house} color={C.house} />
      {hasInv && <Tag at={[7.2, 4.6, 0.6]} title={v.labels.inverter} value={v.text.inv} sub={v.text.invSub} color={C.inv} align="start" />}
      {v.hasEv && <Tag at={[-1.9, 5.4, -0.6]} title={v.labels.ev} value={v.text.ev} sub={v.text.evSub} color={C.ev} />}
    </svg>
  );
}
