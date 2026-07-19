export interface PIIFilterConfig {
  baseUrl?: string;
  timeout?: number;
}

export interface DetectedEntity {
  type: string;
  text: string;
  start: number;
  end: number;
  score: number;
  detector: string;
}

export interface RiskAssessment {
  score: number;
  level: string;
  detected_count: number;
  critical_entities: string[];
  recommendation: string;
}

export interface FilterResult {
  filtered: string;
  risk: RiskAssessment;
  entities: DetectedEntity[];
  replacements: { original: string; replacement: string; entity_type: string }[];
  latency_ms: number;
  blocked: boolean;
  block_reason?: string;
}

export interface ScanResult {
  entities: DetectedEntity[];
  risk: RiskAssessment;
  latency_ms: number;
}

export interface ForwardResult {
  filtered: string;
  response: string;
  risk: RiskAssessment;
  entities: DetectedEntity[];
  latency_ms: number;
}