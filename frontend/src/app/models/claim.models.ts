export interface EvidenceItem {
  source: string;
  text: string;
  section?: string | null;
  page?: number | null;
  score?: number | null;
}

export type MessageType = 'handoff' | 'request' | 'response' | 'guidance' | 'feedback' | 'validation' | 'summary';
export type AgentType = 'orchestrator' | 'technical' | 'functional' | 'validator' | 'synthesis';
export type AgentStatus = 'completed' | 'warning' | 'failed' | 'skipped';
export type ClaimStatus = 'likely_covered' | 'likely_not_covered' | 'partially_covered' | 'requires_human_review';
export type CoverageAssessment = 'covered' | 'not_covered' | 'possibly_covered' | 'unclear';
export type RiskLevel = 'low' | 'medium' | 'high' | 'requires_human_review';

export interface AgentMessage {
  from_agent: string;
  to_agent?: string | null;
  message_type: MessageType;
  content: string;
  metadata: Record<string, unknown>;
}

export interface AgentResponse {
  agent_name: string;
  agent_type: AgentType;
  status: AgentStatus;
  findings: Record<string, unknown>;
  evidence: EvidenceItem[];
  confidence: number;
  warnings: string[];
  requires_human_review: boolean;
  messages: AgentMessage[];
}

export interface ImageAssessment {
  detected_damage: string;
  confidence: number;
  notes: string[];
}

export interface ImageAuthenticity {
  risk_level: RiskLevel;
  risk_score: number;
  signals: string[];
}

export interface ClaimAnalysisResult {
  claim_status: ClaimStatus;
  insurance_type: string;
  claim_type: string;
  coverage_assessment: CoverageAssessment;
  matched_policy_concepts: Array<Record<string, unknown>>;
  potential_exclusions: Array<Record<string, unknown>>;
  missing_documents: string[];
  image_assessment: ImageAssessment;
  image_authenticity: ImageAuthenticity;
  evidence: EvidenceItem[];
  reasoning_summary: string;
  recommendation: string;
  security_flags: string[];
  agent_trace: AgentResponse[];
}

export interface AgentStreamEvent {
  event: 'analysis_started' | 'agent_started' | 'agent_completed' | 'analysis_completed' | 'analysis_failed';
  agent_name?: string;
  index?: number;
  total_agents?: number;
  message?: string;
  agent_response?: AgentResponse;
  result?: ClaimAnalysisResult;
  error?: string;
}
