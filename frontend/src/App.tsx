import { useEffect, useRef, useState } from "react";
import House from "./House";
import { LANG_NAMES, T, pick } from "./i18n";

type Options = {
  show_panel: boolean; language: string; sources: Source[] | null; has_ev: boolean | null;
  production_power: string; battery_power: string; battery_soc: string; battery_invert: boolean; ev_power: string;
};
type Ctx = { hass: any; t: T; locale: string; narrow: boolean };
type Ents = Record<string, string>;  // translation_key -> entity_id

// local sources export can come from (panel.py SOURCES); v2g is the EV node, the rest share one node
export const SOURCES = ["solar", "battery", "wind", "generator", "v2g", "other"] as const;
export type Source = (typeof SOURCES)[number];
const TABS = ["overview", "settings"] as const;
type Tab = (typeof TABS)[number];
const KW: Record<string, number> = { mW: 1e-6, W: 1e-3, kW: 1, MW: 1e3 };  // HA power units -> kW
const AMP: Record<string, number> = { "μA": 1e-6, "µA": 1e-6, mA: 1e-3, A: 1 };
const VOLT: Record<string, number> = { mV: 1e-3, V: 1, kV: 1e3 };
// ponytail: module-level locale, set by App before its children render; fine for one panel per page
let LOCALE = "en-GB";
const fmt = (v: number | null | undefined, d = 0, u = "") =>
  v == null || Number.isNaN(v) ? "–" : `${v.toLocaleString(LOCALE, { minimumFractionDigits: d, maximumFractionDigits: d })}${u ? " " + u : ""}`;
const kwTxt = (v: number | null) => fmt(v == null ? null : Math.abs(v), Math.abs(v ?? 0) < 10 ? 2 : 1, "kW");

// Our entities, by translation_key (entity ids differ between installs/languages), on the PowerHub device of
// the config entry whose settings the panel shows (settings/get returns its entry_id).
// ponytail: one hub (that entry's); add a hub picker if anyone wants to switch between facilities.
function hubEntities(hass: any, entryId?: string | null): { dev?: string; ents?: Ents; hubs: number } {
  const byDev: Record<string, Ents> = {};
  for (const e of Object.values((hass.entities ?? {}) as Record<string, any>))
    if (e.platform === "malarenergi_powerhub" && e.device_id && e.translation_key) (byDev[e.device_id] ??= {})[e.translation_key] = e.entity_id;
  const devs = Object.keys(byDev);
  const dev = devs.find((d) => entryId && hass.devices?.[d]?.config_entries?.includes(entryId)) ?? devs[0];
  return { dev, ents: dev ? byDev[dev] : undefined, hubs: devs.length };
}

// HA core's Bitvis integration reads the same hub locally, on its own device. Ours carries the hub's MAC as a
// connection (since v0.3.0), so the Bitvis device sharing that MAC is the same hub. Without a MAC match, a
// single Bitvis device is only trusted when there's also a single PowerHub and no MAC says they differ. Per-phase sensors share a translation_key; the phase comes from the
// entity id (from the "phase_current_l1"-style key), the friendly name only as a fallback.
function bitvisEntities(hass: any, dev: string | undefined, hubs: number): Ents | undefined {
  const all = Object.values((hass.entities ?? {}) as Record<string, any>).filter((e) => e.platform === "bitvis" && e.device_id);
  const devs = [...new Set(all.map((e) => e.device_id as string))];
  const macs = (d?: string) => ((d && hass.devices?.[d]?.connections) ?? []).filter((c: string[]) => c[0] === "mac").map((c: string[]) => c[1]);
  const ours = macs(dev);
  const use = devs.find((d) => macs(d).some((m: string) => ours.includes(m)))
    ?? (devs.length === 1 && hubs === 1 && !(ours.length && macs(devs[0]).length) ? devs[0] : undefined);
  if (!use) return undefined;
  const out: Ents = {};
  for (const e of all.filter((e) => e.device_id === use && e.translation_key)) {
    const ph = (/_l([123])(?:_|$)/i.exec(e.entity_id) ?? /\bL([123])\b/i.exec(hass.states[e.entity_id]?.attributes?.friendly_name ?? ""))?.[1];
    out[ph ? `${e.translation_key}_l${ph}` : e.translation_key] = e.entity_id;
  }
  return out;
}

