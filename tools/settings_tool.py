import re


TOOL_NAME = "settings_tool"
TOOL_DESCRIPTION = "Consulta ou altera provider, modelo e prompt da Elyra a partir de texto natural."


def _clean_after_patterns(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip(" .:;\"'")
    return ""


def run(raw_request, context):
    api = context.get("api")
    if api is None:
        return {"ok": False, "error": "API da Elyra indisponível para configurações.", "result": ""}

    text = raw_request.strip()
    lowered = text.lower()

    if "provider" in lowered or "provedor" in lowered:
        provider_id = ""
        for candidate_id, config in api.get_provider_configs().items():
            candidate_name = str(config.get("name", "")).lower()
            if candidate_id in lowered or candidate_name in lowered:
                provider_id = candidate_id
                break
        result = api.discord_provider_command(provider_id)
        return {"ok": True, "result": result, "error": ""}

    if "modelo" in lowered or "model" in lowered:
        wants_list = re.search(r"\b(lista|listar|mostra|mostrar|quais|qual|disponiveis|disponíveis)\b", lowered)
        model = _clean_after_patterns(
            text,
            [
                r"modelo\s+(?:para|pra|como|=|:)\s*(.+)$",
                r"model\s+(?:to|as|=|:)\s*(.+)$",
                r"usar\s+(?:o\s+)?modelo\s+(.+)$",
                r"troca(?:r)?\s+(?:o\s+)?modelo\s+(?:para|pra)?\s*(.+)$",
            ],
        )
        if wants_list and not model:
            result = api.discord_model_command("")
        else:
            result = api.discord_model_command(model)
        return {"ok": True, "result": result, "error": ""}

    if "prompt" in lowered or "system" in lowered:
        wants_current = re.search(r"\b(qual|mostra|mostrar|ver|atual|lista|listar)\b", lowered)
        prompt = _clean_after_patterns(
            text,
            [
                r"prompt\s+(?:para|pra|como|=|:)\s*(.+)$",
                r"system prompt\s+(?:para|pra|como|=|:)\s*(.+)$",
                r"muda(?:r)?\s+(?:o\s+)?prompt\s+(?:para|pra)?\s*(.+)$",
                r"troca(?:r)?\s+(?:o\s+)?prompt\s+(?:para|pra)?\s*(.+)$",
            ],
        )
        if wants_current and not prompt:
            result = api.discord_prompt_command("")
        else:
            result = api.discord_prompt_command(prompt)
        return {"ok": True, "result": result, "error": ""}

    current = context.get("settings", {})
    result = (
        "Configuração atual:\n"
        f"- provider: {current.get('provider_id', '')}\n"
        f"- modelo: {current.get('model') or 'nenhum'}\n"
        f"- prompt definido: {'sim' if current.get('system_prompt') else 'não'}"
    )
    return {"ok": True, "result": result, "error": ""}
