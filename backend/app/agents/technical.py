from __future__ import annotations

import re
from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.schemas.agent import AgentResponse, EvidenceItem
from app.schemas.claim import ImageAssessment, ImageAuthenticity
from app.services.model_client import get_model_client
from app.services.retrieval import retrieve_passages


def _contains(text: str, *terms: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in terms)


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_dict_list(value: object, *, default_key: str = "text") -> list[dict]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({default_key: str(item)})
    return normalized


class DocumentIngestionAgent(BaseAgent):
    name = "DocumentIngestionAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        request = context.request
        policy_text = request.policy_text.strip()
        warnings = []
        if not request.policy_text.strip():
            warnings.append("No policy text was provided or extracted. Upload a policy PDF/text file before analysis.")
        findings = {
            "policy_filename": request.policy_filename,
            "policy_text": policy_text,
            "policy_text_length": len(policy_text),
            "supporting_documents": request.supporting_document_names,
            "damage_image_filename": request.damage_image_filename,
        }
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=0.9 if policy_text else 0.0,
            warnings=warnings,
            requires_human_review=not bool(policy_text),
        )


class PolicyConceptExtractionAgent(BaseAgent):
    name = "PolicyConceptExtractionAgent"

    COVERAGE_PATTERNS = {
        "fire_damage": ["fire", "smoke", "explosion", "lightning"],
        "storm_damage": ["storm", "flood", "weather"],
        "theft": ["theft", "attempted theft", "stolen", "forcible"],
        "water_damage": ["escape of water", "water installation", "pipe", "leak", "washing machine"],
        "broken_glass": ["breakage", "fixed glass", "sanitary ware", "glass"],
    }

    EXCLUSION_PATTERNS = {
        "unoccupied_home": ["unoccupied", "unfurnished"],
        "gradual_damage": ["gradual", "repeated exposure", "long-term", "wear and tear"],
        "rot": ["rot"],
        "poor_maintenance": ["poor maintenance", "lack of maintenance"],
        "pipe_or_apparatus_itself": ["apparatus", "pipes from which the water escaped"],
        "subsidence_landslip": ["subsidence", "landslip", "ground heave"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        policy_text = context.memory.get("DocumentIngestionAgent", {}).get("policy_text", "")
        lower = policy_text.lower()

        covered_events = [
            {"concept": concept, "matched_terms": [term for term in terms if term in lower]}
            for concept, terms in self.COVERAGE_PATTERNS.items()
            if any(term in lower for term in terms)
        ]
        exclusions = [
            {"concept": concept, "matched_terms": [term for term in terms if term in lower]}
            for concept, terms in self.EXCLUSION_PATTERNS.items()
            if any(term in lower for term in terms)
        ]

        required_documents = ["claim description", "damage photos"]
        if "repair estimate" in lower or "invoice" in lower:
            required_documents.append("repair estimate or invoice")
        if "police report" in lower:
            required_documents.append("police report for theft")
        if "weather" in lower:
            required_documents.append("weather evidence for storm claims")

        policy_period = None
        date_match = re.search(r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}).{0,80}(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", policy_text)
        if date_match:
            policy_period = {"start": date_match.group(1), "end": date_match.group(2)}

        findings = {
            "policy_type": "home_insurance",
            "policy_period": policy_period,
            "insured_subject": {"type": "home_or_personal_property", "source": "policy"},
            "covered_events": covered_events,
            "exclusions": exclusions,
            "limits": [],
            "deductible_or_excess": "excess mentioned in policy wording" if "excess" in lower else None,
            "required_claim_documents": required_documents,
            "special_conditions": ["policy wording structure normalized into shared concept schema"],
        }
        fallback = findings
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance policy concept extraction agent. "
                "Return only valid JSON. Normalize heterogeneous policy wording into a shared insurance schema."
            ),
            prompt=(
                "Extract normalized insurance policy concepts from this policy text. "
                "Use this exact top-level JSON shape: "
                "{policy_type, policy_period, insured_subject, covered_events, exclusions, limits, "
                "deductible_or_excess, required_claim_documents, special_conditions}. "
                "covered_events and exclusions must be arrays of objects with at least concept and evidence_text.\n\n"
                f"POLICY TEXT:\n{policy_text[:12000]}"
            ),
            fallback=fallback,
        )
        findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=0.78 if covered_events else 0.45,
            warnings=(
                ["Used configured model provider for policy concept extraction."]
                if model_result.used_model
                else ([] if covered_events else ["No covered events were confidently extracted."])
            ),
            requires_human_review=not bool(covered_events),
        )


