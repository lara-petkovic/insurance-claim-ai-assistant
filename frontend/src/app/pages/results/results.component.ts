import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, SimpleChanges } from '@angular/core';
import { AgentTraceComponent } from '../../components/agent-trace/agent-trace.component';
import { EvidenceReferenceComponent } from '../../components/evidence-reference/evidence-reference.component';
import {
  AgentResponse,
  AssessmentProposition,
  ClaimAnalysisResult,
  ClaimFact,
  EvidenceItem,
  PolicyClause,
  PolicyMatch,
  PotentialExclusion
} from '../../models/claim.models';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule, AgentTraceComponent, EvidenceReferenceComponent],
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

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['liveTrace']) {
      this.queueNewAgentResponses();
    }
  }

  ngOnDestroy(): void {
    this.clearRevealTimer();
  }

  formatConcept(value: PolicyMatch | PotentialExclusion): string {
    return value.concept;
  }

  confidenceScore(): number {
    const proposition = this.primaryProposition();
    if (proposition) {
      return Math.round(proposition.confidence * 100);
    }
    const trace = this.result?.agent_trace?.length ? this.result.agent_trace : this.liveTrace;
    if (!trace.length) {
      return 0;
    }
    const total = trace.reduce((sum, agent) => sum + (agent.confidence || 0), 0);
    return Math.round((total / trace.length) * 100);
  }

  confidenceLabel(): string {
    return this.primaryProposition() ? 'Assessment confidence' : 'Average agent confidence';
  }

  primaryProposition(): AssessmentProposition | null {
    return this.result?.assessment_propositions.find(
      (item) => item.proposition_type === 'coverage'
    ) || null;
  }

  primaryPropositionStatusLabel(): string {
    const proposition = this.primaryProposition();
    return proposition ? this.statusLabel(proposition.status) : 'No conclusion';
  }

  allAgentResponsesDisplayed(): boolean {
    return this.liveTrace.length > 0 && this.displayedTrace.length >= this.liveTrace.length && this.revealQueue.length === 0;
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

  decisionSubtitle(): string {
    if (!this.result) {
      return '';
    }
    if (this.result.claim_status === 'likely_covered') {
      return 'The required coverage conclusions are grounded and no unresolved policy contradiction was found.';
    }
    if (this.result.claim_status === 'likely_not_covered') {
      return 'Policy wording currently weighs against coverage. A human adjuster should confirm before any denial.';
    }
    return 'One or more required conclusions are missing support, conditional, or contradicted and need an adjuster.';
  }

  decisionPropositions(): AssessmentProposition[] {
    if (!this.result) {
      return [];
    }
    const priority: Record<string, number> = {
      coverage: 0,
      exclusion: 1,
      condition: 2,
      definition: 3,
      limit: 4,
      missing_evidence: 5,
      claim_fact: 6,
    };
    return [...this.result.assessment_propositions].sort((left, right) => {
      const requiredDifference = Number(right.required_for_coverage) - Number(left.required_for_coverage);
      if (requiredDifference) {
        return requiredDifference;
      }
      return (priority[left.proposition_type] ?? 99) - (priority[right.proposition_type] ?? 99);
    });
  }

  secondaryPropositions(): AssessmentProposition[] {
    const primaryId = this.primaryProposition()?.proposition_id;
    return this.decisionPropositions().filter(
      (item) => item.proposition_id !== primaryId && item.proposition_type !== 'claim_fact'
    );
  }

  blockingPropositions(): AssessmentProposition[] {
    return this.decisionPropositions().filter(
      (item) => item.required_for_coverage && item.status !== 'supported'
    );
  }

  groundedPropositionCount(): number {
    return this.decisionPropositions().filter((item) => item.status === 'supported').length;
  }

  policyCitationCount(): number {
    if (!this.result) {
      return 0;
    }
    const clauseIds = this.result.assessment_propositions.flatMap((item) =>
      item.evidence
        .filter((evidence) => evidence.source_kind === 'policy' && !!evidence.policy_clause_id)
        .map((evidence) => evidence.policy_clause_id as string)
    );
    return new Set(clauseIds).size;
  }

  supportingCitationCount(): number {
    return this.result?.evidence.filter((item) => item.source.startsWith('supporting:')).length || 0;
  }

  supportingEvidence(): EvidenceItem[] {
    return this.result?.evidence.filter((item) => item.source.startsWith('supporting:')) || [];
  }

  openReviewCount(): number {
    if (!this.result) {
      return 0;
    }
    const additionalBlockers = this.blockingPropositions().filter(
      (item) => item.proposition_type !== 'missing_evidence' && item.proposition_type !== 'exclusion'
    );
    return this.result.missing_documents.length
      + this.result.potential_exclusions.length
      + additionalBlockers.length;
  }

  propositionTone(proposition: AssessmentProposition): string {
    return proposition.status;
  }

  propositionStatusCopy(proposition: AssessmentProposition): string {
    if (proposition.status === 'supported') {
      return 'Grounded by the cited evidence';
    }
    if (proposition.status === 'contradicted') {
      return 'Conflicts with policy evidence';
    }
    if (proposition.status === 'inconclusive') {
      return 'More evidence or review is needed';
    }
    return 'Awaiting evidence validation';
  }

  relevantPolicyClauses(): PolicyClause[] {
    if (!this.result) {
      return [];
    }
    const referencedIds = new Set(
      this.result.assessment_propositions.flatMap((item) => [
        ...item.supporting_policy_clause_ids,
        ...item.contradicting_policy_clause_ids,
      ])
    );
    const relevant = this.result.policy_clauses.filter((item) => referencedIds.has(item.clause_id));
    return relevant.length ? relevant : this.result.policy_clauses.slice(0, 6);
  }

  visualEvidenceAvailable(): boolean {
    return !!this.result && (
      this.result.image_assessment.detected_damage !== 'unknown'
      || this.result.image_assessment.confidence > 0
    );
  }

  reviewChecklist(): Array<{ title: string; note: string; checked: boolean }> {
    if (!this.result) {
      return [];
    }

    const exclusions = this.result.potential_exclusions.map((item) => ({
      title: `Review ${this.formatConcept(item)}`,
      note: item.reason || 'Confirm whether this exclusion applies to the submitted claim.',
      checked: false,
    }));
    const missing = this.result.missing_documents.map((document) => ({
      title: `Request ${document}`,
      note: 'Add this document before a final adjuster decision.',
      checked: false,
    }));

    const blockers = this.blockingPropositions()
      .filter((item) => item.proposition_type !== 'missing_evidence' && item.proposition_type !== 'exclusion')
      .map((item) => ({
        title: `Resolve ${this.statusLabel(item.proposition_type)}`,
        note: item.statement,
        checked: false,
      }));

    return [...exclusions, ...missing, ...blockers].slice(0, 6);
  }

  topPolicyMatches(): PolicyMatch[] {
    return this.result?.matched_policy_concepts.slice(0, 4) || [];
  }

  topPolicyClauses(): PolicyClause[] {
    return this.result?.policy_clauses.slice(0, 4) || [];
  }

  claimFacts(): ClaimFact[] {
    return this.result?.claim_facts || [];
  }

  factValue(fact: ClaimFact): string {
    return fact.value === null ? 'Not provided' : String(fact.value);
  }

  provenanceLabel(value: PolicyMatch): string {
    const parts = [value.source_filename, value.page ? `p. ${value.page}` : null, value.section_heading];
    return parts.filter(Boolean).join(' / ') || 'Source location unavailable';
  }

  clauseEffect(value: PolicyMatch): string {
    return this.statusLabel(value.polarity || value.clause_type || 'match');
  }

  topEvidence(): EvidenceItem[] {
    return this.result?.evidence.slice(0, 3) || [];
  }

  statusLabel(status: string): string {
    return status.replaceAll('_', ' ');
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
