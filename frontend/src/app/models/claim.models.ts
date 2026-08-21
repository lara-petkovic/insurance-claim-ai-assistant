export type ExtractionMethod =
  | 'user_input'
  | 'text_extraction'
  | 'pdf_text_extraction'
  | 'pdf_vision_extraction'
  | 'model_extraction'
  | 'rule_extraction'
  | 'retrieval';
export type VerificationStatus = 'unverified' | 'machine_verified' | 'human_verified' | 'rejected';
export type ClauseType = 'coverage' | 'exclusion' | 'condition' | 'limit' | 'deductible' | 'definition' | 'requirement' | 'other';
export type ClausePolarity = 'covered' | 'excluded' | 'conditional' | 'neutral' | 'unclear';
export type PropositionStatus = 'proposed' | 'supported' | 'contradicted' | 'inconclusive';
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped';

export interface DocumentPage {
  page_number: number;
  text: string;
  char_start: number;
  char_end: number;
  extraction_method: ExtractionMethod;
}

export interface SourceDocument {
  document_id: string;
  filename: string;
  document_type: string;
  text: string;
  pages: DocumentPage[];
  extraction_method: ExtractionMethod;
  extraction_warnings: string[];
  text_length: number;
}

export interface PolicyDocument extends SourceDocument {
  document_type: 'policy';
}

export interface SupportingDocument extends SourceDocument {}

export interface EvidenceProvenance {
  source_document_id: string;
  source_filename: string;
  page?: number | null;
  section_heading?: string | null;
  evidence_text: string;
  char_start?: number | null;
  char_end?: number | null;
  stable_location: string;
  extraction_method: ExtractionMethod;
  confidence: number;
  verification_status: VerificationStatus;
}

export interface EvidenceItem {
  source: string;
  text: string;
  section?: string | null;
  page?: number | null;
  score?: number | null;
  source_document_id?: string | null;
  source_filename?: string | null;
  section_heading?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  stable_location?: string | null;
  extraction_method?: ExtractionMethod | null;
  verification_status?: VerificationStatus | null;
}

export interface PolicyClause extends EvidenceProvenance {
  clause_id: string;
  concept: string;
  clause_type: ClauseType;
  polarity: ClausePolarity;
  matched_terms: string[];
  direct_match: boolean;
}

export interface PolicyMatch {
  concept: string;
  evidence_text?: string;
  clause_id?: string;
  clause_type?: ClauseType;
  polarity?: ClausePolarity;
  matched_terms?: string[];
  direct_match?: boolean;
  source_document_id?: string;
  source_filename?: string;
  page?: number | null;
  section_heading?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  stable_location?: string;
  extraction_method?: ExtractionMethod;
  confidence?: number;
  verification_status?: VerificationStatus;
}

export interface ClaimFact extends EvidenceProvenance {
  fact_id: string;
  fact_type: string;
  value: string | number | boolean | null;
}

export interface AssessmentProposition {
  proposition_id: string;
  statement: string;
  status: PropositionStatus;
  evidence: EvidenceProvenance[];
  confidence: number;
  created_by: string;
}

export interface InvestigationTask {
  task_id: string;
  agent_name: string;
  objective: string;
  status: TaskStatus;
  depends_on: string[];
  evidence_ids: string[];
}

