"""Chequeos que se miden solos en una pantalla de Core Tienda.

Los usan navegador.py (`medidas`, `elementos`) y recorrido_completo.py. Son
una ayuda para no pasar nada por alto, NO el juicio final: lo que decide si
algo está mal es cómo se ve en la captura para una persona.

- Desborde: algo más ancho que la pantalla (en el celular obliga a correr de
  costado).
- Letra chica: texto visible de menos de 12 px.
- Contraste: texto contra su fondo por debajo de 4,5:1 (3:1 si es grande).
  Aproximado: toma el primer fondo sólido de los padres; sobre imágenes o
  degradés no opina.
- Para tocar: botones o links de menos de 32 px de alto o ancho en el celular
  (la recomendación es 44).
- Solo ícono: botones sin texto visible (una persona ve un dibujito y tiene
  que adivinar).
- Campos sin etiqueta visible.
"""

# Lo que se puede tocar y está a la vista, con su centro (coordenadas de la captura).
ELEMENTOS_JS = r"""
() => {
  const sel = 'a[href], button, [role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [role=switch], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const vw = innerWidth, vh = innerHeight, out = [], vistos = new Set();
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.right < 0 || r.top > vh || r.left > vw) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity) < 0.1) continue;
    const visible = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ');
    const aria = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('placeholder') || '';
    const nombre = visible || aria || el.getAttribute('name') || '';
    const clave = nombre + '|' + Math.round(r.x) + '|' + Math.round(r.y);
    if (vistos.has(clave)) continue; vistos.add(clave);
    const tag = el.tagName.toLowerCase();
    const rol = el.getAttribute('role') || (tag === 'a' ? 'link' : tag === 'input' ? (el.type || 'input') : tag);
    out.push({
      rol, nombre: nombre || '(sin nombre)',
      x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
      w: Math.round(r.width), h: Math.round(r.height),
      chico: (r.width < 32 || r.height < 32),
      soloIcono: !visible && ['button', 'link', 'a'].includes(rol) && !!el.querySelector('svg, img'),
    });
    if (out.length >= 150) break;
  }
  return out;
}
"""

