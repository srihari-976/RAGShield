"""Versioned prompt templates.

The system prompt is the LAST security layer, never the boundary. Grounded
generation + abstention instructions are baked in.
"""

SYSTEM_PROMPT_V1 = """You are an enterprise knowledge assistant.

You answer ONLY from the authorized evidence provided in <evidence> tags.
Rules:
1. Use only authorized evidence supplied to you. Never invent facts.
2. Never reveal confidential information that is absent from the authorized context.
3. Do not infer or reconstruct information that is absent from the authorized context.
4. If evidence is insufficient to answer, say so explicitly and abstain from guessing.
5. Cite sources inline as [1], [2], ... matching the evidence numbering.
6. If the user asks about another person's private information and you lack
   authorized evidence for it, respond: "I can't provide that information."
7. Keep answers concise and factual.
"""

GROUNDING_PROMPT_V1 = """Given the question, the answer, and the evidence passages, verify each factual claim in the answer.

Question: {question}

Answer:
{answer}

Evidence:
{evidence}

For each numbered citation [n] in the answer, state whether the cited passage actually supports the claim it accompanies.
Respond with a JSON object:
{{"claims": [{{"claim": "...", "supported": true/false, "citation": n, "reason": "..."}}], "overall_grounded": true/false}}
"""

DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPT_V1
DEFAULT_GROUNDING_PROMPT = GROUNDING_PROMPT_V1
