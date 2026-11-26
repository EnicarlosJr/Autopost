// Lê os anúncios da página de resultados do Mercado Livre (lista.mercadolivre.com.br).
// Usado pelas buscas automáticas. O valor da última linha é o resultado.
function readSearchPage() {
  if (/\/gz\/account-verification|\/jms\/.+\/login/.test(location.pathname)) return {blocked: true, items: []};
  const number = text => {
    const t = String(text || '').replace(/[^\d.,]/g, '');
    if (!t) return null;
    const n = Number(t.replace(/\./g, '').replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  };
  const money = el => {
    if (!el) return null;
    const whole = (el.querySelector('.andes-money-amount__fraction')?.textContent || '').replace(/\D/g, '');
    const cents = (el.querySelector('.andes-money-amount__cents')?.textContent || '').replace(/\D/g, '');
    return whole ? Number(cents ? `${whole}.${cents.slice(0, 2).padEnd(2, '0')}` : whole) : null;
  };
  const sold = text => {
    const m = String(text || '').toLowerCase().match(/\+?\s*([\d.,]+)\s*(mil)?\s*vendid/);
    if (!m) return null;
    const n = number(m[1]);
    return n == null ? null : Math.round(m[2] ? n * 1000 : n);
  };
  // 1) Dados embutidos na página (formato atual do Mercado Livre). Os cartões são desenhados a partir deles
  //    só quando a aba fica visível, mas os dados já estão no HTML, inclusive a categoria oficial.
  const fromPayload = readPayload();
  if (fromPayload.length) return {blocked: false, items: fromPayload, source: 'dados'};

  // 2) Cartões já desenhados na página (formato anterior).
  const items = [];
  for (const card of document.querySelectorAll('.poly-card')) {
    const link = card.querySelector('a.poly-component__title, .poly-component__title a, h3 a');
    if (!link) continue;
    let url;
    try { url = new URL(link.href); } catch { continue; }
    if (/click1\./.test(url.hostname)) continue;            // anúncio patrocinado (link de rastreio)
    if (!/mercadolivre\.com\.br$/.test(url.hostname)) continue;
    const fromFilter = (url.searchParams.get('pdp_filters') || '').match(/item_id:?(MLB\d+)/i);
    const fromPath = url.pathname.match(/(MLBU?)-?(\d{6,})/i);
    const externalId = fromFilter ? fromFilter[1] : fromPath ? `${fromPath[1]}${fromPath[2]}` : '';
    const catalogId = (url.pathname.match(/\/p\/(MLB\d+)/i) || [])[1] || '';
    if (!externalId) continue;
    const priceBox = card.querySelector('.poly-component__price, .poly-price');
    const current = priceBox?.querySelector('.poly-price__current .andes-money-amount, .andes-money-amount:not(.andes-money-amount--previous)');
    const previous = priceBox?.querySelector('.andes-money-amount--previous');
    const review = card.querySelector('.poly-component__review-compacted, .poly-reviews');
    // A nota é o rótulo no formato "4.8" (o mesmo bloco traz "+10mil vendidos").
    const ratingLabel = [...(review?.querySelectorAll('.polylabel-label, .poly-reviews__rating') || [])]
      .map(el => el.textContent.trim()).find(text => /^[0-5]([.,]\d)?$/.test(text));
    const rating = ratingLabel ? Number(ratingLabel.replace(',', '.')) : null;
    const shipping = card.querySelector('.poly-component__shipping-v2, .poly-component__shipping')?.textContent || '';
    const img = card.querySelector('img.poly-component__picture, img');
    items.push({
      external_id: externalId.toUpperCase(),
      // Anúncio específico (MLB + número): o link direto abre exatamente este vendedor e preço.
      url: /^MLB\d+$/i.test(externalId) ? `https://produto.mercadolivre.com.br/MLB-${externalId.slice(3)}` : url.origin + url.pathname,
      title: link.textContent.trim(),
      image_url: img?.getAttribute('data-src') || img?.currentSrc || img?.src || '',
      seller: (card.querySelector('.poly-component__seller')?.textContent || '').replace(/^por\s+/i, '').trim(),
      price: money(current),
      original_price: money(previous),
      price_note: /no\s*pix/i.test(priceBox?.textContent || '') ? 'no Pix' : '',
      rating,
      sold: sold(review?.textContent || card.textContent),
      free_shipping: /gr[aá]tis/i.test(shipping),
      catalog_product_id: catalogId.toUpperCase() || null,
    });
  }
  if (items.length) return {blocked: false, items, source: 'cartões'};

  // 3) Cartões antigos da página de Ofertas do dia (promotion-item).
  for (const card of document.querySelectorAll('.promotion-item, [class*="promotion-item__"]')) {
    if (!card.classList.contains('promotion-item')) continue;
    const link = card.querySelector('a.promotion-item__link-container, a[href]');
    let url;
    try { url = new URL(link?.href || ''); } catch { continue; }
    if (/click1\./.test(url.hostname) || !/mercadolivre\.com\.br$/.test(url.hostname)) continue;
    const fromPath = url.pathname.match(/(MLBU?)-?(\d{6,})/i);
    const catalogId = (url.pathname.match(/\/p\/(MLB\d+)/i) || [])[1] || '';
    const externalId = fromPath ? `${fromPath[1]}${fromPath[2]}`.toUpperCase() : catalogId.toUpperCase();
    if (!externalId) continue;
    const title = (card.querySelector('.promotion-item__title, p, h2, h3')?.textContent || '').trim();
    if (!title) continue;
    const img = card.querySelector('img');
    items.push({
      external_id: externalId,
      url: /^MLB\d+$/i.test(externalId) && !catalogId ? `https://produto.mercadolivre.com.br/MLB-${externalId.slice(3)}` : url.origin + url.pathname,
      title,
      image_url: img?.getAttribute('data-src') || img?.currentSrc || img?.src || '',
      seller: (card.querySelector('.promotion-item__seller')?.textContent || '').replace(/^por\s+/i, '').trim(),
      price: money(card.querySelector('.andes-money-amount:not(.andes-money-amount--previous)')),
      original_price: money(card.querySelector('.andes-money-amount--previous')),
      price_note: /no\s*pix/i.test(card.textContent || '') ? 'no Pix' : '',
      rating: null, sold: null,
      free_shipping: /gr[aá]tis/i.test(card.querySelector('.promotion-item__shipping, [class*="shipping"]')?.textContent || ''),
      catalog_product_id: catalogId.toUpperCase() || null,
    });
  }
  return {blocked: false, items, source: items.length ? 'ofertas' : 'cartões'};

  function readPayload() {
    // Trechos no formato _n.ctx.s["..."].q("0:{...}") com cada anúncio em "polycard":{...}.
    const chunks = [];
    for (const script of document.querySelectorAll('script')) {
      const text = script.textContent || '';
      if (!text.includes('polycard')) continue;
      if (!text.startsWith('_n.ctx.s[')) {
        // Outras páginas (ex.: Ofertas do dia) trazem os mesmos cartões num JSON comum (__PRELOADED_STATE__).
        chunks.push(text);
        continue;
      }
      const m = text.match(/\.q\(("(?:[^"\\]|\\.)*")\);?\s*$/s);
      if (!m) continue;
      try { chunks.push(JSON.parse(m[1])); } catch { /* trecho incompleto */ }
    }
    // Objeto entre chaves a partir de "start", respeitando textos entre aspas.
    const objectAt = (s, start) => {
      let depth = 0, inString = false;
      for (let i = start; i < s.length; i++) {
        const ch = s[i];
        if (inString) { if (ch === '\\') i++; else if (ch === '"') inString = false; continue; }
        if (ch === '"') inString = true;
        else if (ch === '{') depth++;
        else if (ch === '}' && --depth === 0) return s.slice(start, i + 1);
      }
      return null;
    };
    // Referências (@12), "u" (indefinido) e NaN não são JSON: viram null fora dos textos.
    const toJson = t => t.replace(/("(?:[^"\\]|\\.)*")|@\d+|\bu\b|\bNaN\b/g, (m, str) => str || 'null');
    const out = [], seen = new Set();
    for (const chunk of chunks) {
      const starts = /"polycard"\s*:\s*\{/g;
      let found;
      while ((found = starts.exec(chunk))) {
        const raw = objectAt(chunk, found.index + found[0].length - 1);
        if (!raw) break;
        let card;
        try { card = JSON.parse(toJson(raw)); } catch { continue; }
        const meta = card.metadata || {};
        const id = String(meta.id || '').toUpperCase();
        if (!/^MLB\d+$/.test(id) || seen.has(id)) continue;
        if (meta.signal?.ads || meta.is_pad === 'true' || /click1\./.test(meta.url || '')) continue;   // patrocinado
        seen.add(id);
        const part = type => (card.components || []).find(c => c.type === type || c.type?.startsWith(type));
        const title = part('title')?.title?.text || '';
        if (!title) continue;
        const price = part('price')?.price || {};
        const previous = (price.price_labels || []).flatMap(l => l.values || []).find(v => v.price?.previous)?.price?.value ?? null;
        const reviewText = (part('review_compacted')?.review_compacted?.values || []).map(v => v.label?.text || '').join(' ');
        const ratingText = (part('review_compacted')?.review_compacted?.values || []).map(v => v.label?.text || '').find(t => /^[0-5]([.,]\d)?$/.test(t));
        const shippingText = JSON.stringify(part('shipping') || {});
        const seller = (part('seller')?.seller?.values || []).map(v => v.label?.text || '').join(' ').trim();
        const picture = card.pictures?.pictures?.[0]?.id;
        out.push({
          external_id: id,
          url: `https://produto.mercadolivre.com.br/MLB-${id.slice(3)}`,
          title,
          image_url: picture ? `https://http2.mlstatic.com/D_NQ_NP_${picture}-O.webp` : '',
          seller: seller.replace(/^por\s+/i, ''),
          price: typeof price.current_price?.value === 'number' ? price.current_price.value : null,
          original_price: typeof previous === 'number' ? previous : null,
          price_note: /no\s*pix/i.test(JSON.stringify(price)) ? 'no Pix' : '',
          rating: ratingText ? Number(ratingText.replace(',', '.')) : null,
          sold: Number.isFinite(meta.signal?.sales) ? meta.signal.sales : sold(reviewText),
          free_shipping: /free_shipping|gr[aá]tis/i.test(shippingText),
          official_store: Boolean(meta.signal?.official_store),
          fulfillment: meta.signal?.ship_logistics === 'full' || /\bfull\b/i.test(shippingText),
          ml_category_id: /^MLB\d+$/.test(meta.category_id || '') ? meta.category_id : null,
          catalog_product_id: catalogOf(meta),
        });
      }
    }
    return out;
  }

  // Produto de catálogo (/p/MLB...): o mesmo produto vendido por lojas diferentes. Usado para agrupar parecidos.
  function catalogOf(meta) {
    for (const value of [meta.product_id, meta.catalog_product_id]) {
      const id = String(value || '').toUpperCase();
      if (/^MLB\d+$/.test(id) && id !== String(meta.id || '').toUpperCase()) return id;
    }
    const fromUrl = String(meta.url || meta.permalink || '').match(/\/p\/(MLB\d+)/i);
    return fromUrl ? fromUrl[1].toUpperCase() : null;
  }
}

readSearchPage();
