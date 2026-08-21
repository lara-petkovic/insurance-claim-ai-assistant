import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { EvidenceItem, EvidenceProvenance } from '../../models/claim.models';

type DisplayEvidence = EvidenceItem | EvidenceProvenance;

@Component({
  selector: 'app-evidence-reference',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './evidence-reference.component.html',
  styleUrl: './evidence-reference.component.css'
})
export class EvidenceReferenceComponent {
  @Input({ required: true }) evidence!: DisplayEvidence;

  quote(): string {
    return 'text' in this.evidence ? this.evidence.text : this.evidence.evidence_text;
  }

  sourceLabel(): string {
    const filename = this.evidence.source_filename;
    if (filename) {
      return filename;
    }
    if ('source' in this.evidence) {
      return this.evidence.source === 'policy' ? 'Policy' : this.evidence.source.startsWith('supporting:')
        ? this.evidence.source.slice('supporting:'.length)
        : this.evidence.source;
    }
    return 'Source document';
  }

  section(): string | null {
    if (this.evidence.section_heading) {
      return this.evidence.section_heading;
    }
    return 'section' in this.evidence ? this.evidence.section || null : null;
  }

  extractionLabel(): string | null {
    return this.evidence.extraction_method?.replaceAll('_', ' ') || null;
  }

  verificationLabel(): string | null {
    return this.evidence.verification_status?.replaceAll('_', ' ') || null;
  }

  relevanceScore(): number | null {
    if (!('score' in this.evidence) || this.evidence.score === null || this.evidence.score === undefined) {
      return null;
    }
    return Math.round(this.evidence.score * 100);
  }

  confidenceScore(): number | null {
    if (!('confidence' in this.evidence)) {
      return null;
    }
    return Math.round(this.evidence.confidence * 100);
  }

  offsetLabel(): string | null {
    const start = this.evidence.char_start;
    const end = this.evidence.char_end;
    return start !== null && start !== undefined && end !== null && end !== undefined
      ? `Chars ${start}-${end}`
      : null;
  }

  sourceKind(): 'policy' | 'supporting' | 'claim' {
    if ('source' in this.evidence) {
      if (this.evidence.source === 'policy') {
        return 'policy';
      }
      return this.evidence.source.startsWith('supporting:') ? 'supporting' : 'claim';
    }
    if (this.evidence.source_kind === 'policy') {
      return 'policy';
    }
    return this.evidence.source_kind === 'supporting_document' ? 'supporting' : 'claim';
  }

  sourceKindLabel(): string {
    if (this.sourceKind() === 'policy') {
      return 'Policy wording';
    }
    if (this.sourceKind() === 'supporting') {
      return 'Claim evidence';
    }
    return 'Claim fact';
  }

  clauseId(): string | null {
    return this.evidence.policy_clause_id || null;
  }

  hasTechnicalDetails(): boolean {
    return !!(this.extractionLabel() || this.offsetLabel() || this.clauseId());
  }
}
