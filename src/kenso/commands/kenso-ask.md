<!--kenso-metadata
codex_description: "Answer questions about the project using the kenso knowledge base. Use when the user asks about how something works, what the rules are, where something is implemented, or any question that could be answered by the project's documentation. Do not use for creating tasks, brainstorming, or explaining specific code snippets."
codex_short_description: "Ask questions about your docs"
-->

# kenso-ask

Answer a question about this project using the kenso knowledge base.

## Instructions

You have access to the kenso CLI (`kenso search`) to find relevant documentation.

1. **Parse the user's question** — identify what they're asking about.

2. **Classify the query type** to choose a search strategy:
   - Entity query ("what is X?") → search for entity name
   - Process query ("how does X work?") → search for process terms
   - Rule query ("what are the rules for X?") → search in rules
   - Implementation query ("how is X implemented?") → search codebase + knowledge
   - Integration query ("how does X connect to Y?") → search integrations
   - General / unclear → broad search

3. **Search the knowledge base:**
   ```bash
   kenso search "<terms>"
   ```
   Run additional searches if the first results are insufficient or the question
   spans multiple topics.

4. **Read full documents** for the top results to get complete context.

5. **Synthesize an answer** that:
   - Leads with the direct answer (not the context)
   - Cites specific documents and sections as sources
   - Mentions related documents the user might want to explore
   - Stays concise — answer the question, don't over-explain

## Input

$ARGUMENTS
