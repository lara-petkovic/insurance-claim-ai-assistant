from core.agents.base import AgentContext, BaseAgent
from core.claim_validation import (
    extract_subject_identifiers,
    inferred_claim_subject_domain,
    parse_date_value,
)
from core.models.agent import AgentResponse


class DateComparisonService:
    """Controlled entry point for policy-period date comparison."""

    @staticmethod
    def compare(context: AgentContext) -> tuple[dict, list[str]]:
        return ConsistencyVerificationAgent._validate_dates(context)


class ConsistencyVerificationAgent(BaseAgent):
    """Cross-checks claim facts, image findings, and required dates for inconsistencies."""

    name = "ConsistencyVerificationAgent"
    agent_type = "validator"

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

        date_validation, date_issues = DateComparisonService.compare(context)
        subject_consistency, subject_issues = self._validate_insured_subject(context, claim_type)
        issues.extend(date_issues)
        issues.extend(subject_issues)

        return self.respond(
            findings={
                "consistency_issues": issues,
                "date_validation": date_validation,
                "insured_subject_consistency": subject_consistency,
            },
            confidence=0.78 if not issues else 0.5,
            warnings=issues,
            requires_human_review=bool(issues),
            messages=[
                self.message(
                    f"Consistency verification completed with {len(issues)} issue(s).",
                    to_agent="OutputValidatorAgent",
                    message_type="validation",
                    metadata={"consistency_issues": issues},
                )
            ],
        )

    @staticmethod
    def _validate_dates(context: AgentContext) -> tuple[dict, list[str]]:
        incident_date, incident_status = parse_date_value(context.request.incident_date)
        policy_period = context.memory.get("PolicyConceptExtractionAgent", {}).get("policy_period")
        if not isinstance(policy_period, dict):
            policy_period = {"start": None, "end": None, "status": "missing"}

        policy_start, start_status = parse_date_value(policy_period.get("start"))
        policy_end, end_status = parse_date_value(policy_period.get("end"))
        period_status = str(policy_period.get("status") or "")
        if not period_status:
            if start_status == "missing" and end_status == "missing":
                period_status = "missing"
            elif start_status == "valid" and end_status == "valid" and policy_start <= policy_end:
                period_status = "valid"
            elif start_status == "invalid" or end_status == "invalid" or (
                policy_start and policy_end and policy_start > policy_end
            ):
                period_status = "invalid"
            else:
                period_status = "unverifiable"

        issues = []
        if incident_status == "missing":
            comparison_status = "missing_incident_date"
            issues.append("Incident date is missing, so policy-period validation cannot be completed.")
        elif incident_status == "invalid":
            comparison_status = "invalid_incident_date"
            issues.append("Incident date is invalid; use YYYY-MM-DD or DD/MM/YYYY.")
        elif period_status == "missing":
            comparison_status = "missing_policy_period"
            issues.append("Policy period is missing, so the incident date cannot be verified against coverage dates.")
        elif period_status == "invalid":
            comparison_status = "invalid_policy_period"
            issues.append("Policy period is invalid, so the incident date cannot be verified against coverage dates.")
        elif period_status != "valid" or policy_start is None or policy_end is None:
            comparison_status = "unverifiable_policy_period"
            issues.append("Policy period is incomplete or unverifiable, so the incident date cannot be checked.")
        elif policy_start <= incident_date <= policy_end:
            comparison_status = "in_period"
        else:
            comparison_status = "out_of_period"
            issues.append(
                f"Incident date {incident_date.isoformat()} is outside the policy period "
                f"{policy_start.isoformat()} to {policy_end.isoformat()}."
            )

        return (
            {
                "incident_date": {
                    "raw": context.request.incident_date,
                    "value": incident_date,
                    "status": incident_status,
                },
                "policy_period": {
                    "start": policy_start,
                    "end": policy_end,
                    "status": period_status,
                },
                "comparison_status": comparison_status,
            },
            issues,
        )
    @staticmethod
    def _validate_insured_subject(context: AgentContext, claim_type: object) -> tuple[dict, list[str]]:
        policy_subject = context.memory.get("PolicyConceptExtractionAgent", {}).get("insured_subject")
        if not isinstance(policy_subject, dict):
            return {"status": "unverifiable", "reason": "Policy insured subject was not extracted."}, []

        selected_domain = context.request.insurance_type
        policy_domain = str(policy_subject.get("domain", ""))
        claim_domain = inferred_claim_subject_domain(claim_type)
        policy_identifiers = policy_subject.get("identifiers", {})
        if not isinstance(policy_identifiers, dict):
            policy_identifiers = {}
        claim_identifiers = extract_subject_identifiers(context.request.claim_description, selected_domain)

        issues = []
        checks = []
        if policy_domain and policy_domain != selected_domain.value:
            checks.append("policy_domain")
            issues.append(
                f"Policy insured subject is {policy_domain}, which is inconsistent with the selected "
                f"{selected_domain.value} insurance domain."
            )
        if claim_domain is not None:
            checks.append("claim_type_domain")
            if claim_domain is not selected_domain:
                issues.append(
                    f"Claim type {claim_type} concerns a {claim_domain.value} insured subject, which is inconsistent "
                    f"with the selected {selected_domain.value} policy."
                )

        comparable_identifiers = sorted(set(policy_identifiers) & set(claim_identifiers))
        for identifier_name in comparable_identifiers:
            checks.append(identifier_name)
            if policy_identifiers[identifier_name] != claim_identifiers[identifier_name]:
                issues.append(
                    f"Claim {identifier_name.replace('_', ' ')} does not match the insured subject in the policy."
                )

        if issues:
            status = "inconsistent"
        elif checks:
            status = "consistent"
        else:
            status = "unverifiable"
        return (
            {
                "status": status,
                "policy_subject": policy_subject,
                "claim_subject_domain": claim_domain.value if claim_domain else None,
                "claim_identifiers": claim_identifiers,
                "checks_performed": checks,
            },
            issues,
        )
