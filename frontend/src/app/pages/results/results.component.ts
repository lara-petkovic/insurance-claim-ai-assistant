import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
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
  @Input() result: ClaimAnalysisResult | null = null;
  @Input() loading = false;
  @Input() progress = 0;
  @Input() activeAgent = '';
  @Input() liveTrace: AgentResponse[] = [];
  @Input() liveEvents: AgentStreamEvent[] = [];

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

  formatConcept(value: Record<string, unknown>): string {
    return String(value['concept'] || value['name'] || JSON.stringify(value));
  }

  statusLabel(status: string): string {
    return status.replaceAll('_', ' ');
  }

  stepState(index: number): 'complete' | 'active' | 'waiting' {
    const step = this.loadingSteps[index];
    if (this.liveTrace.some((agent) => agent.agent_name === step.name)) {
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
    return this.loadingSteps[this.estimatedActiveIndex()]?.name || 'Agents';
  }

  latestLiveResponses(): AgentResponse[] {
    return this.liveTrace.slice(-4).reverse();
  }

  hasLiveReasoning(): boolean {
    return this.liveTrace.length > 0;
  }

  private estimatedActiveIndex(): number {
    const activeIndex = Math.min(
      Math.floor((this.progress / 100) * this.loadingSteps.length),
      this.loadingSteps.length - 1
    );
    return activeIndex;
  }
}
