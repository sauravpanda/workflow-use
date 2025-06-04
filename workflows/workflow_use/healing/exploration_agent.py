import asyncio
import logging
import os

from browser_use import ActionResult, Agent, Browser, Controller
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from patchright.async_api import async_playwright
from playwright.async_api import Page
from pydantic import BaseModel, Field, SecretStr

from workflow_use.healing.views import WorkflowHealingDefinition

logger = logging.getLogger(__name__)


llm = ChatOpenAI(
	base_url='https://api.groq.com/openai/v1',
	model='meta-llama/llama-4-maverick-17b-128e-instruct',
	api_key=SecretStr(os.environ['GROQ_API_KEY']),
	# model='gpt-4.1-mini',
	temperature=0.0,
)
page_extraction_llm = ChatOpenAI(
	base_url='https://api.groq.com/openai/v1',
	model='meta-llama/llama-4-scout-17b-16e-instruct',
	api_key=SecretStr(os.environ['GROQ_API_KEY']),
	temperature=0.0,
)

system_prompt = open('workflow_use/healing/healing_prompt.md').read()


controller = Controller(output_model=WorkflowHealingDefinition)


class ActionModel(BaseModel):
	variable: str = Field(description='Name of the variable/field this action relates to')
	action: str = Field(description='Description of the action that can be performed')
	side_effect: str = Field(description='What happens when this action is performed')
	is_required: bool = Field(description='Whether this action is required for typical workflow completion')


class PageContentAnalysis(BaseModel):
	actions: list[ActionModel] = Field(description='List of all possible actions that can be performed on the page')


@controller.action(
	'Call this action EVERY TIME the content on the page changes or is new. This is very important for understanding workflows.'
)
async def analyse_page_content_and_extract_possible_actions(page: Page):
	import markdownify

	strip = ['a', 'img']

	content = markdownify.markdownify(await page.content(), strip=strip)

	# manually append iframe text into the content so it's readable by the LLM (includes cross-origin iframes)
	for iframe in page.frames:
		if iframe.url != page.url and not iframe.url.startswith('data:'):
			content += f'\n\nIFRAME {iframe.url}:\n'
			content += markdownify.markdownify(await iframe.content())

	prompt = """Analyze the page content and extract all possible actions, variables, and their side effects. This analysis will be used to create workflow steps.

Your task is to identify:
1. All interactive elements (buttons, forms, inputs, links, dropdowns, etc.)
2. Variables that can be filled or selected (form fields, search boxes, etc.)
3. What happens when each action is performed (side effects like navigation, form submission, etc.)
4. Whether each action is required for typical workflow completion

For example:
- For a search input: variable="search_term", action="enter search query", side_effect="triggers search results", is_required=true
- For a submit button: variable="form_submission", action="click submit button", side_effect="submits form and navigates to next page", is_required=true
- For optional fields: is_required=false

Page content: {page}"""

	template = PromptTemplate(input_variables=['page'], template=prompt)

	try:
		structured_llm = llm.with_structured_output(PageContentAnalysis, method='function_calling')
		output: PageContentAnalysis = await structured_llm.ainvoke(template.format(page=content))  # type: ignore
	except Exception as e:
		logger.error(f'Error extracting content: {e}')
		return ActionResult(extracted_content=f'Error extracting content: {e}')

	msg = f'📄  Extracted from page\n: {output.model_dump_json(indent=2)}\n'
	logger.info(msg)
	return ActionResult(extracted_content=msg, include_in_memory=True)


# @controller.action('create_workflow', param_model=WorkflowHealingDefinition)
# async def create_workflow(workflow_definition: WorkflowHealingDefinition):
# 	# Save workflow definition to JSON file
# 	workflow_json = workflow_definition.model_dump_json(indent=2)
# 	with open('./tmp/workflow.json', 'w') as f:
# 		f.write(workflow_json)

# 	# Print workflow definition
# 	print('Workflow Definition:')
# 	print(workflow_json)

# 	return 'workflow saved; please call done function now'


# task_message = """
# Create a workflow for searching for parts on https://shop.advanceautoparts.com

# Search for a part (for example "YH482053P") and extract the price of the part.
# """

# task_message = """
# Create a workflow for the searching a one way flight on https://www.google.com/flights

# Make sure you confirm the flight destination after type it in.
# """

task_message = """
Create a workflow for the government form on https://v0-government-form-example.vercel.app

Make up all information. It's a multi page form. The task is done when you press the first next button (automate only the first page).
"""


async def explore_page():
	async with async_playwright() as playwright:
		browser = Browser(playwright=playwright)

		agent = Agent(
			task=task_message,
			browser_session=browser,
			llm=llm,
			page_extraction_llm=page_extraction_llm,
			controller=controller,
			override_system_message=system_prompt,
			enable_memory=False,
			max_actions_per_step=1,
			include_attributes=[
				'title',
				'type',
				'name',
				'role',
				'aria-label',
				'placeholder',
				'value',
				'alt',
				'aria-expanded',
				'data-date-format',
				'data-state',
				'aria-checked',
			],
			tool_calling_method='auto',
		)

		history = await agent.run()

		workflow_definition = WorkflowHealingDefinition.model_validate_json(history.final_result() or '{}')

		workflow_json = workflow_definition.model_dump_json(indent=2)
		with open('./tmp/workflow.json', 'w') as f:
			f.write(workflow_json)


if __name__ == '__main__':
	asyncio.run(explore_page())