function reader(hass: any) {
  const st = hass.states as Record<string, any>;
  const num = (e?: string) => { const v = parseFloat(String(e && st[e]?.state).replace(/^A/, "")); return Number.isFinite(v) ? v : null; };
  // HA converts to the user's display unit; an unknown unit gives null, never a wrong number
  const conv = (e: string | undefined, table: Record<string, number>, dflt?: string) => {
    const v = num(e), f = table[(e && st[e]?.attributes?.unit_of_measurement) ?? dflt ?? ""];
    return v == null || f == null ? null : v * f;
  };
  return { st, num, conv, kw: (e?: string) => conv(e, KW) };
}

function Info({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => { if (!e.composedPath().includes(ref.current!)) setOpen(false); };
    window.addEventListener("pointerdown", close);
    return () => window.removeEventListener("pointerdown", close);
  }, [open]);
  return (
    <span className="info" ref={ref}>
      <button className="info-btn" onClick={() => setOpen(!open)} aria-label="info">i</button>
      {open && <span className="pop">{text}</span>}
    </span>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return <div className="kpi"><div className="label">{label}</div><div className={`value ${tone ?? ""}`}>{value}</div>{sub && <div className="muted">{sub}</div>}</div>;
}

export default function App({ hass, narrow }: { hass: any; narrow: boolean }) {
  const [opts, setOpts] = useState<Options | null>(null);
  const [entryId, setEntryId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(() => {
    try { const x = localStorage.getItem("ph_tab"); return TABS.includes(x as Tab) ? (x as Tab) : "overview"; } catch { return "overview"; }
  });
  const { t, locale } = pick(hass.locale?.language ?? hass.language, opts?.language);
  LOCALE = locale;
  const load = () => {
    setErr(null);
    hass.connection.sendMessagePromise({ type: "malarenergi_powerhub/settings/get" })
      .then((r: any) => { setOpts(r.options); setEntryId(r.entry_id ?? null); })
      .catch((e: any) => setErr(e?.message ?? String(e)));
  };
  useEffect(load, []);
  const go = (x: Tab) => { setTab(x); try { localStorage.setItem("ph_tab", x); } catch { /* private mode */ } };
  const { dev, ents, hubs } = hubEntities(hass, entryId);
  const bv = bitvisEntities(hass, dev, hubs);
  const ctx = { hass, t, locale, narrow };
  return (
    <div className={`page ${narrow ? "narrow" : ""}`}>
      <header>
        <div className="brand"><h1>{t.title}</h1></div>
        <nav className="tabs">
          {TABS.map((x) => <button key={x} className={tab === x ? "on" : ""} onClick={() => go(x)}>{t[`tab_${x}`]}</button>)}
        </nav>
      </header>
      {!ents ? <div className="card">{t.no_hub}</div>
        : err ? <div className="card error row-between"><span>{t.load_failed}: {err}</span><button className="btn" onClick={load}>{t.retry}</button></div>
        : !opts ? <div className="card">{t.loading}</div> : <>
        {tab === "overview" && <Overview {...ctx} ents={ents} bv={bv} opts={opts} />}
        {tab === "settings" && <Settings {...ctx} ents={ents} opts={opts} setOpts={setOpts} />}
      </>}
    </div>
  );
}

// What the user has behind the meter: their own answer in Settings wins, else what they told the energy company.
function flags(hass: any, ents: Ents, o: Options) {
  const st = hass.states;
  const evType = st[ents.ev_type]?.state;
  const sources: Source[] = o.sources ?? [
    ...(st[ents.has_solar]?.state === "on" ? ["solar" as const] : []),
    ...(st[ents.has_battery]?.state === "on" ? ["battery" as const] : []),
  ];
  return { sources, ev: o.has_ev ?? (!!evType && !["NONE", "unknown", "unavailable"].includes(evType)) };
}

function Overview({ hass, t, locale, narrow, ents, bv, opts }: Ctx & { ents: Ents; bv?: Ents; opts: Options }) {
  const { st, num, conv, kw } = reader(hass);
  // grid: prefer Bitvis' local values when both sides read
  const local = bv && kw(bv.power_active_import) != null && kw(bv.power_active_export) != null;
  const imp = local ? kw(bv!.power_active_import) : kw(ents.power_import);
  const exp = local ? kw(bv!.power_active_export) : kw(ents.power_export);
  const grid = imp == null || exp == null ? null : imp - exp;  // + buying
  const f = flags(hass, ents, opts);
  const node = f.sources.filter((x) => x !== "v2g");  // the one local-production node
  const has = (x: Source) => f.sources.includes(x);
  const v2g = has("v2g"), hasEv = f.ev || v2g;
  const prod0 = node.some((x) => x !== "battery") && opts.production_power ? kw(opts.production_power) : null;
  const prod = prod0 == null ? null : Math.max(0, prod0);
  const batt0 = has("battery") && opts.battery_power ? kw(opts.battery_power) : null;
  const batt = batt0 == null ? null : opts.battery_invert ? -batt0 : batt0;  // + discharging
  // each enabled flow needs its reading: production (any non-battery source), battery, EV
  const prodOk = !node.some((x) => x !== "battery") || prod != null;
  const battOk = !has("battery") || batt != null;
  const ev0 = hasEv && opts.ev_power ? kw(opts.ev_power) : null;
  const ev = ev0 == null ? null : v2g ? ev0 : Math.max(0, ev0);  // + charging; only V2G may feed back
  const evOk = !hasEv || ev != null;
  const inv = node.length && prodOk && battOk ? (prod ?? 0) + (batt ?? 0) : null;
  const soc = has("battery") && opts.battery_soc ? num(opts.battery_soc) : null;
  // house = grid + production + battery − EV. Exact only when every enabled flow has a reading. A missing
  // production reading can only add, so the sum is then a lower bound; a missing battery or EV reading can
  // subtract, so nothing can be said about the house.
  const exact = grid != null && prodOk && battOk && evOk;
  const bound = grid != null && battOk && evOk;
  const houseW = bound ? grid! + (prod ?? 0) + (batt ?? 0) - (ev ?? 0) : null;
  // negative = export nothing selected explains: the arrow shows it, a negative house load would be nonsense
  const house = houseW == null || houseW < 0 ? "–" : exact ? kwTxt(houseW) : `≥ ${kwTxt(houseW)}`;
  const parts = [prod != null && kwTxt(prod), batt != null && `${t.battery} ${batt < 0 ? "↑" : "↓"} ${kwTxt(batt)}`,
    soc != null && `${Math.round(soc)} %`].filter(Boolean).join(" · ");
  const exporting = grid != null && grid < -0.03;
  const from = `${t.export_from}: ${f.sources.map((x) => t[`src_${x}`]).join(", ")}`;

  // phases: Bitvis' local currents, else ours
  const amps = [1, 2, 3].map((n) => conv(bv?.[`phase_current_l${n}`], AMP) ?? conv(ents[`current_l${n}`], AMP));
  const volts = [1, 2, 3].map((n) => conv(bv?.[`phase_voltage_l${n}`], VOLT));
  const fuse = conv(ents.fuse_size, AMP, "A") ?? conv(ents.fuse_limit_set, AMP);
  const up = num(ents.uptime);
  const han = st[ents.han_port_state]?.state;
  const val = (e: string, d = 0, u?: string) => fmt(num(e), d, u ?? st[e]?.attributes?.unit_of_measurement ?? "");

  const gridSub = grid == null ? "" : exporting ? (f.sources.length ? t.exporting : t.unexplained) : grid > 0.03 ? t.importing : t.idle;
  const invLabel = node.every((x) => x === "solar" || x === "battery") ? t.inverter : t.production;
  return (
    <>
      <div className="kpis">
        <Kpi label={grid == null ? t.grid : grid < -0.03 ? t.exporting : grid > 0.03 ? t.importing : t.idle} value={kwTxt(grid)} tone={grid != null && grid < -0.03 ? "pos" : ""} />
        <Kpi label={`${t.bought} · ${t.today}`} value={val(ents.import_today, 1)} />
        <Kpi label={`${t.sold} · ${t.today}`} value={val(ents.export_today, 1)} />
        <Kpi label={t.spot_now} value={val(ents.spot_price, 1)} />
      </div>
      <div className="grid-overview">
        <section className="card flow-card">
          <div className="card-head">
            <h2>{t.title}<Info text={t.flow_info} /></h2>
            <span className={`chip ${local ? "ok" : ""}`}>{local ? t.live_local : t.live_cloud}<Info text={local ? t.live_local_info : t.live_cloud_info} /></span>
          </div>
          <House v={{
            live: !!local, grid, house: houseW, inv, ev, sources: node, hasEv, soc,
            text: {
              grid: kwTxt(grid), gridSub,
              house, inv: kwTxt(inv), invSub: parts || t.not_measured,
              ev: kwTxt(ev), evSub: ev == null ? t.not_measured : ev < -0.03 ? t.ev_discharging : "",
            },
            labels: { grid: t.grid, house: t.house, inverter: invLabel, ev: t.ev, powerhub: t.powerhub },
            // the scene's text is hidden inside role="img", so its name carries the same readings
            ariaLabel: [`${t.grid}: ${kwTxt(grid)}${gridSub ? ` (${gridSub})` : ""}`, `${t.house}: ${house}`,
              node.length ? `${invLabel}: ${kwTxt(inv)}${parts ? ` (${parts})` : ""}` : "",
              hasEv ? `${t.ev}: ${kwTxt(ev)}` : ""].filter(Boolean).join(". "),
          }} />
          {f.sources.length > 0 && <div className="muted center">{from}</div>}
        </section>
        <div className="side">
          <section className="card">
            <h2>{t.phases}<Info text={t.phases_info} /></h2>
            <div className="phases" style={{ marginTop: 12 }}>
              {amps.map((a, i) => {
                const pct = a != null && fuse ? Math.min(100, (a / fuse) * 100) : 0;
                return (
                  <div key={i}>
                    <div className="row-between"><span className="muted">L{i + 1}{volts[i] != null ? ` · ${fmt(volts[i], 0, "V")}` : ""}</span>
                      <span>{fmt(a, 1, "A")}{fuse ? ` / ${fuse} A` : ""}</span></div>
                    <div className="meter"><div style={{ width: `${pct}%`, background: pct > 85 ? "var(--me-neg)" : pct > 60 ? "#f5a524" : "var(--me-accent)" }} /></div>
                  </div>
                );
              })}
            </div>
          </section>
          <section className="card">
            <h2>{t.prices}</h2>
            <div className="stack">
              <div className="row-between"><span className="muted">{t.avg_month}</span><span>{val(ents.avg_price_this_month, 1)}</span></div>
              <div className="row-between"><span className="muted">{t.market_month}</span><span>{val(ents.market_avg_price_this_month, 1)}</span></div>
              <div className="row-between"><span className="muted">{t.baseload}</span><span>{val(ents.baseload_power, 2)}</span></div>
              <div className="row-between"><span className="muted">{t.power_limit}</span><span>{val(ents.power_limit, 1)}</span></div>
            </div>
          </section>
          <section className="card">
            <h2>{t.device}</h2>
            <div className="stack">
              <div className="row-between"><span className="muted">{t.han}</span><span>{han ? (t as any)[`han_${han}`] ?? han.toLowerCase() : "–"}</span></div>
              <div className="row-between"><span className="muted">{t.wifi}</span><span>{val(ents.wifi_rssi)}</span></div>
              <div className="row-between"><span className="muted">{t.uptime}</span><span>{up == null ? "–" : `${Math.floor(up / 86400)} d ${Math.floor((up % 86400) / 3600)} h`}</span></div>
              <div className="row-between"><span className="muted">{t.firmware}</span><span>{st[ents.sw_version]?.state ?? "–"}</span></div>
              {st[ents.latest_notification]?.state && !["unknown", "unavailable"].includes(st[ents.latest_notification].state) &&
                <div className="row-between"><span className="muted">{t.latest}</span><span>{st[ents.latest_notification].state}</span></div>}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

function Toggle({ on, set, disabled }: { on: boolean; set: (v: boolean) => void; disabled?: boolean }) {
  // used inside a <label className="setting">, which gives the checkbox its accessible name
  return <span className="switch"><input type="checkbox" checked={on} disabled={disabled} onChange={(e) => set(e.target.checked)} /><span aria-hidden /></span>;
}

function Settings({ hass, t, ents, opts, setOpts }: Ctx & { ents: Ents; opts: Options; setOpts: (o: Options) => void }) {
  const [msg, setMsg] = useState("");
  const admin = !!hass.user?.is_admin;
  const save = (patch: Partial<Options>) => {
    setOpts({ ...opts, ...patch });  // optimistic; a failed save reloads what the server actually has
    hass.connection.sendMessagePromise({ type: "malarenergi_powerhub/settings/set", options: patch })
      .then((r: any) => { setOpts(r.options); setMsg(t.saved); setTimeout(() => setMsg(""), 1500); })
      .catch((e: any) => {
        setMsg(e?.message ?? String(e));
        hass.connection.sendMessagePromise({ type: "malarenergi_powerhub/settings/get" })
          .then((r: any) => setOpts(r.options)).catch(() => {});
      });
  };
  const f = flags(hass, ents, opts);
  const has = (x: Source) => f.sources.includes(x);
  // sensors offered in the pickers: anything with a power unit, or % for the battery charge
  const sensors = (units: string[]) => Object.values(hass.states as Record<string, any>)
    .filter((s) => s.entity_id.startsWith("sensor.") && units.includes(s.attributes?.unit_of_measurement)).map((s) => s.entity_id).sort();
  const power = sensors(Object.keys(KW)), pct = sensors(["%"]);
  const pickRow = (key: "production_power" | "battery_power" | "battery_soc" | "ev_power", list: string[]) => (
    <label className="setting" key={key}><span>{t[key]}</span>
      <input className="pick" list={`ph-${key}`} defaultValue={opts[key]} disabled={!admin} placeholder="sensor.…"
        onBlur={(e) => e.target.value.trim() !== opts[key] && save({ [key]: e.target.value.trim() })} />
      <datalist id={`ph-${key}`}>{list.map((id) => <option key={id} value={id}>{hass.states[id]?.attributes?.friendly_name}</option>)}</datalist>
    </label>
  );
  return (
    <div className="settings-grid">
      {!admin && <div className="card muted">{t.admin_only}</div>}
      <section className="card">
        <h2>{t.s_sources}<Info text={t.s_sources_info} /></h2>
        {SOURCES.map((x) => (
          <label className="setting" key={x}>
            <span>{t[`opt_${x}`]}{opts.sources == null && <em className="muted"> · {t.from_hub}</em>}</span>
            <Toggle on={has(x)} disabled={!admin}
              set={(v) => save({ sources: v ? SOURCES.filter((y) => y === x || has(y)) : f.sources.filter((y) => y !== x) })} />
          </label>
        ))}
        <label className="setting">
          <span>{t.has_ev}{opts.has_ev == null && <em className="muted"> · {t.from_hub}</em>}</span>
          <Toggle on={f.ev} disabled={!admin} set={(v) => save({ has_ev: v })} />
        </label>
      </section>
      <section className="card">
        <h2>{t.s_sensors}<Info text={t.s_sensors_info} /></h2>
        {f.sources.some((x) => x !== "battery" && x !== "v2g") && pickRow("production_power", power)}
        {has("battery") && <>{pickRow("battery_power", power)}{pickRow("battery_soc", pct)}
          <label className="setting"><span>{t.battery_invert}</span><Toggle on={opts.battery_invert} disabled={!admin} set={(v) => save({ battery_invert: v })} /></label></>}
        {(f.ev || has("v2g")) && pickRow("ev_power", power)}
        {!f.sources.length && !f.ev && <div className="muted">{t.s_sources_info}</div>}
      </section>
      <section className="card">
        <h2>{t.s_panel}</h2>
        <label className="setting"><span>{t.s_lang}</span>
          <select className="pick" value={opts.language} disabled={!admin} onChange={(e) => save({ language: e.target.value })}>
            <option value="auto">{t.lang_auto}</option>
            {Object.entries(LANG_NAMES).map(([k, n]) => <option key={k} value={k}>{n}</option>)}
          </select></label>
        <label className="setting"><span>{t.show_panel}<br /><em className="muted">{t.show_panel_info}</em></span>
          <Toggle on={opts.show_panel} disabled={!admin} set={(v) => save({ show_panel: v })} /></label>
        {msg && <div className="muted">{msg}</div>}
      </section>
    </div>
  );
}
