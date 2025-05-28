from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from workflow_use.healing.views import WorkflowSinglePageDefinition

page_analysis_prompt = """
You are an AI assistant that analyzes the page state from Browser Use library.Here is the format of the state:
`
Interactive Elements
[index]<type>text</type>

- index: Numeric identifier for interaction
- type: HTML element type (button, input, etc.)
- text: Element description
  Example:
  [33]<div>User form</div>
  \t*[35]*<button aria-label='Submit form'>Submit</button>

- Only elements with numeric indexes in [] are interactive
- (stacked) indentation (with \t) is important and means that the element is a (html) child of the element above (with a lower index)
- Elements with \* are new elements that were added after the previous step (if url has not changed)
`

You task is to output a function definition that can be used to interact with the elements on the page.

Make th
"""


# TODO: Define your custom output schema here
class PageAnalysis(BaseModel):
	"""Template for your custom output schema - modify as needed"""

	reasoning: str = Field(description='Explanation possible actions you see on the screen')

	workflow_definition: WorkflowSinglePageDefinition = Field(
		description='Create a workflow that can be used to interact with the elements on the page'
	)


async def analyze_page_state(clickable_elements: str, screenshot: str | None) -> PageAnalysis:
	"""
	Analyze page state using LLM with multimodal input
	"""
	# Initialize LLM - you can switch to other providers (Claude, etc.)
	llm = ChatOpenAI(
		model='gpt-4.1',  # Use multimodal model
		temperature=0.1,
	)

	# Create multimodal message
	if screenshot is not None:
		messages = [
			SystemMessage(content=page_analysis_prompt),
			HumanMessage(
				content=[
					{'type': 'text', 'text': f'Clickable elements on the page:\n{clickable_elements}'},
					{'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{screenshot}'}},
				]
			),
		]
	else:
		messages = [
			SystemMessage(content=page_analysis_prompt),
			HumanMessage(content=f'Clickable elements on the page:\n{clickable_elements}'),
		]

	# Get structured output using Pydantic with function_calling method
	structured_llm = llm.with_structured_output(PageAnalysis, method='function_calling')
	response = await structured_llm.ainvoke(messages)

	return PageAnalysis(**response) if isinstance(response, dict) else response
