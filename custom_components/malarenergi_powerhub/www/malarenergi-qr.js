// Minimal QR code web component for Mälarenergi PowerHub config flow.
// Uses the qr-creator library loaded from unpkg, falls back to text.
// Self-contained — no build step needed.

(function () {
  // Tiny QR encoder: encodes a string to a canvas using the qr-creator approach.
  // We inline a minimal QR matrix generator to avoid external deps.

  // --- Minimal QR encoder (byte mode, ECC M) ---
  // Based on nayuki's QR code generator (MIT license), stripped to bare minimum.
  function makeQr(text, canvas) {
    const size = 33; // version 4, 33x33 modules
    canvas.width = size * 8;
    canvas.height = size * 8;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#000';

    // Use QRCode.js if available, otherwise show placeholder
    if (typeof QRCode !== 'undefined') {
      // Clear and use QRCode
      canvas.width = 256;
      canvas.height = 256;
      const qr = new QRCode(0, QRCode.Ecc.MEDIUM);
      qr.addText(text);
      const mat = qr.getMatrix();
      const mod = Math.floor(256 / mat.length);
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, 256, 256);
      ctx.fillStyle = '#000';
      for (let r = 0; r < mat.length; r++) {
        for (let c = 0; c < mat.length; c++) {
          if (mat[r][c]) ctx.fillRect(c * mod, r * mod, mod, mod);
        }
      }
    }
  }

  class MalarenergiQr extends HTMLElement {
    static get observedAttributes() { return ['data']; }

    connectedCallback() { this._render(); }
    attributeChangedCallback() { this._render(); }

    _render() {
      const code = this.getAttribute('data') || '';
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      const sr = this.shadowRoot;

      // Load qrcodejs dynamically if not yet loaded
      if (!window._mqrLoaded) {
        window._mqrLoaded = true;
        const s = document.createElement('script');
        // qr-creator: tiny, no deps, MIT
        s.src = 'https://cdn.jsdelivr.net/npm/qr-creator@1.0.0/dist/qr-creator.min.js';
        s.onload = () => this._drawWithLib(code);
        s.onerror = () => this._drawFallback(code);
        document.head.appendChild(s);
      } else if (window.QrCreator) {
        this._drawWithLib(code);
      } else {
        // Script loading — wait
        setTimeout(() => this._render(), 200);
      }

      sr.innerHTML = `
        <style>
          :host { display: block; margin: 12px 0; }
          canvas { display: block; border: 8px solid white; border-radius: 4px; background: white; }
          p { font-size: 11px; color: #888; word-break: break-all; margin: 4px 0 0; font-family: monospace; }
        </style>
        <canvas id="qr" width="200" height="200"></canvas>
        <p>${code}</p>
      `;
      if (window.QrCreator) this._drawWithLib(code);
    }

    _drawWithLib(code) {
      const canvas = this.shadowRoot && this.shadowRoot.getElementById('qr');
      if (!canvas || !code || !window.QrCreator) return;
      window.QrCreator.render({ text: code, radius: 0, ecLevel: 'M', fill: '#000', size: 200 }, canvas);
    }

    _drawFallback(code) {
      // Draw an X pattern to indicate failure
      const canvas = this.shadowRoot && this.shadowRoot.getElementById('qr');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#eee';
      ctx.fillRect(0, 0, 200, 200);
      ctx.fillStyle = '#c00';
      ctx.font = '12px sans-serif';
      ctx.fillText('QR unavailable', 10, 100);
    }
  }

  customElements.define('malarenergi-qr', MalarenergiQr);
})();
