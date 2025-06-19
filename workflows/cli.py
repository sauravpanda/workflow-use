import asyncio
import json
import os
import subprocess
import tempfile  # For temporary file handling
import webbrowser
from pathlib import Path

import typer
from browser_use import Browser
from langchain.chat_models.base import BaseChatModel

# Assuming OPENAI_API_KEY is set in the environment
from langchain_openai import ChatOpenAI
from patchright.async_api import async_playwright as patchright_async_playwright

from workflow_use.builder.service import BuilderService
from workflow_use.controller.service import WorkflowController
from workflow_use.mcp.service import get_mcp_server
from workflow_use.recorder.service import RecordingService  # Added import
from workflow_use.workflow.service import Workflow

# Placeholder for recorder functionality
# from src.recorder.service import RecorderService

app = typer.Typer(
	name='workflow-cli',
	help='A CLI tool to create and run workflows.',
	add_completion=False,
	no_args_is_help=True,
)

# Default LLM instance to None
llm_instance: BaseChatModel
try:
	llm_instance = ChatOpenAI(model='gpt-4o-mini')
	page_extraction_llm = ChatOpenAI(model='gpt-4o-mini')
except Exception as e:
	typer.secho(f'Error initializing LLM: {e}. Would you like to set your OPENAI_API_KEY?', fg=typer.colors.RED)
	set_openai_api_key = input('Set OPENAI_API_KEY? (y/n): ')
	if set_openai_api_key.lower() == 'y':
		os.environ['OPENAI_API_KEY'] = input('Enter your OPENAI_API_KEY: ')
		llm_instance = ChatOpenAI(model='gpt-4o')
		page_extraction_llm = ChatOpenAI(model='gpt-4o-mini')

builder_service = BuilderService(llm=llm_instance) if llm_instance else None
# recorder_service = RecorderService() # Placeholder
recording_service = (
	RecordingService()
)  # Assuming RecordingService does not need LLM, or handle its potential None state if it does.


def get_default_save_dir() -> Path:
	"""Returns the default save directory for workflows."""
	# Ensure ./tmp exists for temporary files as well if we use it
	tmp_dir = Path('./tmp').resolve()
	tmp_dir.mkdir(parents=True, exist_ok=True)
	return tmp_dir


# --- Helper function for building and saving workflow ---
def _build_and_save_workflow_from_recording(
	recording_path: Path,
	default_save_dir: Path,
	is_temp_recording: bool = False,  # To adjust messages if it's from a live recording
) -> Path | None:
	"""Builds a workflow from a recording file, prompts for details, and saves it."""
	if not builder_service:
		typer.secho(
			'BuilderService not initialized. Cannot build workflow.',
			fg=typer.colors.RED,
		)
		return None

	prompt_subject = 'recorded' if is_temp_recording else 'provided'
	typer.echo()  # Add space
	description: str = typer.prompt(typer.style(f'What is the purpose of this {prompt_subject} workflow?', bold=True))

	typer.echo()  # Add space
	output_dir_str: str = typer.prompt(
		typer.style('Where would you like to save the final built workflow?', bold=True)
		+ f" (e.g., ./my_workflows, press Enter for '{default_save_dir}')",
		default=str(default_save_dir),
	)
	output_dir = Path(output_dir_str).resolve()
	output_dir.mkdir(parents=True, exist_ok=True)

	typer.echo(f'The final built workflow will be saved in: {typer.style(str(output_dir), fg=typer.colors.CYAN)}')
	typer.echo()  # Add space

	typer.echo(
		f'Processing recording ({typer.style(str(recording_path.name), fg=typer.colors.MAGENTA)}) and building workflow...'
	)
	try:
		workflow_definition = asyncio.run(
			builder_service.build_workflow_from_path(
				recording_path,
				description,
			)
		)
	except FileNotFoundError:
		typer.secho(
			f'Error: Recording file not found at {recording_path}. Please ensure it exists.',
			fg=typer.colors.RED,
		)
		return None
	except Exception as e:
		typer.secho(f'Error building workflow: {e}', fg=typer.colors.RED)
		return None

	if not workflow_definition:
		typer.secho(
			f'Failed to build workflow definition from the {prompt_subject} recording.',
			fg=typer.colors.RED,
		)
		return None

	typer.secho('Workflow built successfully!', fg=typer.colors.GREEN, bold=True)
	typer.echo()  # Add space

	file_stem = recording_path.stem
	if is_temp_recording:
		file_stem = file_stem.replace('temp_recording_', '') or 'recorded'

	default_workflow_filename = f'{file_stem}.workflow.json'
	workflow_output_name: str = typer.prompt(
		typer.style('Enter a name for the generated workflow file', bold=True) + ' (e.g., my_search.workflow.json):',
		default=default_workflow_filename,
	)
	# Ensure the file name ends with .json
	if not workflow_output_name.endswith('.json'):
		workflow_output_name = f'{workflow_output_name}.json'
	final_workflow_path = output_dir / workflow_output_name

	try:
		asyncio.run(builder_service.save_workflow_to_path(workflow_definition, final_workflow_path))
		typer.secho(
			f'Final workflow definition saved to: {typer.style(str(final_workflow_path.resolve()), fg=typer.colors.BRIGHT_GREEN, bold=True)}',
			fg=typer.colors.GREEN,  # Overall message color
		)
		return final_workflow_path
	except Exception as e:
		typer.secho(f'Error saving workflow: {e}', fg=typer.colors.RED)
		return None


