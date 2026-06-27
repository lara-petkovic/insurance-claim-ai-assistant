"""Functional agents act as domain experts.

Their main task is to decide what should be checked for a given insurance
domain and claim type. They provide rules, checklists, and guidance that help
technical agents perform the right analysis.
"""

from core.agents.functional_agents.auto import AutoInsuranceFunctionalAgent
from core.agents.functional_agents.general import GeneralInsuranceFunctionalAgent
from core.agents.functional_agents.home import HomeInsuranceFunctionalAgent
from core.agents.functional_agents.travel import TravelInsuranceFunctionalAgent

__all__ = [
    "AutoInsuranceFunctionalAgent",
    "GeneralInsuranceFunctionalAgent",
    "HomeInsuranceFunctionalAgent",
    "TravelInsuranceFunctionalAgent",
]
