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
    
    def __init__(self, browser: Browser, max_retries: int = 3, max_global_failures: int = 5, max_verification_failures: int = 3):
        self.browser = browser
        self.semantic_extractor = SemanticExtractor()
        self.current_mapping: Dict[str, Dict] = {}
        self.max_retries = max_retries
        self.max_global_failures = max_global_failures
        self.max_verification_failures = max_verification_failures
        self.global_failure_count = 0
        self.consecutive_failures = 0
        self.consecutive_verification_failures = 0
        self.last_successful_step = None
    
    async def _refresh_semantic_mapping(self) -> None:
        """Refresh the semantic mapping for the current page."""
        page = await self.browser.get_current_page()
        self.current_mapping = await self.semantic_extractor.extract_semantic_mapping(page)
        logger.info(f"Refreshed semantic mapping with {len(self.current_mapping)} elements")
        
        # Print detailed mapping for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("=== Current Semantic Mapping ===")
            for text, element_info in self.current_mapping.items():
                logger.debug(f"'{text}' -> {element_info['selectors']} (fallback: {element_info.get('fallback_selector', 'none')})")
            logger.debug("=== End Semantic Mapping ===")
       
    def _find_element_by_text(self, target_text: str) -> Optional[Dict]:
        """Find element by visible text using semantic mapping with improved fallback strategies."""
        if not target_text:
            return None
        
        # Try the semantic extractor's find method first
        element_info = self.semantic_extractor.find_element_by_text(self.current_mapping, target_text)
        if element_info:
            return element_info
        
        # Enhanced fallback strategies
        target_lower = target_text.lower()
        
        # Try partial matches with different strategies
        for text, element_info in self.current_mapping.items():
            text_lower = text.lower()
            
            # Check if target text is contained in element text (more lenient)
            if target_lower in text_lower or text_lower in target_lower:
                # For radio buttons and checkboxes, be more specific
                if element_info.get('element_type') in ['radio', 'checkbox']:
                    # Check if the target text matches the value or is close to the label
                    element_value = element_info.get('selectors', '')
                    if 'value=' in element_value and target_lower in element_value.lower():
                        logger.info(f"Found radio/checkbox by value match: '{target_text}' -> {element_info['selectors']}")
                        return element_info
                
                # For other elements, use the match
                logger.info(f"Found element by partial text match: '{target_text}' -> '{text}'")
                return element_info
        
        # Strategy 3: Try to find by checking common form patterns
        # Look for elements that might be related to the target text
        target_words = target_text.lower().split()
        best_match = None
        best_score = 0
        
        for text, element_info in self.current_mapping.items():
            text_words = text.lower().split()
            
            # Calculate word overlap score
            overlap = len(set(target_words) & set(text_words))
            if overlap > 0:
                score = overlap / max(len(target_words), len(text_words))
                if score > best_score and score > 0.3:  # At least 30% overlap
                    best_match = element_info
                    best_score = score
        
        if best_match:
            # Find the corresponding text key for logging
            matched_text = ""
            for text, element_info in self.current_mapping.items():
                if element_info == best_match:
                    matched_text = text
                    break
            logger.info(f"Found element by word overlap: '{target_text}' -> '{matched_text}' (score: {best_score:.2f})")
            return best_match
        
        return None
    
    async def _try_direct_selector(self, target_text: str) -> Optional[str]:
        """Try to use target_text as a direct selector (ID or name) with improved robustness."""
        if not target_text or not target_text.replace('_', '').replace('-', '').replace('.', '').isalnum():
            return None
        
        # Clean the target text to make it a valid selector
        cleaned_text = target_text.strip()
        
        # Try as ID first, then name attribute, then other common patterns
        selectors_to_try = [
            f"#{cleaned_text}",
            f"[name='{cleaned_text}']",
            f"[id='{cleaned_text}']",
            f"[data-testid='{cleaned_text}']",
            f"[placeholder='{cleaned_text}']"
        ]
        
        # Also try with common variations
        if '_' in cleaned_text or '-' in cleaned_text:
            # Try camelCase version
            camel_case = ''.join(word.capitalize() if i > 0 else word for i, word in enumerate(cleaned_text.replace('-', '_').split('_')))
            selectors_to_try.extend([
                f"#{camel_case}",
                f"[name='{camel_case}']",
                f"[id='{camel_case}']"
            ])
            
            # Try lowercase version
            lower_case = cleaned_text.lower()
            selectors_to_try.extend([
                f"#{lower_case}",
                f"[name='{lower_case}']",
                f"[id='{lower_case}']"
            ])
        
        for selector in selectors_to_try:
            try:
                page = await self.browser.get_current_page()
                
                # Check if element exists first
                element_count = await page.locator(selector).count()
                if element_count == 0:
                    continue
                
                # Check if it's visible
                await page.wait_for_selector(selector, timeout=2000, state="visible")
                
                # Check if this selector resolves to multiple elements (strict mode violation)
                if element_count > 1:
                    logger.warning(f"Selector {selector} matches {element_count} elements, trying to make it more specific")
                    
                    # Try to make it more specific for form elements
                    specific_selectors = [
                        f"{selector}:not([type='hidden'])",
                        f"{selector}:visible",
                        f"{selector}:first-of-type"
                    ]
                    
                    for specific_selector in specific_selectors:
                        try:
                            specific_count = await page.locator(specific_selector).count()
                            if specific_count == 1:
                                await page.wait_for_selector(specific_selector, timeout=1000, state="visible")
                                logger.info(f"Found specific element using selector: {specific_selector}")
                                return specific_selector
                        except:
                            continue
                    
                    # If we can't make it specific, return the original but log the issue
                    logger.warning(f"Using non-specific selector {selector} (matches {element_count} elements)")
                    return selector
                
                logger.info(f"Found element using direct selector: {selector}")
                return selector
                
            except Exception as e:
                logger.debug(f"Element not found with selector {selector}: {e}")
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
        
        # Get current URL and normalize both URLs for comparison
        current_url = page.url
        target_url = step.url
        
        # Normalize URLs by removing fragments and trailing slashes
        def normalize_url(url: str) -> str:
            if not url:
                return ""
            # Remove fragment (everything after #)
            if '#' in url:
                url = url.split('#')[0]
            # Remove trailing slash
            return url.rstrip('/')
        
        current_normalized = normalize_url(current_url)
        target_normalized = normalize_url(target_url)
        
        # Skip navigation if we're already at the target URL
        if current_normalized == target_normalized:
            msg = f"⏭️ Skipped navigation - already at URL: {step.url}"
            logger.info(msg)
            # Still refresh semantic mapping even if we don't navigate, in case page state has changed
            await self._refresh_semantic_mapping()
            return ActionResult(extracted_content=msg, include_in_memory=True)
        
        # Perform navigation
        await page.goto(step.url)
        await page.wait_for_load_state()
        
        # Wait extra time for dynamic content and SPAs to load
        await asyncio.sleep(3)
        
        # Wait for common form elements to be present (indicates page is ready)
        try:
            # Wait for any input, button, or form element to be present
            await page.wait_for_selector('input, button, form, textarea, select', timeout=10000)
        except:
            logger.warning("No form elements found after navigation, continuing anyway")
        
        # Refresh semantic mapping after navigation
        await self._refresh_semantic_mapping()
        
        # Execute navigation with verification and retry
        async def navigation_executor():
            msg = f"🔗 Navigated to URL: {step.url}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)
        
        async def navigation_verifier():
            return await self._verify_navigation_action(step.url)
        
        return await self._execute_with_verification_and_retry(navigation_executor, step, navigation_verifier)
    
    async def execute_click_step(self, step: ClickStep) -> ActionResult:
        """Execute click step using semantic mapping with improved selector strategies."""
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
                # Enhanced error message with debugging info
                available_texts = list(self.current_mapping.keys())[:15]  # Show first 15 available options
                error_msg = f"No selector available for click step: '{target_identifier or step.description}'"
                error_msg += f"\nAvailable elements on page: {available_texts}"
                if len(self.current_mapping) > 15:
                    error_msg += f" (and {len(self.current_mapping) - 15} more)"
                
                # Try to find similar text matches for debugging
                if target_identifier:
                    similar_matches = []
                    target_lower = target_identifier.lower()
                    for text in self.current_mapping.keys():
                        if any(word in text.lower() for word in target_lower.split()):
                            similar_matches.append(text)
                    
                    if similar_matches:
                        error_msg += f"\nSimilar text found: {similar_matches[:5]}"
                
                logger.error(error_msg)
                raise Exception(error_msg)
        
        # Wait for element and click using improved strategies
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
        
        # Execute click with verification and retry
        async def click_executor():
            success = await self._click_element_intelligently(selector_to_use, target_identifier, element_info)
            if not success:
                raise Exception(f"Failed to click element: {target_identifier or step.description or selector_to_use}")
            
            msg = f"🖱️ Clicked element: {target_identifier or step.description or selector_to_use}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)
        
        async def click_verifier():
            return await self._verify_click_action(selector_to_use, target_identifier, step.type, step)
        
        return await self._execute_with_verification_and_retry(click_executor, step, click_verifier)
    
    async def _click_element_intelligently(self, selector: str, target_text: str, element_info: Dict = None) -> bool:
        """Click element using the most appropriate strategy based on element type."""
        page = await self.browser.get_current_page()
        
        try:
            # Strategy 0: For buttons, ensure we're clicking the right button by text content
            if "button" in selector.lower() or "submit" in selector.lower():
                # If we have target_text, try to find the specific button by its text content
                if target_text and target_text.strip():
                    # Try multiple strategies to find the correct button
                    button_strategies = [
                        f'button:has-text("{target_text}")',
                        f'input[type="submit"][value="{target_text}"]',
                        f'input[type="button"][value="{target_text}"]',
                        f'*:has-text("{target_text}"):is(button, [role="button"])',
                        # XPath fallback
                        f'xpath=//button[contains(text(), "{target_text}")]',
                        f'xpath=//input[@type="submit" and @value="{target_text}"]',
                        f'xpath=//input[@type="button" and @value="{target_text}"]'
                    ]
                    
                    for button_selector in button_strategies:
                        try:
                            locator = page.locator(button_selector)
                            count = await locator.count()
                            if count == 1:
                                await locator.click()
                                logger.info(f"Successfully clicked button using text-based selector: {button_selector}")
                                return True
                            elif count > 1:
                                # Multiple matches, try the first one
                                await locator.first.click()
                                logger.info(f"Clicked first matching button: {button_selector}")
                                return True
                        except Exception as e:
                            logger.debug(f"Button strategy failed for {button_selector}: {e}")
                            continue
                
                # Fall back to original selector if text-based strategies fail
                try:
                    locator = page.locator(selector)
                    count = await locator.count()
                    if count >= 1:
                        if count > 1:
                            logger.warning(f"Multiple buttons found with selector {selector}, clicking first")
                        await locator.first.click()
                        logger.info(f"Successfully clicked button using original selector: {selector}")
                        return True
                except Exception as e:
                    logger.debug(f"Original button selector failed: {e}")
            
            # Strategy 1: For radio buttons and checkboxes, try label clicking first
            elif "radio" in selector.lower() or "checkbox" in selector.lower():
                # Try clicking the associated label first (most reliable)
                if target_text:
                    label_strategies = [
                        f'label:has-text("{target_text}")',
                        f'label[for*="{target_text.lower()}"]',
                        f'label:has(input[value="{target_text.lower()}"])'
                    ]
                    
                    for label_selector in label_strategies:
                        try:
                            label_locator = page.locator(label_selector)
                            label_count = await label_locator.count()
                            if label_count == 1:
                                await label_locator.click()
                                logger.info(f"Successfully clicked label: {label_selector}")
                                return True
                            elif label_count > 1:
                                # Multiple labels found, be more specific
                                await label_locator.first.click()
                                logger.info(f"Clicked first matching label: {label_selector}")
                                return True
                        except Exception as e:
                            logger.debug(f"Label click failed for {label_selector}: {e}")
                            continue
                
                # Strategy 2: Use .check() for radio buttons and checkboxes
                try:
                    # Make selector more specific if needed
                    if selector == 'input[type="radio"]' or selector == 'input[type="checkbox"]':
                        # This is too generic, try to make it specific
                        if target_text:
                            specific_selectors = [
                                f'input[type="radio"][value="{target_text.lower()}"]',
                                f'input[type="checkbox"][value="{target_text.lower()}"]',
                                f'input[value="{target_text.lower()}"]'
                            ]
                            
                            for specific_selector in specific_selectors:
                                try:
                                    locator = page.locator(specific_selector)
                                    count = await locator.count()
                                    if count == 1:
                                        await page.check(specific_selector)
                                        logger.info(f"Successfully checked using specific selector: {specific_selector}")
                                        return True
                                except Exception as e:
                                    logger.debug(f"Specific check failed for {specific_selector}: {e}")
                                    continue
                    else:
                        # Use the provided selector with .check()
                        await page.check(selector)
                        logger.info(f"Successfully checked: {selector}")
                        return True
                        
                except Exception as e:
                    logger.debug(f"Check operation failed: {e}")
                
                # Strategy 3: Fall back to clicking the input directly (with specificity)
                try:
                    locator = page.locator(selector)
                    count = await locator.count()
                    if count == 1:
                        await locator.click()
                        logger.info(f"Successfully clicked radio/checkbox: {selector}")
                        return True
                    elif count > 1:
                        # Multiple elements, try to be more specific
                        if target_text:
                            specific_locator = page.locator(f'{selector}[value="{target_text.lower()}"]')
                            if await specific_locator.count() > 0:
                                await specific_locator.click()
                                logger.info(f"Clicked specific radio/checkbox by value: {target_text}")
                                return True
                        
                        # Fall back to first match
                        radio_locator = page.locator(selector)
                        await radio_locator.first.check()
                        logger.warning(f"Selected first radio button (multiple found): {selector}")
                        return True
                except Exception as e:
                    logger.debug(f"Direct radio/checkbox click failed: {e}")
            
            # Strategy 4: For buttons and other elements, use regular click
            try:
                locator = page.locator(selector)
                count = await locator.count()
                if count == 1:
                    await locator.click(force=True)
                    logger.info(f"Successfully clicked element: {selector}")
                    return True
                elif count > 1:
                    # Multiple elements found, click first one with warning
                    await locator.first.click(force=True)
                    logger.warning(f"Clicked first element (multiple found): {selector}")
                    return True
                else:
                    logger.error(f"No elements found for selector: {selector}")
                    return False
            except Exception as e:
                logger.error(f"Regular click failed: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Intelligent click failed: {e}")
            return False
    
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
                # Enhanced error message with debugging info
                available_texts = list(self.current_mapping.keys())[:15]  # Show first 15 available options
                error_msg = f"No selector available for input step: '{target_identifier or step.description}'"
                error_msg += f"\nAvailable elements on page: {available_texts}"
                if len(self.current_mapping) > 15:
                    error_msg += f" (and {len(self.current_mapping) - 15} more)"
                
                # Try to find similar text matches for debugging
                if target_identifier:
                    similar_matches = []
                    target_lower = target_identifier.lower()
                    for text in self.current_mapping.keys():
                        if any(word in text.lower() for word in target_lower.split()):
                            similar_matches.append(text)
                    
                    if similar_matches:
                        error_msg += f"\nSimilar text found: {similar_matches[:5]}"
                
                logger.error(error_msg)
                raise Exception(error_msg)
        
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
        
        # Execute input with verification and retry
        async def input_executor():
            locator = page.locator(selector_to_use)
            element_type = await locator.evaluate('(el) => ({ tagName: el.tagName, type: el.type, value: el.value })')
            
            # Handle radio buttons and checkboxes with improved strategies
            if element_type['type'] in ['radio', 'checkbox']:
                success = await self._handle_radio_checkbox_input(selector_to_use, step.value, target_identifier, element_type['type'])
                if not success:
                    raise Exception(f"Failed to select {element_type['type']} button: {target_identifier}")
                
                action_type = "🔘" if element_type['type'] == 'radio' else "☑️"
                msg = f"{action_type} Selected '{step.value}' for: {target_identifier or step.description}"
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
        
        async def input_verifier():
            locator = page.locator(selector_to_use)
            element_type = await locator.evaluate('(el) => ({ tagName: el.tagName, type: el.type, value: el.value })')
            return await self._verify_input_action(selector_to_use, step.value, element_type['type'])
        
        return await self._execute_with_verification_and_retry(input_executor, step, input_verifier)
    
    async def _handle_radio_checkbox_input(self, selector: str, value: str, target_text: str, input_type: str) -> bool:
        """Handle radio button and checkbox input with improved strategies."""
        page = await self.browser.get_current_page()
        
        try:
            # Strategy 1: For radio buttons, find the specific radio button by value
            if input_type == 'radio':
                # Try to be more specific with radio button selection
                radio_strategies = [
                    f'input[type="radio"][value="{value.lower()}"]',
                    f'input[type="radio"][value="{value}"]',
                    f'input[value="{value.lower()}"]',
                    f'input[value="{value}"]'
                ]
                
                for radio_selector in radio_strategies:
                    try:
                        count = await page.locator(radio_selector).count()
                        if count == 1:
                            await page.check(radio_selector)
                            logger.info(f"Successfully selected radio button: {radio_selector}")
                            return True
                        elif count > 1:
                            # Multiple radio buttons with same value, try to narrow down by name or context
                            if target_text:
                                # Try to find by label association
                                contextual_selectors = [
                                    f'input[type="radio"][value="{value.lower()}"][name*="{target_text.lower()}"]',
                                    f'label:has-text("{target_text}") input[type="radio"][value="{value.lower()}"]'
                                ]
                                
                                for ctx_selector in contextual_selectors:
                                    try:
                                        ctx_count = await page.locator(ctx_selector).count()
                                        if ctx_count == 1:
                                            await page.check(ctx_selector)
                                            logger.info(f"Selected radio button with context: {ctx_selector}")
                                            return True
                                    except Exception as e:
                                        logger.debug(f"Contextual radio selection failed: {e}")
                                        continue
                            
                            # Fall back to first match
                            radio_locator = page.locator(radio_selector)
                            await radio_locator.first.check()
                            logger.warning(f"Selected first radio button (multiple found): {radio_selector}")
                            return True
                    except Exception as e:
                        logger.debug(f"Radio button selection failed for {radio_selector}: {e}")
                        continue
                
                # Try label clicking as fallback
                if value:
                    try:
                        await page.click(f'label:has-text("{value}")')
                        logger.info(f"Selected radio button by clicking label: {value}")
                        return True
                    except Exception as e:
                        logger.debug(f"Label click failed for radio button: {e}")
            
            # Strategy 2: For checkboxes, determine desired state and set accordingly
            elif input_type == 'checkbox':
                should_check = value.lower() in ['true', '1', 'on', 'yes', 'checked']
                
                try:
                    # Get current state
                    is_currently_checked = await page.locator(selector).is_checked()
                    
                    if should_check and not is_currently_checked:
                        await page.check(selector)
                        logger.info(f"Checked checkbox: {target_text}")
                        return True
                    elif not should_check and is_currently_checked:
                        await page.uncheck(selector)
                        logger.info(f"Unchecked checkbox: {target_text}")
                        return True
                    else:
                        logger.info(f"Checkbox already in desired state: {target_text}")
                        return True
                except Exception as e:
                    logger.debug(f"Checkbox operation failed: {e}")
                    
                    # Try label clicking as fallback
                    try:
                        await page.click(f'label:has-text("{target_text}")')
                        logger.info(f"Toggled checkbox by clicking label: {target_text}")
                        return True
                    except Exception as e:
                        logger.debug(f"Label click failed for checkbox: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Radio/checkbox input handling failed: {e}")
            return False
    
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
            # Enhanced error message with debugging info
            available_texts = list(self.current_mapping.keys())[:10]  # Show first 10 available options
            error_msg = f"No selector available for select step: {target_identifier or step.description}"
            error_msg += f"\nAvailable elements on page: {available_texts}"
            if len(self.current_mapping) > 10:
                error_msg += f" (and {len(self.current_mapping) - 10} more)"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # Wait for element and select option
        if not await self._wait_for_element(selector_to_use):
            raise Exception(f"Element not found: {selector_to_use}")
        
        # Execute select with verification and retry
        async def select_executor():
            locator = page.locator(selector_to_use)
            await locator.select_option(label=step.selectedText)
            
            msg = f"🔽 Selected '{step.selectedText}' in: {target_identifier or step.description or selector_to_use}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)
        
        async def select_verifier():
            return await self._verify_input_action(selector_to_use, step.selectedText, 'select')
        
        return await self._execute_with_verification_and_retry(select_executor, step, select_verifier)
    
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
            # Enhanced error message with debugging info
            available_texts = list(self.current_mapping.keys())[:10]  # Show first 10 available options
            error_msg = f"No selector available for key press step: {target_identifier or step.description}"
            error_msg += f"\nAvailable elements on page: {available_texts}"
            if len(self.current_mapping) > 10:
                error_msg += f" (and {len(self.current_mapping) - 10} more)"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # Wait for element and press key
        if not await self._wait_for_element(selector_to_use):
            raise Exception(f"Element not found: {selector_to_use}")
        
        # Execute key press with verification and retry
        async def keypress_executor():
            locator = page.locator(selector_to_use)
            await locator.press(step.key)
            
            msg = f"🔑 Pressed key '{step.key}' on: {target_identifier or step.description or selector_to_use}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)
        
        async def keypress_verifier():
            # For key presses, just verify the element is still accessible
            # (More specific verification could be added based on the key and context)
            try:
                locator = page.locator(selector_to_use)
                return await locator.count() > 0 and await locator.is_visible()
            except:
                return False
        
        return await self._execute_with_verification_and_retry(keypress_executor, step, keypress_verifier)
    
    async def execute_scroll_step(self, step: ScrollStep) -> ActionResult:
        """Execute scroll step."""
        page = await self.browser.get_current_page()
        await page.evaluate(f"window.scrollBy({step.scrollX}, {step.scrollY})")
        
        msg = f"📜 Scrolled by ({step.scrollX}, {step.scrollY})"
        logger.info(msg)
        return ActionResult(extracted_content=msg, include_in_memory=True)
    
    async def execute_button_step(self, step) -> ActionResult:
        """Execute button click step using semantic mapping."""
        # Button steps are essentially click steps but with button-specific metadata
        # Convert to click step format for execution
        click_step = ClickStep(
            type="button",  # Use button type for verification
            target_text=getattr(step, 'target_text', getattr(step, 'button_text', '')),
            description=step.description,
            cssSelector=getattr(step, 'cssSelector', ''),
            xpath=getattr(step, 'xpath', '')
        )
        
        # Execute with button-specific verification
        result = await self.execute_click_step(click_step)
        
        # Update the message to indicate it was a button click
        button_text = getattr(step, 'button_text', getattr(step, 'target_text', 'button'))
        button_type = getattr(step, 'button_type', 'button')
        msg = f"🔘 Clicked {button_type} button: {button_text}"
        logger.info(msg)
        
        return ActionResult(extracted_content=msg, include_in_memory=True)

    def set_workflow_context(self, workflow_steps: list):
        """Set the current workflow steps for context-aware verification."""
        self._current_workflow_steps = workflow_steps

    async def execute_step(self, step: WorkflowStep) -> ActionResult:
        """Execute a single workflow step."""
        # Always refresh semantic mapping before each step to avoid stale selectors
        await self._refresh_semantic_mapping()
        
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
        elif step.type == 'button':
            return await self.execute_button_step(step)
        else:
            raise Exception(f"Unsupported step type: {step.type}")
    
    async def print_semantic_mapping(self) -> None:
        """Print current semantic mapping for debugging."""
        if not self.current_mapping:
            await self._refresh_semantic_mapping()
        
        logger.info("=== Current Semantic Mapping ===")
        for text, element_info in self.current_mapping.items():
            logger.info(f"'{text}' -> {element_info['deterministic_id']} ({element_info['selectors']})")
        logger.info("=== End Semantic Mapping ===")
    
    async def _execute_with_verification_and_retry(self, step_executor, step, verification_method):
        """Execute a step with verification and retry logic."""
        # Check if we've hit global failure limits before starting
        if self.global_failure_count >= self.max_global_failures:
            error_msg = f"❌ Global failure limit reached ({self.global_failure_count}/{self.max_global_failures}). Workflow appears to be encountering systematic issues."
            logger.error(error_msg)
            raise Exception(error_msg)
        
        if self.consecutive_failures >= 3:
            error_msg = f"❌ Too many consecutive failures ({self.consecutive_failures}). Form may have unexpected changes or invalid input data."
            logger.error(error_msg)
            raise Exception(error_msg)
        
        if self.consecutive_verification_failures >= self.max_verification_failures:
            error_msg = f"❌ Too many consecutive verification failures ({self.consecutive_verification_failures}). Steps are executing but not achieving expected results."
            logger.error(error_msg)
            raise Exception(error_msg)
        
        last_exception = None
        last_result = None
        
        for attempt in range(self.max_retries + 1):  # +1 for initial attempt
            try:
                if attempt > 0:
                    logger.info(f"🔄 Retry attempt {attempt}/{self.max_retries} for step: {step.description}")
                    # Refresh semantic mapping before retry
                    await self._refresh_semantic_mapping()
                    # Small delay before retry
                    await asyncio.sleep(1)
                
                # Execute the step
                result = await step_executor()
                last_result = result
                
                # Check for validation errors immediately after execution
                validation_errors = await self._detect_form_validation_errors()
                if validation_errors:
                    logger.warning(f"⚠️ Form validation errors detected after step execution: {validation_errors}")
                    if attempt < self.max_retries:
                        logger.warning(f"⚠️ Step caused validation errors, will retry...")
                        continue
                    else:
                        logger.error(f"❌ Step caused validation errors after {self.max_retries} retries")
                        # Don't break here, let it continue to verification
                
                # Verify the step was successful
                verification_passed = await verification_method()
                
                if verification_passed and not validation_errors:
                    if attempt > 0:
                        logger.info(f"✅ Step succeeded on retry {attempt}")
                    
                    # Reset all failure counters on success
                    self.consecutive_failures = 0
                    self.consecutive_verification_failures = 0
                    self.last_successful_step = step.description if hasattr(step, 'description') else str(step.type)
                    return result
                else:
                    # Track verification failures separately from execution failures
                    if not validation_errors and not verification_passed:
                        # This is a pure verification failure (step executed but didn't achieve expected result)
                        pass  # We'll increment this counter after all retries are exhausted
                    
                    if attempt < self.max_retries:
                        if validation_errors:
                            logger.warning(f"⚠️ Step caused validation errors, will retry...")
                        else:
                            logger.warning(f"⚠️ Step verification failed, will retry...")
                        continue
                    else:
                        # This is the final attempt and it failed
                        if validation_errors:
                            last_exception = Exception(f"Step caused form validation errors: {list(validation_errors.values())}")
                        else:
                            # For verification failures, increment the counter immediately
                            self.consecutive_verification_failures += 1
                            last_exception = Exception("Step verification failed")
                            
                            # Check if we should stop due to verification failures
                            if self.consecutive_verification_failures >= self.max_verification_failures:
                                raise Exception(f"Too many consecutive verification failures ({self.consecutive_verification_failures}). Steps are executing but not achieving expected results.")
                        break
                        
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    # Check for specific error patterns that indicate systematic issues
                    error_str = str(e).lower()
                    if any(pattern in error_str for pattern in [
                        'element not found', 'timeout', 'selector failed', 
                        'no such element', 'element is not attached'
                    ]):
                        logger.warning(f"⚠️ Element detection failed (attempt {attempt + 1}): {e}")
                    else:
                        logger.warning(f"⚠️ Step execution failed (attempt {attempt + 1}): {e}")
                    continue
                else:
                    logger.error(f"❌ Step execution failed after {self.max_retries} retries: {e}")
                    break
        
        # If we get here, the step failed after all retries are exhausted
        self.global_failure_count += 1
        self.consecutive_failures += 1
        
        # Determine failure type and update appropriate counters
        failure_type = "execution"
        if last_exception and "verification failed" in str(last_exception).lower():
            self.consecutive_verification_failures += 1
            failure_type = "verification"
        elif last_exception and "validation errors" in str(last_exception).lower():
            failure_type = "validation"
        else:
            failure_type = "execution"
        
        # Enhanced error reporting
        error_context = {
            'step_type': step.type if hasattr(step, 'type') else 'unknown',
            'description': step.description if hasattr(step, 'description') else 'No description',
            'target_text': getattr(step, 'target_text', None),
            'value': getattr(step, 'value', None),
            'failure_type': failure_type,
            'global_failures': self.global_failure_count,
            'consecutive_failures': self.consecutive_failures,
            'consecutive_verification_failures': self.consecutive_verification_failures,
            'last_successful_step': self.last_successful_step
        }
        
        logger.error(f"❌ Step failed completely after {self.max_retries + 1} attempts. Context: {error_context}")
        
        # Provide specific guidance based on failure patterns
        if self.consecutive_verification_failures >= 2:
            logger.warning("⚠️  Multiple consecutive verification failures detected. This may indicate:")
            logger.warning("   • Steps are executing but not achieving expected results")
            logger.warning("   • Form behavior has changed (validation rules, navigation flow)")
            logger.warning("   • Data being entered is causing unexpected form states")
            logger.warning("   • Page interactions are not waiting long enough for effects")
        elif self.consecutive_failures >= 2:
            logger.warning("⚠️  Multiple consecutive execution failures detected. This may indicate:")
            logger.warning("   • Form structure has changed")
            logger.warning("   • Invalid input data for current form state")
            logger.warning("   • Element selectors are outdated")
            logger.warning("   • Form validation is rejecting inputs")
        
        # Raise the last exception that occurred
        if last_exception:
            raise last_exception
        else:
            raise Exception(f"Step failed after {self.max_retries + 1} attempts. Global failures: {self.global_failure_count}")
        
        return last_result

    async def _detect_form_validation_errors(self) -> Dict[str, str]:
        """Detect form validation errors that might indicate invalid input data."""
        page = await self.browser.get_current_page()
        validation_errors = {}
        
        try:
            # Common error message selectors
            error_selectors = [
                '.error', '.error-message', '.validation-error', '.field-error',
                '[role="alert"]', '.alert-danger', '.text-red', '.text-error',
                '.invalid-feedback', '.form-error', '.help-block.error'
            ]
            
            for selector in error_selectors:
                try:
                    error_elements = await page.query_selector_all(selector)
                    for i, element in enumerate(error_elements):
                        if await element.is_visible():
                            error_text = await element.text_content()
                            if error_text and error_text.strip():
                                # Filter out browser internal scripts and long technical content
                                clean_text = error_text.strip()
                                
                                # Skip if it looks like browser internal code
                                if any(pattern in clean_text for pattern in [
                                    'document.getElementById', 'function addPageBinding', 
                                    'serializeAsCallArgument', '__next_f', 'globalThis',
                                    'self.__next_f', 'serializeAsCallArgument'
                                ]):
                                    continue
                                
                                # Skip very long messages (likely technical content)
                                if len(clean_text) > 200:
                                    continue
                                
                                # Only include messages that look like actual validation errors
                                if any(pattern in clean_text.lower() for pattern in [
                                    'required', 'invalid', 'error', 'must', 'cannot', 'please',
                                    'missing', 'incorrect', 'format', 'valid', 'enter', 'provide',
                                    'field', 'complete', 'fill'
                                ]):
                                    validation_errors[f"{selector}_{i}"] = clean_text
                except:
                    continue
            
            # Check for common validation patterns in text
            if validation_errors:
                logger.warning(f"🚨 Form validation errors detected: {validation_errors}")
                
        except Exception as e:
            logger.debug(f"Error checking for validation messages: {e}")
        
        return validation_errors

    async def _detect_form_submission_failure(self, expected_progress_indicators: list = None) -> bool:
        """Detect if a form submission failed by checking for common failure indicators."""
        page = await self.browser.get_current_page()
        
        try:
            # Check if we're still on the same form step/page when we should have progressed
            if expected_progress_indicators:
                for indicator in expected_progress_indicators:
                    try:
                        elements = await page.query_selector_all(f"text={indicator}")
                        if elements:
                            logger.warning(f"Form submission may have failed: still showing '{indicator}'")
                            return True
                    except:
                        continue
            
            # Check for common submission failure indicators
            failure_indicators = [
                'form-error', 'submission-error', 'error-summary',
                'alert-error', 'error-container'
            ]
            
            for indicator in failure_indicators:
                try:
                    elements = await page.query_selector_all(f".{indicator}")
                    for element in elements:
                        if await element.is_visible():
                            error_text = await element.text_content()
                            if error_text and error_text.strip():
                                logger.warning(f"Form submission failure detected: {error_text.strip()}")
                                return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking for form submission failure: {e}")
            return False

    async def _verify_navigation_success_by_next_step(self, current_step) -> bool:
        """Verify navigation success by checking if next step elements are available."""
        if not current_step or not hasattr(current_step, '__dict__'):
            return False
        
        try:
            # Get workflow context to find the next step
            workflow_steps = getattr(self, '_current_workflow_steps', None)
            if not workflow_steps:
                return False
            
            # Find current step index
            current_step_desc = getattr(current_step, 'description', '')
            current_index = -1
            
            for i, step in enumerate(workflow_steps):
                if step.get('description') == current_step_desc:
                    current_index = i
                    break
            
            if current_index == -1 or current_index >= len(workflow_steps) - 1:
                return False
            
            # Get next step
            next_step = workflow_steps[current_index + 1]
            next_step_type = next_step.get('type', '')
            
            # Skip non-interactive steps (scroll, etc.)
            step_offset = 1
            while (current_index + step_offset < len(workflow_steps) and 
                   workflow_steps[current_index + step_offset].get('type') in ['scroll', 'navigation']):
                step_offset += 1
            
            if current_index + step_offset >= len(workflow_steps):
                return False
            
            target_step = workflow_steps[current_index + step_offset]
            target_text = target_step.get('target_text')
            
            if not target_text:
                return False
            
            # Refresh semantic mapping to check for next step elements
            await self._refresh_semantic_mapping()
            
            # Check if the target element for the next step is now available
            element_info = self._find_element_by_text(target_text)
            if element_info:
                logger.info(f"Verification: Found next step element '{target_text}' - navigation successful")
                return True
            
            # Also check if target_text is a direct selector that exists
            try:
                page = await self.browser.get_current_page()
                direct_selector = await self._try_direct_selector(target_text)
                if direct_selector:
                    await page.wait_for_selector(direct_selector, timeout=2000, state="visible")
                    logger.info(f"Verification: Found next step element by direct selector '{target_text}' - navigation successful")
                    return True
            except Exception:
                pass
            
            logger.debug(f"Verification: Next step element '{target_text}' not found - navigation may have failed")
            return False
            
        except Exception as e:
            logger.debug(f"Error verifying navigation by next step: {e}")
            return False

    async def _analyze_failure_context(self, step, error: Exception) -> str:
        """Analyze the context of a step failure to provide better error messages."""
        context_info = []
        
        try:
            # Check current page state
            page = await self.browser.get_current_page()
            current_url = page.url
            page_title = await page.title()
            
            context_info.append(f"URL: {current_url}")
            context_info.append(f"Page Title: {page_title}")
            
            # Check for validation errors
            validation_errors = await self._detect_form_validation_errors()
            if validation_errors:
                context_info.append(f"Validation Errors: {list(validation_errors.values())}")
            
            # Check if expected elements are present on page
            if hasattr(step, 'target_text') and step.target_text:
                element_count = len(self.current_mapping)
                has_target = step.target_text in self.current_mapping
                context_info.append(f"Elements on page: {element_count}, Target '{step.target_text}' found: {has_target}")
                
                if not has_target:
                    # Find similar elements
                    similar_elements = []
                    target_lower = step.target_text.lower()
                    for text in self.current_mapping.keys():
                        if target_lower in text.lower() or text.lower() in target_lower:
                            similar_elements.append(text)
                    
                    if similar_elements:
                        context_info.append(f"Similar elements found: {similar_elements[:3]}")
                        
        except Exception as e:
            context_info.append(f"Context analysis failed: {e}")
        
        return " | ".join(context_info)

    async def _verify_click_action(self, selector: str, target_text: str, step_type: str = "click", current_step=None) -> bool:
        """Verify that a click action had the expected effect."""
        try:
            page = await self.browser.get_current_page()
            
            # Small delay to let the click effect take place
            await asyncio.sleep(0.5)
            
            # Check for validation errors first - if there are validation errors after a button click,
            # it usually means the click didn't achieve its intended purpose
            validation_errors = await self._detect_form_validation_errors()
            if validation_errors:
                logger.warning(f"Verification failed: Form validation errors after click: {validation_errors}")
                return False
            
            # For radio buttons and checkboxes, verify they are checked/selected
            if "radio" in selector.lower() or "checkbox" in selector.lower() or step_type in ["radio", "checkbox"]:
                element = page.locator(selector).first
                if await element.count() > 0:
                    is_checked = await element.is_checked()
                    logger.info(f"Verification: Radio/checkbox {'is' if is_checked else 'is not'} checked")
                    return is_checked
                else:
                    logger.warning(f"Verification: Radio/checkbox element not found")
                    return False
            
            # For buttons, verify the click had some effect
            elif step_type == "button" or "button" in selector.lower() or any(keyword in target_text.lower() for keyword in ['submit', 'next', 'continue', 'save', 'finish']):
                # Wait a bit for any page changes
                await asyncio.sleep(1)
                
                # Check for validation errors again after waiting (some forms show errors after delay)
                validation_errors = await self._detect_form_validation_errors()
                if validation_errors:
                    logger.warning(f"Verification failed: Form validation errors after button click: {validation_errors}")
                    return False
                
                # Try to find the button using the target_text we have
                element = None
                try:
                    # First try the original selector
                    element = page.locator(selector).first
                    button_exists = await element.count() > 0
                    
                    # If button doesn't exist with original selector, try finding by text
                    if not button_exists and target_text:
                        # Try different ways to find the button by its text
                        text_selectors = [
                            f"//button[contains(text(), '{target_text}')]",
                            f"//input[@type='button' and @value='{target_text}']",
                            f"//input[@type='submit' and @value='{target_text}']",
                            f"//*[contains(text(), '{target_text}') and (self::button or @role='button')]"
                        ]
                        
                        for text_selector in text_selectors:
                            try:
                                text_element = page.locator(f"xpath={text_selector}").first
                                if await text_element.count() > 0:
                                    element = text_element
                                    button_exists = True
                                    break
                            except:
                                continue
                    
                    # For navigation/submit buttons, check if we moved to a different section or page
                    if any(keyword in target_text.lower() for keyword in ['next', 'continue', 'submit', 'finish']):
                        # Get current URL to see if page changed
                        current_url = page.url
                        page_title = await page.title()
                        logger.info(f"Verification: After '{target_text}' click - URL: {current_url}, Title: {page_title}")
                        
                        # Try to verify by checking if expected next step elements are available
                        if await self._verify_navigation_success_by_next_step(current_step):
                            logger.info(f"Verification: Navigation successful - next step elements found")
                            return True
                        
                        # Fallback: If URL changed or title changed, likely successful navigation
                        # This is a more reliable indicator than button state for navigation buttons
                        return True
                    
                    # If button still exists after click, verify it's clickable
                    if button_exists and element:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()
                        logger.info(f"Verification: Button '{target_text}' still exists and clickable: visible={is_visible}, enabled={is_enabled}")
                        return is_visible and is_enabled
                    
                    # If button disappeared, this is often a sign of successful interaction
                    # (navigation, form submission, modal close, etc.)
                    else:
                        logger.info(f"Verification: Button '{target_text}' disappeared after click - likely successful interaction")
                        return True
                        
                except Exception as e:
                    logger.info(f"Verification: Button verification had issues, assuming success: {e}")
                    return True
            
            # For generic clicks, just verify element is still accessible
            else:
                element = page.locator(selector).first
                if await element.count() > 0:
                    logger.info(f"Verification: Click target still exists and accessible")
                    return True
                else:
                    # Element might have disappeared due to click (like dropdown items), which could be success
                    logger.info(f"Verification: Click target disappeared (may be expected)")
                    return True
                
        except Exception as e:
            logger.warning(f"Click verification failed: {e}")
            return False
    
    async def _verify_input_action(self, selector: str, expected_value: str, input_type: str = "text") -> bool:
        """Verify that an input action succeeded by checking the element's value."""
        try:
            page = await self.browser.get_current_page()
            
            # Small delay to let the input effect take place
            await asyncio.sleep(0.3)
            
            element = page.locator(selector).first
            
            if await element.count() > 0:
                # For radio buttons and checkboxes, check if they're selected/checked
                if input_type in ['radio', 'checkbox'] or 'radio' in selector.lower() or 'checkbox' in selector.lower():
                    is_checked = await element.is_checked()
                    expected_checked = expected_value.lower() in ['true', '1', 'on', 'yes', 'checked']
                    matches = is_checked == expected_checked
                    logger.info(f"Verification: Radio/checkbox expected checked={expected_checked}, actual checked={is_checked}, match: {matches}")
                    return matches
                
                # For select elements, check selected option
                elif input_type == 'select' or element.evaluate('el => el.tagName') == 'SELECT':
                    try:
                        selected_text = await element.evaluate('el => el.options[el.selectedIndex]?.text || ""')
                        matches = selected_text.strip() == expected_value.strip()
                        logger.info(f"Verification: Select expected '{expected_value}', got '{selected_text}', match: {matches}")
                        return matches
                    except:
                        # Fallback to value comparison
                        actual_value = await element.input_value()
                        matches = actual_value.strip() == expected_value.strip()
                        logger.info(f"Verification: Select (by value) expected '{expected_value}', got '{actual_value}', match: {matches}")
                        return matches
                
                # For text inputs and other input types
                else:
                    actual_value = await element.input_value()
                    matches = actual_value.strip() == expected_value.strip()
                    logger.info(f"Verification: Input expected '{expected_value}', got '{actual_value}', match: {matches}")
                    return matches
            else:
                logger.warning(f"Verification: Input element not found with selector {selector}")
                return False
        except Exception as e:
            logger.warning(f"Input verification failed: {e}")
            return False
    
    async def _verify_navigation_action(self, expected_url: str) -> bool:
        """Verify that navigation succeeded by checking current URL."""
        try:
            page = await self.browser.get_current_page()
            current_url = page.url
            
            # Normalize URLs for comparison
            def normalize_url(url: str) -> str:
                if not url:
                    return ""
                if '#' in url:
                    url = url.split('#')[0]
                return url.rstrip('/')
            
            current_normalized = normalize_url(current_url)
            expected_normalized = normalize_url(expected_url)
            
            matches = current_normalized == expected_normalized
            logger.info(f"Verification: Current URL '{current_url}' {'matches' if matches else 'does not match'} expected '{expected_url}'")
            return matches
        except Exception as e:
            logger.warning(f"Navigation verification failed: {e}")
            return False 