# --- Helper function for building semantic workflow from recording ---
def _build_and_save_semantic_workflow_from_recording(
	recording_path: Path,
	default_save_dir: Path,
	is_temp_recording: bool = False,
) -> Path | None:
	"""Builds a semantic workflow from a recording file using visible text mappings."""
	from workflow_use.workflow.semantic_extractor import SemanticExtractor
	
	prompt_subject = 'recorded' if is_temp_recording else 'provided'
	typer.echo()  # Add space
	description: str = typer.prompt(typer.style(f'What is the purpose of this {prompt_subject} workflow?', bold=True))

	typer.echo()  # Add space
	output_dir_str: str = typer.prompt(
		typer.style('Where would you like to save the final semantic workflow?', bold=True)
		+ f" (e.g., ./my_workflows, press Enter for '{default_save_dir}')",
		default=str(default_save_dir),
	)
	output_dir = Path(output_dir_str).resolve()
	output_dir.mkdir(parents=True, exist_ok=True)

	typer.echo(f'The final semantic workflow will be saved in: {typer.style(str(output_dir), fg=typer.colors.CYAN)}')
	typer.echo()  # Add space

	typer.echo(
		f'Processing recording ({typer.style(str(recording_path.name), fg=typer.colors.MAGENTA)}) and building semantic workflow...'
	)
	
	# Load the recording
	try:
		with open(recording_path, 'r') as f:
			recording_data = json.load(f)
	except FileNotFoundError:
		typer.secho(
			f'Error: Recording file not found at {recording_path}. Please ensure it exists.',
			fg=typer.colors.RED,
		)
		return None
	except Exception as e:
		typer.secho(f'Error loading recording: {e}', fg=typer.colors.RED)
		return None

	# Convert recording to semantic workflow format
	try:
		semantic_workflow = asyncio.run(_convert_recording_to_semantic_workflow(recording_data, description))
	except Exception as e:
		typer.secho(f'Error converting to semantic workflow: {e}', fg=typer.colors.RED)
		return None

	if not semantic_workflow:
		typer.secho(
			f'Failed to build semantic workflow definition from the {prompt_subject} recording.',
			fg=typer.colors.RED,
		)
		return None

	typer.secho('Semantic workflow built successfully!', fg=typer.colors.GREEN, bold=True)
	typer.echo()  # Add space

	file_stem = recording_path.stem
	if is_temp_recording:
		file_stem = file_stem.replace('temp_recording_', '') or 'recorded'

	default_workflow_filename = f'{file_stem}.semantic.workflow.json'
	workflow_output_name: str = typer.prompt(
		typer.style('Enter a name for the generated semantic workflow file', bold=True) + ' (e.g., my_search.semantic.workflow.json):',
		default=default_workflow_filename,
	)
	# Ensure the file name ends with .json
	if not workflow_output_name.endswith('.json'):
		workflow_output_name = f'{workflow_output_name}.json'
	final_workflow_path = output_dir / workflow_output_name

	try:
		with open(final_workflow_path, 'w') as f:
			json.dump(semantic_workflow, f, indent=2)
		typer.secho(
			f'Final semantic workflow saved to: {typer.style(str(final_workflow_path.resolve()), fg=typer.colors.BRIGHT_GREEN, bold=True)}',
			fg=typer.colors.GREEN,
		)
		return final_workflow_path
	except Exception as e:
		typer.secho(f'Error saving semantic workflow: {e}', fg=typer.colors.RED)
		return None


async def _convert_recording_to_semantic_workflow(recording_data, description):
	"""Convert a recorded workflow to semantic format using target_text fields."""
	from workflow_use.workflow.semantic_extractor import SemanticExtractor
	
	# Extract workflow metadata
	workflow_name = recording_data.get('name', 'Recorded Workflow')
	steps = recording_data.get('steps', [])
	
	if not steps:
		raise Exception("No steps found in recording")

	# Initialize semantic extractor
	semantic_extractor = SemanticExtractor()
	
	# Start browser to process pages
	playwright = await patchright_async_playwright().start()
	browser = Browser(playwright=playwright)
	
	semantic_steps = []
	current_url = None
	semantic_mapping = {}
	
	try:
		for step in steps:
			step_type = step.get('type', '').lower()
			
			if step_type == 'navigation':
				# Navigation step - extract semantic mapping for new page
				current_url = step.get('url')
				if current_url:
					semantic_steps.append({
						'description': f"Navigate to {current_url}",
						'type': 'navigation',
						'url': current_url
					})
					
					# Extract semantic mapping for this page
					try:
						page = await browser.get_current_page()
						await page.goto(current_url)
						await page.wait_for_load_state()
						semantic_mapping = await semantic_extractor.extract_semantic_mapping(page)
						typer.echo(f"Extracted {len(semantic_mapping)} semantic elements from {current_url}")
					except Exception as e:
						typer.echo(f"Warning: Could not extract semantic mapping from {current_url}: {e}")
						semantic_mapping = {}
			
			elif step_type in ['click', 'input', 'select', 'keypress']:
				# Interactive step - convert to semantic format
				semantic_step = await _convert_step_to_semantic(step, semantic_mapping)
				if semantic_step:
					semantic_steps.append(semantic_step)
			
			elif step_type == 'scroll':
				# Keep scroll steps as-is
				semantic_steps.append({
					'description': step.get('description', 'Scroll page'),
					'type': 'scroll',
					'scrollX': step.get('scrollX', 0),
					'scrollY': step.get('scrollY', 0)
				})
	
	finally:
		await browser.close()
		await playwright.stop()
	
	# Build the semantic workflow
	semantic_workflow = {
		'workflow_analysis': f'Semantic version of recorded workflow. Uses visible text to identify elements instead of CSS selectors for improved reliability.',
		'name': f'{workflow_name} (Semantic)',
		'description': description,
		'version': '1.0',
		'steps': semantic_steps,
		'input_schema': []  # Can be enhanced later with variable detection
	}
	
	return semantic_workflow