export interface PotentialExclusion {
  concept: string;
  severity?: 'low' | 'medium' | 'high';
  reason?: string;
  evidence_text?: string;
  requires_corroboration?: boolean;
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

export interface ClaimExtractionFindings {
  claim_type: string;
  incident_date: string | null;
  incident_location: string;
  damage_or_loss_type: string;
  claimed_cause: string;
  claimed_amount: string | null;
  facts: ClaimFact[];
  model_used: boolean;
}

export interface PolicyExtractionFindings {
  policy_type: string;
  covered_events: PolicyMatch[];
  coverage_clauses: PolicyClause[];
  exclusions: PotentialExclusion[];
  model_used: boolean;
}

export interface CoverageFindings {
  coverage_assessment: CoverageAssessment;
  matched_policy_concepts: PolicyMatch[];
  supporting_policy_passages: string[];
  clause_polarities: ClausePolarity[];
  model_used: boolean;
}

export interface VisualEvidenceFindings {
  detected_damage: string;
  confidence: number;
  notes: string[];
  model_used: boolean;
}

export interface ImageIntegrityFindings {
  risk_level: RiskLevel;
  risk_score: number;
  signals: string[];
  model_used: boolean;
}

export interface PlanningFindings {
  planned_agents: string[];
  skipped_agents: string[];
  rationale: string[];
  planning_mode: string;
}

export type GenericAgentFindings = { [key: string]: unknown };
export type AgentFindings =
  | ClaimExtractionFindings
  | PolicyExtractionFindings
  | CoverageFindings
  | VisualEvidenceFindings
  | ImageIntegrityFindings
  | PlanningFindings
  | GenericAgentFindings;

export interface AgentResponse {
  agent_name: string;
  agent_type: AgentType;
  status: AgentStatus;
  findings: AgentFindings;
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
  matched_policy_concepts: PolicyMatch[];
  potential_exclusions: PotentialExclusion[];
  missing_documents: string[];
  image_assessment: ImageAssessment;
  image_authenticity: ImageAuthenticity;
  evidence: EvidenceItem[];
  claim_facts: ClaimFact[];
  policy_clauses: PolicyClause[];
  assessment_propositions: AssessmentProposition[];
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

const EVENT_TYPES = new Set<AgentStreamEvent['event']>([
  'analysis_started', 'agent_started', 'agent_completed', 'analysis_completed', 'analysis_failed'
]);
const AGENT_TYPES = new Set<AgentType>(['orchestrator', 'technical', 'functional', 'validator', 'synthesis']);
const AGENT_STATUSES = new Set<AgentStatus>(['completed', 'warning', 'failed', 'skipped']);
const CLAIM_STATUSES = new Set<ClaimStatus>(['likely_covered', 'likely_not_covered', 'partially_covered', 'requires_human_review']);
const COVERAGE_ASSESSMENTS = new Set<CoverageAssessment>(['covered', 'not_covered', 'possibly_covered', 'unclear']);
const RISK_LEVELS = new Set<RiskLevel>(['low', 'medium', 'high', 'requires_human_review']);
const EXTRACTION_METHODS = new Set<ExtractionMethod>([
  'user_input', 'text_extraction', 'pdf_text_extraction', 'pdf_vision_extraction',
  'model_extraction', 'rule_extraction', 'retrieval'
]);
const VERIFICATION_STATUSES = new Set<VerificationStatus>([
  'unverified', 'machine_verified', 'human_verified', 'rejected'
]);

export function parseAgentStreamEvent(value: unknown): AgentStreamEvent {
  if (!isRecord(value) || typeof value['event'] !== 'string' || !EVENT_TYPES.has(value['event'] as AgentStreamEvent['event'])) {
    throw new Error('Malformed analysis stream event.');
  }
  if (value['agent_response'] !== undefined && !isAgentResponse(value['agent_response'])) {
    throw new Error('Malformed agent response in analysis stream.');
  }
  if (value['event'] === 'analysis_failed' && typeof value['error'] !== 'string') {
    throw new Error('Malformed analysis failure event.');
  }
  if (value['event'] === 'analysis_completed') {
    if (!isClaimAnalysisResult(value['result'])) {
      throw new Error('Malformed final claim-analysis result.');
    }
    value['result'] = withProvenanceDefaults(value['result']);
  }
  return value as unknown as AgentStreamEvent;
}

function withProvenanceDefaults(result: Record<string, unknown>): ClaimAnalysisResult {
  return {
    ...result,
    claim_facts: Array.isArray(result['claim_facts']) ? result['claim_facts'] : [],
    policy_clauses: Array.isArray(result['policy_clauses']) ? result['policy_clauses'] : [],
    assessment_propositions: Array.isArray(result['assessment_propositions']) ? result['assessment_propositions'] : [],
  } as unknown as ClaimAnalysisResult;
}

function isAgentResponse(value: unknown): value is AgentResponse {
  return isRecord(value)
    && typeof value['agent_name'] === 'string'
    && typeof value['agent_type'] === 'string'
    && AGENT_TYPES.has(value['agent_type'] as AgentType)
    && typeof value['status'] === 'string'
    && AGENT_STATUSES.has(value['status'] as AgentStatus)
    && isRecord(value['findings'])
    && isUnitInterval(value['confidence'])
    && Array.isArray(value['evidence'])
    && value['evidence'].every(isEvidenceItem)
    && Array.isArray(value['warnings'])
    && value['warnings'].every((item) => typeof item === 'string')
    && typeof value['requires_human_review'] === 'boolean'
    && Array.isArray(value['messages'])
    && value['messages'].every(isAgentMessage);
}

function isClaimAnalysisResult(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) {
    return false;
  }
  return typeof value['claim_status'] === 'string'
    && CLAIM_STATUSES.has(value['claim_status'] as ClaimStatus)
    && typeof value['insurance_type'] === 'string'
    && typeof value['claim_type'] === 'string'
    && typeof value['coverage_assessment'] === 'string'
    && COVERAGE_ASSESSMENTS.has(value['coverage_assessment'] as CoverageAssessment)
    && typeof value['reasoning_summary'] === 'string'
    && typeof value['recommendation'] === 'string'
    && Array.isArray(value['matched_policy_concepts'])
    && value['matched_policy_concepts'].every(isRecord)
    && Array.isArray(value['potential_exclusions'])
    && value['potential_exclusions'].every(isRecord)
    && Array.isArray(value['missing_documents'])
    && Array.isArray(value['evidence'])
    && value['evidence'].every(isEvidenceItem)
    && Array.isArray(value['agent_trace'])
    && value['agent_trace'].every(isAgentResponse)
    && optionalArrayOf(value['claim_facts'], isClaimFact)
    && optionalArrayOf(value['policy_clauses'], isPolicyClause)
    && optionalArrayOf(value['assessment_propositions'], isAssessmentProposition)
    && isRecord(value['image_assessment'])
    && typeof value['image_assessment']['detected_damage'] === 'string'
    && isUnitInterval(value['image_assessment']['confidence'])
    && isRecord(value['image_authenticity'])
    && typeof value['image_authenticity']['risk_level'] === 'string'
    && RISK_LEVELS.has(value['image_authenticity']['risk_level'] as RiskLevel)
    && isUnitInterval(value['image_authenticity']['risk_score']);
}

function isAgentMessage(value: unknown): value is AgentMessage {
  return isRecord(value)
    && typeof value['from_agent'] === 'string'
    && typeof value['message_type'] === 'string'
    && typeof value['content'] === 'string'
    && isRecord(value['metadata']);
}

function isClaimFact(value: unknown): value is ClaimFact {
  if (!isRecord(value) || !isEvidenceProvenance(value)) {
    return false;
  }
  const record = value as unknown as Record<string, unknown>;
  return typeof record['fact_id'] === 'string'
    && typeof record['fact_type'] === 'string'
    && (record['value'] === null || ['string', 'number', 'boolean'].includes(typeof record['value']));
}

function isPolicyClause(value: unknown): value is PolicyClause {
  if (!isRecord(value) || !isEvidenceProvenance(value)) {
    return false;
  }
  const record = value as unknown as Record<string, unknown>;
  return typeof record['clause_id'] === 'string'
    && typeof record['concept'] === 'string'
    && typeof record['clause_type'] === 'string'
    && typeof record['polarity'] === 'string'
    && Array.isArray(record['matched_terms']);
}

function isAssessmentProposition(value: unknown): value is AssessmentProposition {
  return isRecord(value)
    && typeof value['proposition_id'] === 'string'
    && typeof value['statement'] === 'string'
    && typeof value['status'] === 'string'
    && isUnitInterval(value['confidence'])
    && typeof value['created_by'] === 'string'
    && Array.isArray(value['evidence'])
    && value['evidence'].every(isEvidenceProvenance);
}

function isEvidenceProvenance(value: unknown): value is EvidenceProvenance {
  return isRecord(value)
    && typeof value['source_document_id'] === 'string'
    && typeof value['source_filename'] === 'string'
    && typeof value['evidence_text'] === 'string'
    && typeof value['stable_location'] === 'string'
    && typeof value['extraction_method'] === 'string'
    && EXTRACTION_METHODS.has(value['extraction_method'] as ExtractionMethod)
    && isUnitInterval(value['confidence'])
    && typeof value['verification_status'] === 'string'
    && VERIFICATION_STATUSES.has(value['verification_status'] as VerificationStatus);
}

function isEvidenceItem(value: unknown): value is EvidenceItem {
  return isRecord(value)
    && typeof value['source'] === 'string'
    && typeof value['text'] === 'string'
    && (value['score'] === undefined || value['score'] === null || isUnitInterval(value['score']))
    && (value['page'] === undefined || value['page'] === null || (Number.isInteger(value['page']) && Number(value['page']) >= 1));
}

function isUnitInterval(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}

function optionalArrayOf<T>(value: unknown, guard: (item: unknown) => item is T): boolean {
  return value === undefined || (Array.isArray(value) && value.every(guard));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
