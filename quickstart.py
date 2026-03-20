import io
import oci
from pypdf import PdfReader
from oci.generative_ai_inference.models import (
    ChatDetails,
    GenericChatRequest,
    OnDemandServingMode,
    SystemMessage,
    TextContent,
    UserMessage,
)

COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaamxleq3holrutfb7hih7u4nq42mam77a3ye6m5ufgaqx4itdfxr6a"
REGION = "us-phoenix-1"
BUCKET_NAME = "agent-knowledge-base"
NAMESPACE = "axzkbtajofjq"
MODEL_ID = "google.gemini-2.5-flash"

MIN_CONTENT_LENGTH = 300

SYSTEM_PROMPT = (
    "You are a JD Edwards Integrity Report analyst. "
    "When given an Integrity Report with data, analyze it thoroughly. "
    "Identify the specific integrity issues found, explain what each problem "
    "means in JDE context, and recommend the corrective actions or fixes. "
    "Structure your response with: 1) Summary of findings, "
    "2) Detailed problems identified, 3) Recommended fixes."
)

DEFAULT_ANALYSIS_PROMPT = "Analyze this Integrity Report. Identify all problems and recommend fixes."


def main():
    object_name = "R007011_CAN0001_32083_PDF.pdf"
    prompt = DEFAULT_ANALYSIS_PROMPT

    config = oci.config.from_file("~/.oci/config", "DEFAULT")

    # ── Step 1: Download PDF and check for content ──
    os_client = oci.object_storage.ObjectStorageClient(config)
    obj = os_client.get_object(NAMESPACE, BUCKET_NAME, object_name)
    pdf_bytes = obj.data.content

    reader = PdfReader(io.BytesIO(pdf_bytes))
    full_text = ""
    for page in reader.pages:
        full_text += (page.extract_text() or "")

    has_data = len(full_text.strip()) > MIN_CONTENT_LENGTH
    checker_text = "Yes" if has_data else "No"
    print(f"checkerResponse: {checker_text}")
    print(f"  ({len(full_text.strip())} chars from {len(reader.pages)} pages)")

    # ── Step 2: Analyze with LLM (only if report has data) ──
    if has_data:
        ai_client = oci.generative_ai_inference.GenerativeAiInferenceClient(config)
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

    print(f"\nanalysisResponse:\n{analysis_text}")


if __name__ == "__main__":
    main()
