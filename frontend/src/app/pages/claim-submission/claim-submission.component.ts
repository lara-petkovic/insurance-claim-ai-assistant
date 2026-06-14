import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AgentStreamEvent, ClaimAnalysisResult } from '../../models/claim.models';
import { ClaimAnalysisService } from '../../services/claim-analysis.service';

@Component({
  selector: 'app-claim-submission',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './claim-submission.component.html',
  styleUrl: './claim-submission.component.css'
})
export class ClaimSubmissionComponent {
  @Output() resultReady = new EventEmitter<ClaimAnalysisResult>();
  @Output() streamEvent = new EventEmitter<AgentStreamEvent>();
  @Output() analysisStarted = new EventEmitter<void>();
  @Output() analysisFinished = new EventEmitter<void>();

  insuranceType = 'home';
  incidentDate = '';
  claimDescription = '';
  policyFile: File | null = null;
  damageImage: File | null = null;
  supportingDocuments: File[] = [];
  error = '';

  constructor(private readonly service: ClaimAnalysisService) {}

  selectPolicy(event: Event): void {
    this.policyFile = this.firstFile(event);
  }

  selectImage(event: Event): void {
    this.damageImage = this.firstFile(event);
  }

  selectSupportingDocuments(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.supportingDocuments = input.files ? Array.from(input.files) : [];
  }

  analyze(): void {
    this.error = '';
    const formData = new FormData();
    formData.append('insurance_type', this.insuranceType);
    formData.append('claim_description', this.claimDescription);
    if (this.incidentDate) {
      formData.append('incident_date', this.incidentDate);
    }
    if (this.policyFile) {
      formData.append('policy_file', this.policyFile);
    }
    if (this.damageImage) {
      formData.append('damage_image', this.damageImage);
    }
    for (const document of this.supportingDocuments) {
      formData.append('supporting_documents', document);
    }

    this.analysisStarted.emit();
    this.service.analyzeStream(formData).subscribe({
      next: (event) => {
        this.streamEvent.emit(event);
        if (event.event === 'analysis_completed' && event.result) {
          this.resultReady.emit(event.result);
        }
        if (event.event === 'analysis_failed') {
          this.error = event.error || 'Analysis failed.';
          this.analysisFinished.emit();
        }
      },
      complete: () => {
        this.analysisFinished.emit();
      },
      error: (error) => {
        this.error = error?.message || 'Analysis failed.';
        this.analysisFinished.emit();
      }
    });
  }

  private firstFile(event: Event): File | null {
    const input = event.target as HTMLInputElement;
    return input.files?.item(0) ?? null;
  }
}
