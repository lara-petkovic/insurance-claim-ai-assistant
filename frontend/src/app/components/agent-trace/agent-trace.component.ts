import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { AgentMessage, AgentResponse } from '../../models/claim.models';

@Component({
  selector: 'app-agent-trace',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './agent-trace.component.html',
  styleUrl: './agent-trace.component.css'
})
export class AgentTraceComponent {
  @Input({ required: true }) trace: AgentResponse[] = [];
  expanded = new Set<string>();

  newestFirstTrace(): AgentResponse[] {
    return [...this.trace].reverse();
  }

  trackAgent(_: number, agent: AgentResponse): string {
    return `${agent.agent_name}-${agent.messages?.at(-1)?.message_type || agent.status}`;
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

  latestMessage(agent: AgentResponse): AgentMessage | null {
    return agent.messages?.at(-1) || null;
  }

  summary(agent: AgentResponse): string {
    const message = this.latestMessage(agent);
    if (message) {
      return message.content;
    }
    const findings = agent.findings || {};
    const keys = Object.keys(findings);
    if (!keys.length) {
      return agent.evidence.length ? `${agent.evidence.length} evidence item(s) returned.` : 'Agent completed without additional findings.';
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
      return `${events.length} normalized covered event concept(s) extracted.`;
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
