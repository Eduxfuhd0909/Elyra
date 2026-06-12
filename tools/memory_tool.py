import json
import re


TOOL_NAME = "memory_tool"
TOOL_DESCRIPTION = "Salva fatos na memória longa ou consulta o que a Elyra lembra."


def _extract_memory_text(raw_request):
    text = raw_request.strip()
    patterns = [
        r"(?:lembre(?:-se)?|lembrar|memorize|guarde|salva|salvar)\s+(?:que\s+)?(.+)$",
        r"(?:minha|meu|eu)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip(" .:;\"'")
    return text


def run(raw_request, context):
    api = context.get("api")
    if api is None:
        return {"ok": False, "error": "API da Elyra indisponível para memória.", "result": ""}

    lowered = raw_request.lower()
    wants_lookup = re.search(r"\b(o que|quais|qual|mostra|mostrar|consulta|consultar|lista|listar|lembra sobre)\b", lowered)
    if wants_lookup:
        memories = context.get("memories") or api.memory.load_all_long_term_memories(limit=40)
        if not memories:
            return {"ok": True, "result": "Ainda não há memórias relevantes salvas.", "error": ""}
        result = "Memórias relevantes:\n" + "\n".join(f"- {memory}" for memory in memories[:40])
        return {"ok": True, "result": result, "error": ""}

    memory_text = _extract_memory_text(raw_request)
    raw = api.remember(memory_text)
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        response = {"ok": False, "error": raw}

    if not response.get("ok"):
        return {"ok": False, "error": response.get("error", "Não consegui salvar a memória."), "result": ""}

    return {"ok": True, "result": f"Memória salva: {response.get('memory', memory_text)}", "error": ""}
