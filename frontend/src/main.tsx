import { createRoot, Root } from "react-dom/client";
import App from "./App";
import css from "./styles.css?inline";

class PowerHubPanel extends HTMLElement {
  private root?: Root;
  private _hass: any;
  private _narrow = false;
  private _active: string | null = null;  // the entry whose settings apply (panel config, set by the backend)
  set hass(h: any) { this._hass = h; this.render(); }
  set narrow(n: boolean) { this._narrow = n; this.render(); }
  set panel(p: any) { this._active = p?.config?.entry_id ?? null; this.render(); }
  connectedCallback() {
    if (this.root) return;
    // a re-attached element keeps its shadow root; attachShadow() would throw a second time
    const shadow = this.shadowRoot ?? this.attachShadow({ mode: "open" });
    shadow.replaceChildren();
    const style = document.createElement("style");
    style.textContent = css;
    const mount = document.createElement("div");
    shadow.append(style, mount);
    this.root = createRoot(mount);
    this.render();
  }
  disconnectedCallback() { this.root?.unmount(); this.root = undefined; }
  private render() { if (this.root && this._hass) this.root.render(<App hass={this._hass} narrow={this._narrow} active={this._active} />); }
}

if (!customElements.get("malarenergi-powerhub-panel")) customElements.define("malarenergi-powerhub-panel", PowerHubPanel);