class ClaimExtractionAgent(BaseAgent):
    name = "ClaimExtractionAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        description = context.request.claim_description
        text = description.lower()
        claim_type = "unknown"
        if _contains(text, "pipe", "leak", "water", "ceiling", "bathroom", "flooded"):
            claim_type = "water_damage"
        elif _contains(text, "storm", "wind", "roof", "hail", "attic"):
            claim_type = "storm_damage"
        elif _contains(text, "stole", "stolen", "theft", "break", "broke into", "burglar"):
            claim_type = "theft"
        elif _contains(text, "fire", "smoke", "burn"):
            claim_type = "fire_damage"
        elif _contains(text, "glass", "window", "sanitary"):
            claim_type = "broken_glass"

        amount_match = re.search(r"([$EUReurRSD\s]*\d[\d,.]*)", description)
        findings = {
            "claim_type": claim_type,
            "incident_date": context.request.incident_date,
            "incident_location": "insured_property" if _contains(text, "home", "house", "bathroom", "kitchen", "roof") else "unknown",
            "damage_or_loss_type": claim_type,
            "claimed_cause": description,
            "claimed_amount": amount_match.group(1).strip() if amount_match else None,
            "user_provided_evidence": {
                "has_image": bool(context.request.damage_image_filename),
                "supporting_documents": context.request.supporting_document_names,
            },
        }
        fallback = findings
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance claim extraction agent. "
                "Return only valid JSON using the requested schema."
            ),
            prompt=(
                "Extract structured claim facts from this description. "
                "Use this exact top-level JSON shape: "
                "{claim_type, incident_date, incident_location, damage_or_loss_type, "
                "claimed_cause, claimed_amount, user_provided_evidence}. "
                "claim_type should be one of water_damage, storm_damage, theft, fire_damage, "
                "broken_glass, vehicle_damage, medical, baggage_loss, unknown.\n\n"
                f"INCIDENT DATE FIELD: {context.request.incident_date}\n"
                f"SUPPORTING DOCUMENT NAMES: {context.request.supporting_document_names}\n"
                f"DAMAGE IMAGE FILENAME: {context.request.damage_image_filename}\n"
                f"CLAIM DESCRIPTION:\n{description}"
            ),
            fallback=fallback,
        )
        findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        claim_type = str(findings.get("claim_type", claim_type))
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=0.82 if claim_type != "unknown" else 0.35,
            warnings=(
                ["Used configured model provider for claim extraction."]
                if model_result.used_model
                else ([] if claim_type != "unknown" else ["Could not classify claim type from description."])
            ),
            requires_human_review=claim_type == "unknown",
        )


class RetrievalAgent(BaseAgent):
    name = "RetrievalAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        policy_text = context.memory.get("DocumentIngestionAgent", {}).get("policy_text", "")
        claim = context.memory.get("ClaimExtractionAgent", {})
        claim_type = claim.get("claim_type", "unknown")
        query = f"{claim_type} covered not covered exclusions required documents {context.request.claim_description}"
        evidence = retrieve_passages(policy_text, query, top_k=5)
        return AgentResponse(
            agent_name=self.name,
            findings={"query": query, "retrieved_count": len(evidence)},
            evidence=evidence,
            confidence=0.75 if evidence else 0.25,
            warnings=[] if evidence else ["Retrieval returned no matching policy clauses."],
            requires_human_review=not bool(evidence),
        )


