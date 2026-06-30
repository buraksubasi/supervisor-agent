"""
LLM-as-Judge
============
Gemini'yi hakem olarak kullanarak her agent cevabını üç boyutta değerlendirir:

  faithfulness   – Cevap, kaynak bilgiye ne kadar sadık?          (1 = tamamen sadık)
  relevance      – Cevap, soruyu ne kadar iyi yanıtlıyor?         (1 = tam isabet)
  hallucination  – Kaynakta olmayan bilgi var mı?                  (0 = hiç yok, iyi)

Genel skor = (faithfulness + relevance + (1 - hallucination)) / 3
"""

import json
import logging
from dataclasses import dataclass

import google.generativeai as genai
from config import GEMINI_MODEL

logger = logging.getLogger("supervisor.judge")

# ---------------------------------------------------------------------------
# Prompt şablonları
# ---------------------------------------------------------------------------

_FAITHFULNESS_PROMPT = """Bir AI cevabının kaynak bilgiye sadakati değerlendir.

Soru: {question}
Kaynak / Bağlam: {context}
Cevap: {answer}

Değerlendirme kriteri — Faithfulness (0.0 - 1.0):
- 1.0: Cevabın tüm iddiaları kaynaktan doğrudan destekleniyor
- 0.5: Bazı iddialar kaynakta var, bazıları belirsiz
- 0.0: Cevap kaynakla çelişiyor veya kaynak yokmuş gibi davranılıyor

SADECE şu JSON formatında cevap ver:
{{"score": 0.0, "reason": "kısa gerekçe (1-2 cümle)"}}"""

_RELEVANCE_PROMPT = """Bir AI cevabının soruyla ne kadar alakalı olduğunu değerlendir.

Soru: {question}
Cevap: {answer}

Değerlendirme kriteri — Relevance (0.0 - 1.0):
- 1.0: Cevap soruyu doğrudan ve eksiksiz yanıtlıyor
- 0.5: Cevap kısmen alakalı ama önemli bilgiler eksik
- 0.0: Cevap soruyla alakasız veya tamamen yanlış

SADECE şu JSON formatında cevap ver:
{{"score": 0.0, "reason": "kısa gerekçe (1-2 cümle)"}}"""

_HALLUCINATION_PROMPT = """Bir AI cevabının kaynakta olmayan bilgi içerip içermediğini tespit et.

Soru: {question}
Kaynak / Bağlam: {context}
Cevap: {answer}

Değerlendirme kriteri — Hallucination (0.0 - 1.0):
- 0.0: Cevap yalnızca kaynaktaki bilgileri kullanıyor (iyi, halüsinasyon yok)
- 0.5: Cevap bazı kaynakta olmayan bilgiler içeriyor
- 1.0: Cevap büyük ölçüde uydurma bilgi içeriyor (kötü)

SADECE şu JSON formatında cevap ver:
{{"score": 0.0, "reason": "kısa gerekçe (1-2 cümle)"}}"""


# ---------------------------------------------------------------------------
# Sonuç veri sınıfı
# ---------------------------------------------------------------------------

@dataclass
class JudgeResult:
    faithfulness_score: float
    relevance_score: float
    hallucination_score: float
    overall_score: float

    faithfulness_reason: str
    relevance_reason: str
    hallucination_reason: str

    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------

def _call_judge(prompt: str) -> tuple[float, str, int, int]:
    """Gemini'yi çağırır, (score, reason, input_tokens, output_tokens) döner."""
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)

    meta = getattr(response, "usage_metadata", None)
    inp = getattr(meta, "prompt_token_count", 0) or 0
    out = getattr(meta, "candidates_token_count", 0) or 0

    try:
        clean = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        score = float(data.get("score", 0.5))
        reason = str(data.get("reason", ""))
        score = max(0.0, min(1.0, score))  # 0-1 aralığına sıkıştır
    except (json.JSONDecodeError, ValueError):
        logger.warning("Judge JSON parse hatası: %s", response.text)
        score, reason = 0.5, "Parse hatası — varsayılan değer atandı"

    return score, reason, inp, out


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def evaluate(
    question: str,
    answer: str,
    context: str = "",
) -> JudgeResult:
    """
    Senkron olarak üç boyutlu değerlendirme yapar.

    Args:
        question: Kullanıcının sorusu
        answer:   Agent'ın verdiği cevap
        context:  Kaynak metin (RAG chunk'ları, DB sonuçları, vb.)
                  Boş bırakılabilir — faithfulness/hallucination
                  o zaman sadece cevabın iç tutarlılığına bakarak çalışır.
    """
    ctx = context or "Kaynak bilgi sağlanmadı."

    f_score, f_reason, f_inp, f_out = _call_judge(
        _FAITHFULNESS_PROMPT.format(question=question, context=ctx, answer=answer)
    )
    r_score, r_reason, r_inp, r_out = _call_judge(
        _RELEVANCE_PROMPT.format(question=question, answer=answer)
    )
    h_score, h_reason, h_inp, h_out = _call_judge(
        _HALLUCINATION_PROMPT.format(question=question, context=ctx, answer=answer)
    )

    overall = round((f_score + r_score + (1 - h_score)) / 3, 4)

    logger.info(
        "[judge] faithfulness=%.2f relevance=%.2f hallucination=%.2f overall=%.2f",
        f_score, r_score, h_score, overall,
    )

    return JudgeResult(
        faithfulness_score=round(f_score, 4),
        relevance_score=round(r_score, 4),
        hallucination_score=round(h_score, 4),
        overall_score=overall,
        faithfulness_reason=f_reason,
        relevance_reason=r_reason,
        hallucination_reason=h_reason,
        input_tokens=f_inp + r_inp + h_inp,
        output_tokens=f_out + r_out + h_out,
    )