# Las mediciones de la pantalla. Recibe `celular` (bool).
MEDIDAS_JS = r"""
(celular) => {
  const vw = document.documentElement.clientWidth, vh = innerHeight;
  const lienzo = document.createElement('canvas'); lienzo.width = lienzo.height = 1;
  const ctx = lienzo.getContext('2d', { willReadFrequently: true });
  const aRgb = (c) => {  // cualquier color CSS (rgb, oklch, lab...) a [r,g,b,a]
    ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255];
  };
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const fondoDe = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const st = getComputedStyle(e);
      if (st.backgroundImage && st.backgroundImage !== 'none') return null;
      const c = st.backgroundColor;
      if (c && c !== 'transparent' && c !== 'rgba(0, 0, 0, 0)') { const v = aRgb(c); if (v[3] > 0.85) return v; }
    }
    const raiz = getComputedStyle(document.body).backgroundColor;
    return raiz ? aRgb(raiz) : [255, 255, 255, 1];
  };
  const visible = (el, r) => {
    if (r.width < 1 || r.height < 1 || r.bottom < 0 || r.top > vh * 3) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && parseFloat(st.opacity) >= 0.3;
  };

  // Desborde horizontal
  const anchoPagina = document.documentElement.scrollWidth;
  const anchos = [];
  if (anchoPagina > vw + 2) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.right > vw + 2 && r.width > 0 && r.width <= anchoPagina + 50) {
        const st = getComputedStyle(el.parentElement || el);
        if (st.overflowX === 'auto' || st.overflowX === 'scroll') continue;
        anchos.push((el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + ' «' + (el.innerText || '').trim().slice(0, 40) + '»').replace(/\s+/g, ' '));
        if (anchos.length >= 5) break;
      }
    }
  }

  // Texto: letra chica y contraste
  const padres = new Set();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: n => n.textContent.trim().length > 1 ? 1 : 3 });
  while (tw.nextNode() && padres.size < 600) padres.add(tw.currentNode.parentElement);
  let chicos = 0; const ejChicos = []; let bajos = 0; const ejBajos = []; let medidos = 0;
  for (const el of padres) {
    if (!el) continue;
    const r = el.getBoundingClientRect();
    if (!visible(el, r)) continue;
    const st = getComputedStyle(el);
    const px = parseFloat(st.fontSize), peso = parseInt(st.fontWeight) || 400;
    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 50);
    if (!txt) continue;
    if (px < 12) { chicos++; if (ejChicos.length < 5) ejChicos.push(`${px}px «${txt}»`); }
    const fondo = fondoDe(el); if (!fondo) continue;
    const fg = aRgb(st.color); if (fg[3] < 0.1) continue;
    const a = fg[3]; const mezcla = [0, 1, 2].map(i => fg[i] * a + fondo[i] * (1 - a));
    const L1 = lum(mezcla), L2 = lum(fondo);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const grande = px >= 24 || (px >= 18.66 && peso >= 700);
    medidos++;
    if (ratio < (grande ? 3 : 4.5)) { bajos++; if (ejBajos.length < 6) ejBajos.push(`${ratio.toFixed(1)}:1 «${txt}»`); }
  }

  // Para tocar (celular), solo íconos y campos sin etiqueta
  let tocarChico = 0; const ejTocar = []; let soloIcono = 0; const ejIcono = []; let sinEtiqueta = 0; const ejSin = [];
  for (const el of document.querySelectorAll('a[href], button, [role=button], input, select, textarea')) {
    const r = el.getBoundingClientRect();
    if (!visible(el, r) || r.top > vh) continue;
    const texto = (el.innerText || '').trim();
    const tag = el.tagName.toLowerCase();
    if (celular && (r.width < 32 || r.height < 32) && !['input', 'select', 'textarea'].includes(tag)) {
      tocarChico++; if (ejTocar.length < 5) ejTocar.push(`${Math.round(r.width)}x${Math.round(r.height)} «${texto.slice(0, 30) || el.getAttribute('aria-label') || tag}»`);
    }
    if (['button', 'a'].includes(tag) && !texto && el.querySelector('svg, img')) {
      soloIcono++; if (ejIcono.length < 5) ejIcono.push(el.getAttribute('aria-label') || el.getAttribute('title') || '(sin nombre ni para lectores)');
    }
    if (['input', 'select', 'textarea'].includes(tag) && !['hidden', 'submit', 'button', 'checkbox', 'radio', 'file'].includes(el.type)) {
      const tieneLabel = (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || el.closest('label') || el.getAttribute('aria-label');
      if (!tieneLabel) { sinEtiqueta++; if (ejSin.length < 5) ejSin.push(el.getAttribute('placeholder') || el.name || tag); }
    }
  }

  const h1 = [...document.querySelectorAll('h1, h2')].filter(e => e.offsetParent).slice(0, 3).map(e => e.innerText.trim().slice(0, 60));
  return {
    ancho: vw, anchoPagina, desborde: anchoPagina > vw + 2, anchos,
    alto: document.documentElement.scrollHeight, pantallasDeAlto: +(document.documentElement.scrollHeight / vh).toFixed(1),
    chicos, ejChicos, bajos, ejBajos, medidos, tocarChico, ejTocar, soloIcono, ejIcono, sinEtiqueta, ejSin, titulos: h1,
    largoTexto: (document.body.innerText || '').trim().length,
  };
}
"""


def contar_en_texto(m: dict, celular: bool) -> str:
    """Las medidas en criollo, una línea por chequeo."""
    lineas = [f"Títulos: {' / '.join(m['titulos']) or '(ninguno visible)'}",
              f"Alto: {m['pantallasDeAlto']} pantallas"]
    if m["desborde"]:
        lineas.append(f"⚠ Se sale de costado: la página mide {m['anchoPagina']}px y la pantalla {m['ancho']}px. "
                      f"Culpables: {'; '.join(m['anchos']) or '?'}")
    if m["chicos"]:
        lineas.append(f"⚠ Letra de menos de 12px: {m['chicos']} textos. Ej.: {'; '.join(m['ejChicos'])}")
    if m["bajos"]:
        lineas.append(f"⚠ Contraste bajo (aprox.): {m['bajos']} de {m['medidos']} textos. Ej.: {'; '.join(m['ejBajos'])}")
    if celular and m["tocarChico"]:
        lineas.append(f"⚠ Difíciles de tocar con el dedo (<32px): {m['tocarChico']}. Ej.: {'; '.join(m['ejTocar'])}")
    if m["soloIcono"]:
        lineas.append(f"• Botones que son solo un ícono: {m['soloIcono']}. Ej.: {'; '.join(m['ejIcono'])}")
    if m["sinEtiqueta"]:
        lineas.append(f"• Campos sin etiqueta: {m['sinEtiqueta']}. Ej.: {'; '.join(m['ejSin'])}")
    if len(lineas) == 2:
        lineas.append("Sin alertas automáticas (igual mirá la captura).")
    return "\n".join(lineas)
