import re
import logging
from typing import Dict, List, Optional, Tuple
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class SemanticExtractor:
    """Extracts semantic mappings from HTML pages by mapping visible text to deterministic selectors."""
    
    def __init__(self):
        self.element_counters = {
            'input': 0,
            'button': 0,
            'select': 0,
            'textarea': 0,
            'a': 0,
            'radio': 0,
            'checkbox': 0
        }
    
    def _reset_counters(self):
        """Reset element counters for a new page."""
        self.element_counters = {
            'input': 0,
            'button': 0,
            'select': 0,
            'textarea': 0,
            'a': 0,
            'radio': 0,
            'checkbox': 0
        }
    
    def _get_element_type_and_id(self, element_info: Dict) -> Tuple[str, str]:
        """Determine element type and generate deterministic ID."""
        tag = element_info.get('tag', '').lower()
        input_type = element_info.get('type', '').lower()
        role = element_info.get('role', '').lower()
        
        # Determine element type
        if tag == 'input':
            if input_type in ['radio']:
                element_type = 'radio'
            elif input_type in ['checkbox']:
                element_type = 'checkbox'
            else:
                element_type = 'input'
        elif tag == 'button' or role == 'button':
            element_type = 'button'
        elif tag == 'select':
            element_type = 'select'
        elif tag == 'textarea':
            element_type = 'textarea'
        elif tag == 'a':
            element_type = 'a'
        else:
            element_type = 'input'  # fallback
        
        # Generate ID
        self.element_counters[element_type] += 1
        element_id = f"{element_type}_{self.element_counters[element_type]}"
        
        return element_type, element_id
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for consistent mapping."""
        if not text:
            return ""
        # Remove extra whitespace and normalize
        return re.sub(r'\s+', ' ', text.strip())
    
    def _get_element_text(self, element_info: Dict) -> str:
        """Extract meaningful text from element information."""
        # Priority order for text extraction
        text_sources = [
            element_info.get('label_text', ''),
            element_info.get('text_content', ''),
            element_info.get('placeholder', ''),
            element_info.get('title', ''),
            element_info.get('aria_label', ''),
            element_info.get('value', ''),
            element_info.get('name', ''),
            element_info.get('id', '')
        ]
        
        for text in text_sources:
            if text and text.strip():
                return self._normalize_text(text)
        
        return ""
    
    def _create_fallback_text(self, element_info: Dict, element_type: str, element_id: str) -> str:
        """Create fallback text for elements without meaningful text."""
        tag = element_info.get('tag', '').lower()
        
        if tag == 'button' or element_type == 'button':
            return f"[Button]"
        elif element_type == 'input':
            input_type = element_info.get('type', 'text').lower()
            return f"[Input Field - {input_type}]"
        elif element_type == 'select':
            return f"[Dropdown]"
        elif element_type == 'textarea':
            return f"[Text Area]"
        elif element_type == 'radio':
            return f"[Radio Button]"
        elif element_type == 'checkbox':
            return f"[Checkbox]"
        else:
            return f"[{tag.upper()} Element]"
    
    def _handle_duplicate_text(self, text: str, existing_keys: set, element_info: Dict) -> str:
        """Handle duplicate text by adding context."""
        if text not in existing_keys:
            return text
        
        # Try adding context from nearby elements or attributes
        contexts = []
        
        # Add position-based context
        position = element_info.get('position', {})
        if position:
            contexts.append(f"at {position.get('x', 0)},{position.get('y', 0)}")
        
        # Add parent context if available
        parent_text = element_info.get('parent_text', '')
        if parent_text:
            contexts.append(f"in {parent_text}")
        
        # Add attribute context
        if element_info.get('id'):
            contexts.append(f"id:{element_info['id']}")
        elif element_info.get('class'):
            contexts.append(f"class:{element_info['class'][:20]}")
        
        # Try different combinations
        for i, context in enumerate(contexts):
            candidate = f"{text} ({context})"
            if candidate not in existing_keys:
                return candidate
        
        # Final fallback with index
        counter = 2
        while f"{text} ({counter})" in existing_keys:
            counter += 1
        
        return f"{text} ({counter})"
    
    async def extract_interactive_elements(self, page: Page) -> List[Dict]:
        """Extract all interactive elements from the page."""
        # JavaScript to extract element information
        js_code = """
        () => {
            const elements = [];
            
            // Selectors for interactive elements
            const selectors = [
                'input:not([type="hidden"])',
                'button',
                'select',
                'textarea',
                'a[href]',
                '[role="button"]',
                '[role="link"]',
                '[role="textbox"]',
                '[role="combobox"]',
                '[role="listbox"]',
                '[role="radio"]',
                '[role="checkbox"]'
            ];
            
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach((el, index) => {
                    if (!el.offsetParent && el.tagName !== 'OPTION') return; // Skip hidden elements
                    
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return; // Skip invisible elements
                    
                    // Get associated label
                    let labelText = '';
                    if (el.id) {
                        const label = document.querySelector(`label[for="${el.id}"]`);
                        if (label) labelText = label.textContent?.trim() || '';
                    }
                    
                    // Get parent context
                    let parentText = '';
                    let parent = el.parentElement;
                    while (parent && !parentText && parent !== document.body) {
                        const text = parent.textContent?.trim() || '';
                        if (text && text.length < 100) {
                            parentText = text;
                        }
                        parent = parent.parentElement;
                    }
                    
                    // Build selector
                    let selector = '';
                    if (el.id) {
                        selector = `#${el.id}`;
                    } else {
                        selector = el.tagName.toLowerCase();
                        
                        // Add attribute selectors for more reliable targeting
                        if (el.name) selector += `[name="${el.name}"]`;
                        if (el.type) selector += `[type="${el.type}"]`;
                        
                        // For radio buttons and checkboxes, add value to make selector unique
                        if ((el.type === 'radio' || el.type === 'checkbox') && el.value) {
                            selector += `[value="${el.value}"]`;
                        }
                        
                        // Only add valid CSS classes (avoid complex selectors with & or other special chars)
                        if (el.className) {
                            const classes = el.className.split(' ')
                                .filter(c => c.trim() && 
                                    !c.includes('[') && 
                                    !c.includes(']') && 
                                    !c.includes('&') && 
                                    !c.includes(':') &&
                                    c.match(/^[a-zA-Z_-][a-zA-Z0-9_-]*$/))
                                .slice(0, 3); // Limit to first 3 valid classes
                            if (classes.length > 0) {
                                selector += '.' + classes.join('.');
                            }
                        }
                    }
                    
                    // Generate a simple fallback selector if the main one is too complex
                    let fallbackSelector = el.tagName.toLowerCase();
                    if (el.id) {
                        fallbackSelector = `#${el.id}`;
                    } else if (el.name) {
                        fallbackSelector += `[name="${el.name}"]`;
                        if (el.type) fallbackSelector += `[type="${el.type}"]`;
                        // For radio buttons and checkboxes, include value in fallback too
                        if ((el.type === 'radio' || el.type === 'checkbox') && el.value) {
                            fallbackSelector += `[value="${el.value}"]`;
                        }
                    } else if (el.type) {
                        fallbackSelector += `[type="${el.type}"]`;
                        if ((el.type === 'radio' || el.type === 'checkbox') && el.value) {
                            fallbackSelector += `[value="${el.value}"]`;
                        }
                    }
                    
                    // Generate text-based XPath as another fallback
                    let textXPath = '';
                    const elementText = el.textContent?.trim();
                    if (elementText) {
                        textXPath = `//${el.tagName.toLowerCase()}[contains(text(), "${elementText}")]`;
                    } else if (el.placeholder) {
                        textXPath = `//${el.tagName.toLowerCase()}[@placeholder="${el.placeholder}"]`;
                    } else if (el.value) {
                        textXPath = `//${el.tagName.toLowerCase()}[@value="${el.value}"]`;
                    }
                    
                    elements.push({
                        tag: el.tagName,
                        type: el.type || '',
                        role: el.getAttribute('role') || '',
                        id: el.id || '',
                        name: el.name || '',
                        class: el.className || '',
                        text_content: el.textContent?.trim() || '',
                        placeholder: el.placeholder || '',
                        title: el.title || '',
                        aria_label: el.getAttribute('aria-label') || '',
                        value: el.value || '',
                        label_text: labelText,
                        parent_text: parentText,
                        css_selector: selector,
                        fallback_selector: fallbackSelector,
                        text_xpath: textXPath,
                        position: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    });
                });
            });
            
            return elements;
        }
        """
        
        elements = await page.evaluate(js_code)
        return elements
    
    async def extract_semantic_mapping(self, page: Page) -> Dict[str, Dict]:
        """Extract semantic mapping from the current page.
        
        Returns mapping: visible_text -> {"class": "", "id": "", "selectors": ""}
        """
        self._reset_counters()
        
        # Get all interactive elements
        elements = await self.extract_interactive_elements(page)
        
        mapping = {}
        existing_keys = set()
        
        for element_info in elements:
            # Determine element type and generate ID
            element_type, element_id = self._get_element_type_and_id(element_info)
            
            # Get meaningful text
            text = self._get_element_text(element_info)
            
            # Use fallback if no meaningful text found
            if not text:
                text = self._create_fallback_text(element_info, element_type, element_id)
            
            # Handle duplicates
            final_text = self._handle_duplicate_text(text, existing_keys, element_info)
            existing_keys.add(final_text)
            
            # Store mapping in the format requested: visible_text -> {"class": "", "id": "", "selectors": ""}
            mapping[final_text] = {
                'class': element_info.get('class', ''),
                'id': element_info.get('id', ''),
                'selectors': element_info['css_selector'],
                'fallback_selector': element_info.get('fallback_selector', element_info['css_selector']),
                'text_xpath': element_info.get('text_xpath', ''),
                # Additional info for internal use
                'element_type': element_type,
                'deterministic_id': element_id,
                'original_text': text
            }
            
            logger.debug(f"Mapped '{final_text}' -> {element_info['css_selector']}")
        
        return mapping
    
    def find_element_by_text(self, mapping: Dict[str, Dict], target_text: str) -> Optional[Dict]:
        """Find element by text with intelligent fuzzy matching and contextual understanding."""
        if not target_text or not mapping:
            return None
        
        target_lower = target_text.lower().strip()
        
        # Strategy 1: Exact match (case-insensitive)
        for text, element_info in mapping.items():
            if text.lower() == target_lower:
                logger.debug(f"Exact match found: '{target_text}' -> '{text}'")
                return element_info
        
        # Strategy 2: Check if target looks like an element ID or name attribute
        # and try to find elements with matching ID/name in their selectors
        if target_text.replace('_', '').replace('-', '').isalnum():
            for text, element_info in mapping.items():
                selectors = element_info.get('selectors', '')
                # Check if the selector contains the target as an ID or name
                if f"#{target_text}" in selectors or f'[name="{target_text}"]' in selectors or f'[id="{target_text}"]' in selectors:
                    logger.debug(f"ID/name match found: '{target_text}' -> '{text}' (selector: {selectors})")
                    return element_info
        
        # Strategy 3: Fuzzy text matching - check if target is contained in element text
        best_match = None
        best_score = 0.0
        
        for text, element_info in mapping.items():
            text_lower = text.lower()
            
            # Calculate different types of matches
            scores = []
            
            # Substring match (both directions)
            if target_lower in text_lower:
                scores.append(len(target_lower) / len(text_lower))
            if text_lower in target_lower:
                scores.append(len(text_lower) / len(target_lower))
            
            # Word-based matching
            target_words = set(target_lower.split())
            text_words = set(text_lower.split())
            
            if target_words and text_words:
                # Calculate Jaccard similarity (intersection over union)
                intersection = len(target_words & text_words)
                union = len(target_words | text_words)
                if union > 0:
                    jaccard_score = intersection / union
                    scores.append(jaccard_score)
                
                # Calculate word overlap score
                overlap_score = intersection / max(len(target_words), len(text_words))
                scores.append(overlap_score)
            
            # Take the best score for this element
            if scores:
                element_score = max(scores)
                if element_score > best_score and element_score > 0.3:  # Minimum threshold
                    best_match = element_info
                    best_score = element_score
                    best_text = text
        
        if best_match:
            logger.debug(f"Fuzzy match found: '{target_text}' -> '{best_text}' (score: {best_score:.2f})")
            return best_match
        
        # Strategy 4: Try partial word matching with common form field patterns
        # Look for elements where target text might be related to form field labels
        target_words = target_lower.split()
        if len(target_words) == 1:  # Single word target
            word = target_words[0]
            
            for text, element_info in mapping.items():
                text_lower = text.lower()
                
                # Check for common patterns like:
                # "firstName" matching "First Name"
                # "emailAddress" matching "Email Address" 
                # "phoneNumber" matching "Phone Number"
                
                # Split camelCase or snake_case
                import re
                word_parts = re.findall(r'[a-z]+|[A-Z][a-z]*', word)
                word_parts = [part.lower() for part in word_parts if part]
                
                if word_parts:
                    # Check if all parts of the target word appear in the element text
                    parts_found = sum(1 for part in word_parts if part in text_lower)
                    if parts_found >= len(word_parts) * 0.7:  # At least 70% of parts match
                        score = parts_found / len(word_parts)
                        if score > best_score:
                            best_match = element_info
                            best_score = score
                            best_text = text
        
        if best_match:
            logger.debug(f"Pattern match found: '{target_text}' -> '{best_text}' (score: {best_score:.2f})")
            return best_match
        
        logger.debug(f"No match found for: '{target_text}'")
        return None 