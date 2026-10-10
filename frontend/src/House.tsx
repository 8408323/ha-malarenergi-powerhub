// Isometric house scene (adapted from the villa-energy panel): the grid's cable cabinet, the PowerHub at the meter and, for the sources
// the user ticked, physical objects (roof panels, battery cabinet, generator, wind turbine, garage with an EV) wired to
// one inverter node. Pure SVG, back to front.

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
  sources: Source[]; hasEv: boolean; soc: number | null; underground: boolean;  // sources: the production node's, no v2g
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

// ── physical sources, drawn where they'd stand: panels on the roof, a battery cabinet and a generator against the
// side wall, a wind turbine on the grass. Thin cables run to the inverter box; they carry no flow of their own
// because the PowerHub only measures the grid connection (the inverter node shows the combined value).

// a point on the front roof slope: u along the ridge (x), t from eave (0) to ridge (1)
const roof = (u: number, t: number): V => [u, 4.5 - 2.5 * t, 2.85 + 2.15 * t];

function SolarPanels() {
  const cols = [0.5, 1.75, 3.0, 4.25], rows = [0.04, 0.4];
  return <g>{rows.flatMap((t) => cols.map((u) => {
    const q = [roof(u, t), roof(u + 1.12, t), roof(u + 1.12, t + 0.32), roof(u, t + 0.32)];
    const lift = (v: V): V => [v[0], v[1], v[2] + 0.05];
    const cells = [1, 2].map((k) => [roof(u + (1.12 * k) / 3, t), roof(u + (1.12 * k) / 3, t + 0.32)]);
    return <g key={`${u},${t}`}>
      <polygon points={pts(q.map(lift))} fill="#1f3a8a" stroke="#c9d6f2" strokeWidth={1.2} />
      {cells.map(([m, n], i) => <polyline key={i} points={pts([lift(m), lift(n)])} stroke="#5c7bd6" strokeWidth={0.8} />)}
      <polyline points={pts([lift(roof(u, t + 0.16)), lift(roof(u + 1.12, t + 0.16))])} stroke="#5c7bd6" strokeWidth={0.8} />
    </g>;
  }))}</g>;
}

function BatteryCabinet({ soc }: { soc: number | null }) {
  const lvl = Math.max(0, Math.min(100, soc ?? 60)) / 100;
  return <g>
    {box(6.08, 6.62, 2.55, 3.65, 0, 1.45, "#f2f5f9", "#d8dee8", "#ffffff")}
    <polygon points={pts([[6.62, 2.8, 1.12], [6.62, 3.4, 1.12], [6.62, 3.4, 1.22], [6.62, 2.8, 1.22]])} fill={C.batt} />
    {/* charge gauge on the front face */}
    <polygon points={pts([[6.2, 3.65, 0.3], [6.5, 3.65, 0.3], [6.5, 3.65, 0.95], [6.2, 3.65, 0.95]])} fill="#2a3240" />
    <polygon points={pts([[6.24, 3.66, 0.34], [6.46, 3.66, 0.34], [6.46, 3.66, 0.34 + 0.57 * lvl], [6.24, 3.66, 0.34 + 0.57 * lvl]])} fill={C.batt} />
  </g>;
}

function Generator() {
  const [ex, ey] = P([6.95, 1.05, 0.95]);
  return <g>
    {box(6.12, 7.05, 0.75, 1.95, 0, 0.85, "#e5484d", "#c13a3e", "#f26b6f")}
    {[0.3, 0.45, 0.6].map((z) => <polyline key={z} points={pts([[7.05, 1.15, z], [7.05, 1.65, z]])} stroke="#8e2a2d" strokeWidth={1.4} />)}
    <rect x={ex - 2} y={ey - 14} width={4} height={14} rx={1.5} fill="#5b616c" />
  </g>;
}

function WindTurbine({ at }: { at: V }) {
  const [bx, by] = P(at), [hx, hy] = P([at[0], at[1], at[2] + 3.4]);
  return <g>
    <path d={`M${bx - 4},${by} L${hx - 1.5},${hy} L${hx + 1.5},${hy} L${bx + 4},${by} Z`} fill="#eef2f7" stroke="#c3ccd8" />
    <ellipse cx={hx + 3} cy={hy} rx={6} ry={3.5} fill="#dfe5ee" stroke="#c3ccd8" />
    <g transform={`translate(${hx - 2},${hy})`}>
      <g>
        {[0, 120, 240].map((a) => <path key={a} transform={`rotate(${a})`} d="M0,-2 C8,-3.5 26,-2.5 36,0 C26,2.5 8,3.5 0,2 Z" fill="#f8fafc" stroke="#aab4c3" strokeWidth={0.8} />)}
        {!REDUCED && <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="5s" repeatCount="indefinite" />}
      </g>
      <circle r={3.2} fill="#c3ccd8" />
    </g>
  </g>;
}

