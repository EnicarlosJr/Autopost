// Atualiza o catálogo de categorias oficiais do Mercado Livre pelo navegador (o servidor pode ser bloqueado).
// Baixa a árvore completa da API pública, reduz aos campos usados e envia ao Autopost.
import {api} from './api.js';
import {log} from './config.js';

const ALL_URL = 'https://api.mercadolibre.com/sites/MLB/categories/all';

export async function syncCategories() {
  let response;
  try {
    response = await fetch(ALL_URL, {credentials: 'omit', cache: 'no-store'});
  } catch (error) {
    throw new Error(`Não consegui falar com a API do Mercado Livre: ${error.message || error}`);
  }
  if (!response.ok) throw new Error(`A API do Mercado Livre respondeu ${response.status} ao baixar as categorias.`);
  const tree = await response.json();
  const categories = Object.entries(tree).map(([id, node]) => {
    const path = node.path_from_root || [];
    return {
      id, name: node.name || id,
      parent_id: path.length >= 2 ? path[path.length - 2].id : null,
      total_items: node.total_items_in_this_category || 0,
      children: (node.children_categories || []).length,
    };
  });
  log('categorias baixadas', categories.length);
  return api('/ml-categories/import', {method: 'POST', body: {categories}});
}
