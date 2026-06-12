TOOL_NAME = "status_tool"
TOOL_DESCRIPTION = "Mostra o estado atual da Elyra, provider, modelo, Discord e ferramentas carregadas."


def run(raw_request, context):
    settings = context.get("settings", {})
    tools = context.get("tools", [])
    tool_errors = context.get("tool_errors", {})
    discord = settings.get("discord", {})
    tool_names = ", ".join(tool.get("name", "") for tool in tools) or "nenhuma"
    result = (
        "Status da Elyra:\n"
        f"- origem: {context.get('origin', 'desconhecida')}\n"
        f"- provider: {settings.get('provider_id') or 'nenhum'}\n"
        f"- modelo: {settings.get('model') or 'nenhum'}\n"
        f"- API key configurada: {'sim' if settings.get('has_api_key') else 'não'}\n"
        f"- Discord: {discord.get('status', 'desconhecido')}\n"
        f"- servidor Discord: {discord.get('guild_id', 'não configurado')}\n"
        f"- ferramentas: {tool_names}"
    )
    if discord.get("error"):
        result += f"\n- erro Discord: {discord.get('error')}"
    if tool_errors:
        errors = "; ".join(f"{name}: {error}" for name, error in tool_errors.items())
        result += f"\n- erros de ferramentas: {errors}"
    return {"ok": True, "result": result, "error": ""}
