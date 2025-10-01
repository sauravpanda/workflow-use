# Semantic-Based Web Automation: Non-AI Approach

## Table of Contents
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Semantic Extraction Process](#semantic-extraction-process)
5. [Semantic Execution Engine](#semantic-execution-engine)
6. [Workflow Recording & Conversion](#workflow-recording--conversion)
7. [Key Advantages](#key-advantages) 
8. [Optimization Opportunities](#optimization-opportunities)
9. [Implementation Examples](#implementation-examples)
10. [Technical Deep Dive](#technical-deep-dive)

## Overview

The Semantic-Based Web Automation system provides **AI-free**, **deterministic** web automation by using **visible text** and **semantic context** to identify and interact with web elements, rather than relying on fragile CSS selectors or XPath expressions.

### Key Principle
Instead of targeting elements with brittle selectors like:
```css
button.px-4.py-2.bg-blue-500.hover:bg-blue-600.text-white.rounded-md.transition-colors
```

The system uses human-readable text identifiers:
```json
{
  "type": "click",
  "target_text": "Submit Application",
  "description": "Click the submit button"
}
```

## System Architecture

The system consists of four main phases:

1. **Recording Phase**: Browser extension captures user interactions with semantic context
2. **Conversion Phase**: Recorded workflows are converted to semantic format  
3. **Extraction Phase**: Live DOM is analyzed to create semantic mappings
4. **Execution Phase**: Workflows are executed using semantic text targeting

## Core Components

### 1. SemanticExtractor (`semantic_extractor.py`)
**Purpose**: Maps visible text to deterministic CSS selectors

**Key Responsibilities**:
- Scans DOM for interactive elements (inputs, buttons, links, etc.)
- Extracts meaningful text using multiple strategies
- Creates fallback selectors and XPath expressions
- Generates deterministic element mappings

### 2. SemanticWorkflowExecutor (`semantic_executor.py`) 
**Purpose**: Executes workflows using semantic text mappings

**Key Responsibilities**:
- Refreshes semantic mappings for each page
- Finds elements by visible text with fuzzy matching
- Provides fallback strategies for element location
- Handles verification and retry logic

### 3. SemanticWorkflowConverter (`semantic_converter.py`)
**Purpose**: Converts recorded workflows to semantic format

**Key Responsibilities**:
- Extracts semantic identifiers from recorded steps
- Prioritizes meaningful text over CSS selectors  
- Maintains backward compatibility with existing workflows

### 4. Browser Extension (`content.ts`)
**Purpose**: Records user interactions with semantic context

**Key Responsibilities**:
- Captures element interactions during recording
- Extracts semantic information (labels, placeholders, aria-labels)
- Provides rich context for element identification

## Semantic Extraction Process

### Phase 1: DOM Element Discovery
The system identifies interactive elements using comprehensive selectors:

```javascript
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
```

### Phase 2: Text Extraction Hierarchy
For each element, the system extracts meaningful text using this priority order:

1. **Label Text** - Associated `<label>` elements
2. **Text Content** - Direct text content of the element
3. **Placeholder** - Input placeholder attribute  
4. **Title** - Title attribute
5. **ARIA Label** - aria-label attribute
6. **Value** - Input value attribute
7. **Name** - Name attribute
8. **ID** - Element ID attribute

### Phase 3: Selector Generation
The system creates multiple selector formats for reliability:

```python
# Primary selector (most specific)
selector = "#elementId" if has_id else "input[name='fieldName'][type='text']"

# Fallback selector (simplified)
fallback_selector = "input[name='fieldName']"

# Text-based XPath (semantic)
text_xpath = "//input[@placeholder='Enter your name']"
```

### Phase 4: Duplicate Handling
When multiple elements have similar text, the system adds contextual information:

```python
"Submit" → "Submit (at 150,300)"
"Save" → "Save (in Settings Panel)"  
"Cancel" → "Cancel (id:cancelBtn)"
```

## Semantic Execution Engine

### Element Location Strategy

The executor uses a multi-stage fallback approach:

```python
def find_element_by_text(self, target_text: str):
    # Strategy 1: Exact text match
    if exact_match_found:
        return element_info
    
    # Strategy 2: Direct selector (ID/name)
    if looks_like_identifier(target_text):
        return try_direct_selector(target_text)
    
    # Strategy 3: Fuzzy text matching
    return fuzzy_match_with_scoring(target_text)
```

### Matching Algorithms

**1. Exact Match**
```python
target_lower = target_text.lower().strip()
for text, element_info in mapping.items():
    if text.lower() == target_lower:
        return element_info
```

**2. Substring Matching**
```python
if target_lower in text_lower or text_lower in target_lower:
    return element_info
```

**3. Word Overlap Scoring**
```python
target_words = set(target_text.lower().split())
text_words = set(element_text.lower().split())
overlap = len(target_words & text_words)
score = overlap / max(len(target_words), len(text_words))
```

**4. Jaccard Similarity**
```python
intersection = len(target_words & text_words)
union = len(target_words | text_words)
jaccard_score = intersection / union if union > 0 else 0
```

### Intelligent Element Interaction

The system adapts interaction methods based on element type:

```python
async def _click_element_intelligently(self, selector, target_text, element_info):
    if element_type == "radio" or element_type == "checkbox":
        # Handle form controls specially
        return await self._handle_radio_checkbox_input(selector, value, target_text, element_type)
    elif "button" in selector.lower():
        # Use force click for buttons that might be covered
        await locator.click(force=True)
    else:
        # Standard click for other elements
        await locator.click()
```

## Workflow Recording & Conversion

### Extension-Side Recording

The browser extension captures rich semantic information during recording:

```typescript
function extractSemanticInfo(element: HTMLElement) {
    return {
        labelText: findAssociatedLabel(element),
        placeholder: element.placeholder,
        ariaLabel: element.getAttribute('aria-label'),
        textContent: element.textContent?.trim(),
        name: element.name,
        id: element.id,
        parentContext: extractParentContext(element)
    };
}
```

### Conversion Process

The converter transforms recorded steps into semantic format:

```python
def _extract_semantic_target_text(self, step):
    # Priority order for semantic targeting:
    # 1. targetText (if already captured by extension)
    # 2. elementText (visible text content)  
    # 3. Extract from semanticInfo if available
    # 4. Extract meaningful text from element attributes
    
    if step.get("targetText"):
        return step["targetText"].strip()
    
    semantic_info = step.get("semanticInfo", {})
    for field in ["labelText", "placeholder", "ariaLabel", "textContent", "name", "id"]:
        value = semantic_info.get(field, "").strip()
        if value and len(value) < 100:
            return value
```

## Key Advantages

### 1. **Resilience to UI Changes**
- Survives CSS class name changes
- Survives DOM structure modifications  
- Survives styling framework updates
- Works across different responsive breakpoints

### 2. **Human-Readable Workflows**
```json
{
  "description": "Enter first name",
  "type": "input", 
  "target_text": "First Name",
  "value": "John"
}
```
vs brittle CSS:
```json
{
  "type": "input",
  "cssSelector": "div.form-group:nth-child(1) > input.form-control.px-3.py-2.border.border-gray-300"
}
```

### 3. **Zero AI/LLM Dependencies**
- **Deterministic**: Same input always produces same output
- **Fast**: No API calls or model inference
- **Cost-effective**: No token consumption
- **Privacy-friendly**: No data sent to external services
- **Offline-capable**: Works without internet connection

### 4. **Multi-Language Support**
The system works with any language since it uses visible text:
```json
{"target_text": "Отправить"} // Russian
{"target_text": "送信"} // Japanese  
{"target_text": "Enviar"} // Spanish
```

### 5. **Cross-Framework Compatibility**
Works with any web framework (React, Vue, Angular, etc.) since it targets final rendered text, not framework-specific classes.

## Optimization Opportunities

### 1. **Caching & Performance**

**Current State**: Semantic mapping is regenerated on every page
**Optimization**: Implement smart caching based on DOM structure hash

```python
class OptimizedSemanticExtractor:
    def __init__(self):
        self.mapping_cache = {}
        self.dom_hash_cache = {}
    
    async def extract_semantic_mapping(self, page):
        dom_hash = await self._compute_dom_hash(page)
        if dom_hash in self.mapping_cache:
            return self.mapping_cache[dom_hash]
        
        mapping = await self._extract_fresh_mapping(page)
        self.mapping_cache[dom_hash] = mapping
        return mapping
```

### 2. **Improved Element Prioritization**

**Current State**: Basic element type counters
**Optimization**: Contextual prioritization based on page structure

```python
def _prioritize_elements(self, elements):
    # Prioritize elements inside forms
    # Prioritize elements with better accessibility attributes
    # Prioritize elements in main content areas vs sidebars
    return sorted(elements, key=self._element_importance_score, reverse=True)
```

### 3. **Enhanced Fuzzy Matching**

**Current State**: Basic word overlap and substring matching
**Optimization**: Advanced NLP-free semantic similarity

```python
class EnhancedTextMatcher:
    def __init__(self):
        self.common_synonyms = {
            'submit': ['send', 'save', 'apply'],
            'cancel': ['close', 'dismiss', 'abort'],
            'name': ['title', 'label', 'heading']
        }
    
    def enhanced_similarity_score(self, target, candidate):
        # Include synonym matching
        # Handle common abbreviations
        # Account for pluralization
        pass
```

### 4. **Predictive Element Mapping**

**Current State**: Reactive mapping on page load
**Optimization**: Predictive mapping based on common patterns

```python
class PredictiveMapper:
    def __init__(self):
        self.pattern_database = self._load_common_patterns()
    
    def predict_likely_elements(self, page_url, page_title):
        # Predict likely form fields based on page context
        # Pre-generate selectors for common patterns
        # Reduce mapping time for known page types
        pass
```

### 5. **Selector Optimization**

**Current State**: Multiple selector formats generated
**Optimization**: Machine learning-free selector ranking

```python
def rank_selectors_by_reliability(self, selectors):
    scores = {}
    for selector in selectors:
        score = 0
        # ID-based selectors: highest score
        if selector.startswith('#'):
            score += 100
        # Name-based: medium score  
        elif '[name=' in selector:
            score += 50
        # Class-based: lower score based on class stability
        elif '.' in selector:
            score += self._calculate_class_stability(selector)
        
        scores[selector] = score
    
    return sorted(selectors, key=lambda s: scores[s], reverse=True)
```

## Implementation Examples

### Example 1: Government Form Automation

**Workflow Definition**:
```json
{
  "name": "Government Form - Semantic Version",
  "steps": [
    {
      "type": "navigation",
      "url": "https://example.gov/application"
    },
    {
      "type": "input",
      "target_text": "First Name (Given Name) *",
      "value": "{first_name}"
    },
    {
      "type": "input", 
      "target_text": "Last Name (Family Name) *",
      "value": "{last_name}"
    },
    {
      "type": "click",
      "target_text": "Male"
    },
    {
      "type": "click",
      "target_text": "Single"
    },
    {
      "type": "click",
      "target_text": "Next: Contact Information"
    }
  ]
}
```

**Generated Semantic Mapping**:
```python
{
  "First Name (Given Name) *": {
    "selectors": "input[name='firstName'][type='text']",
    "fallback_selector": "input[name='firstName']",
    "text_xpath": "//input[@placeholder='First Name (Given Name) *']",
    "element_type": "input",
    "deterministic_id": "input_1"
  },
  "Male": {
    "selectors": "input[type='radio'][name='gender'][value='male']",
    "fallback_selector": "input[name='gender'][value='male']", 
    "text_xpath": "//input[@value='male']",
    "element_type": "radio",
    "deterministic_id": "radio_1"
  }
}
```

### Example 2: Complex Form with Dynamic Elements

**HTML Structure**:
```html
<form class="dynamic-form">
  <div class="field-group">
    <label for="email-field">Email Address</label>
    <input id="email-field" name="email" type="email" placeholder="Enter your email">
    <span class="validation-message"></span>
  </div>
  
  <div class="radio-group">
    <span class="group-label">Preferred Contact Method</span>
    <label class="radio-item">
      <input type="radio" name="contact" value="email">
      <span>Email</span> 
    </label>
    <label class="radio-item">
      <input type="radio" name="contact" value="phone">
      <span>Phone</span>
    </label>
  </div>
</form>
```

**Extraction Process**:
```python
# Step 1: Element Discovery
elements = await page.evaluate("""
  () => {
    return Array.from(document.querySelectorAll('input, button, select, textarea')).map(el => ({
      tag: el.tagName,
      type: el.type,
      id: el.id,
      name: el.name,
      placeholder: el.placeholder,
      // ... extract all relevant attributes
    }));
  }
""")

# Step 2: Text Extraction
for element_info in elements:
    if element_info['id']:
        label = find_label_for_id(element_info['id'])
        if label:
            text = label.textContent
    
    # Apply text extraction hierarchy...

# Step 3: Mapping Generation  
mapping = {
  "Email Address": {
    "selectors": "#email-field",
    "fallback_selector": "input[name='email']",
    "element_type": "input"
  },
  "Email": {  # Radio button option
    "selectors": "input[type='radio'][name='contact'][value='email']",
    "fallback_selector": "input[name='contact'][value='email']",
    "element_type": "radio"
  }
}
```

## Technical Deep Dive

### Element Type Detection Logic

```python
def _get_element_type_and_id(self, element_info):
    tag = element_info.get('tag', '').lower()
    input_type = element_info.get('type', '').lower()
    role = element_info.get('role', '').lower()
    
    # Classification hierarchy
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
    
    # Generate deterministic ID
    self.element_counters[element_type] += 1
    element_id = f"{element_type}_{self.element_counters[element_type]}"
    
    return element_type, element_id
```

### Verification and Retry Mechanism

```python
async def _execute_with_verification_and_retry(self, step_executor, step, verification_method):
    """Execute step with verification and retry logic."""
    
    for attempt in range(self.max_retries):
        try:
            # Execute the step
            result = await step_executor()
            
            # Verify the action was successful
            if verification_method:
                verification_passed = await verification_method()
                if verification_passed:
                    logger.info(f"Step executed successfully on attempt {attempt + 1}")
                    return result
                else:
                    logger.warning(f"Step verification failed on attempt {attempt + 1}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1)  # Wait before retry
                        await self._refresh_semantic_mapping()  # Refresh mapping
                        continue
                    else:
                        raise Exception(f"Step verification failed after {self.max_retries} attempts")
            else:
                return result
                
        except Exception as e:
            logger.error(f"Step execution failed on attempt {attempt + 1}: {e}")
            if attempt < self.max_retries - 1:
                await asyncio.sleep(1)
                await self._refresh_semantic_mapping()
                continue
            else:
                raise e
```

## Conclusion

The Semantic-Based Web Automation system represents a **paradigm shift** from fragile, technical selectors to **human-readable, resilient text-based targeting**. By leveraging visible text and semantic context instead of AI/LLM processing, it provides:

- **Deterministic behavior** with zero external dependencies
- **High resilience** to UI changes and framework updates
- **Human-readable workflows** that non-technical users can understand
- **Cost-effective operation** with no API or token costs
- **Fast execution** with optimizable performance characteristics

The system's **non-AI approach** proves that sophisticated web automation can be achieved through **clever algorithms** and **semantic understanding** without requiring machine learning models or large language models. This makes it ideal for **enterprise environments** where **predictability**, **cost control**, and **data privacy** are paramount.

## Next Steps for Implementation

1. **Implement caching optimizations** for production performance
2. **Add cross-framework testing** with major web frameworks  
3. **Expand fuzzy matching algorithms** for better text similarity
4. **Create browser-specific optimizations** for maximum compatibility
5. **Develop monitoring tools** for semantic mapping quality assessment 