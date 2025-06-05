from browser_use.agent.views import ActionModel, AgentBrain
from pydantic import BaseModel


class SimpleResult(BaseModel):
	success: bool
	extracted_content: str | None


class SimpleDomElement(BaseModel):
	tag_name: str
	# xpath: str
	highlight_index: int | None
	entire_parent_branch_path: list[str]
	# attributes: dict[str, str]
	shadow_root: bool
	css_selector: str | None


class ParsedAgentStep(BaseModel):
	"""
	Simple step for parsed agent output.
	"""

	url: str
	title: str

	agent_brain: AgentBrain
	actions: list[ActionModel]

	results: list[SimpleResult]

	interacted_elements: list[SimpleDomElement | None]