async def _convert_step_to_semantic(step, semantic_mapping):
	"""Convert a single recorded step to semantic format."""
	step_type = step.get('type', '').lower()
	description = step.get('description', '')
	
	# Try to find the best semantic target_text for this step
	target_text = None
	
	# Look for element text or other identifiers
	element_text = step.get('elementText', '').strip()
	css_selector = step.get('cssSelector', '')
	xpath = step.get('xpath', '')
	
	if element_text:
		# Try to find this text in our semantic mapping
		target_text = _find_best_semantic_match(element_text, semantic_mapping)
	
	# If no good semantic match, try to extract from CSS selector
	if not target_text and css_selector:
		target_text = _extract_target_from_selector(css_selector)
	
	# Build the semantic step
	semantic_step = {
		'description': description or f'{step_type.title()} element',
		'type': step_type
	}
	
	if target_text:
		semantic_step['target_text'] = target_text
	elif css_selector:
		# Fallback to original CSS selector if no semantic mapping available
		semantic_step['cssSelector'] = css_selector
	
	# Add step-specific fields
	if step_type == 'input' and 'value' in step:
		semantic_step['value'] = step['value']
	elif step_type == 'select' and 'selectedText' in step:
		semantic_step['selectedText'] = step['selectedText']
	elif step_type == 'keypress' and 'key' in step:
		semantic_step['key'] = step['key']
	
	return semantic_step


def _find_best_semantic_match(element_text, semantic_mapping):
	"""Find the best semantic match for element text."""
	if not element_text or not semantic_mapping:
		return None
	
	element_text_lower = element_text.lower().strip()
	
	# Exact match first
	for text_key in semantic_mapping.keys():
		if text_key.lower() == element_text_lower:
			return text_key
	
	# Partial match
	for text_key in semantic_mapping.keys():
		if element_text_lower in text_key.lower() or text_key.lower() in element_text_lower:
			return text_key
	
	# If no good match, return original text (the semantic executor will try to find it)
	return element_text


def _extract_target_from_selector(css_selector):
	"""Extract a target_text from CSS selector if possible."""
	if not css_selector:
		return None
	
	# Try to extract ID
	if '#' in css_selector:
		id_part = css_selector.split('#')[1].split('[')[0].split('.')[0]
		if id_part:
			return id_part
	
	# Try to extract name from attribute selector
	if '[name=' in css_selector:
		name_match = css_selector.split('[name=')[1].split(']')[0].strip('"\'')
		if name_match:
			return name_match
	
	return None


@app.command(
	name='create-workflow',
	help='Records a new browser interaction and then builds a workflow definition.',
)
def create_workflow():
	"""
	Guides the user through recording browser actions, then uses the helper
	to build and save the workflow definition.
	"""
	if not recording_service:
		# Adjusted RecordingService initialization check assuming it doesn't need LLM
		typer.secho(
			'RecordingService not available. Cannot create workflow.',
			fg=typer.colors.RED,
		)
		raise typer.Exit(code=1)

	default_tmp_dir = get_default_save_dir()  # Ensures ./tmp exists for temporary files

	typer.echo(typer.style('Starting interactive browser recording session...', bold=True))
	typer.echo('Please follow instructions in the browser. Close the browser or follow prompts to stop recording.')
	typer.echo()  # Add space

	temp_recording_path = None
	try:
		captured_recording_model = asyncio.run(recording_service.capture_workflow())

		if not captured_recording_model:
			typer.secho(
				'Recording session ended, but no workflow data was captured.',
				fg=typer.colors.YELLOW,
			)
			raise typer.Exit(code=1)

		typer.secho('Recording captured successfully!', fg=typer.colors.GREEN, bold=True)
		typer.echo()  # Add space

		with tempfile.NamedTemporaryFile(
			mode='w',
			suffix='.json',
			prefix='temp_recording_',
			delete=False,
			dir=default_tmp_dir,
			encoding='utf-8',
		) as tmp_file:
			try:
				tmp_file.write(captured_recording_model.model_dump_json(indent=2))
			except AttributeError:
				json.dump(captured_recording_model, tmp_file, indent=2)
			temp_recording_path = Path(tmp_file.name)

		# Use the helper function to build and save
		saved_path = _build_and_save_workflow_from_recording(temp_recording_path, default_tmp_dir, is_temp_recording=True)
		if not saved_path:
			typer.secho(
				'Failed to complete workflow creation after recording.',
				fg=typer.colors.RED,
			)
			raise typer.Exit(code=1)

	except Exception as e:
		typer.secho(f'An error occurred during workflow creation: {e}', fg=typer.colors.RED)
		raise typer.Exit(code=1)


