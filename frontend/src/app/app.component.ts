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
  result: ClaimAnalysisResult | null = null;
  loading = false;
  progress = 0;
  activeAgent = '';
  liveTrace: AgentResponse[] = [];
  liveEvents: AgentStreamEvent[] = [];
  private progressTimer: ReturnType<typeof setInterval> | null = null;

  setLoading(value: boolean): void {
    this.loading = value;
    if (value) {
      if (this.progressTimer) {
        clearInterval(this.progressTimer);
      }
      this.result = null;
      this.liveTrace = [];
      this.liveEvents = [];
      this.activeAgent = 'Starting agents';
      this.progress = 3;
      this.progressTimer = setInterval(() => {
        this.progress = Math.min(this.progress + 4, 94);
      }, 700);
      return;
    }

    this.progress = 100;
    if (this.progressTimer) {
      clearInterval(this.progressTimer);
      this.progressTimer = null;
    }
  }

  setResult(result: ClaimAnalysisResult): void {
    this.result = result;
    this.liveTrace = result.agent_trace;
    this.activeAgent = '';
  }

  handleStreamEvent(event: AgentStreamEvent): void {
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

