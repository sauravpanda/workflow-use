# Text-Only Workflow Architecture

## **Core Principle: Zero CSS Selectors in Workflows**

The system now follows a **pure text-based approach** where workflows store **ONLY** visible text and context hints. CSS selectors are **never stored in workflows** - they are generated fresh at runtime.

## **Architecture Overview**

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   WORKFLOW      │    │   RUNTIME        │    │   EXECUTION     │
│   (Text Only)   │───▶│   MAPPING        │───▶│   (Selectors)   │
│                 │    │   GENERATION     │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### **1. Workflow Storage (Text-Only)**
```json
{
  "type": "click",
  "target_text": "Submit (in Personal Information)",
  "container_hint": "Personal Information",
  "position_hint": "item 2 of 3",
  "interaction_type": "form_submit"
}
```

**What's Stored:**
- ✅ `target_text`: Visible/accessible text with context
- ✅ `container_hint`: Text-based container context
- ✅ `position_hint`: Text-based position context
- ✅ `interaction_type`: Semantic interaction type
- ❌ ~~`cssSelector`~~ (too brittle)
- ❌ ~~`xpath`~~ (too brittle)
- ❌ ~~`hierarchical_selector`~~ (too brittle)

### **2. Runtime Semantic Mapping**
At execution time, the semantic extractor:
1. **Scans current page** for all interactive elements
2. **Generates fresh CSS selectors** with hierarchical context
3. **Creates text-to-selector mapping** with fallback strategies
4. **Provides multiple selector options** for each text identifier

### **3. Element Resolution Process**
```
target_text: "Submit (in Personal Information)"
     ↓
1. Direct text match in mapping
2. Hierarchical context matching using container_hint
3. Position-based matching using position_hint
4. Fuzzy text matching (partial, word overlap)
5. Fallback selector strategies
```

## **Updated Components**

### **Schema (views.py)**
```python
class SelectorWorkflowSteps(BaseWorkflowStep):
    # PRIMARY: Text-based semantic targeting (non-brittle)
    target_text: str = Field(..., description='Visible text with context')
    
    # OPTIONAL: Context hints for disambiguation (text, not selectors)
    container_hint: Optional[str] = Field(None, description='Container context')
    position_hint: Optional[str] = Field(None, description='Position context')
    interaction_type: Optional[str] = Field(None, description='Interaction type')
    
    # LEGACY: Kept for backward compatibility but discouraged
    cssSelector: Optional[str] = Field(None, description='[LEGACY] Avoid in new workflows')
```

### **Recorder (recorder.py)**
```python
@dataclass
class ClickEvent(BaseEvent):
    target_text: str = ""  # Primary identifier
    container_hint: str = ""  # e.g., "Personal Information"
    position_hint: str = ""   # e.g., "item 2 of 3"
    interaction_type: str = ""  # e.g., "form_submit"
    # Legacy fields for backward compatibility only
    css_selector: Optional[str] = None
```

### **Semantic Converter (semantic_converter.py)**
- Extracts **text-based context hints** from semantic info
- Creates **contextual target text** like "Submit (in Personal Information)"
- **Avoids storing any CSS selectors** in converted workflows

### **Executor (semantic_executor.py)**
- Uses **text-based hints** to improve element resolution
- Tries **multiple fallback strategies** when text matches multiple elements
- Generates **fresh selectors at runtime** for reliability

## **Context Disambiguation Examples**

### **Multiple Submit Buttons**
```json
// Workflow stores:
{"target_text": "Submit (in Personal Information)", "container_hint": "Personal Information"}
{"target_text": "Submit (in Billing Information)", "container_hint": "Billing Information"}

// Runtime resolves to specific selectors:
"#personal-info-section button[type='submit']"
"#billing-section button[type='submit']"
```

### **Repeated Table Actions**
```json
// Workflow stores:
{"target_text": "Edit (item 2 of 3)", "position_hint": "item 2 of 3"}

// Runtime resolves to:
"tbody tr:nth-child(2) .edit-button"
```

### **Form Fields in Different Sections**
```json
// Workflow stores:
{"target_text": "First Name (in Personal Information)", "container_hint": "Personal Information"}
{"target_text": "First Name (in Billing Address)", "container_hint": "Billing Address"}

// Runtime resolves to:
"#personal-section input[name='firstName']"
"#billing-section input[name='firstName']"
```

## **Benefits of Text-Only Approach**

### **1. Maximum Robustness**
- ✅ Works across different page layouts
- ✅ Survives CSS class name changes
- ✅ Adapts to DOM structure modifications
- ✅ Handles dynamic content

### **2. Human Readability**
- ✅ Workflows are self-documenting
- ✅ Easy to understand what each step does
- ✅ Simple to modify and maintain
- ✅ Clear debugging information

### **3. Scalability**
- ✅ Works with complex forms with repeated elements
- ✅ Handles dynamic applications (SPAs, React, etc.)
- ✅ Adapts to A/B testing and design changes
- ✅ Future-proof against UI updates

### **4. Debugging Clarity**
- ✅ Clear error messages with available elements
- ✅ Context-aware element suggestions
- ✅ Hierarchical fallback information
- ✅ Human-readable execution logs

## **Migration Path**

### **Existing Workflows**
- **Legacy CSS selectors** are preserved for backward compatibility
- **Gradual migration** to text-based approach recommended
- **Automatic conversion tools** available in semantic converter

### **New Workflows**
- **Must use text-only approach** with `target_text` as primary identifier
- **CSS selectors discouraged** and marked as legacy
- **Context hints encouraged** for disambiguation

## **Runtime Execution Flow**

```
1. Load workflow (text-only)
2. Navigate to page
3. Extract semantic mapping (text → selectors)
4. For each step:
   a. Find element by target_text
   b. Use context hints for disambiguation
   c. Apply fallback strategies if needed
   d. Execute action with resolved selector
   e. Verify action success
```

This architecture ensures **maximum reliability** while maintaining **human readability** and **future adaptability**. 