@app.command(
	name='create-workflow-no-ai',
	help='Records a new browser interaction and builds a semantic workflow optimized for no-AI execution.',
)
def create_workflow_no_ai():
	"""
	Records browser actions and builds a semantic workflow using target_text fields 
	instead of CSS selectors, optimized for run-workflow-no-ai execution.
	"""
	if not recording_service:
		typer.secho(
			'RecordingService not available. Cannot create workflow.',
			fg=typer.colors.RED,
		)
		raise typer.Exit(code=1)

	default_tmp_dir = get_default_save_dir()

	typer.echo(typer.style('Starting semantic workflow recording session...', bold=True))
	typer.echo('🎯 This will create a workflow optimized for semantic execution (no AI required)!')
	typer.echo('Please follow instructions in the browser. Close the browser or follow prompts to stop recording.')
	typer.echo()  # Add space

	temp_recording_path = None
	try:
		captured_recording_model = asyncio.run(recording_service.capture_workflow())

		if not captured_recording_model:
			typer.secho(
				'Recording session ended, but no workflow data was captured.',
				fg=typer.colors.YELLOW,
			)
			raise typer.Exit(code=1)

		typer.secho('Recording captured successfully!', fg=typer.colors.GREEN, bold=True)
		typer.echo()  # Add space

		with tempfile.NamedTemporaryFile(
			mode='w',
			suffix='.json',
			prefix='temp_recording_',
			delete=False,
			dir=default_tmp_dir,
			encoding='utf-8',
		) as tmp_file:
			try:
				tmp_file.write(captured_recording_model.model_dump_json(indent=2))
			except AttributeError:
				json.dump(captured_recording_model, tmp_file, indent=2)
			temp_recording_path = Path(tmp_file.name)

		# Use the semantic workflow builder instead of the regular one
		saved_path = _build_and_save_semantic_workflow_from_recording(temp_recording_path, default_tmp_dir, is_temp_recording=True)
		if not saved_path:
			typer.secho(
				'Failed to complete semantic workflow creation after recording.',
				fg=typer.colors.RED,
			)
			raise typer.Exit(code=1)
		
		# Show next steps
		typer.echo()
		typer.secho('🎉 Semantic workflow created successfully!', fg=typer.colors.GREEN, bold=True)
		typer.echo()
		typer.echo(typer.style('Next steps:', bold=True))
		typer.echo(f'1. Test your workflow: {typer.style(f"python cli.py run-workflow-no-ai {saved_path.name}", fg=typer.colors.CYAN)}')
		typer.echo('2. Edit the workflow file to add variables or customize steps')
		typer.echo('3. The workflow uses visible text mappings for reliable execution!')

	except Exception as e:
		typer.secho(f'An error occurred during semantic workflow creation: {e}', fg=typer.colors.RED)
		raise typer.Exit(code=1)


@app.command(
	name='build-from-recording',
	help='Builds a workflow definition from an existing recording JSON file.',
)
def build_from_recording_command(
	recording_path: Path = typer.Argument(
		...,
		exists=True,
		file_okay=True,
		dir_okay=False,
		readable=True,
		resolve_path=True,
		help='Path to the existing recording JSON file.',
	),
):
	"""
	Takes a path to a recording JSON file, prompts for workflow details,
	builds the workflow using BuilderService, and saves it.
	"""
	default_save_dir = get_default_save_dir()
	typer.echo(
		typer.style(
			f'Building workflow from provided recording: {typer.style(str(recording_path.resolve()), fg=typer.colors.MAGENTA)}',
			bold=True,
		)
	)
	typer.echo()  # Add space

	saved_path = _build_and_save_workflow_from_recording(recording_path, default_save_dir, is_temp_recording=False)
	if not saved_path:
		typer.secho(f'Failed to build workflow from {recording_path.name}.', fg=typer.colors.RED)
		raise typer.Exit(code=1)


@app.command(
	name='build-semantic-from-recording',
	help='Builds a semantic workflow from an existing recording JSON file (optimized for no-AI execution).',
)
def build_semantic_from_recording_command(
	recording_path: Path = typer.Argument(
		...,
		exists=True,
		file_okay=True,
		dir_okay=False,
		readable=True,
		resolve_path=True,
		help='Path to the existing recording JSON file.',
	),
):
	"""
	Takes a path to a recording JSON file and builds a semantic workflow using target_text fields
	instead of CSS selectors, optimized for run-workflow-no-ai execution.
	"""
	default_save_dir = get_default_save_dir()
	typer.echo(
		typer.style(
			f'Building semantic workflow from recording: {typer.style(str(recording_path.resolve()), fg=typer.colors.MAGENTA)}',
			bold=True,
		)
	)
	typer.echo()  # Add space

	saved_path = _build_and_save_semantic_workflow_from_recording(recording_path, default_save_dir, is_temp_recording=False)
	if not saved_path:
		typer.secho(f'Failed to build semantic workflow from {recording_path.name}.', fg=typer.colors.RED)
		raise typer.Exit(code=1)
	
	# Show next steps
	typer.echo()
	typer.secho('🎉 Semantic workflow created successfully!', fg=typer.colors.GREEN, bold=True)
	typer.echo()
	typer.echo(typer.style('Next steps:', bold=True))
	typer.echo(f'1. Test your workflow: {typer.style(f"python cli.py run-workflow-no-ai {saved_path.name}", fg=typer.colors.CYAN)}')
	typer.echo('2. Edit the workflow file to add variables or customize steps')
	typer.echo('3. The workflow uses visible text mappings for reliable execution!')


