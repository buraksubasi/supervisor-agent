"""
Supervisor Agent
================
Gelen kullanıcı sorusunu Gemini'nin function-calling özelliğiyle analiz eder,
hangi alt servis(ler)in çağrılması gerektiğine karar verir, onları tetikler
ve sonuçları sentezleyip kullanıcıya tek bir cevap olarak döner.

Çalıştırma (local, Docker olmadan):
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Çalıştırma (Docker Compose içinde):
    docker compose up supervisor
"""

import json
import logging

import google.generativeai as genai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_AGENT_STEPS
from tools import TOOL_DEFINITIONS, TOOL_DISPATCH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supervisor")

genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(title="Supervisor Agent")

# Next.js'ten istek atabilmek için CORS — production'da origin'i daraltmayı unutma
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    trace: list[dict]  # hangi tool'ların hangi sırayla çağrıldığını gösterir (debug/UI için)


SYSTEM_INSTRUCTION = (
    "Sen, kullanıcının sorusuna göre doğru aracı seçip çağıran bir supervisor "
    "agent'sın. Elindeki araçlar: YouTube videoları hakkında soru cevaplayan bir "
    "RAG sistemi, bir veritabanına doğal dille soru sorduran bir SQL agent ve "
    "web'de gezinen bir browser agent. Kullanıcının sorusu birden fazla aracı "
    "gerektiriyorsa sırayla hepsini çağırabilirsin. Bir aracı çağırmadan önce "
    "gerekli tüm bilgiye (örn. video URL'si) sahip olduğundan emin ol; eksikse "
    "kullanıcıya doğrudan sor. Tüm araç sonuçlarını topladıktan sonra kullanıcıya "
    "net, Türkçe bir özet/cevap ver."
)


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        tools=TOOL_DEFINITIONS,
        system_instruction=SYSTEM_INSTRUCTION,
    )
    chat = model.start_chat()

    logger.info("Gelen soru: %r", req.question)

    trace: list[dict] = []
    response = chat.send_message(req.question)

    # Tool-calling loop: Gemini bir fonksiyon çağırmak isterse, biz onu çalıştırıp
    # sonucu tekrar modele besliyoruz; model "artık yeterli bilgim var" deyip
    # düz metin cevap verene kadar bu döngü devam ediyor. MAX_AGENT_STEPS sonsuz
    # döngüye karşı bir güvenlik sınırı.
    for step in range(MAX_AGENT_STEPS):
        function_calls = [
            part.function_call
            for part in response.candidates[0].content.parts
            if part.function_call
        ]

        if not function_calls:
            # Model artık tool çağırmıyor -> elimizdeki metin nihai cevap
            final_text = response.text
            logger.info("Adım %d: Tool çağrısı yok, nihai cevap döndürülüyor.", step + 1)
            return AskResponse(answer=final_text, trace=trace)

        logger.info(
            "Adım %d: Gemini %d tool çağırıyor -> %s",
            step + 1,
            len(function_calls),
            [c.name for c in function_calls],
        )

        # Gemini aynı turda birden fazla fonksiyon çağırabilir; hepsini çalıştırıp
        # sonuçları tek seferde geri besliyoruz.
        function_response_parts = []
        for call in function_calls:
            tool_name = call.name
            tool_args = dict(call.args)

            logger.info("  -> Tool: %-25s | Args: %s", tool_name, tool_args)

            handler = TOOL_DISPATCH.get(tool_name)
            if handler is None:
                result = f"[bilinmeyen tool: {tool_name}]"
            else:
                result = await handler(**tool_args)

            logger.info("  <- Tool: %-25s | Sonuç (ilk 120 kar): %.120s", tool_name, result)

            trace.append({"tool": tool_name, "args": tool_args, "result": result})

            function_response_parts.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=tool_name,
                        response={"result": result},
                    )
                )
            )

        response = chat.send_message(
            genai.protos.Content(parts=function_response_parts)
        )

    # MAX_AGENT_STEPS'e ulaşıldı ama model hâlâ tool çağırmaya devam ediyor olabilir.
    # Sonsuz döngüye girmemek için elimizdeki son metni (varsa) dönüyoruz.
    fallback_text = getattr(response, "text", None) or (
        "Adım sınırına ulaşıldı, işlem tamamlanamadı."
    )
    return AskResponse(answer=fallback_text, trace=trace)


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """SSE endpoint: agent adımlarını gerçek zamanlı olarak akıtır.

    Event tipleri:
      thinking   - Gemini düşünüyor / ara adım geçiş mesajı
      tool_call  - Hangi tool hangi argümanlarla çağrılıyor
      tool_result- Tool sonucunun kısa önizlemesi
      answer     - Nihai Türkçe cevap metni
      done       - Tüm trace bilgisiyle stream sonu
      error      - Beklenmedik hata
    """

    def emit(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_generator():
        try:
            yield emit({"type": "thinking", "message": "Sorunuz analiz ediliyor..."})

            model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                tools=TOOL_DEFINITIONS,
                system_instruction=SYSTEM_INSTRUCTION,
            )
            chat = model.start_chat()

            logger.info("Gelen soru (stream): %r", req.question)

            trace: list[dict] = []
            response = chat.send_message(req.question)

            for step in range(MAX_AGENT_STEPS):
                function_calls = [
                    part.function_call
                    for part in response.candidates[0].content.parts
                    if part.function_call
                ]

                if not function_calls:
                    final_text = response.text
                    logger.info("Adım %d: Nihai cevap gönderiliyor.", step + 1)
                    yield emit({"type": "thinking", "message": "Yanıt yazılıyor..."})
                    yield emit({"type": "answer", "content": final_text})
                    yield emit({"type": "done", "trace": trace})
                    return

                logger.info(
                    "Adım %d: Gemini %d tool çağırıyor -> %s",
                    step + 1,
                    len(function_calls),
                    [c.name for c in function_calls],
                )

                function_response_parts = []
                for call in function_calls:
                    tool_name = call.name
                    tool_args = dict(call.args)

                    logger.info("  -> Tool: %-25s | Args: %s", tool_name, tool_args)
                    yield emit(
                        {"type": "tool_call", "step": step + 1, "tool": tool_name, "args": tool_args}
                    )

                    handler = TOOL_DISPATCH.get(tool_name)
                    if handler is None:
                        result = f"[bilinmeyen tool: {tool_name}]"
                    else:
                        result = await handler(**tool_args)

                    logger.info("  <- Tool: %-25s | Sonuç (ilk 120 kar): %.120s", tool_name, result)
                    yield emit(
                        {"type": "tool_result", "step": step + 1, "tool": tool_name, "preview": result[:300]}
                    )

                    trace.append({"tool": tool_name, "args": tool_args, "result": result})

                    function_response_parts.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={"result": result},
                            )
                        )
                    )

                yield emit({"type": "thinking", "message": f"Tüm sonuçlar toplandı, Gemini yanıtı sentezliyor..."})
                response = chat.send_message(
                    genai.protos.Content(parts=function_response_parts)
                )

            fallback_text = getattr(response, "text", None) or "Adım sınırına ulaşıldı, işlem tamamlanamadı."
            yield emit({"type": "answer", "content": fallback_text})
            yield emit({"type": "done", "trace": trace})

        except Exception as exc:
            logger.error("Stream hatası: %s", exc, exc_info=True)
            yield emit({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}