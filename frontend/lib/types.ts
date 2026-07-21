// Shared types — mirror backend Pydantic schemas (M0 + M1)

export type CompetitorType = "direct" | "indirect" | "cross_industry";
export type CompetitorStatus = "confirmed" | "pending" | "excluded";

export interface Competitor {
  id: string;
  canonical_name: string;
  aliases: string[];
  parent_company: string | null;
  official_domain: string | null;
  help_center_domain: string | null;
  video_channels: string[];
  app_store_pages: string[];
  acquired_from: string | null;
  valid_from: string | null;
  valid_to: string | null;
  status: CompetitorStatus;
  competitor_type: CompetitorType | null;
  created_at: string;
  updated_at: string;
}

export type LexiconLevel = "category" | "project";
export type LexiconTermType = "task" | "role" | "ui_state" | "product_alias";

export interface LexiconEntry {
  id: string;
  term: string;
  term_type: LexiconTermType;
  language: string;
  level: LexiconLevel;
  valid_for_competitors: string[];
  source: string | null;
  created_at: string;
  updated_at: string;
}

export type CellStatus = "active" | "deprecated";

export interface GridCell {
  id: string;
  cell_key: string;
  jtbd: string;
  journey_stage: string;
  page_state: string;
  value_score: number;
  version: number;
  status: CellStatus;
  requires_review: boolean;
  created_at: string;
  updated_at: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
}

// M5 · Coverage
export type CoverageStatus =
  | "SATURATED"
  | "SHORTLIST_READY"
  | "PARTIAL"
  | "UNPROBED"
  | "REJECTED_EMPTY"
  | "QUEUED"
  | "PROBING"
  | "STALE";

export interface CoverageRow {
  cell_id: string;
  competitor_id: string;
  status: CoverageStatus;
  independent_source_count: number;
  latest_captured_at: string | null;
  coverage_confidence: number; // 0–1
  evidence_type_breakdown: Record<string, number>;
  tier: string;
}