@app.command(
	name='run-as-tool',
	help='Runs an existing workflow and automatically parse the required variables from prompt.',
)
def run_as_tool_command(
	workflow_path: Path = typer.Argument(
		...,
		exists=True,
		file_okay=True,
		dir_okay=False,
		readable=True,
		help='Path to the .workflow.json file.',
		show_default=False,
	),
	prompt: str = typer.Option(
		...,
		'--prompt',
		'-p',
		help='Prompt for the LLM to reason about and execute the workflow.',
		prompt=True,  # Prompts interactively if not provided
	),
):
	"""
	Run the workflow and automatically parse the required variables from the input/prompt that the user provides.
	"""
	if not llm_instance:
		typer.secho(
			'LLM not initialized. Please check your OpenAI API key. Cannot run as tool.',
			fg=typer.colors.RED,
		)
		raise typer.Exit(code=1)

	typer.echo(
		typer.style(f'Loading workflow from: {typer.style(str(workflow_path.resolve()), fg=typer.colors.MAGENTA)}', bold=True)
	)
	typer.echo()  # Add space

	try:
		# Pass llm_instance to ensure the workflow can use it if needed for as_tool() or run_with_prompt()
		workflow_obj = Workflow.load_from_file(str(workflow_path), llm=llm_instance, page_extraction_llm=page_extraction_llm)
	except Exception as e:
		typer.secho(f'Error loading workflow: {e}', fg=typer.colors.RED)
		raise typer.Exit(code=1)

	typer.secho('Workflow loaded successfully.', fg=typer.colors.GREEN, bold=True)
	typer.echo()  # Add space
	typer.echo(typer.style(f'Running workflow as tool with prompt: "{prompt}"', bold=True))

	try:
		result = asyncio.run(workflow_obj.run_as_tool(prompt))
		typer.secho('\nWorkflow execution completed!', fg=typer.colors.GREEN, bold=True)
		typer.echo(typer.style('Result:', bold=True))
		# Ensure result is JSON serializable for consistent output
		try:
			typer.echo(json.dumps(json.loads(result), indent=2))  # Assuming result from run_with_prompt is a JSON string
		except (json.JSONDecodeError, TypeError):
			typer.echo(result)  # Fallback to string if not a JSON string or not serializable
	except Exception as e:
		typer.secho(f'Error running workflow as tool: {e}', fg=typer.colors.RED)
		raise typer.Exit(code=1)


