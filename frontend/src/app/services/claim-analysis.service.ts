import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { AgentStreamEvent } from '../models/claim.models';

@Injectable({ providedIn: 'root' })
export class ClaimAnalysisService {
  private readonly baseUrl = '/api';

  analyzeStream(formData: FormData): Observable<AgentStreamEvent> {
    return new Observable<AgentStreamEvent>((subscriber) => {
      const controller = new AbortController();

      fetch(`${this.baseUrl}/claims/analyze-stream`, {
        method: 'POST',
        body: formData,
        signal: controller.signal
      })
        .then(async (response) => {
          if (!response.ok || !response.body) {
            const text = await response.text();
            throw new Error(this.errorMessage(text, response.status));
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed) {
                continue;
              }
              subscriber.next(JSON.parse(trimmed) as AgentStreamEvent);
            }
          }

          const remaining = buffer.trim();
          if (remaining) {
            subscriber.next(JSON.parse(remaining) as AgentStreamEvent);
          }
          subscriber.complete();
        })
        .catch((error) => {
          if (!controller.signal.aborted) {
            subscriber.error(error);
          }
        });

      return () => controller.abort();
    });
  }

  private errorMessage(body: string, status: number): string {
    if (body) {
      try {
        const parsed = JSON.parse(body) as { detail?: unknown; error?: unknown };
        if (typeof parsed.detail === 'string') {
          return parsed.detail;
        }
        if (typeof parsed.error === 'string') {
          return parsed.error;
        }
      } catch {
        return body;
      }
    }
    return `Request failed with status ${status}`;
  }
}
