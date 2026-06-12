import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-result-section',
  standalone: true,
  imports: [CommonModule],
  template: `
    <section class="section">
      <h2>{{ title }}</h2>
      <ng-content></ng-content>
    </section>
  `,
  styles: [`
    .section {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 18px;
    }

    h2 {
      font-size: 16px;
      margin: 0 0 12px;
    }
  `]
})
export class ResultSectionComponent {
  @Input({ required: true }) title = '';
}

