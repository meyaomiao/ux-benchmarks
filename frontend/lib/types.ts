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

// M4 · Shortlist (evidence awaiting review)
export type EvidenceType = "observed" | "claimed" | "inferred";

export interface RubricBreakdown {
  state_match: number;
  product_match: number;
  version_recency: number;
  evidence_directness: number;
  fidelity: number;
  reasoning?: string;
  scored_by?: string;
}

export interface ShortlistItem {
  id: string;
  cell_id: string;
  competitor_id: string;
  source_url: string;
  source_type: string | null;
  title: string | null;
  snippet: string | null;
  evidence_type: EvidenceType;
  ai_score: number | null; // 0–1 overall relevance
  ai_score_breakdown: RubricBreakdown | null;
  rights_status: string;
  media_disposition: string;
  captured_at: string;
  image_path_available: boolean;
}

export interface ShortlistResponse {
  items: ShortlistItem[];
  total: number;
}

// M3 · Queue
export interface QueueItem {
  id: string;
  cell_id: string;
  competitor_id: string;
  status: string;
  probe_cycles: number;
  last_probed_at?: string | null;
  created_at: string;
}

// L3 · Insights
export interface Insight {
  id: string;
  cell_id: string;
  competitor_id: string;
  claim: string;
  analysis: string | null;
  recommendation: string | null;
  design_principle: string | null;
  limits: string | null;
  source_observation_ids: string[];
  confidence: "high" | "medium" | "low" | "hypothesis";
  generated_by: string;
  is_draft: boolean;
  created_at: string;
  updated_at: string;
}

// L5 · Reports
export type ReportAudience = "management" | "designer" | "pm";
export type ReportFormat = "summary_5min" | "review_15min" | "onepager" | "full";

export interface Report {
  id: string;
  title: string;
  audience: ReportAudience;
  format_type: ReportFormat;
  source_insight_ids: string[];
  body_markdown: string;
  generated_by: string;
  created_at: string;
  updated_at: string;
}

// M2 · Mapping cards
export interface MappingCard {
  id: string;
  cell_id: string;
  intent_definition: string;    // max 150 chars
  inclusion_criteria: string | null;
  exclusion_criteria: string | null;
  anchor_screenshot_asset_id: string | null;
  version: number;
  is_complete: boolean;
  created_by: string | null;
  reviewed_by: string | null;
  created_at: string;
  updated_at: string;
}
