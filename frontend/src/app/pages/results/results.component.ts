import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, OnDestroy, Output, SimpleChanges } from '@angular/core';
import { AgentTraceComponent } from '../../components/agent-trace/agent-trace.component';
import { ResultSectionComponent } from '../../components/result-section/result-section.component';
import { AgentResponse, AgentStreamEvent, ClaimAnalysisResult } from '../../models/claim.models';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule, AgentTraceComponent, ResultSectionComponent],
  templateUrl: './results.component.html',
  styleUrl: './results.component.css'
})
export class ResultsComponent {
  @Input() view: 'agents' | 'results' = 'agents';
  @Input() result: ClaimAnalysisResult | null = null;
  @Input() loading = false;
  @Input() progress = 0;
  @Input() activeAgent = '';
  @Input() liveTrace: AgentResponse[] = [];
  @Input() liveEvents: AgentStreamEvent[] = [];
  @Output() reviewResults = new EventEmitter<void>();

  displayedTrace: AgentResponse[] = [];
  private revealQueue: AgentResponse[] = [];
  private revealTimer: ReturnType<typeof setTimeout> | null = null;

  loadingSteps = [
    { name: 'DocumentIngestionAgent', role: 'technical', waitsFor: 'policy PDF text extraction' },
    { name: 'PolicyConceptExtractionAgent', role: 'model', waitsFor: 'normalized policy concepts' },
    { name: 'ClaimExtractionAgent', role: 'model', waitsFor: 'claim facts and incident details' },
    { name: 'GeneralInsuranceFunctionalAgent', role: 'functional', waitsFor: 'general insurance rules' },
    { name: 'HomeInsuranceFunctionalAgent', role: 'functional', waitsFor: 'home insurance rules' },
    { name: 'RetrievalAgent', role: 'technical', waitsFor: 'relevant policy clauses' },
    { name: 'VisualEvidenceAgent', role: 'vision model', waitsFor: 'damage image interpretation' },
    { name: 'ImageAuthenticityAgent', role: 'vision model', waitsFor: 'image risk assessment' },
    { name: 'CoverageMatchingAgent', role: 'model', waitsFor: 'coverage decision evidence' },
    { name: 'ExclusionCheckingAgent', role: 'model', waitsFor: 'possible exclusions' },
    { name: 'MissingDocumentsAgent', role: 'validator', waitsFor: 'required evidence checklist' },
    { name: 'ConsistencyVerificationAgent', role: 'validator', waitsFor: 'cross-document consistency' },
    { name: 'CitationAgent', role: 'technical', waitsFor: 'source snippets' },
    { name: 'OutputValidatorAgent', role: 'validator', waitsFor: 'final schema validation' }
  ];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['liveTrace']) {
      this.queueNewAgentResponses();
    }
  }

  ngOnDestroy(): void {
    this.clearRevealTimer();
  }

  formatConcept(value: Record<string, unknown>): string {
    return String(value['concept'] || value['name'] || JSON.stringify(value));
  }

  confidenceScore(): number {
    const trace = this.result?.agent_trace?.length ? this.result.agent_trace : this.liveTrace;
    if (!trace.length) {
      return 0;
    }
    const total = trace.reduce((sum, agent) => sum + (agent.confidence || 0), 0);
    return Math.round((total / trace.length) * 100);
  }

  visibleAgentMessages(): Array<{
    step: { name: string; role: string; waitsFor: string };
    response?: AgentResponse;
    state: 'complete' | 'active' | 'waiting';
    index: number;
  }> {
    return this.loadingSteps
      .map((step, index) => ({
        step,
        response: this.displayedTrace.find((agent) => agent.agent_name === step.name),
        state: this.stepState(index),
        index,
      }))
      .filter((item) => item.state !== 'waiting' || item.index <= this.firstWaitingIndex())
      .sort((a, b) => {
        if (a.state === 'waiting' && b.state !== 'waiting') {
          return 1;
        }
        if (b.state === 'waiting' && a.state !== 'waiting') {
          return -1;
        }
        return b.index - a.index;
      });
  }

  allAgentResponsesDisplayed(): boolean {
    return this.liveTrace.length > 0 && this.displayedTrace.length >= this.liveTrace.length && this.revealQueue.length === 0;
  }

  trackAgentMessage(_: number, item: { step: { name: string } }): string {
    return item.step.name;
  }

  agentRoleLabel(step: { role: string }, response?: AgentResponse): string {
    if (response?.findings?.['model_used'] === true) {
      return `MODEL: ${step.role.toUpperCase()}`;
    }
    return step.role.toUpperCase();
  }

  agentTimeLabel(state: 'complete' | 'active' | 'waiting'): string {
    if (state === 'active') {
      return 'Now';
    }
    if (state === 'complete') {
      return 'Completed';
    }
    return 'Queued';
  }

  agentMessage(item: { step: { name: string; role: string; waitsFor: string }; response?: AgentResponse; state: 'complete' | 'active' | 'waiting' }): string {
    if (item.response) {
      return this.agentSummary(item.response);
    }
    if (item.state === 'active') {
      return `Processing ${item.step.waitsFor}. Waiting for streamed findings from the backend.`;
    }
    return `Queued after ${item.step.waitsFor}.`;
  }

  detailTitle(item: { step: { name: string }; response?: AgentResponse; state: 'complete' | 'active' | 'waiting' }): string {
    if (item.response) {
      return this.agentOutcomeTitle(item.step.name, item.response);
    }
    if (item.state === 'active') {
      return 'Processing';
    }
    return 'Waiting';
  }

  detailSubtitle(item: { step: { waitsFor: string }; response?: AgentResponse; state: 'complete' | 'active' | 'waiting' }): string {
    if (item.response) {
      return this.agentOutcomeSubtitle(item.response);
    }
    if (item.state === 'active') {
      return `Working on ${item.step.waitsFor}`;
    }
    return item.step.waitsFor;
  }

  agentOutcomeTitle(agentName: string, response: AgentResponse): string {
    const findings = response.findings || {};

    switch (agentName) {
      case 'DocumentIngestionAgent':
        return Number(findings['policy_text_length'] || 0) > 0 ? 'Policy document read' : 'Policy text needs review';
      case 'PolicyConceptExtractionAgent':
        return this.countLabel(findings['covered_events'], 'covered policy concept', 'covered policy concepts');
      case 'ClaimExtractionAgent':
        return `Claim classified as ${this.readable(findings['claim_type'] || 'unclear')}`;
      case 'GeneralInsuranceFunctionalAgent':
      case 'HomeInsuranceFunctionalAgent':
        return 'Coverage rules loaded';
      case 'RetrievalAgent':
        return `${findings['retrieved_count'] || response.evidence.length || 0} relevant policy clause(s) found`;
      case 'VisualEvidenceAgent':
        return `Image check: ${this.readable(findings['detected_damage'] || 'no image evidence')}`;
      case 'ImageAuthenticityAgent':
        return `Image risk: ${this.readable(findings['risk_level'] || 'not assessed')}`;
      case 'CoverageMatchingAgent':
        return `Coverage looks ${this.readable(findings['coverage_assessment'] || 'unclear')}`;
      case 'ExclusionCheckingAgent':
        return this.countLabel(findings['potential_exclusions'], 'possible exclusion', 'possible exclusions', 'No exclusions found');
      case 'MissingDocumentsAgent':
        return this.countLabel(findings['missing_documents'], 'missing document', 'missing documents', 'No missing documents');
      case 'ConsistencyVerificationAgent':
        return this.countLabel(findings['consistency_issues'], 'consistency issue', 'consistency issues', 'No consistency issues');
      case 'CitationAgent':
        return `${findings['citation_count'] || response.evidence.length || 0} citation(s) attached`;
      case 'OutputValidatorAgent':
        return findings['schema_ready'] === false ? 'Final output needs review' : 'Final output validated';
      default:
        return response.evidence.length ? `${response.evidence.length} evidence item(s) used` : 'Agent completed';
    }
  }

  agentOutcomeSubtitle(response: AgentResponse): string {
    const findings = response.findings || {};
    const confidence = Math.round((response.confidence || 0) * 100);
    const details = this.agentDetailFragments(response.agent_name, findings);
    const status = response.requires_human_review
      ? `Human review flagged, confidence ${confidence}%`
      : response.warnings.length
        ? `${response.warnings.length} warning${response.warnings.length === 1 ? '' : 's'}, confidence ${confidence}%`
        : `Confidence ${confidence}%`;

    return details.length ? `${details.join(' | ')} | ${status}` : status;
  }

  agentDetailFragments(agentName: string, findings: Record<string, unknown>): string[] {
    switch (agentName) {
      case 'DocumentIngestionAgent':
        return [
          findings['policy_filename'] ? `Policy: ${findings['policy_filename']}` : '',
          Number(findings['policy_text_length'] || 0) ? `${findings['policy_text_length']} chars extracted` : '',
        ].filter(Boolean) as string[];
      case 'PolicyConceptExtractionAgent':
        return [
          this.previewConcepts(findings['covered_events'], 'Covered'),
          this.previewConcepts(findings['exclusions'], 'Exclusions'),
        ].filter(Boolean) as string[];
      case 'ClaimExtractionAgent':
        return [
          findings['incident_date'] ? `Date: ${findings['incident_date']}` : '',
          findings['claimed_cause'] ? `Cause: ${this.readable(findings['claimed_cause'])}` : '',
        ].filter(Boolean) as string[];
      case 'CoverageMatchingAgent':
        return [
          this.previewConcepts(findings['matched_policy_concepts'], 'Matched'),
          findings['reason'] ? `Reason: ${String(findings['reason']).slice(0, 90)}` : '',
        ].filter(Boolean) as string[];
      case 'ExclusionCheckingAgent':
        return [this.previewConcepts(findings['potential_exclusions'], 'Checked exclusions')].filter(Boolean) as string[];
      case 'MissingDocumentsAgent':
        return [this.previewValues(findings['missing_documents'], 'Missing')].filter(Boolean) as string[];
      case 'ConsistencyVerificationAgent':
        return [this.previewValues(findings['consistency_issues'], 'Issues')].filter(Boolean) as string[];
      case 'VisualEvidenceAgent':
        return [this.previewValues(findings['notes'], 'Visual notes')].filter(Boolean) as string[];
      case 'ImageAuthenticityAgent':
        return [this.previewValues(findings['signals'], 'Signals')].filter(Boolean) as string[];
      case 'OutputValidatorAgent':
        return [
          this.previewValues(findings['missing_agent_outputs'], 'Missing outputs'),
          this.previewValues(findings['non_model_agents'], 'Fallback agents'),
        ].filter(Boolean) as string[];
      default:
        return [];
    }
  }

  private countLabel(value: unknown, singular: string, plural: string, emptyLabel = `No ${plural}`): string {
    const count = Array.isArray(value) ? value.length : Number(value || 0);
    if (!count) {
      return emptyLabel;
    }
    return `${count} ${count === 1 ? singular : plural}`;
  }

  detailCode(item: { response?: AgentResponse; state: 'complete' | 'active' | 'waiting' }): string {
    if (item.response?.requires_human_review) {
      return 'REVIEW';
    }
    if (item.response?.warnings.length) {
      return 'WARN';
    }
    if (item.response) {
      return 'OK';
    }
    if (item.state === 'active') {
      return 'RUN';
    }
    return 'NEXT';
  }

  currentAgentSummary(): string {
    const latest = this.displayedTrace.at(-1) || this.result?.agent_trace?.at(-1);
    if (!latest) {
      return 'Awaiting first agent signal from the orchestration pipeline.';
    }
    return this.agentSummary(latest);
  }

  exclusionInsight(): string {
    const count = this.result?.potential_exclusions.length || 0;
    return count ? `${count} potential exclusion(s) detected.` : 'Awaiting exclusion and consistency review.';
  }

  decisionTone(): 'success' | 'warning' | 'danger' {
    if (!this.result) {
      return 'warning';
    }
    if (this.result.claim_status === 'likely_covered') {
      return 'success';
    }
    if (this.result.claim_status === 'likely_not_covered') {
      return 'danger';
    }
    return 'warning';
  }

  decisionTitle(): string {
    if (!this.result) {
      return 'No final decision yet';
    }
    if (this.result.claim_status === 'likely_covered') {
      return 'Likely covered';
    }
    if (this.result.claim_status === 'likely_not_covered') {
      return 'Likely not covered';
    }
    if (this.result.claim_status === 'partially_covered') {
      return 'Partially covered';
    }
    return 'Needs human review';
  }

  coverageLabel(): string {
    return this.result ? this.statusLabel(this.result.coverage_assessment) : 'Pending';
  }

  agentProgress(index: number): number {
    const state = this.stepState(index);
    if (state === 'complete') {
      return 100;
    }
    if (state === 'active') {
      return 0;
    }
    return 0;
  }

  agentProgressLabel(index: number): string {
    const state = this.stepState(index);
    if (state === 'complete') {
      return '100%';
    }
    if (state === 'active') {
      return 'Running';
    }
    return 'Waiting';
  }

  agentSummary(agent: AgentResponse): string {
    const findings = agent.findings || {};
    if ('claim_type' in findings) {
      return `Classified claim as ${findings['claim_type']}.`;
    }
    if ('coverage_assessment' in findings) {
      return `Coverage assessment is ${findings['coverage_assessment']}.`;
    }
    if ('missing_documents' in findings) {
      const missing = findings['missing_documents'] as unknown[];
      return missing.length ? `${missing.length} missing document(s) detected.` : 'No missing documents detected.';
    }
    if ('potential_exclusions' in findings) {
      const exclusions = findings['potential_exclusions'] as unknown[];
      return exclusions.length ? `${exclusions.length} potential exclusion(s) found.` : 'No potential exclusions found.';
    }
    if ('retrieved_count' in findings) {
      return `${findings['retrieved_count']} relevant policy clause(s) retrieved.`;
    }
    return agent.evidence.length ? `${agent.evidence.length} evidence item(s) returned.` : `${agent.agent_name} completed its reasoning step.`;
  }

  statusLabel(status: string): string {
    return status.replaceAll('_', ' ');
  }

  private readable(value: unknown): string {
    return String(value).replaceAll('_', ' ');
  }

  private previewConcepts(value: unknown, label: string): string {
    if (!Array.isArray(value) || !value.length) {
      return '';
    }
    const names = value
      .slice(0, 2)
      .map((item) => this.formatConcept(item as Record<string, unknown>))
      .map((item) => this.readable(item));
    return `${label}: ${names.join(', ')}${value.length > 2 ? ` +${value.length - 2}` : ''}`;
  }

  private previewValues(value: unknown, label: string): string {
    if (!Array.isArray(value) || !value.length) {
      return '';
    }
    const names = value.slice(0, 2).map((item) => this.readable(item));
    return `${label}: ${names.join(', ')}${value.length > 2 ? ` +${value.length - 2}` : ''}`;
  }

  stepState(index: number): 'complete' | 'active' | 'waiting' {
    const step = this.loadingSteps[index];
    if (this.displayedTrace.some((agent) => agent.agent_name === step.name)) {
      return 'complete';
    }
    if (this.activeAgent === step.name) {
      return 'active';
    }
    const activeIndex = this.estimatedActiveIndex();
    if (index < activeIndex) {
      return 'complete';
    }
    if (index === activeIndex) {
      return 'active';
    }
    return 'waiting';
  }

  activeStepName(): string {
    if (this.activeAgent) {
      return this.activeAgent;
    }
    if (this.loading) {
      return 'Waiting for first agent';
    }
    return this.result ? 'Assessment complete' : 'Not started';
  }

  latestLiveResponses(): AgentResponse[] {
    return this.displayedTrace.slice(-4).reverse();
  }

  hasLiveReasoning(): boolean {
    return this.displayedTrace.length > 0;
  }

  private queueNewAgentResponses(): void {
    if (this.liveTrace.length < this.displayedTrace.length) {
      this.displayedTrace = [];
      this.revealQueue = [];
      this.clearRevealTimer();
    }

    const displayedNames = new Set(this.displayedTrace.map((agent) => agent.agent_name));
    const queuedNames = new Set(this.revealQueue.map((agent) => agent.agent_name));
    const newResponses = this.liveTrace.filter(
      (agent) => !displayedNames.has(agent.agent_name) && !queuedNames.has(agent.agent_name)
    );

    if (!newResponses.length) {
      return;
    }

    this.revealQueue = [...this.revealQueue, ...newResponses];
    this.scheduleNextReveal();
  }

  private scheduleNextReveal(): void {
    if (this.revealTimer || !this.revealQueue.length) {
      return;
    }

    this.revealTimer = setTimeout(() => {
      const [next, ...rest] = this.revealQueue;
      this.revealQueue = rest;
      if (next && !this.displayedTrace.some((agent) => agent.agent_name === next.agent_name)) {
        this.displayedTrace = [...this.displayedTrace, next];
      }
      this.revealTimer = null;
      this.scheduleNextReveal();
    }, this.displayedTrace.length ? 650 : 180);
  }

  private clearRevealTimer(): void {
    if (this.revealTimer) {
      clearTimeout(this.revealTimer);
      this.revealTimer = null;
    }
  }

  openResults(): void {
    this.reviewResults.emit();
  }

  private estimatedActiveIndex(): number {
    const activeIndex = Math.min(
      Math.floor((this.progress / 100) * this.loadingSteps.length),
      this.loadingSteps.length - 1
    );
    return activeIndex;
  }

  private firstWaitingIndex(): number {
    const activeIndex = this.loadingSteps.findIndex((_, index) => this.stepState(index) === 'active');
    if (activeIndex >= 0) {
      return activeIndex + 1;
    }
    const firstWaiting = this.loadingSteps.findIndex((_, index) => this.stepState(index) === 'waiting');
    return firstWaiting >= 0 ? firstWaiting : this.loadingSteps.length - 1;
  }
}