// a small mark on the inverter face for sources without an object of their own ("other")
function Bolt({ x, y }: { x: number; y: number }) {
  return <path d={`M${x + 1} ${y - 8} L${x - 4} ${y + 1} H${x} L${x - 1} ${y + 8} L${x + 4} ${y - 1} H${x} Z`} fill="#c3ccd8" />;
}

const WIND_AT: V = [8.0, -1.6, 0];
const POLE: V = [8.2, 0.6, 0];        // overhead: the pole behind the house
const CAB: [number, number] = [4.0, 6.7];  // underground: the cable cabinet in front of the meter (x, front y)

export default function House({ v }: { v: HouseValues }) {
  const hasInv = v.sources.length > 0;
  const has = (x: Source) => v.sources.includes(x);
  const max = Math.max(1e-9, ...[v.grid, v.house, v.inv, v.ev].map((x) => Math.abs(x ?? 0)));
  const W = 4.04; // wire plane, just in front of the front wall
  return (
    <svg viewBox={v.hasEv ? "0 105 610 430" : "90 105 520 430"} className="house-scene" role="img" aria-label={v.ariaLabel}>
      <defs>
        <linearGradient id="hs-wall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f4f7fb" /><stop offset="100%" stopColor="#dde4ee" />
        </linearGradient>
        <radialGradient id="hs-ground" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--me-accent)" stopOpacity="0.16" /><stop offset="100%" stopColor="var(--me-accent)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx={P([2, 3, 0])[0]} cy={P([2, 3, 0])[1]} rx={270} ry={120} fill="url(#hs-ground)" />
      <polygon points={pts([[v.hasEv ? -5.2 : -1.6, has("wind") ? -1.8 : -0.4, 0], [9.7, has("wind") ? -2.2 : -0.4, 0], [9.7, 5.8, 0], [v.hasEv ? -5.2 : -1.6, 5.8, 0]])} className="hs-plot" />
      {has("wind") && <WindTurbine at={WIND_AT} />}
      {v.hasEv ? <>{tree(-5, 0.6)}{tree(-4.4, -0.2)}</> : tree(-1.2, 0.2)}

      {/* the grid feed, as the user picked: an overhead line from a pole behind the house, or an underground cable
          from the street's cable cabinet (kabelskåp) in front of it */}
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
      {box(1.25, 2.45, 4.0, 4.45, 0, 0.14, "#cfd6df", "#b7c2d1", "#e3e8ef")}
      {[0.9, 2.3].map((y0, i) => (
        <polygon key={i} points={pts([[6, y0, 1.25], [6, y0 + 0.8, 1.25], [6, y0 + 0.8, 2.2], [6, y0, 2.2]])} className="hs-window side" />
      ))}
      <polygon points={pts([[-0.35, 2, 5], [6.35, 2, 5], [6.35, -0.5, 2.85], [-0.35, -0.5, 2.85]])} className="hs-roof back" />
      <polygon points={pts([[6.35, 2, 5], [6.35, -0.5, 2.85], [6.35, -0.5, 2.7], [6.35, 2, 4.85]])} fill="#1d2027" />
      <polygon points={pts([[-0.35, 4.5, 2.85], [6.35, 4.5, 2.85], [6.35, 2, 5], [-0.35, 2, 5]])} className="hs-roof" />
      <polygon points={pts([[6.35, 4.5, 2.85], [6.35, 4.5, 2.7], [6.35, 2, 4.85], [6.35, 2, 5]])} fill="#1d2027" />
      {has("solar") && <SolarPanels />}
      {has("generator") && <Generator />}
      {has("battery") && <BatteryCabinet soc={v.soc} />}

      {/* the PowerHub at the meter: everything behind it is "house" to the grid */}
      <polygon points={pts([[3.45, W, 1.6], [4.15, W, 1.6], [4.15, W, 2.35], [3.45, W, 2.35]])} fill="#f8fafc" stroke="#aab4c3">
        <title>{v.labels.powerhub}</title></polygon>
      <circle cx={P([3.8, W, 1.8])[0]} cy={P([3.8, W, 1.8])[1]} r={2.2} fill={v.live ? "#2ec27e" : "#9aa4b2"} />
      {/* one node for every local source: the grid meter can't tell them apart */}
      {hasInv && <g>
        <polygon points={pts([[4.55, W, 0.45], [5.65, W, 0.45], [5.65, W, 1.75], [4.55, W, 1.75]])} fill="#f8fafc" stroke="#aab4c3" />
        <polygon points={pts([[4.75, W + 0.01, 1.2], [5.45, W + 0.01, 1.2], [5.45, W + 0.01, 1.55], [4.75, W + 0.01, 1.55]])} fill="#2a3240" />
        <circle cx={P([4.85, W, 0.75])[0]} cy={P([4.85, W, 0.75])[1]} r={2.2} fill="#2ec27e" />
        {has("other") && <Bolt x={P([5.25, W, 0.8])[0]} y={P([5.25, W, 0.8])[1]} />}
      </g>}
      {v.underground && <g>
        {box(CAB[0] - 0.3, CAB[0] + 0.3, CAB[1], CAB[1] + 0.6, 0, 1.15, "#3f7d4f", "#2f6340", "#5a9a69")}
        <polygon points={pts([[CAB[0] - 0.2, CAB[1] + 0.6, 0.85], [CAB[0] + 0.2, CAB[1] + 0.6, 0.85], [CAB[0] + 0.2, CAB[1] + 0.6, 0.95], [CAB[0] - 0.2, CAB[1] + 0.6, 0.95]])} fill="#f5d90a" />
      </g>}
      {!hasInv && tree(7.6, 3.4) /* that spot is the inverter label's and the cabinets' */}

      {/* flows: only grid import/export is measured by the PowerHub; the rest when the user picked sensors */}
      <Wire route={v.underground ? [[CAB[0], CAB[1], 0.02], [CAB[0], W, 0.02], [CAB[0], W, 1.6]] : [[POLE[0], POLE[1], 3.95], [3.6, W, 2.35]]} w={v.grid} max={max} color={C.grid} />
      <Wire route={[[3.45, W, 1.75], [3.38, W, 1.75], [3.38, W, 1.0], [2.36, W, 1.0]]} w={v.house} max={max} color={C.house} />
      {/* one cable per source, each on its own lane into the inverter (separate entry points, no shared
          segments), drawn on top so none is hidden: solar down the front wall, the others along the ground */}
      {has("solar") && <Wire route={[[5.35, W, 2.84], [5.35, W, 1.75]]} w={null} max={max} color={C.inv} />}
      {has("battery") && <Wire route={[[6.35, 3.66, 0.3], [6.35, 4.3, 0.02], [5.25, 4.3, 0.02], [5.25, W, 0.02], [5.25, W, 0.45]]} w={null} max={max} color={C.inv} />}
      {has("generator") && <Wire route={[[6.9, 1.96, 0.3], [6.9, 4.5, 0.02], [5.0, 4.5, 0.02], [5.0, W, 0.02], [5.0, W, 0.45]]} w={null} max={max} color={C.inv} />}
      {has("wind") && <Wire route={[[WIND_AT[0], WIND_AT[1] + 0.1, 0.02], [7.35, WIND_AT[1] + 0.1, 0.02], [7.35, 4.7, 0.02], [4.75, 4.7, 0.02], [4.75, W, 0.02], [4.75, W, 0.45]]} w={null} max={max} color={C.inv} />}
      {/* the pole stands in front of the ground cables behind it, so it is drawn after them */}
      {!v.underground && <g>
        <line x1={P(POLE)[0]} y1={P(POLE)[1]} x2={P([POLE[0], POLE[1], 4.4])[0]} y2={P([POLE[0], POLE[1], 4.4])[1]} stroke="#7a5a3a" strokeWidth={5} strokeLinecap="round" />
        <line x1={P([POLE[0], POLE[1] - 0.5, 4.1])[0]} y1={P([POLE[0], POLE[1] - 0.5, 4.1])[1]} x2={P([POLE[0], POLE[1] + 0.5, 4.1])[0]} y2={P([POLE[0], POLE[1] + 0.5, 4.1])[1]} stroke="#7a5a3a" strokeWidth={4} strokeLinecap="round" />
      </g>}
      {hasInv && <Wire route={[[4.55, W, 1.55], [4.35, W, 1.55], [4.35, W, 1.8], [4.15, W, 1.8]]} w={v.inv} max={max} color={C.inv} />}
      {v.hasEv && <Wire route={[[3.55, W, 1.6], [3.55, W, 0.12], [-0.35, W, 0.12], [-0.35, W, 0.9]]} w={v.ev} max={max} color={C.ev} />}

      <Tag at={v.underground ? [CAB[0] + 0.5, CAB[1] + 1.4, -0.6] : [POLE[0] + 0.2, POLE[1], 6.2]} title={v.labels.grid} value={v.text.grid} sub={v.text.gridSub} color={C.grid} />
      <Tag at={v.underground ? [2.37, 6.27, 0] : [2.4, 5.6, -0.7]} title={v.labels.house} value={v.text.house} color={C.house} align={v.underground ? "end" : "middle"} />
      {hasInv && <Tag at={[8.2, 6.2, 0]} title={v.labels.inverter} value={v.text.inv} sub={v.text.invSub} color={C.inv} align="start" />}
      {v.hasEv && <Tag at={[-1.9, 5.4, -0.6]} title={v.labels.ev} value={v.text.ev} sub={v.text.evSub} color={C.ev} />}
    </svg>
  );
}
