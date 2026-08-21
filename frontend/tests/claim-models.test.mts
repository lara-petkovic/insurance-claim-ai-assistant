import assert from 'node:assert/strict';
import test from 'node:test';

import { parseAgentStreamEvent } from '../src/app/models/claim.models.ts';

function legacyResult() {
  return {
    claim_status: 'requires_human_review',
    insurance_type: 'home',
    claim_type: 'water_damage',
    coverage_assessment: 'unclear',
    matched_policy_concepts: [],
    potential_exclusions: [],
    missing_documents: [],
    image_assessment: { detected_damage: 'unknown', confidence: 0, notes: [] },
    image_authenticity: { risk_level: 'low', risk_score: 0, signals: [] },
    evidence: [],
    reasoning_summary: 'Review required.',
    recommendation: 'Review.',
    security_flags: [],
    agent_trace: [],
  };
}

test('adapts a compatible legacy result with empty provenance collections', () => {
  const event = parseAgentStreamEvent({ event: 'analysis_completed', result: legacyResult() });

  assert.deepEqual(event.result?.claim_facts, []);
  assert.deepEqual(event.result?.policy_clauses, []);
  assert.deepEqual(event.result?.assessment_propositions, []);
});

test('rejects an out-of-range final risk score', () => {
  const result = legacyResult();
  result.image_authenticity.risk_score = 1.5;

  assert.throws(
    () => parseAgentStreamEvent({ event: 'analysis_completed', result }),
    /Malformed final claim-analysis result/,
  );
});

test('rejects a malformed streamed agent response', () => {
  assert.throws(
    () => parseAgentStreamEvent({
      event: 'agent_completed',
      agent_response: {
        agent_name: 'ClaimExtractionAgent',
        agent_type: 'technical',
        status: 'completed',
        findings: {},
        evidence: [],
        confidence: -0.1,
        warnings: [],
        requires_human_review: false,
        messages: [],
      },
    }),
    /Malformed agent response/,
  );
});
