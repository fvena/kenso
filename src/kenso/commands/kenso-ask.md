---
name: kenso-ask
description: "Answer questions about the project using the kenso knowledge base. Use when the user asks about how something works, what the rules are, where something is implemented, or any question that could be answered by the project's documentation."
---

# kenso-ask

Answer a question about this project using the kenso knowledge base.

## Prerequisites

The kenso index must exist. If `kenso search` returns "No documents indexed",
tell the user to run `kenso ingest <path>` first.

## Instructions

When the user asks a question after invoking this command:

### 1. Analyze the question

Determine what the user is asking about. Classify the query:
- **Entity:** "What is X?" — search for the entity name
- **Process:** "How does X work?" — search for process terms and workflows
- **Rule:** "What are the rules for X?" — search with category filter on rules
- **Implementation:** "How is X implemented?" — search across codebase and knowledge
- **Integration:** "How does X connect to Y?" — search integrations
- **General:** anything else — broad search

### 2. Search the knowledge base

Run kenso search to find relevant documents:
```bash
kenso search "<key terms from the question>" --json --limit 5
```

If the query type suggests a specific category, add the filter:
```bash
kenso search "<terms>" --json --limit 5 --category <category>
```

#### Evaluating results

Check the `cascade_stage` and `relevance` fields in search results:
- Results from the `AND` stage with `high` relevance are strong matches
- Results from the `OR` stage with `low` relevance are likely noise — do not
  use them as sources for your answer
- If all results have `low` relevance, tell the user the KB doesn't cover
  this topic instead of synthesizing from weak matches

If the first search returns no results or irrelevant results, try:
- Different terms (synonyms, more specific, more general)
- Removing the category filter
- Splitting into multiple focused searches

### 3. Read relevant documents

For the top 2-3 results, read the full document or the specific section
indicated by the chunk title:
```bash
cat <path to document>
```

If the chunk title indicates a specific section (e.g., "Settlement > Failed
Trade Handling"), read just that section instead of the full file.

### 4. Synthesize the answer

Compose an answer that:
- **Leads with the answer**, not with context or caveats
- **Cites specific sources** using the format: `docs/path/file.md > Section Name`
- **Mentions related documents** the user might want to explore
- **Stays concise** — answer the question, don't write an essay
- **Never fabricates information** — only state what the documents say

If the search found nothing relevant, say:
"I couldn't find information about this in the knowledge base. The KB may not
cover this topic. You can check what's indexed with `kenso stats`."

### 5. Suggest follow-ups (optional)

If the answer naturally leads to related questions, briefly suggest them:
"You might also want to know about [related topic] — try asking about that."

## Input

$ARGUMENTS
