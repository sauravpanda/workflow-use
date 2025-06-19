import asyncio
import logging
from typing import Any, Dict, Optional
from playwright.async_api import Page

from browser_use import Browser
from browser_use.agent.views import ActionResult
from workflow_use.schema.views import (
    ClickStep,
    InputStep,
    KeyPressStep,
    NavigationStep,
    ScrollStep,
    SelectChangeStep,
    WorkflowStep,
)
from workflow_use.workflow.semantic_extractor import SemanticExtractor

logger = logging.getLogger(__name__)


class SemanticWorkflowExecutor:
    """Executes workflow steps using semantic mappings without AI/LLM involvement."""
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self.semantic_extractor = SemanticExtractor()
        self.current_mapping: Dict[str, Dict] = {}
    
    async def _refresh_semantic_mapping(self) -> None:
        """Refresh the semantic mapping for the current page."""
        page = await self.browser.get_current_page()
        self.current_mapping = await self.semantic_extractor.extract_semantic_mapping(page)
        logger.info(f"Refreshed semantic mapping with {len(self.current_mapping)} elements")
    
    def _find_element_by_text(self, target_text: str) -> Optional[Dict]:
        """Find element by visible text using semantic mapping."""
        if not target_text:
            return None
        
        return self.semantic_extractor.find_element_by_text(self.current_mapping, target_text)
    
    async def _try_direct_selector(self, target_text: str) -> Optional[str]:
        """Try to use target_text as a direct selector (ID or name)."""
        if not target_text or not target_text.replace('_', '').replace('-', '').isalnum():
            return None
        
        # Try as ID first, then name attribute
        selectors_to_try = [
            f"#{target_text}",
            f"[name='{target_text}']",
            f"[id='{target_text}']"
        ]
        
        for selector in selectors_to_try:
            try:
                page = await self.browser.get_current_page()
                await page.wait_for_selector(selector, timeout=5000, state="visible")
                
                # Check if this selector resolves to multiple elements (strict mode violation)
                elements = await page.query_selector_all(selector)
                if len(elements) > 1:
                    logger.warning(f"Selector {selector} matches {len(elements)} elements, skipping direct selector")
                    continue
                
                logger.info(f"Found element using direct selector: {selector}")
                return selector
            except Exception as e:
                logger.warning(f"Element not found with selector {selector}: {e}")
                continue
        
        return None

    async def _handle_strict_mode_violation(self, selector: str, target_text: str = None) -> Optional[str]:
        """Handle cases where selector matches multiple elements."""
        page = await self.browser.get_current_page()
        
        try:
            elements = await page.query_selector_all(selector)
            if len(elements) <= 1:
                return selector  # No violation
            
            logger.warning(f"Selector {selector} matches {len(elements)} elements, trying to narrow down...")
            
            # For radio buttons, try to be more specific
            if "radio" in selector.lower():
                # Try to find radio button by value if target_text looks like a value
                if target_text:
                    value_selector = f'input[type="radio"][value="{target_text.lower()}"]'
                    try:
                        await page.wait_for_selector(value_selector, timeout=2000, state="visible")
                        value_elements = await page.query_selector_all(value_selector)
                        if len(value_elements) == 1:
                            logger.info(f"Found specific radio button by value: {value_selector}")
                            return value_selector
                    except:
                        pass
                    
                    # Try to find by label text
                    try:
                        label_locator = page.get_by_label(target_text, exact=False)
                        count = await label_locator.count()
                        if count == 1:
                            logger.info(f"Found radio button by label: {target_text}")
                            return f"xpath=//label[contains(text(), '{target_text}')]//input[@type='radio'] | //input[@type='radio' and @id=(//label[contains(text(), '{target_text}')]/@for)]"
                    except:
                        pass
                
                # For radio buttons, cannot resolve automatically, let the calling code handle it
                logger.warning(f"Cannot automatically resolve radio button selector, returning None")
                return None
            
            # For other elements, cannot resolve automatically either
            logger.warning(f"Cannot automatically resolve selector, returning None")
            return None
            
        except Exception as e:
            logger.error(f"Error handling strict mode violation: {e}")
            return None
    
    async def _wait_for_element(self, selector: str, timeout_ms: int = 5000) -> bool:
        """Wait for element to be available."""
        try:
            page = await self.browser.get_current_page()
            await page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
            
            # Check if the selector would cause strict mode violations
            elements = await page.query_selector_all(selector)
            if len(elements) > 1:
                logger.warning(f"Selector {selector} matches {len(elements)} elements during wait")
                return True  # Element exists, but we'll handle the strict mode later
            
            return True
        except Exception as e:
            logger.warning(f"Element not found with selector {selector}: {e}")
            return False
    
    async def execute_navigation_step(self, step: NavigationStep) -> ActionResult:
        """Execute navigation step."""
        page = await self.browser.get_current_page()
        await page.goto(step.url)
        await page.wait_for_load_state()
        
        # Refresh semantic mapping after navigation
        await self._refresh_semantic_mapping()
        
        msg = f"🔗 Navigated to URL: {step.url}"
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)
    
    async def execute_click_step(self, step: ClickStep) -> ActionResult:
        """Execute click step using semantic mapping."""
        page = await self.browser.get_current_page()
        
        # Try to find element using multiple strategies (prioritize target_text)
        element_info = None
        target_identifier = None
        selector_to_use = None
        
        if hasattr(step, 'target_text') and step.target_text:
            target_identifier = step.target_text
            
            # Try direct selector first (for ID/name attributes)
            selector_to_use = await self._try_direct_selector(step.target_text)
            
            # If direct selector fails, try semantic mapping
            if not selector_to_use:
                element_info = self._find_element_by_text(step.target_text)
                if element_info:
                    selector_to_use = element_info['selectors']
                    logger.info(f"Using semantic mapping: '{target_identifier}' -> {selector_to_use}")
                    
        elif step.description:
            target_identifier = step.description
            element_info = self._find_element_by_text(step.description)
            if element_info:
                selector_to_use = element_info['selectors']
                logger.info(f"Using semantic mapping: '{target_identifier}' -> {selector_to_use}")
        
        # Final fallback to original CSS selector
        if not selector_to_use:
            if step.cssSelector:
                selector_to_use = step.cssSelector
                logger.info(f"Falling back to original CSS selector: {selector_to_use}")
            else:
                raise Exception(f"No selector available for click step: {target_identifier or step.description}")
        
        # Wait for element and click - try fallbacks if main selector fails
        if not await self._wait_for_element(selector_to_use):
            # Try fallback selector if available
            if element_info and 'fallback_selector' in element_info:
                fallback_selector = element_info['fallback_selector']
                logger.info(f"Main selector failed, trying fallback: {fallback_selector}")
                if await self._wait_for_element(fallback_selector):
                    selector_to_use = fallback_selector
                elif element_info.get('text_xpath'):
                    # Try XPath as final fallback
                    xpath_selector = element_info['text_xpath']
                    logger.info(f"CSS fallback failed, trying XPath: {xpath_selector}")
                    try:
                        page = await self.browser.get_current_page()
                        await page.wait_for_selector(f"xpath={xpath_selector}", timeout=2000)
                        selector_to_use = f"xpath={xpath_selector}"
                    except:
                        raise Exception(f"Element not found with any selector. Main: {selector_to_use}, Fallback: {fallback_selector}, XPath: {xpath_selector}")
                else:
                    raise Exception(f"Element not found with main selector: {selector_to_use} or fallback: {fallback_selector}")
            else:
                raise Exception(f"Element not found: {selector_to_use}")
        
        # Try to click the element, with fallback to nth(0) if strict mode violation occurs
        try:
            locator = page.locator(selector_to_use)
            await locator.click(force=True)
        except Exception as click_error:
            if "strict mode violation" in str(click_error).lower():
                logger.warning(f"Strict mode violation during click, using first element: {click_error}")
                first_locator = page.locator(selector_to_use).nth(0)
                await first_locator.click(force=True)
                msg = f"🖱️ Clicked element (first match due to strict mode): {target_identifier or step.description or selector_to_use}"
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            else:
                raise click_error
        
        msg = f"🖱️ Clicked element: {target_identifier or step.description or selector_to_use}"
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)
    
    async def execute_input_step(self, step: InputStep) -> ActionResult:
        """Execute input step using semantic mapping."""
        page = await self.browser.get_current_page()
        
        # Try to find element using multiple strategies (prioritize target_text)
        element_info = None
        target_identifier = None
        selector_to_use = None
        
        if hasattr(step, 'target_text') and step.target_text:
            target_identifier = step.target_text
            
            # Try direct selector first (for ID/name attributes)
            selector_to_use = await self._try_direct_selector(step.target_text)
            
            # If direct selector fails, try semantic mapping
            if not selector_to_use:
                element_info = self._find_element_by_text(step.target_text)
                if element_info:
                    selector_to_use = element_info['selectors']
                    logger.info(f"Using semantic mapping: '{target_identifier}' -> {selector_to_use}")
                    
        elif step.description:
            target_identifier = step.description
            element_info = self._find_element_by_text(step.description)
            if element_info:
                selector_to_use = element_info['selectors']
                logger.info(f"Using semantic mapping: '{target_identifier}' -> {selector_to_use}")
        
        # Final fallback to original CSS selector
        if not selector_to_use:
            if step.cssSelector:
                selector_to_use = step.cssSelector
                logger.info(f"Falling back to original CSS selector: {selector_to_use}")
            else:
                raise Exception(f"No selector available for input step: {target_identifier or step.description}")
        
        # Wait for element and input text - try fallbacks if main selector fails
        if not await self._wait_for_element(selector_to_use):
            # Try fallback selector if available
            if element_info and 'fallback_selector' in element_info:
                fallback_selector = element_info['fallback_selector']
                logger.info(f"Main selector failed, trying fallback: {fallback_selector}")
                if await self._wait_for_element(fallback_selector):
                    selector_to_use = fallback_selector
                elif element_info.get('text_xpath'):
                    # Try XPath as final fallback
                    xpath_selector = element_info['text_xpath']
                    logger.info(f"CSS fallback failed, trying XPath: {xpath_selector}")
                    try:
                        page = await self.browser.get_current_page()
                        await page.wait_for_selector(f"xpath={xpath_selector}", timeout=2000)
                        selector_to_use = f"xpath={xpath_selector}"
                    except:
                        raise Exception(f"Element not found with any selector. Main: {selector_to_use}, Fallback: {fallback_selector}, XPath: {xpath_selector}")
                else:
                    raise Exception(f"Element not found with main selector: {selector_to_use} or fallback: {fallback_selector}")
            else:
                raise Exception(f"Element not found: {selector_to_use}")
        
        locator = page.locator(selector_to_use)
        
        # Check element type to handle different input types properly
        element_type = await locator.evaluate('(el) => ({ tagName: el.tagName, type: el.type, value: el.value })')
        
        if element_type['tagName'] == 'SELECT':
            return ActionResult(
                extracted_content='Ignored input into select element',
                include_in_memory=True,
            )
        
        # Handle radio buttons and checkboxes
        if element_type['type'] in ['radio', 'checkbox']:
            # For radio buttons, find the one with matching value
            if element_type['type'] == 'radio':
                # Use a more specific selector that includes the value
                name_attr = await locator.get_attribute('name')
                if name_attr:
                    radio_selector = f'input[name="{name_attr}"][value="{step.value}"]'
                    radio_locator = page.locator(radio_selector)
                    if await self._wait_for_element(radio_selector, 2000):
                        await radio_locator.click(force=True)
                        msg = f"🔘 Selected radio button '{step.value}' for: {target_identifier or step.description}"
                        logger.info(msg)
                        return ActionResult(extracted_content=msg, include_in_memory=True)
                    else:
                        # Fallback: look for label text that matches the value
                        try:
                            radio_by_label = page.get_by_label(step.value)
                            await radio_by_label.click(force=True)
                            msg = f"🔘 Selected radio button by label '{step.value}' for: {target_identifier or step.description}"
                            logger.info(msg)
                            return ActionResult(extracted_content=msg, include_in_memory=True)
                        except:
                            pass
            
            # For checkboxes, check if we want to check or uncheck
            elif element_type['type'] == 'checkbox':
                should_check = step.value.lower() in ['true', '1', 'on', 'yes', 'checked']
                is_checked = await locator.is_checked()
                
                if should_check and not is_checked:
                    await locator.check(force=True)
                    msg = f"☑️ Checked checkbox: {target_identifier or step.description}"
                elif not should_check and is_checked:
                    await locator.uncheck(force=True)
                    msg = f"☐ Unchecked checkbox: {target_identifier or step.description}"
                else:
                    msg = f"✓ Checkbox already in desired state: {target_identifier or step.description}"
                
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
        
        # Regular input handling for text fields, etc.
        await locator.fill(step.value)
        await asyncio.sleep(0.5)
        await locator.click(force=True)
        await asyncio.sleep(0.5)
        
        msg = f"⌨️ Input '{step.value}' into: {target_identifier or step.description or selector_to_use}"
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)
    
    async def execute_select_step(self, step: SelectChangeStep) -> ActionResult:
        """Execute select dropdown step using semantic mapping."""
        page = await self.browser.get_current_page()
        
        # Try to find element using semantic mapping first (prioritize target_text)
        element_info = None
        target_identifier = None
        
        if hasattr(step, 'target_text') and step.target_text:
            target_identifier = step.target_text
            element_info = self._find_element_by_text(step.target_text)
        elif step.description:
            target_identifier = step.description
            element_info = self._find_element_by_text(step.description)
        
        # Fallback to original CSS selector if semantic mapping fails
        selector_to_use = None
        if element_info:
            selector_to_use = element_info['selectors']
            logger.info(f"Using semantic mapping: '{target_identifier}' -> {selector_to_use}")
        elif step.cssSelector:
            selector_to_use = step.cssSelector
            logger.info(f"Falling back to original CSS selector: {selector_to_use}")
        else:
            raise Exception(f"No selector available for select step: {target_identifier or step.description}")
        
        # Wait for element and select option
        if not await self._wait_for_element(selector_to_use):
            raise Exception(f"Element not found: {selector_to_use}")
        
        locator = page.locator(selector_to_use)
        await locator.select_option(label=step.selectedText)
        
        msg = f"🔽 Selected '{step.selectedText}' in: {target_identifier or step.description or selector_to_use}"
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)
    
    async def execute_key_press_step(self, step: KeyPressStep) -> ActionResult:
        """Execute key press step using semantic mapping."""
        page = await self.browser.get_current_page()
        
        # Try to find element using semantic mapping first (prioritize target_text)
        element_info = None
        target_identifier = None
        
        if hasattr(step, 'target_text') and step.target_text:
            target_identifier = step.target_text
            element_info = self._find_element_by_text(step.target_text)
        elif step.description:
            target_identifier = step.description
            element_info = self._find_element_by_text(step.description)
        
        # Fallback to original CSS selector if semantic mapping fails
        selector_to_use = None
        if element_info:
            selector_to_use = element_info['selectors']
            logger.info(f"Using semantic mapping: '{target_identifier}' -> {selector_to_use}")
        elif step.cssSelector:
            selector_to_use = step.cssSelector
            logger.info(f"Falling back to original CSS selector: {selector_to_use}")
        else:
            raise Exception(f"No selector available for key press step: {target_identifier or step.description}")
        
        # Wait for element and press key
        if not await self._wait_for_element(selector_to_use):
            raise Exception(f"Element not found: {selector_to_use}")
        
        locator = page.locator(selector_to_use)
        await locator.press(step.key)
        
        msg = f"🔑 Pressed key '{step.key}' on: {target_identifier or step.description or selector_to_use}"
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)
    
    async def execute_scroll_step(self, step: ScrollStep) -> ActionResult:
        """Execute scroll step."""
        page = await self.browser.get_current_page()
        await page.evaluate(f"window.scrollBy({step.scrollX}, {step.scrollY})")
        
        msg = f"📜 Scrolled by ({step.scrollX}, {step.scrollY})"
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)
    
    async def execute_step(self, step: WorkflowStep) -> ActionResult:
        """Execute a single workflow step."""
        try:
            if isinstance(step, NavigationStep):
                return await self.execute_navigation_step(step)
            elif isinstance(step, ClickStep):
                return await self.execute_click_step(step)
            elif isinstance(step, InputStep):
                return await self.execute_input_step(step)
            elif isinstance(step, SelectChangeStep):
                return await self.execute_select_step(step)
            elif isinstance(step, KeyPressStep):
                return await self.execute_key_press_step(step)
            elif isinstance(step, ScrollStep):
                return await self.execute_scroll_step(step)
            else:
                raise Exception(f"Unsupported step type: {step.type}")
        
        except Exception as e:
            logger.error(f"Step execution failed: {e}")
            # Try to refresh semantic mapping on failure and retry once
            try:
                await self._refresh_semantic_mapping()
                logger.info("Retrying step after refreshing semantic mapping...")
                
                if isinstance(step, NavigationStep):
                    return await self.execute_navigation_step(step)
                elif isinstance(step, ClickStep):
                    return await self.execute_click_step(step)
                elif isinstance(step, InputStep):
                    return await self.execute_input_step(step)
                elif isinstance(step, SelectChangeStep):
                    return await self.execute_select_step(step)
                elif isinstance(step, KeyPressStep):
                    return await self.execute_key_press_step(step)
                elif isinstance(step, ScrollStep):
                    return await self.execute_scroll_step(step)
                else:
                    raise Exception(f"Unsupported step type: {step.type}")
            except Exception as retry_error:
                logger.error(f"Step execution failed on retry: {retry_error}")
                raise retry_error
    
    async def print_semantic_mapping(self) -> None:
        """Print current semantic mapping for debugging."""
        if not self.current_mapping:
            await self._refresh_semantic_mapping()
        
        logger.info("=== Current Semantic Mapping ===")
        for text, element_info in self.current_mapping.items():
            logger.info(f"'{text}' -> {element_info['deterministic_id']} ({element_info['selectors']})")
        logger.info("=== End Semantic Mapping ===") 