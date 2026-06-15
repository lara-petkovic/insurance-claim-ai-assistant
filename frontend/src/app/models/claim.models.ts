export interface EvidenceItem {
  source: string;
  text: string;
  section?: string | null;
  page?: number | null;
  score?: number | null;
}

export interface AgentMessage {
  from_agent: string;
  to_agent?: string | null;
  message_type: 'handoff' | 'request' | 'response' | 'guidance' | 'feedback' | 'validation' | 'summary';
  content: string;
  metadata: Record<string, unknown>;
}

export interface AgentResponse {
  agent_name: string;
  agent_type: 'orchestrator' | 'technical' | 'functional' | 'validator' | 'synthesis';
  status: 'completed' | 'warning' | 'failed' | 'skipped';
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
  risk_level: 'low' | 'medium' | 'high' | 'requires_human_review';
  risk_score: number;
  signals: string[];
}

export interface ClaimAnalysisResult {
  claim_status: 'likely_covered' | 'likely_not_covered' | 'partially_covered' | 'requires_human_review';
  insurance_type: string;
  claim_type: string;
  coverage_assessment: 'covered' | 'not_covered' | 'possibly_covered' | 'unclear';
  matched_policy_concepts: Array<Record<string, unknown>>;
  potential_exclusions: Array<Record<string, unknown>>;
  missing_documents: string[];
  image_assessment: ImageAssessment;
  image_authenticity: ImageAuthenticity;
  evidence: EvidenceItem[];
  reasoning_summary: string;
  recommendation: string;
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
