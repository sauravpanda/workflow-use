import asyncio
import json

import aiofiles
from browser_use import AgentHistoryList
from browser_use.agent.views import AgentOutput
from langchain_openai import ChatOpenAI

from workflow_use.healing._agent.controller import HealingController
from workflow_use.healing.service import HealingService

llm = ChatOpenAI(model='gpt-4.1', temperature=0)


task_message = """
Create a workflow for the government form on https://v0-simple-government-form-xi.vercel.app

Make up all information. It's a multi page form. The task is done when you submit the form.
"""


ActionModel = HealingController(llm=llm).registry.create_action_model()
WorkflowAgentOutput = AgentOutput.type_with_custom_actions(ActionModel)


async def test_workflow_creation():
	healing_service = HealingService(llm)

	history_list = AgentHistoryList.load_from_file('./tmp/history.json', output_model=WorkflowAgentOutput)

	workflow_definition = await healing_service.create_workflow_definition(task_message, history_list)

	# save to json
	async with aiofiles.open('./tmp/workflow_definition.json', mode='w') as f:
		await f.write(json.dumps(workflow_definition.model_dump(), indent=2))


if __name__ == '__main__':
	asyncio.run(test_workflow_creation())
