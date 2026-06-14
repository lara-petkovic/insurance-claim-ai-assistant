import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { AgentResponse, AgentStreamEvent, ClaimAnalysisResult } from './models/claim.models';
import { ClaimSubmissionComponent } from './pages/claim-submission/claim-submission.component';
import { ResultsComponent } from './pages/results/results.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ClaimSubmissionComponent, ResultsComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  activePage: 'input' | 'agents' | 'results' = 'input';
  result: ClaimAnalysisResult | null = null;
  loading = false;
  analysisStarted = false;
  progress = 0;
  activeAgent = '';
  liveTrace: AgentResponse[] = [];
  liveEvents: AgentStreamEvent[] = [];

  setLoading(value: boolean): void {
    this.loading = value;
    if (value) {
      this.analysisStarted = true;
      this.result = null;
      this.liveTrace = [];
      this.liveEvents = [];
      this.activeAgent = '';
      this.progress = 0;
      this.goToPage('agents');
      return;
    }

    this.progress = this.result ? 100 : this.progress;
  }

  showAnalysis(): boolean {
    return this.analysisStarted || this.loading || !!this.result || this.liveTrace.length > 0;
  }

  canOpenAgents(): boolean {
    return this.showAnalysis();
  }

  canOpenResults(): boolean {
    return !!this.result;
  }

  goToPage(page: 'input' | 'agents' | 'results'): void {
    if (page === 'agents' && !this.canOpenAgents()) {
      return;
    }
    if (page === 'results' && !this.canOpenResults()) {
      return;
    }
    this.activePage = page;
    setTimeout(() => window.scrollTo({ top: 0, behavior: 'smooth' }), 0);
  }

  setResult(result: ClaimAnalysisResult): void {
    this.result = result;
    this.liveTrace = result.agent_trace;
    this.activeAgent = '';
    this.progress = 100;
  }

  handleStreamEvent(event: AgentStreamEvent): void {
    if (event.event === 'analysis_started') {
      this.analysisStarted = true;
      this.progress = 0;
      this.activePage = 'agents';
    }
    this.liveEvents = [...this.liveEvents, event];
    if (event.event === 'agent_started' && event.agent_name) {
      this.activeAgent = event.agent_name;
      this.setProgressFromEvent(event);
    }
    if (event.event === 'agent_completed' && event.agent_response) {
      this.liveTrace = [...this.liveTrace, event.agent_response];
      this.activeAgent = event.agent_name || this.activeAgent;
      this.setProgressFromEvent(event);
    }
    if (event.event === 'analysis_completed') {
      this.progress = 100;
      this.activeAgent = '';
    }
  }

  private setProgressFromEvent(event: AgentStreamEvent): void {
    if (!event.index || !event.total_agents) {
      return;
    }
    const completedOffset = event.event === 'agent_completed' ? 1 : 0;
    this.progress = Math.min(
      Math.round(((event.index - 1 + completedOffset) / event.total_agents) * 100),
      99
    );
  }
}
