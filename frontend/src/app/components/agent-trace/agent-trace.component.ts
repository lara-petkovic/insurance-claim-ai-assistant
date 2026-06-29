import { CommonModule } from '@angular/common';
import {
  AfterViewChecked,
  Component,
  ElementRef,
  Input,
  OnChanges,
  QueryList,
  SimpleChanges,
  ViewChildren
} from '@angular/core';
import { AgentMessage, AgentResponse } from '../../models/claim.models';

@Component({
  selector: 'app-agent-trace',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './agent-trace.component.html',
  styleUrl: './agent-trace.component.css'
})
export class AgentTraceComponent implements OnChanges, AfterViewChecked {
  @Input({ required: true }) trace: AgentResponse[] = [];
  @ViewChildren('traceItem') traceItems!: QueryList<ElementRef<HTMLElement>>;

  expanded = new Set<string>();
  private latestTraceKey = '';
  private shouldFocusLatest = false;

  orderedTrace(): AgentResponse[] {
    return this.trace;
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['trace']) {
      return;
    }

    const latest = this.trace.at(-1);
    const nextTraceKey = latest ? `${this.trace.length}-${this.trackAgent(this.trace.length - 1, latest)}` : '';
    if (nextTraceKey && nextTraceKey !== this.latestTraceKey) {
      this.latestTraceKey = nextTraceKey;
      this.shouldFocusLatest = true;
    }
  }

  ngAfterViewChecked(): void {
    if (!this.shouldFocusLatest || !this.traceItems?.length) {
      return;
    }

    this.shouldFocusLatest = false;
    const latest = this.traceItems.last.nativeElement;
    latest.focus({ preventScroll: true });
    latest.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  trackAgent(index: number, agent: AgentResponse): string {
    return `${index}-${agent.agent_name}-${agent.messages?.at(-1)?.message_type || agent.status}`;
  }

  confidencePercent(value: number): string {
    return `${this.confidenceScore(value)}%`;
  }

  confidenceScore(value: number): number {
    return Math.round((value || 0) * 100);
  }

  role(agent: AgentResponse): string {
    return agent.agent_type || 'technical';
  }

  roleLabel(agent: AgentResponse): string {
    return this.role(agent).toUpperCase();
  }

  statusLabel(agent: AgentResponse): string {
    return agent.status.replaceAll('_', ' ').toUpperCase();
  }

  tone(agent: AgentResponse): 'cyan' | 'amber' | 'green' | 'red' {
    if (agent.status === 'failed') {
      return 'red';
    }
    if (agent.requires_human_review || agent.agent_type === 'validator') {
      return 'amber';
    }
    if (agent.agent_type === 'functional') {
      return 'green';
    }
    return 'cyan';
  }

  latestMessage(agent: AgentResponse): AgentMessage | null {
    return agent.messages?.at(-1) || null;
  }

  outboundMessages(agent: AgentResponse): AgentMessage[] {
    return (agent.messages || []).filter((message) => Boolean(message.to_agent));
  }

  hasOutboundMessages(agent: AgentResponse): boolean {
    return this.outboundMessages(agent).length > 0;
  }

  messageTitle(message: AgentMessage): string {
    return `Message to ${message.to_agent || 'Team Trace'}`;
  }

  messageSubtitle(message: AgentMessage): string {
    return `${message.from_agent} -> ${message.to_agent || 'Team Trace'}`;
  }

  messageTypeLabel(message: AgentMessage): string {
    return message.message_type.toUpperCase();
  }

  summary(agent: AgentResponse): string {
    const findings = agent.findings || {};
    const keys = Object.keys(findings);
    if (!keys.length) {
      const message = this.latestMessage(agent);
      if (message) {
        return message.content;
      }
      return agent.evidence.length ? `${agent.evidence.length} evidence item(s) returned.` : 'Agent completed without additional findings.';
    }

    if ('planned_agents' in findings) {
      const planned = findings['planned_agents'] as unknown[];
      return `Dynamic execution plan selected ${planned.length} agent(s).`;
    }
    if ('policy_text_length' in findings) {
      return `Policy document ingested with ${findings['policy_text_length']} extracted characters.`;
    }
    if ('document_quality_issues' in findings) {
      const issues = findings['document_quality_issues'] as unknown[];
      return `Document quality check completed with ${issues.length} extraction/layout issue(s).`;
    }

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
    if ('detected_damage' in findings) {
      return `Detected visual evidence: ${findings['detected_damage']}.`;
    }
    if ('risk_level' in findings) {
      return `Image authenticity risk is ${findings['risk_level']}.`;
    }
    if ('covered_events' in findings) {
      const events = findings['covered_events'] as unknown[];
      const exclusions = Array.isArray(findings['exclusions']) ? findings['exclusions'] as unknown[] : [];
      return `Normalized ${events.length} covered event(s) and ${exclusions.length} exclusion concept(s).`;
    }
    if ('retrieved_count' in findings) {
      return `${findings['retrieved_count']} policy clause(s) retrieved.`;
    }
    if ('rules' in findings || 'rules_by_claim_type' in findings) {
      return 'Domain rules supplied for downstream validation.';
    }
    if ('citation_count' in findings) {
      return `${findings['citation_count']} citation(s) attached to final decision.`;
    }
    if ('schema_ready' in findings) {
      const feedback = Array.isArray(findings['feedback']) ? findings['feedback'] as unknown[] : [];
      return `Output validation completed with ${feedback.length} feedback item(s).`;
    }
    if ('message_count' in findings) {
      return `Final synthesis prepared after reviewing ${findings['message_count']} inter-agent message(s).`;
    }
    if ('completed_agents' in findings) {
      const completed = findings['completed_agents'] as unknown[];
      return `Orchestrator completed ${completed.length} planned agent step(s).`;
    }

    return `${keys.length} structured finding group(s) returned.`;
  }

  toggle(agentName: string): void {
    if (this.expanded.has(agentName)) {
      this.expanded.delete(agentName);
      return;
    }
    this.expanded.add(agentName);
  }

  isExpanded(agentName: string): boolean {
    return this.expanded.has(agentName);
  }

  modelUsed(agent: AgentResponse): boolean {
    return agent.findings?.['model_used'] === true;
  }
}
