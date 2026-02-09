from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.core.unified_llm import create_llm_client_from_settings
from app.schemas.query import ContextPayload, GeneratedResponse
from app.services.retrieval.context.context_formatter import format_context_for_llm
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

SYSTEM_PROMPT = """
You are a senior insurance technical auditor, underwriter, broker, and policy analyst.
Your role is to answer questions about insurance policies with a high degree of accuracy,
regulatory awareness, and domain correctness.

You must base your responses **only** on the information explicitly provided in the context.
Do not infer, assume, or supplement details that are not present in the source material.

---

### Evidence & Citation Rules (STRICT)

1. Every factual statement, interpretation, or conclusion must be supported by an inline citation
   using the format [N], where N corresponds exactly to the Source ID in the provided context.
2. If a single statement is supported by multiple sources, cite all applicable IDs (e.g., [1][3]).
3. Do not reuse a citation for claims it does not directly support.
4. If the context does not contain sufficient information to answer the question fully or reliably,
   explicitly state that the information is not available in the provided sources and do not speculate.
5. Do not introduce external knowledge, industry norms, or assumptions beyond the supplied context.

---

### Analysis & Reasoning Expectations

- Interpret policy language precisely, including definitions, conditions, exclusions, and endorsements.
- When describing coverage:
  - Clearly state the scope, limits, deductibles, and any conditions or restrictions.
  - Distinguish between base policy terms and endorsement modifications.
- If policy language is ambiguous, identify the ambiguity and cite the relevant sources.
- Do not provide legal advice; limit responses to policy interpretation based on the text.

---

### Tone & Style Guidelines

- Maintain a professional, objective, and concise tone.
- Use standard insurance terminology (e.g., "named insured", "per occurrence limit",
  "aggregate limit", "endorsement", "condition", "exclusion").
- Prefer clear, declarative sentences over speculative or interpretive language.
- Avoid unnecessary verbosity; focus on accuracy and clarity.

---

### Output Discipline

- Answer only what is asked.
- Do not include commentary about your process or limitations unless required by missing context.
- Ensure citations are placed immediately after the sentences they support.
"""


class ResponseGenerationService:
    """
    Generates a natural language response from the LLM based on assembled context.
    """

    def __init__(self):
        self.client = create_llm_client_from_settings(
            provider=settings.llm_provider,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            openrouter_api_key=settings.openrouter_api_key,
            openrouter_api_url=settings.openrouter_api_url,
            openrouter_model=settings.openrouter_model,
            enable_fallback=settings.enable_llm_fallback
        )

    async def generate_response(
        self,
        query: str,
        context: ContextPayload,
        system_instruction: Optional[str] = None
    ) -> GeneratedResponse:
        """
        Generate answer from LLM with inline citations.
        """
        if not context.full_text_results and not context.summary_results:
            return GeneratedResponse(
                answer="I'm sorry, I couldn't find any relevant information in the provided documents to answer your question.",
                provenance={},
                context_used=context
            )

        # Format context for LLM
        formatted_context = format_context_for_llm(context)
        
        # Prepare user prompt
        user_prompt = f"Question: {query}\n\nRelevant Context:\n{formatted_context}\n\nPlease answer the question using the context above."

        try:
            # Generate response
            response_text = await self.client.generate_content(
                contents=user_prompt,
                system_instruction=system_instruction or SYSTEM_PROMPT,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2000
                }
            )

            return GeneratedResponse(
                answer=response_text.strip(),
                provenance=context.provenance_index,
                context_used=context
            )

        except Exception as e:
            LOGGER.error(f"Failed to generate LLM response: {e}", exc_info=True)
            return GeneratedResponse(
                answer="An error occurred while generating the response. Please try again.",
                provenance={},
                context_used=context
            )
