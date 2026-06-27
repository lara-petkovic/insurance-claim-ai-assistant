import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, SimpleChanges } from '@angular/core';
import { AgentTraceComponent } from '../../components/agent-trace/agent-trace.component';
import { AgentResponse, ClaimAnalysisResult, EvidenceItem } from '../../models/claim.models';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule, AgentTraceComponent],
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
  @Output() reviewResults = new EventEmitter<void>();

  displayedTrace: AgentResponse[] = [];
  private revealQueue: AgentResponse[] = [];
  private revealTimer: ReturnType<typeof setTimeout> | null = null;

  private readonly knownStepNames = [
    'DynamicPlanningAgent',
    'DocumentIngestionAgent',
    'DocumentQualityAgent',
    'PolicyConceptExtractionAgent',
    'ClaimExtractionAgent',
    'GeneralInsuranceFunctionalAgent',
    'HomeInsuranceFunctionalAgent',
    'AutoInsuranceFunctionalAgent',
    'TravelInsuranceFunctionalAgent',
    'QueryRewriteAgent',
    'RetrievalAgent',
    'VisualEvidenceAgent',
    'ImageAuthenticityAgent',
    'CoverageMatchingAgent',
    'ExclusionCheckingAgent',
    'MissingDocumentsAgent',
    'ConsistencyVerificationAgent',
    'CitationAgent',
    'OutputValidatorAgent',
    'FinalDecisionSynthesisAgent'
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

  allAgentResponsesDisplayed(): boolean {
    return this.liveTrace.length > 0 && this.displayedTrace.length >= this.liveTrace.length && this.revealQueue.length === 0;
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

  primaryMissingDocument(): string {
    return this.result?.missing_documents[0] || 'None';
  }

  missingDocumentAction(): string {
    const count = this.result?.missing_documents.length || 0;
    if (!count) {
      return 'Complete';
    }
    return count === 1 ? 'Action required' : `${count} actions required`;
  }

  exclusionCountLabel(): string {
    const count = this.result?.potential_exclusions.length || 0;
    return count ? `${count.toString().padStart(2, '0')} Trigger${count === 1 ? '' : 's'}` : 'No Triggers';
  }

  reviewChecklist(): Array<{ title: string; note: string; checked: boolean }> {
    if (!this.result) {
      return [];
    }

    const exclusions = this.result.potential_exclusions.map((item) => ({
      title: `Review ${this.formatConcept(item)}`,
      note: 'Confirm whether this exclusion applies to the submitted claim.',
      checked: false,
    }));
    const missing = this.result.missing_documents.map((document) => ({
      title: `Request ${document}`,
      note: 'Add this document before a final adjuster decision.',
      checked: false,
    }));

    return [...exclusions, ...missing].slice(0, 5);
  }

  topPolicyMatches(): Array<Record<string, unknown>> {
    return this.result?.matched_policy_concepts.slice(0, 4) || [];
  }

  topEvidence(): EvidenceItem[] {
    return this.result?.evidence.slice(0, 3) || [];
  }

  agentSummary(agent: AgentResponse): string {
    const lastMessage = agent.messages?.at(-1);
    if (lastMessage) {
      return lastMessage.content;
    }
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

  agentStepCount(): number {
    const planned = this.plannedAgentNames();
    if (planned.length) {
      return planned.length;
    }

    const traceNames = [...this.liveTrace, ...(this.result?.agent_trace || [])].map((agent) => agent.agent_name);
    const uniqueTraceNames = Array.from(new Set(traceNames));
    if (uniqueTraceNames.length) {
      return uniqueTraceNames.length;
    }

    return this.knownStepNames.length;
  }

  private plannedAgentNames(): string[] {
    const planningAgent = [...this.liveTrace, ...(this.result?.agent_trace || [])]
      .find((agent) => agent.agent_name === 'DynamicPlanningAgent');
    const planned = planningAgent?.findings?.['planned_agents'];
    if (!Array.isArray(planned)) {
      return [];
    }
    return ['DynamicPlanningAgent', ...planned.map((name) => String(name))];
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

  private queueNewAgentResponses(): void {
    if (this.liveTrace.length < this.displayedTrace.length) {
      this.displayedTrace = [];
      this.revealQueue = [];
      this.clearRevealTimer();
    }

    const nextIndex = this.displayedTrace.length + this.revealQueue.length;
    const newResponses = this.liveTrace.slice(nextIndex);

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
      if (next) {
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
}
