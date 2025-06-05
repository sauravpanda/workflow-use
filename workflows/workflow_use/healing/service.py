import json
from typing import Any, Dict, List, Sequence, Union

import aiofiles
from browser_use import AgentHistoryList
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from workflow_use.builder.service import BuilderService
from workflow_use.healing.views import ParsedAgentStep, SimpleDomElement, SimpleResult
from workflow_use.schema.views import WorkflowDefinitionSchema


class HealingService:
	def __init__(self, llm: BaseChatModel):
		self.llm = llm

	def _remove_none_fields_from_dict(self, d: dict) -> dict:
		return {k: v for k, v in d.items() if v is not None}

	def _history_to_workflow_definition(self, history_list: AgentHistoryList) -> list[HumanMessage]:
		# history

		messages: list[HumanMessage] = []

		for history in history_list.history:
			if history.model_output is None:
				continue

			screenshot = history.state.screenshot
			parsed_step = ParsedAgentStep(
				url=history.state.url,
				title=history.state.title,
				agent_brain=history.model_output.current_state,
				actions=[self._remove_none_fields_from_dict(action.model_dump()) for action in history.model_output.action],
				results=[
					SimpleResult(
						success=result.success or False,
						extracted_content=result.extracted_content,
					)
					for result in history.result
				],
				interacted_elements=[
					SimpleDomElement(
						tag_name=element.tag_name,
						highlight_index=element.highlight_index,
						# entire_parent_branch_path=element.entire_parent_branch_path,
						shadow_root=element.shadow_root,
						# css_selector=element.css_selector,
						element_hash=f'{element.highlight_index}_{hash(str(element)) % 1000000:06d}',
					)
					for element in history.state.interacted_element
					if element is not None
				],
			)

			parsed_step_json = json.dumps(parsed_step.model_dump(exclude_none=True))
			content_blocks: List[Union[str, Dict[str, Any]]] = []

			text_block: Dict[str, Any] = {'type': 'text', 'text': parsed_step_json}
			content_blocks.append(text_block)

			if screenshot:
				# Assuming screenshot is a base64 encoded string.
				# Adjust mime type if necessary (e.g., image/png)
				image_block: Dict[str, Any] = {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{screenshot}'}}
				content_blocks.append(image_block)

			messages.append(HumanMessage(content=content_blocks))

		return messages

	async def create_workflow_definition(self, task: str, history_list: AgentHistoryList) -> WorkflowDefinitionSchema:
		async with aiofiles.open('workflow_use/healing/workflow_creation_prompt.md', mode='r') as f:
			prompt_content = await f.read()

		prompt_content = prompt_content.format(goal=task, actions=BuilderService._get_available_actions_markdown())

		system_message = SystemMessage(content=prompt_content)
		human_messages = self._history_to_workflow_definition(history_list)

		all_messages: Sequence[BaseMessage] = [system_message] + human_messages

		# Chain the model with the structured output schema
		structured_llm = self.llm.with_structured_output(WorkflowDefinitionSchema, method='function_calling')

		workflow_definition = await structured_llm.ainvoke(all_messages)

		return workflow_definition  # type: ignore
