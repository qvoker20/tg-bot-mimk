from fastapi import Request


templates = None


def set_templates(engine) -> None:
    global templates
    templates = engine


def ensure_templates():
    if templates is None:
        raise RuntimeError("Templates engine is not configured.")
    return templates


def render_template(request: Request, template_name: str, context: dict, *, status_code: int = 200):
    template_engine = ensure_templates()
    return template_engine.TemplateResponse(
        request,
        template_name,
        context,
        status_code=status_code,
    )
