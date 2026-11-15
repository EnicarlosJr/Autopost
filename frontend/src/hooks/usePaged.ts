import {useCallback, useEffect, useRef, useState} from 'react';
import {apiError, getPage} from '../services/api';

/** Lista paginada com "Carregar mais", estado de carregamento e erro visível. */
export function usePaged<T>(url: string, params: Record<string, unknown>, pageSize = 30) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const key = JSON.stringify(params);
  const latest = useRef(key);

  const load = useCallback(async (more = false, quiet = false) => {
    latest.current = key;
    if (!quiet) setLoading(true);
    try {
      const offset = more ? items.length : 0;
      const size = quiet && !more ? Math.max(pageSize, items.length) : pageSize;
      const page = await getPage<T>(url, {...JSON.parse(key), limit: size, offset});
      if (latest.current !== key) return;
      setItems(old => (more ? [...old, ...page.items] : page.items));
      setTotal(page.total);
      setError('');
    } catch (e) {
      setError(apiError(e, 'Não foi possível carregar a lista.'));
    } finally {
      setLoading(false);
    }
  }, [url, key, items.length, pageSize]);

  useEffect(() => { load(); }, [url, key]); // eslint-disable-line react-hooks/exhaustive-deps

  return {items, total, loading, error, setError, reload: (quiet = false) => load(false, quiet), loadMore: () => load(true),
          hasMore: items.length < total};
}
