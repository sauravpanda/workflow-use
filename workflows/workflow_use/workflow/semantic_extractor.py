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
        """Find element in mapping by text with fuzzy matching."""
        target_normalized = self._normalize_text(target_text)
        
        # Exact match first
        if target_normalized in mapping:
            return mapping[target_normalized]
        
        # Case-insensitive exact match
        target_lower = target_normalized.lower()
        for text, element_info in mapping.items():
            if text.lower() == target_lower:
                return element_info
        
        # Partial match - but be more restrictive
        best_match = None
        best_score = 0
        
        for text, element_info in mapping.items():
            text_lower = text.lower()
            
            # Skip very short text matches (they're often generic like "on", "off", etc.)
            if len(text.strip()) <= 2:
                continue
                
            # Skip if the text is just a generic placeholder or fallback
            if text.startswith('[') and text.endswith(']'):
                continue
            
            # Check for meaningful substring matches
            score = 0
            if target_lower in text_lower:
                # Target is contained in the element text - good match
                score = len(target_lower) / len(text_lower)
                if score > 0.3:  # At least 30% of the element text matches
                    if score > best_score:
                        best_match = element_info
                        best_score = score
            elif text_lower in target_lower:
                # Element text is contained in target - only good if element text is meaningful
                if len(text.strip()) >= 4:  # At least 4 characters for meaningful match
                    score = len(text_lower) / len(target_lower)
                    if score > 0.4:  # At least 40% of the target matches
                        if score > best_score:
                            best_match = element_info
                            best_score = score
        
        if best_match:
            # Find the corresponding text key for logging
            matched_text = ""
            for text, element_info in mapping.items():
                if element_info == best_match:
                    matched_text = text
                    break
            logger.info(f"Fuzzy matched '{target_text}' to '{matched_text}' (score: {best_score:.2f})")
            return best_match
        
        # Word-based overlap matching as final fallback
        target_words = set(target_normalized.lower().split())
        
        for text, element_info in mapping.items():
            # Skip very short text
            if len(text.strip()) <= 2:
                continue
                
            text_words = set(text.lower().split())
            overlap = len(target_words.intersection(text_words))
            
            # Require at least 2 words to overlap, or 1 word if it's significant
            if overlap >= 2 or (overlap == 1 and max(len(w) for w in target_words.intersection(text_words)) >= 4):
                score = overlap / max(len(target_words), len(text_words))
                
                if score > best_score and score > 0.4:  # At least 40% word overlap
                    best_match = element_info
                    best_score = score
        
        if best_match:
            # Find the corresponding text key for logging
            matched_text = ""
            for text, element_info in mapping.items():
                if element_info == best_match:
                    matched_text = text
                    break
            logger.info(f"Word-based fuzzy matched '{target_text}' to '{matched_text}' (score: {best_score:.2f})")
            return best_match
        
        return None 