// Lê nome, imagem e preços da página de produto aberta. Usado pelo botão da extensão
// e pela leitura automática do painel. O valor da última linha é o resultado.
function readProductPage() {
  const $ = sel => document.querySelector(sel);
  const meta = (...keys) => {
    for (const key of keys) {
      const el = document.querySelector(`meta[property="${key}"], meta[name="${key}"]`);
      if (el?.content) return el.content.trim();
    }
    return '';
  };
  const number = value => {
    if (value == null) return null;
    let t = String(value).replace(/[^\d.,-]/g, '');
    if (!t) return null;
    if (t.includes(',') && t.includes('.')) t = t.replace(/\./g, '').replace(',', '.');
    else if (t.includes(',')) t = t.replace(',', '.');
    else if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, '');
    const n = Number(t);
    return Number.isFinite(n) ? n : null;
  };
  const money = el => {
    if (!el) return null;
    const fraction = el.querySelector('.andes-money-amount__fraction');
    if (!fraction) return number(el.textContent);
    const whole = fraction.textContent.replace(/\D/g, '');
    const cents = (el.querySelector('.andes-money-amount__cents')?.textContent || '').replace(/\D/g, '');
    return whole ? Number(cents ? `${whole}.${cents.slice(0, 2).padEnd(2, '0')}` : whole) : null;
  };

  if (/\/gz\/account-verification|\/jms\/.+\/login/.test(location.pathname)) return {blocked: true};

  const result = {
    page_url: location.href,
    canonical_url: document.querySelector('link[rel="canonical"]')?.href || '',
    title: ($('h1.ui-pdp-title')?.textContent || $('#productTitle')?.textContent || meta('twitter:title', 'og:title') || $('h1')?.textContent || '').trim(),
    description: meta('og:description', 'description'),
    image_url: meta('og:image', 'twitter:image') || $('.ui-pdp-gallery__figure img')?.src || $('#landingImage')?.src || '',
    price: null, original_price: null, price_note: '', store: '',
    // Preço no cartão quando o destaque depende de Pix/Mercado Pago, condições lidas e disponibilidade.
    regular_price: null, price_conditions: '', available: true,
  };
  const text = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();

  // Mercado Livre: bloco de preço em destaque (ignora miniaturas de variações).
  const ml = $('#price .ui-pdp-price__main-container, .ui-pdp-container__row--price .ui-pdp-price__main-container');
  if (ml) {
    result.original_price = money(ml.querySelector('.ui-pdp-price__original-value, .andes-money-amount--previous'));
    const line = ml.querySelector('.ui-pdp-price__second-line') || ml;
    result.price = number(line.querySelector('meta[itemprop="price"]')?.content) ?? money(line.querySelector('.andes-money-amount:not(.andes-money-amount--previous)'));
    const lineText = text(line);
    if (/no\s*pix/i.test(lineText)) result.price_note = 'no Pix';
    else if (/mercado\s*pago/i.test(lineText)) result.price_note = 'com Mercado Pago';
    // "ou R$ 4.580 em 10x sem juros": o preço para quem não paga no Pix (só vale sem juros).
    const subtitles = ml.querySelector('.ui-pdp-price__subtitles');
    const subText = text(subtitles);
    if (/^ou\b/i.test(subText) && (/sem juros/i.test(subText) || !/\d+\s*x\b/i.test(subText))) {
      result.regular_price = money(subtitles.querySelector('.andes-money-amount'));
    }
    // Condições perto do preço: Pix, Mercado Pago, cupom e Meli+ (descontos que nem todo comprador tem).
    const promos = [...document.querySelectorAll('.ui-pdp-promotions-pill-label, .ui-vpp-coupons-awareness, .ui-pdp-coupons, [class*="coupon-awareness"]')]
      .slice(0, 8).map(text).join(' ');
    const area = `${text($('#price') || ml)} ${promos}`;
    const conditions = [];
    if (/no\s*pix/i.test(area)) conditions.push('no Pix');
    if (/mercado\s*pago/i.test(area)) conditions.push('com Mercado Pago');
    if (/cupom/i.test(area)) conditions.push('cupom disponível');
    if (/meli\s*(\+|mais)/i.test(area)) conditions.push('Meli+');
    result.price_conditions = conditions.join(' · ');
    result.store = 'Mercado Livre';
  }
  // Amazon
  const amazon = $('#corePriceDisplay_desktop_feature_div, #corePrice_feature_div, #corePrice_desktop');
  if (amazon && result.price == null) {
    result.price = number(amazon.querySelector('.priceToPay .a-offscreen, .apexPriceToPay .a-offscreen')?.textContent);
    result.original_price = number(amazon.querySelector('.basisPrice .a-offscreen, .a-price.a-text-price .a-offscreen')?.textContent);
    result.store = 'Amazon';
  }
  // Magalu e lojas com data-testid
  if (result.price == null && $('[data-testid="price-value"]')) {
    result.price = number($('[data-testid="price-value"]').textContent);
    result.original_price = number($('[data-testid="price-original"]')?.textContent);
  }
  // JSON-LD como último recurso
  if (result.price == null) {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const queue = [JSON.parse(script.textContent)];
        while (queue.length && result.price == null) {
          const item = queue.shift();
          if (Array.isArray(item)) { queue.push(...item); continue; }
          if (!item || typeof item !== 'object') continue;
          if (item['@graph']) queue.push(item['@graph']);
          if (item.offers) queue.push(item.offers);
          if (item.price != null) result.price = number(item.price);
        }
      } catch { /* JSON inválido */ }
    }
  }
  if (result.original_price != null && result.price != null && result.original_price <= result.price) result.original_price = null;
  if (result.regular_price != null && (result.price == null || result.regular_price <= result.price)) result.regular_price = null;
  // Sem preço e com aviso de esgotado/pausado: o produto está indisponível (o Autopost guarda o último preço).
  if (result.price == null && /mercadoli[vb]re/.test(location.hostname)) {
    const page = text($('.ui-pdp-container') || $('main') || document.body).slice(0, 20000);
    if (/an[uú]ncio (est[aá] )?pausado|publica[cç][aã]o (est[aá] )?(pausada|finalizada)|sem estoque|estoque esgotado|produto esgotado|(est[aá]|produto) indispon[ií]vel|n[aã]o est[aá] dispon[ií]vel|n[aã]o h[aá] (mais )?unidades/i.test(page)) {
      result.available = false;
    }
  }
  return result;
}

readProductPage();