class VisualEvidenceAgent(BaseAgent):
    name = "VisualEvidenceAgent"

    LABEL_KEYWORDS = {
        "water_damage": ["water", "leak", "ceiling", "mold", "wet", "pipe"],
        "fire_damage": ["fire", "smoke", "burn"],
        "storm_damage": ["storm", "roof", "hail", "wind"],
        "broken_glass": ["glass", "window", "broken"],
        "theft_damage": ["theft", "stolen", "breakin", "burglary"],
        "vehicle_damage": ["car", "vehicle", "auto"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        filename = (context.request.damage_image_filename or "").lower()
        detected = "unknown"
        for label, keywords in self.LABEL_KEYWORDS.items():
            if any(keyword in filename for keyword in keywords):
                detected = label
                break

        if not filename:
            warning = "No damage image was uploaded."
            confidence = 0.0
        elif detected == "unknown":
            warning = "Image classification is inconclusive without a successful vision model response."
            confidence = 0.3
        else:
            warning = ""
            confidence = 0.72

        findings = ImageAssessment(
            detected_damage=detected,
            confidence=confidence,
            notes=["Fallback classification is used only when model fallback mode is explicitly enabled."],
        ).model_dump()
        model_client = get_model_client()
        model_result = model_client.image_json_response(
            system=(
                "You are a visual insurance evidence agent. "
                "Inspect the image and return only valid JSON."
            ),
            prompt=(
                "Classify visible insurance damage. Use this exact JSON shape: "
                "{detected_damage, confidence, notes}. detected_damage should be one of "
                "water_damage, fire_damage, storm_damage, broken_glass, theft_damage, "
                "vehicle_damage, unknown. confidence must be a number between 0 and 1."
            ),
            image_bytes=context.request.damage_image_bytes,
            image_mime_type=context.request.damage_image_mime_type,
            fallback=findings,
        )
        findings = {**findings, **model_result.data, "model_used": model_result.used_model}
        findings["notes"] = [str(note) for note in _as_list(findings.get("notes"))]
        detected = str(findings.get("detected_damage", detected))
        confidence = float(findings.get("confidence", confidence) or 0)
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=confidence,
            warnings=(
                ["Used configured vision-capable model for visual evidence assessment."]
                if model_result.used_model
                else ([warning] if warning else [])
            ),
            requires_human_review=detected == "unknown",
        )


class ImageAuthenticityAgent(BaseAgent):
    name = "ImageAuthenticityAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        filename = context.request.damage_image_filename or ""
        suffix = Path(filename).suffix.lower()
        signals: list[str] = []
        score = 0.1
        if not filename:
            signals.append("no_image_uploaded")
            score = 0.6
        if suffix and suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            signals.append("unusual_file_extension")
            score += 0.25
        if context.request.damage_image_size is not None and context.request.damage_image_size < 8_000:
            signals.append("very_small_image_file")
            score += 0.2
        if _contains(filename, "ai", "generated", "edited", "fake", "photoshop"):
            signals.append("suspicious_filename")
            score += 0.35
        if filename and "metadata" not in filename.lower():
            signals.append("metadata_not_available_in_mvp_upload")
            score += 0.05

        score = min(round(score, 2), 1.0)
        if score >= 0.75:
            risk = "requires_human_review"
        elif score >= 0.5:
            risk = "high"
        elif score >= 0.25:
            risk = "medium"
        else:
            risk = "low"

        findings = ImageAuthenticity(risk_level=risk, risk_score=score, signals=signals).model_dump()
        model_client = get_model_client()
        model_result = model_client.image_json_response(
            system=(
                "You are an insurance image authenticity risk agent. "
                "Return only valid JSON. Do not claim certainty; estimate risk signals."
            ),
            prompt=(
                "Assess whether this insurance claim image has authenticity risks. "
                "Use this exact JSON shape: {risk_level, risk_score, signals}. "
                "risk_level must be low, medium, high, or requires_human_review. "
                "risk_score must be a number between 0 and 1. signals must be short textual observations."
            ),
            image_bytes=context.request.damage_image_bytes,
            image_mime_type=context.request.damage_image_mime_type,
            fallback=findings,
        )
        findings = {**findings, **model_result.data, "model_used": model_result.used_model}
        findings["signals"] = [str(signal) for signal in _as_list(findings.get("signals"))]
        risk = str(findings.get("risk_level", risk))
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=0.6,
            warnings=(
                ["Used configured vision-capable model for image authenticity assessment."]
                if model_result.used_model
                else ["Authenticity assessment did not use a model because no image was uploaded or fallback mode is enabled."]
            ),
            requires_human_review=risk in {"high", "requires_human_review"},
        )


