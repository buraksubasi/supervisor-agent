import os
from dotenv import load_dotenv

load_dotenv()

# Gemini API key (ayni projede zaten kullaniyorsun)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Alt servislerin URL'leri.
# ONEMLI: Her proje kendi ayri docker-compose dosyasiyla ayaga kalktigi icin
# supervisor ile ayni Docker network'unde DEGILLER. Bu yuzden servis adi
# (orn. http://sql-agent:8000) ISE YARAMAZ -- host makine uzerinden,
# port mapping'leriyle erisiyoruz.
#
# Supervisor de Docker icinde calistigi icin "localhost" kendi container'ini
# isaret eder, host makineyi degil. Bunun yerine Docker Desktop'in (Windows/Mac)
# native destekledigi "host.docker.internal" kullaniliyor -- bu, host makineye
# container icinden erismeyi sagliyor.
#
# Eger ileride Linux'ta (Docker Desktop olmadan) calistirirsan, supervisor'in
# docker-compose.yml dosyasina su satiri eklemen gerekir:
#   extra_hosts:
#     - "host.docker.internal:host-gateway"
YOUTUBE_RAG_URL = os.getenv("YOUTUBE_RAG_URL", "http://localhost:8001")
SQL_AGENT_URL = os.getenv("SQL_AGENT_URL", "http://localhost:8002")
BROWSER_AGENT_URL = os.getenv("BROWSER_AGENT_URL", "http://localhost:8003")

# Alt servis isteklerinde timeout (saniye) -- yavas servisler (orn. browser agent) icin ayri tutulabilir
DEFAULT_TIMEOUT = float(os.getenv("SUBSERVICE_TIMEOUT", "30"))
BROWSER_AGENT_TIMEOUT = float(os.getenv("BROWSER_AGENT_TIMEOUT", "60"))

# Tool-calling loop'unun maksimum adim sayisi (sonsuz dongu korumasi)
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "5"))