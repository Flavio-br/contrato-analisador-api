import os
import fitz  # PyMuPDF
import google.generativeai as genai

# ===============================
# Carregamento do .env (LOCAL)
# ===============================
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # Em produção (Render), ignora

API_GEMINI_INTERNAL_VERSION = "1.02"

# ===============================
# Configuração da API Gemini
# ===============================
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY não definida. "
        "Configure no .env (local) ou no Render > Environment."
    )

genai.configure(api_key=API_KEY)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

try:
    _gemini_model = genai.GenerativeModel(MODEL_NAME)
except Exception as e:
    raise RuntimeError(
        f"Erro ao inicializar o modelo Gemini '{MODEL_NAME}': {e}"
    )

# ===============================
# Leitura de PDF
# ===============================
def _read_pdf_content(pdf_file_path: str):
    try:
        doc = fitz.open(pdf_file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"[Api_Gemini] Erro ao ler PDF: {e}")
        return None

# ===============================
# Processamento com Gemini
# ===============================
def processar_pdf_com_gemini(prompt: str, pdf_file_path: str) -> str:
    print(f"[Api_Gemini v{API_GEMINI_INTERNAL_VERSION}] PDF recebido: {pdf_file_path}")

    pdf_text = _read_pdf_content(pdf_file_path)
    if not pdf_text:
        return "Erro: não foi possível ler o conteúdo do PDF."

    full_prompt = (
        f"{prompt}\n\n"
        f"=== CONTEÚDO DO DOCUMENTO ===\n\n"
        f"{pdf_text}"
    )

    try:
        response = _gemini_model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Erro ao gerar resposta do Gemini: {e}"

# ===============================
# Execução direta (debug)
# ===============================
if __name__ == "__main__":
    print("Api_Gemini carregado com sucesso.")
    print(f"Versão interna: {API_GEMINI_INTERNAL_VERSION}")
    print(f"Modelo: {MODEL_NAME}")