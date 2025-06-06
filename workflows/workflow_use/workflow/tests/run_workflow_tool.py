import asyncio
from pathlib import Path

# Ensure langchain-openai is installed and OPENAI_API_KEY is set
from langchain_openai import ChatOpenAI

from workflow_use.workflow.service import Workflow

# Instantiate the LLM and the service directly
llm_instance = ChatOpenAI(model='gpt-4o-mini')  # Or your preferred model


async def test_run_workflow():
	"""
	Tests that the workflow is built correctly from a JSON file path.
	"""
	path = Path(__file__).parent.parent.parent.parent / 'tmp' / 'workflow_definition.json'

	workflow = Workflow.load_from_file(path, llm=llm_instance)
	result = await workflow.run_as_tool('Make up all the information for the form.')
	print(result)


if __name__ == '__main__':
	asyncio.run(test_run_workflow())