@app.command(name='run-workflow', help='Runs an existing workflow from a JSON file.')
def run_workflow_command(
	workflow_path: Path = typer.Argument(
		...,
		exists=True,
		file_okay=True,
		dir_okay=False,
		readable=True,
		help='Path to the .workflow.json file.',
		show_default=False,
	),
):
	"""
	Loads and executes a workflow, prompting the user for required inputs.
	"""

	async def _run_workflow():
		typer.echo(
			typer.style(f'Loading workflow from: {typer.style(str(workflow_path.resolve()), fg=typer.colors.MAGENTA)}', bold=True)
		)
		typer.echo()  # Add space

		try:
			# Instantiate Browser and WorkflowController for the Workflow instance
			# Pass llm_instance for potential agent fallbacks or agentic steps
			playwright = await patchright_async_playwright().start()

			browser = Browser(playwright=playwright)
			controller_instance = WorkflowController()  # Add any necessary config if required
			workflow_obj = Workflow.load_from_file(
				str(workflow_path),
				browser=browser,
				llm=llm_instance,
				controller=controller_instance,
				page_extraction_llm=page_extraction_llm,
			)
		except Exception as e:
			typer.secho(f'Error loading workflow: {e}', fg=typer.colors.RED)
			raise typer.Exit(code=1)

		typer.secho('Workflow loaded successfully.', fg=typer.colors.GREEN, bold=True)

		inputs = {}
		input_definitions = workflow_obj.inputs_def  # Access inputs_def from the Workflow instance

		if input_definitions:  # Check if the list is not empty
			typer.echo()  # Add space
			typer.echo(typer.style('Provide values for the following workflow inputs:', bold=True))
			typer.echo()  # Add space

			for input_def in input_definitions:
				var_name_styled = typer.style(input_def.name, fg=typer.colors.CYAN, bold=True)
				prompt_question = typer.style(f'Enter value for {var_name_styled}', bold=True)

				var_type = input_def.type.lower()  # type is a direct attribute
				is_required = input_def.required

				type_info_str = f'type: {var_type}'
				if is_required:
					status_str = typer.style('required', fg=typer.colors.RED)
				else:
					status_str = typer.style('optional', fg=typer.colors.YELLOW)

				# Add format information if available
				format_info_str = ''
				if hasattr(input_def, 'format') and input_def.format:
					format_info_str = f', format: {typer.style(input_def.format, fg=typer.colors.GREEN)}'

				full_prompt_text = f'{prompt_question} ({status_str}, {type_info_str}{format_info_str})'

				input_val = None
				if var_type == 'bool':
					input_val = typer.confirm(full_prompt_text)
				elif var_type == 'number':
					input_val = typer.prompt(full_prompt_text, type=float)
				elif var_type == 'string':  # Default to string for other unknown types as well
					input_val = typer.prompt(full_prompt_text, type=str)
				else:  # Should ideally not happen if schema is validated, but good to have a fallback
					typer.secho(
						f"Warning: Unknown type '{var_type}' for variable '{input_def.name}'. Treating as string.",
						fg=typer.colors.YELLOW,
					)
					input_val = typer.prompt(full_prompt_text, type=str)

				inputs[input_def.name] = input_val
				typer.echo()  # Add space after each prompt
		else:
			typer.echo('No input schema found in the workflow, or no properties defined. Proceeding without inputs.')

		typer.echo()  # Add space
		typer.echo(typer.style('Running workflow...', bold=True))

		try:
			# Call run on the Workflow instance
			# close_browser_at_end=True is the default for Workflow.run, but explicit for clarity
			result = await workflow_obj.run(inputs=inputs, close_browser_at_end=True)

			typer.secho('\nWorkflow execution completed!', fg=typer.colors.GREEN, bold=True)
			typer.echo(typer.style('Result:', bold=True))
			# Output the number of steps executed, similar to previous behavior
			typer.echo(f'{typer.style(str(len(result.step_results)), bold=True)} steps executed.')
			# For more detailed results, one might want to iterate through the 'result' list
			# and print each item, or serialize the whole list to JSON.
			# For now, sticking to the step count as per original output.

		except Exception as e:
			typer.secho(f'Error running workflow: {e}', fg=typer.colors.RED)
			raise typer.Exit(code=1)

	return asyncio.run(_run_workflow())


@app.command(name='run-workflow-no-ai', help='Runs an existing workflow without AI using semantic abstraction.')
def run_workflow_no_ai_command(
	workflow_path: Path = typer.Argument(
		...,
		exists=True,
		file_okay=True,
		dir_okay=False,
		readable=True,
		help='Path to the .workflow.json file.',
		show_default=False,
	),
):
	"""
	Loads and executes a workflow using semantic abstraction without any AI/LLM involvement.
	This uses visible text mappings to deterministic selectors instead of fragile CSS selectors.
	"""

	async def _run_workflow_no_ai():
		typer.echo(
			typer.style(f'Loading workflow from: {typer.style(str(workflow_path.resolve()), fg=typer.colors.MAGENTA)}', bold=True)
		)
		typer.echo()  # Add space

		try:
			# Instantiate Browser for the Workflow instance
			# No LLM needed for semantic abstraction approach
			playwright = await patchright_async_playwright().start()

			browser = Browser(playwright=playwright)
			# Create a dummy LLM instance since it's required by the constructor but won't be used
			dummy_llm = None
			try:
				from langchain_openai import ChatOpenAI
				dummy_llm = ChatOpenAI(model='gpt-4o-mini')
			except:
				# If OpenAI is not available, we'll handle it gracefully
				pass
			
			workflow_obj = Workflow.load_from_file(
				str(workflow_path),
				browser=browser,
				llm=dummy_llm,  # Won't be used in run_with_no_ai
			)
		except Exception as e:
			typer.secho(f'Error loading workflow: {e}', fg=typer.colors.RED)
			raise typer.Exit(code=1)

		typer.secho('Workflow loaded successfully.', fg=typer.colors.GREEN, bold=True)
		typer.secho('Using semantic abstraction mode (no AI/LLM).', fg=typer.colors.BLUE, bold=True)

		inputs = {}
		input_definitions = workflow_obj.inputs_def  # Access inputs_def from the Workflow instance

		if input_definitions:  # Check if the list is not empty
			typer.echo()  # Add space
			typer.echo(typer.style('Provide values for the following workflow inputs:', bold=True))
			typer.echo()  # Add space

			for input_def in input_definitions:
				var_name_styled = typer.style(input_def.name, fg=typer.colors.CYAN, bold=True)
				prompt_question = typer.style(f'Enter value for {var_name_styled}', bold=True)

				var_type = input_def.type.lower()  # type is a direct attribute
				is_required = input_def.required

				type_info_str = f'type: {var_type}'
				if is_required:
					status_str = typer.style('required', fg=typer.colors.RED)
				else:
					status_str = typer.style('optional', fg=typer.colors.YELLOW)

				# Add format information if available
				format_info_str = ''
				if hasattr(input_def, 'format') and input_def.format:
					format_info_str = f', format: {typer.style(input_def.format, fg=typer.colors.GREEN)}'

				full_prompt_text = f'{prompt_question} ({status_str}, {type_info_str}{format_info_str})'

				input_val = None
				if var_type == 'bool':
					input_val = typer.confirm(full_prompt_text)
				elif var_type == 'number':
					input_val = typer.prompt(full_prompt_text, type=float)
				elif var_type == 'string':  # Default to string for other unknown types as well
					input_val = typer.prompt(full_prompt_text, type=str)
				else:  # Should ideally not happen if schema is validated, but good to have a fallback
					typer.secho(
						f"Warning: Unknown type '{var_type}' for variable '{input_def.name}'. Treating as string.",
						fg=typer.colors.YELLOW,
					)
					input_val = typer.prompt(full_prompt_text, type=str)

				inputs[input_def.name] = input_val
				typer.echo()  # Add space after each prompt
		else:
			typer.echo('No input schema found in the workflow, or no properties defined. Proceeding without inputs.')

		typer.echo()  # Add space
		typer.echo(typer.style('Running workflow with semantic abstraction (no AI)...', bold=True))

		try:
			# Call run_with_no_ai on the Workflow instance
			result = await workflow_obj.run_with_no_ai(inputs=inputs, close_browser_at_end=False)

			typer.secho('\nWorkflow execution completed!', fg=typer.colors.GREEN, bold=True)
			typer.echo(typer.style('Result:', bold=True))
			# Output the number of steps executed
			typer.echo(f'{typer.style(str(len(result.step_results)), bold=True)} steps executed using semantic abstraction.')

		except Exception as e:
			typer.secho(f'Error running workflow: {e}', fg=typer.colors.RED)
			raise typer.Exit(code=1)

	return asyncio.run(_run_workflow_no_ai())