class CoverageMatchingAgent(BaseAgent):
    name = "CoverageMatchingAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        covered_events = context.memory.get("PolicyConceptExtractionAgent", {}).get("covered_events", [])
        matches = [event for event in covered_events if event.get("concept") == claim_type]
        assessment = "covered" if matches else "unclear"
        if claim_type == "storm_damage" and any(event.get("concept") == "storm_damage" for event in covered_events):
            assessment = "possibly_covered"
        if claim_type == "unknown":
            assessment = "unclear"
        fallback = {"coverage_assessment": assessment, "matched_policy_concepts": matches}
        retrieved_evidence = []
        for response in context.responses:
            if response.agent_name == "RetrievalAgent":
                retrieved_evidence = [item.model_dump() for item in response.evidence]
                break
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance coverage matching agent. "
                "Return only valid JSON. Use policy evidence conservatively."
            ),
            prompt=(
                "Compare the claim facts with the normalized policy concepts and decide coverage. "
                "Use this JSON shape: {coverage_assessment, matched_policy_concepts, explanation}. "
                "coverage_assessment must be covered, not_covered, possibly_covered, or unclear.\n\n"
                f"CLAIM FACTS:\n{context.memory.get('ClaimExtractionAgent', {})}\n\n"
                f"POLICY CONCEPTS:\n{context.memory.get('PolicyConceptExtractionAgent', {})}\n\n"
                f"RETRIEVED EVIDENCE:\n{retrieved_evidence}"
            ),
            fallback=fallback,
        )
        final_findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        final_findings["matched_policy_concepts"] = _as_dict_list(
            final_findings.get("matched_policy_concepts"),
            default_key="concept",
        )
        return AgentResponse(
            agent_name=self.name,
            findings=final_findings,
            confidence=0.82 if final_findings.get("matched_policy_concepts") else 0.4,
            warnings=(
                ["Used configured model provider for coverage matching."]
                if model_result.used_model
                else ([] if matches else ["No direct policy concept match found for the claim type."])
            ),
            requires_human_review=final_findings.get("coverage_assessment") != "covered",
        )


