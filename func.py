import io
import json
import logging

import oci
from pypdf import PdfReader
from fdk import response
from oci.generative_ai_inference.models import (
    ChatDetails,
    GenericChatRequest,
    OnDemandServingMode,
    SystemMessage,
    TextContent,
    UserMessage,
)

logger = logging.getLogger(__name__)

COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a"
REGION = "us-phoenix-1"
BUCKET_NAME = "agent-knowledge-base"
NAMESPACE = "axzkbtajofjq"
MODEL_ID = "google.gemini-2.5-flash"

# Minimum characters of extracted text to consider a report as having data.
# Empty JDE Integrity Reports still have headers/footers (~100-200 chars).
MIN_CONTENT_LENGTH = 300

SYSTEM_PROMPT = (
    "You are a JD Edwards Integrity Report analyst. "
    "When given an Integrity Report with data, analyze it thoroughly. "
    "Identify the specific integrity issues found, explain what each problem "
    "means in JDE context, and recommend the corrective actions or fixes. "
    "Acommodate the response to the content of the report — if it is very long, focus on summarizing key issues. It should not be a response with more than 850 words. "
    "Structure your response with: 1) Summary of findings, "
    "2) Detailed problems identified, 3) Recommended fixes."
)

DEFAULT_ANALYSIS_PROMPT = "Analyze this Integrity Report. Identify all problems and recommend fixes."


def handler(ctx, data: io.BytesIO = None):
    try:
        body = json.loads(data.getvalue()) if data else {}
        object_name = body.get("object_name", "")
        prompt = body.get("prompt", "") or DEFAULT_ANALYSIS_PROMPT

        if not object_name:
            return response.Response(
                ctx,
                response_data=json.dumps({"error": "Missing 'object_name' in request body"}),
                headers={"Content-Type": "application/json"},
                status_code=400,
            )

        # ── Step 1: Download PDF and extract text (code-based checker) ──
        signer = oci.auth.signers.get_resource_principals_signer()
        os_client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)

        try:
            obj = os_client.get_object(NAMESPACE, BUCKET_NAME, object_name)
            pdf_bytes = obj.data.content
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                return response.Response(
                    ctx,
                    response_data=json.dumps({"error": f"Object '{object_name}' not found in bucket"}),
                    headers={"Content-Type": "application/json"},
                    status_code=404,
                )
            raise

        reader = PdfReader(io.BytesIO(pdf_bytes))
        full_text = ""
        for page in reader.pages:
            full_text += (page.extract_text() or "")

        has_data = len(full_text.strip()) > MIN_CONTENT_LENGTH
        checker_text = "Yes" if has_data else "No"

        # ── Step 2: Analyze with LLM (only if report has data) ────────
        if has_data:
            ai_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                config={}, signer=signer
            )
            user_message = f"{prompt}\n\n--- DOCUMENT: {object_name} ---\n\n{full_text}"

            chat_response = ai_client.chat(
                ChatDetails(
                    compartment_id=COMPARTMENT_ID,
                    serving_mode=OnDemandServingMode(model_id=MODEL_ID),
                    chat_request=GenericChatRequest(
                        api_format="GENERIC",
                        messages=[
                            SystemMessage(content=[TextContent(text=SYSTEM_PROMPT)]),
                            UserMessage(content=[TextContent(text=user_message)]),
                        ],
                        max_tokens=8192,
                        temperature=0.2,
                    ),
                )
            )
            analysis_text = chat_response.data.chat_response.choices[0].message.content[0].text
        else:
            analysis_text = "No data found, analysis skipped."

        return response.Response(
            ctx,
            response_data=json.dumps({
                "checkerResponse": checker_text,
                "analysisResponse": analysis_text,
            }),
            headers={"Content-Type": "application/json"},
            status_code=200,
        )

    except Exception as ex:
        logger.exception("Error handling request")
        return response.Response(
            ctx,
            response_data=json.dumps({"error": str(ex)}),
            headers={"Content-Type": "application/json"},
            status_code=500,
        )
