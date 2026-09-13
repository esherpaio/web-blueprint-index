from flask import Response, make_response, render_template
from web.optimizer import optimizer

from bp_index import index_bp
from bp_index.llms import LlmsService


@index_bp.route("/llms.txt")
@optimizer.cache
def llms() -> Response:
    service = LlmsService()
    text = render_template(
        "llms.txt",
        summary=service.get_summary(),
        sections=service.get_sections(),
    )
    response = make_response(text)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response
