import logging
import os

from browser_use import ActionResult, Controller
from browser_use.llm.base import BaseChatModel
from browser_use.llm import ChatOpenAI, SystemMessage, UserMessage
from browser_use.browser.session import BrowserSession
from pydantic import BaseModel, Field, SecretStr

logger = logging.getLogger(__name__)


page_extraction_llm = ChatOpenAI(
    base_url='https://api.groq.com/openai/v1',
    model='meta-llama/llama-4-scout-17b-16e-instruct',
    api_key=os.environ['GROQ_API_KEY'],
    temperature=0.0,
)


class ActionModel(BaseModel):
    variable: str = Field(
        description='Name of the variable/field this action relates to')
    action: str = Field(
        description='Description of the action that can be performed')
    side_effect: str = Field(
        description='What happens when this action is performed')
    is_required: bool = Field(
        description='Whether this action is required for typical workflow completion')


class PageContentAnalysis(BaseModel):
    actions: list[ActionModel] = Field(
        description='List of all possible actions that can be performed on the page')


class HealingController(Controller):
    def __init__(
            self, extraction_llm: BaseChatModel, exclude_actions: list[str] = [], output_model: type[BaseModel] | None = None
    ):
        super().__init__(exclude_actions=exclude_actions, output_model=output_model)
        self.extraction_llm = extraction_llm

        self.registry.action(
            'Call this action EVERY TIME the content on the page changes or is new. This is very important for understanding workflows.'
        )(self.analyse_page_content_and_extract_possible_actions)

    async def analyse_page_content_and_extract_possible_actions(self, browser: BrowserSession):
        # Get page content using browser-use DOM service
        dom_tree = await browser.dom_service.get_dom_tree()

        # Extract text content from DOM tree for analysis
        content = self._extract_text_content_from_dom(dom_tree)

        system_prompt = """You are an expert at analyzing page content and extracting all possible actions, variables, and their side effects. This analysis will be used to create workflow steps.

Your task is to identify:
1. All interactive elements (buttons, forms, inputs, links, dropdowns, etc.)
2. Variables that can be filled or selected (form fields, search boxes, etc.)
3. What happens when each action is performed (side effects like navigation, form submission, etc.)
4. Whether each action is required for typical workflow completion

For example:
- For a search input: variable="search_term", action="enter search query", side_effect="triggers search results", is_required=true
- For a submit button: variable="form_submission", action="click submit button", side_effect="submits form and navigates to next page", is_required=true
- For optional fields: is_required=false"""

        user_prompt = f"Analyze the following page content and extract all possible actions:\n\n{content}"

        try:
            messages = [
                SystemMessage(content=system_prompt),
                UserMessage(content=user_prompt)
            ]
            response = await self.extraction_llm.ainvoke(messages, output_format=PageContentAnalysis)
            output = response.completion
        except Exception as e:
            logger.error(f'Error extracting content: {e}')
            return ActionResult(extracted_content=f'Error extracting content: {e}')

        msg = f'📄  Extracted from page\n: {output.model_dump_json(indent=2)}\n'
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)

    def _extract_text_content_from_dom(self, dom_tree):
        """Extract readable text content from DOM tree for analysis."""
        content = ""
        if hasattr(dom_tree, 'text') and dom_tree.text:
            content += dom_tree.text + " "

        if hasattr(dom_tree, 'children') and dom_tree.children:
            for child in dom_tree.children:
                content += self._extract_text_content_from_dom(child)

        return content.strip()