class ExclusionCheckingAgent(BaseAgent):
    name = "ExclusionCheckingAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_text = context.request.claim_description.lower()
        policy_exclusions = context.memory.get("PolicyConceptExtractionAgent", {}).get("exclusions", [])
        found = []
        for exclusion in policy_exclusions:
            concept = exclusion.get("concept")
            if concept == "unoccupied_home" and _contains(claim_text, "unoccupied", "empty", "away for months"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests home may have been unoccupied."})
            if concept == "gradual_damage" and _contains(claim_text, "months", "slow", "gradual", "long time"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests gradual damage."})
            if concept == "rot" and _contains(claim_text, "rot", "mold", "mould"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim mentions rot or mold."})
            if concept == "poor_maintenance" and _contains(claim_text, "maintenance", "old", "neglected"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim may involve maintenance condition."})
            if concept == "pipe_or_apparatus_itself" and _contains(claim_text, "replace the pipe", "repair the pipe"):
                found.append({"concept": concept, "severity": "medium", "reason": "Damage to the pipe itself may be excluded."})

        fallback = {"potential_exclusions": found}
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance exclusion checking agent. "
                "Return only valid JSON. Be conservative: uncertainty should be flagged for human review."
            ),
            prompt=(
                "Check whether policy exclusions may apply to this claim. "
                "Use this JSON shape: {potential_exclusions}. "
                "potential_exclusions must be an array of objects with concept, severity, reason, and evidence_text if available.\n\n"
                f"CLAIM DESCRIPTION:\n{context.request.claim_description}\n\n"
                f"CLAIM FACTS:\n{context.memory.get('ClaimExtractionAgent', {})}\n\n"
                f"POLICY EXCLUSIONS:\n{policy_exclusions}\n\n"
                f"RETRIEVED POLICY EVIDENCE:\n"
                f"{[item.model_dump() for response in context.responses if response.agent_name == 'RetrievalAgent' for item in response.evidence]}"
            ),
            fallback=fallback,
        )
        final_findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        final_findings["potential_exclusions"] = _as_dict_list(
            final_findings.get("potential_exclusions"),
            default_key="concept",
        )
        found = final_findings.get("potential_exclusions", found)

        return AgentResponse(
            agent_name=self.name,
            findings=final_findings,
            confidence=0.72,
            warnings=(
                ["Used configured model provider for exclusion checking."]
                if model_result.used_model
                else ([] if not found else ["Potential exclusions require adjuster review."])
            ),
            requires_human_review=bool(found),
        )


class MissingDocumentsAgent(BaseAgent):
    name = "MissingDocumentsAgent"

    REQUIREMENTS = {
        "water_damage": ["damage photos", "plumber report", "repair estimate"],
        "storm_damage": ["damage photos", "weather report", "repair estimate"],
        "theft": ["police report", "proof of ownership"],
        "fire_damage": ["damage photos", "incident report", "repair estimate"],
        "broken_glass": ["damage photos", "repair estimate"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        provided_names = " ".join(context.request.supporting_document_names).lower()
        missing = []
        for requirement in self.REQUIREMENTS.get(claim_type, ["supporting evidence"]):
            if requirement == "damage photos":
                if not context.request.damage_image_filename:
                    missing.append(requirement)
                continue
            tokens = requirement.split()
            if not any(token in provided_names for token in tokens):
                missing.append(requirement)

        return AgentResponse(
            agent_name=self.name,
            findings={"missing_documents": missing},
            confidence=0.83,
            warnings=[] if not missing else ["Claim package is incomplete."],
            requires_human_review=bool(missing),
        )


class ConsistencyVerificationAgent(BaseAgent):
    name = "ConsistencyVerificationAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        visual = context.memory.get("VisualEvidenceAgent", {})
        detected_damage = visual.get("detected_damage", "unknown")
        issues = []
        if detected_damage != "unknown" and claim_type != "unknown":
            visual_to_claim = {
                "theft_damage": "theft",
                "water_damage": "water_damage",
                "fire_damage": "fire_damage",
                "storm_damage": "storm_damage",
                "broken_glass": "broken_glass",
            }
            expected = visual_to_claim.get(detected_damage, detected_damage)
            if expected != claim_type:
                issues.append(f"Image suggests {detected_damage}, while claim was classified as {claim_type}.")
        if not context.request.incident_date:
            issues.append("Incident date is missing, so policy-period validation cannot be completed.")

        return AgentResponse(
            agent_name=self.name,
            findings={"consistency_issues": issues},
            confidence=0.78 if not issues else 0.5,
            warnings=issues,
            requires_human_review=bool(issues),
        )


class CitationAgent(BaseAgent):
    name = "CitationAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        retrieval_evidence = []
        for response in context.responses:
            if response.agent_name == "RetrievalAgent":
                retrieval_evidence.extend(response.evidence)
        return AgentResponse(
            agent_name=self.name,
            findings={"citation_count": len(retrieval_evidence)},
            evidence=retrieval_evidence[:4],
            confidence=0.84 if retrieval_evidence else 0.25,
            warnings=[] if retrieval_evidence else ["No citations available for final decision."],
            requires_human_review=not bool(retrieval_evidence),
        )


class OutputValidatorAgent(BaseAgent):
    name = "OutputValidatorAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        model_client = get_model_client()
        required = [
            "ClaimExtractionAgent",
            "PolicyConceptExtractionAgent",
            "CoverageMatchingAgent",
            "ExclusionCheckingAgent",
            "MissingDocumentsAgent",
        ]
        missing = [name for name in required if name not in context.memory]
        required_model_agents = [
            "ClaimExtractionAgent",
            "PolicyConceptExtractionAgent",
            "CoverageMatchingAgent",
            "ExclusionCheckingAgent",
        ]
        if context.request.damage_image_bytes:
            required_model_agents.extend(["VisualEvidenceAgent", "ImageAuthenticityAgent"])
        non_model_agents = [
            name
            for name in required_model_agents
            if context.memory.get(name, {}).get("model_used") is not True
        ]
        warnings = []
        if missing:
            warnings.append(f"Missing agent outputs: {', '.join(missing)}")
        if model_client.require_models and non_model_agents:
            warnings.append(f"These model-backed agents did not use a model: {', '.join(non_model_agents)}")
        return AgentResponse(
            agent_name=self.name,
            findings={
                "schema_ready": not missing and not (model_client.require_models and non_model_agents),
                "missing_agent_outputs": missing,
                "model_required": model_client.require_models,
                "non_model_agents": non_model_agents,
            },
            confidence=1.0 if not missing and not non_model_agents else 0.2,
            warnings=warnings,
            requires_human_review=bool(missing or (model_client.require_models and non_model_agents)),
        )