@app.command(name='generate-semantic-mapping', help='Generate semantic mapping for a URL to help with workflow creation.')
def generate_semantic_mapping_command(
	url: str = typer.Argument(..., help='URL to generate semantic mapping for'),
	output_file: Path = typer.Option(
		None,
		'--output',
		'-o',
		help='Output file to save the semantic mapping (optional)',
	),
):
	"""
	Generate a semantic mapping for a given URL to help with creating workflows.
	This shows how visible text maps to selectors.
	"""

	async def _generate_mapping():
		typer.echo(typer.style(f'Generating semantic mapping for: {url}', bold=True))
		typer.echo()

		try:
			from workflow_use.workflow.semantic_extractor import SemanticExtractor
			from browser_use import Browser
			from patchright.async_api import async_playwright as patchright_async_playwright

			playwright = await patchright_async_playwright().start()
			browser = Browser(playwright=playwright)
			extractor = SemanticExtractor()

			await browser.start()
			page = await browser.get_current_page()
			await page.goto(url)
			await page.wait_for_load_state()

			# Generate semantic mapping
			mapping = await extractor.extract_semantic_mapping(page)

			typer.secho(f'Found {len(mapping)} interactive elements', fg=typer.colors.GREEN, bold=True)
			typer.echo()

			# Display mapping
			typer.echo(typer.style('=== SEMANTIC MAPPING ===', bold=True))
			typer.echo()

			for text, element_info in mapping.items():
				element_type = element_info['element_type']
				selector = element_info['selectors']
				class_name = element_info['class']
				element_id = element_info['id']
				
				# Color code by element type
				if element_type == 'button':
					text_color = typer.colors.GREEN
				elif element_type == 'input':
					text_color = typer.colors.BLUE
				elif element_type == 'select':
					text_color = typer.colors.MAGENTA
				else:
					text_color = typer.colors.CYAN

				typer.echo(f'{typer.style(text, fg=text_color, bold=True)}')
				typer.echo(f'  Type: {element_type}')
				typer.echo(f'  Class: {class_name or "(none)"}')
				typer.echo(f'  ID: {element_id or "(none)"}')
				typer.echo(f'  Selector: {selector}')
				typer.echo()

			# Save to file if requested
			if output_file:
				output_data = {}
				for text, element_info in mapping.items():
					output_data[text] = {
						'class': element_info['class'],
						'id': element_info['id'], 
						'selectors': element_info['selectors']
					}

				with open(output_file, 'w') as f:
					import json
					json.dump(output_data, f, indent=2)

				typer.secho(f'Semantic mapping saved to: {output_file}', fg=typer.colors.GREEN)

			await browser.close()

		except Exception as e:
			typer.secho(f'Error generating semantic mapping: {e}', fg=typer.colors.RED)
			raise typer.Exit(code=1)

	return asyncio.run(_generate_mapping())


