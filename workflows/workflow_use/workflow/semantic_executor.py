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
            if await self._wait_for_element(selector):
                logger.info(f"Found element using direct selector: {selector}")
                return selector
        
        return None
    
    async def _wait_for_element(self, selector: str, timeout_ms: int = 5000) -> bool:
        """Wait for element to be available."""
        try:
            page = await self.browser.get_current_page()
            await page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
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
        
        locator = page.locator(selector_to_use)
        await locator.click(force=True)
        
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
        
        # Check if it's a SELECT element
        is_select = await locator.evaluate('(el) => el.tagName === "SELECT"')
        if is_select:
            return ActionResult(
                extracted_content='Ignored input into select element',
                include_in_memory=True,
            )
        
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