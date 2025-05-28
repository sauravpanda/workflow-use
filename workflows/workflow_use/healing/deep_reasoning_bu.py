import asyncio

from browser_use import Browser
from rich import print as pprint

from workflow_use.healing.page_analysis import analyze_page_state


async def main():
	b = Browser()

	async with b:
		await b.navigate('https://v0-complex-form-example.vercel.app')

		while True:
			print('--------------------------------')
			state = await b.get_state_summary(cache_clickable_elements_hashes=True)
			clickable_elements = state.element_tree.clickable_elements_to_string()
			print(clickable_elements)

			# Get screenshot bytes
			screenshot = state.screenshot

			# Skip if no screenshot available
			if screenshot is None:
				print('No screenshot available, skipping LLM analysis')
				continue

			# Analyze with LLM
			try:
				page_analysis = await analyze_page_state(clickable_elements, screenshot)

				print('----------')

				pprint(f'LLM Decision: {page_analysis}')

				print('----------')
			except Exception as e:
				print(f'Error calling LLM: {e}')

			print('--------------------------------')

			# Add a small delay to avoid overwhelming the API
			await asyncio.sleep(2)


if __name__ == '__main__':
	asyncio.run(main())
