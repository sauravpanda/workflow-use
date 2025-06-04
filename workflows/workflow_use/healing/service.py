# class ExplorerAgent:
# 	def __init__(self):
# 		pass

# 	async def explore_page():
# 		async with async_playwright() as playwright:
# 			browser = Browser(playwright=playwright)

# 			agent = Agent(
# 				task=task_message,
# 				browser_session=browser,
# 				llm=llm,
# 				page_extraction_llm=page_extraction_llm,
# 				controller=controller,
# 				override_system_message=system_prompt,
# 				enable_memory=False,
# 				max_actions_per_step=1,
# 				include_attributes=[
# 					'title',
# 					'type',
# 					'name',
# 					'role',
# 					'aria-label',
# 					'placeholder',
# 					'value',
# 					'alt',
# 					'aria-expanded',
# 					'data-date-format',
# 					'data-state',
# 					'aria-checked',
# 				],
# 				tool_calling_method='auto',
# 			)

# 			history = await agent.run()

# 			workflow_definition = WorkflowHealingDefinition.model_validate_json(history.final_result() or '{}')

# 			workflow_json = workflow_definition.model_dump_json(indent=2)
# 			with open('./tmp/workflow.json', 'w') as f:
# 				f.write(workflow_json)


from browser_use import AgentHistoryList


class HealingService:
	def __init__(self):
		pass

		# def

	def history_to_workflow_definition(self, history_list: AgentHistoryList):
		# history
		pass

		messages = []

		for history in history_list.history:
			output = history.model_output

			result = history.result

			state = history.state