@app.command(name='create-semantic-workflow', help='Create a workflow template using semantic text mapping.')
def create_semantic_workflow_command(
	url: str = typer.Argument(..., help='URL to create workflow for'),
	output_file: Path = typer.Option(
		None,
		'--output',
		'-o',
		help='Output workflow file (defaults to semantic_workflow.json)',
	),
):
	"""
	Create a workflow template using semantic text mapping for a given URL.
	This generates a template that users can customize.
	"""

	async def _create_semantic_workflow():
		output_path = output_file or Path('semantic_workflow.json')
		
		typer.echo(typer.style(f'Creating semantic workflow for: {url}', bold=True))
		typer.echo()

		try:
			from workflow_use.workflow.semantic_extractor import SemanticExtractor
			from browser_use import Browser
			from patchright.async_api import async_playwright as patchright_async_playwright

			playwright = await patchright_async_playwright().start()
			browser = Browser(playwright=playwright)
			extractor = SemanticExtractor()

			await browser.start()
			page = await browser.get_current_page()
			await page.goto(url)
			await page.wait_for_load_state()

			# Generate semantic mapping
			mapping = await extractor.extract_semantic_mapping(page)

			typer.secho(f'Found {len(mapping)} interactive elements', fg=typer.colors.GREEN, bold=True)
			typer.echo()

			# Show available elements
			typer.echo(typer.style('Available elements for workflow:', bold=True))
			for i, (text, element_info) in enumerate(mapping.items(), 1):
				element_type = element_info['element_type']
				
				# Color code by element type
				if element_type == 'button':
					text_color = typer.colors.GREEN
				elif element_type == 'input':
					text_color = typer.colors.BLUE
				elif element_type == 'select':
					text_color = typer.colors.MAGENTA
				else:
					text_color = typer.colors.CYAN

				typer.echo(f'{i:2}. {typer.style(text, fg=text_color)} ({element_type})')

			typer.echo()

			# Create basic workflow template
			workflow_name = typer.prompt('Enter workflow name', default='Semantic Workflow')
			workflow_description = typer.prompt('Enter workflow description', default='Automated workflow using semantic text mapping')

			# Create template workflow
			template = {
				"workflow_analysis": f"Semantic workflow for {url}. Uses visible text to identify elements instead of CSS selectors.",
				"name": workflow_name,
				"description": workflow_description,
				"version": "1.0",
				"steps": [
					{
						"description": f"Navigate to {url}",
						"type": "navigation",
						"url": url
					}
				],
				"input_schema": []
			}

			# Add some example steps as comments in the JSON
			example_steps = []
			for text, element_info in list(mapping.items())[:5]:  # Show first 5 elements as examples
				element_type = element_info['element_type']
				
				if element_type == 'button':
					example_steps.append({
						"description": f"Click {text}",
						"type": "click",
						"target_text": text,
						"_comment": "Remove this line - it's just an example"
					})
				elif element_type == 'input':
					example_steps.append({
						"description": f"Enter value into {text}",
						"type": "input", 
						"target_text": text,
						"value": "{variable_name}",
						"_comment": "Remove this line - it's just an example. Replace {variable_name} with actual variable."
					})

			template["example_steps_to_customize"] = example_steps

			# Save template
			with open(output_path, 'w') as f:
				import json
				json.dump(template, f, indent=2)

			typer.secho(f'Workflow template created: {output_path}', fg=typer.colors.GREEN, bold=True)
			typer.echo()
			typer.echo(typer.style('Next steps:', bold=True))
			typer.echo('1. Edit the workflow file to add your specific steps')
			typer.echo('2. Use target_text field to reference visible text')
			typer.echo('3. Add input_schema for dynamic values')
			typer.echo('4. Test with: python cli.py run-workflow-no-ai your_workflow.json')

			await browser.close()

		except Exception as e:
			typer.secho(f'Error creating semantic workflow: {e}', fg=typer.colors.RED)
			raise typer.Exit(code=1)

	return asyncio.run(_create_semantic_workflow())


@app.command(name='mcp-server', help='Starts the MCP server which expose all the created workflows as tools.')
def mcp_server_command(
	port: int = typer.Option(
		8008,
		'--port',
		'-p',
		help='Port to run the MCP server on.',
	),
):
	"""
	Starts the MCP server which expose all the created workflows as tools.
	"""
	typer.echo(typer.style('Starting MCP server...', bold=True))
	typer.echo()  # Add space

	llm_instance = ChatOpenAI(model='gpt-4o')
	page_extraction_llm = ChatOpenAI(model='gpt-4o-mini')

	mcp = get_mcp_server(llm_instance, page_extraction_llm=page_extraction_llm, workflow_dir='./tmp')

	mcp.run(
		transport='sse',
		host='0.0.0.0',
		port=port,
	)


@app.command('launch-gui', help='Launch the workflow visualizer GUI.')
def launch_gui():
	"""Launch the workflow visualizer GUI."""
	typer.echo(typer.style('Launching workflow visualizer GUI...', bold=True))

	logs_dir = Path('./tmp/logs')
	logs_dir.mkdir(parents=True, exist_ok=True)
	backend_log = open(logs_dir / 'backend.log', 'w')
	frontend_log = open(logs_dir / 'frontend.log', 'w')

	backend = subprocess.Popen(['uvicorn', 'backend.api:app', '--reload'], stdout=backend_log, stderr=subprocess.STDOUT)
	typer.echo(typer.style('Starting frontend...', bold=True))
	frontend = subprocess.Popen(['npm', 'run', 'dev'], cwd='../ui', stdout=frontend_log, stderr=subprocess.STDOUT)
	typer.echo(typer.style('Opening browser...', bold=True))
	webbrowser.open('http://localhost:5173')
	try:
		typer.echo(typer.style('Press Ctrl+C to stop the GUI and servers.', fg=typer.colors.YELLOW, bold=True))
		backend.wait()
		frontend.wait()
	except KeyboardInterrupt:
		typer.echo(typer.style('\nShutting down servers...', fg=typer.colors.RED, bold=True))
		backend.terminate()
		frontend.terminate()


if __name__ == '__main__':
	app()
