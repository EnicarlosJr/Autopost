export type MlCategory = {
  id: string; name: string; parent_id: string | null; path: string; path_ids: string[]; depth: number;
  is_leaf: boolean; children_count: number; total_items: number; active: boolean; favorite: boolean;
};
export type CategoryPick = {id: string; include_children: boolean; name?: string; path?: string; is_leaf?: boolean; active?: boolean};
export type Niche = {
  id: number; name: string; description: string; favorite: boolean; tags: string[];
  include_keywords: string[]; exclude_keywords: string[]; gender?: 'any' | 'male' | 'female'; categories: (CategoryPick & {name: string; path: string})[];
  created_at: string; updated_at: string;
};
export type CatalogStatus = {total: number; roots: number; synced_at: string | null};
