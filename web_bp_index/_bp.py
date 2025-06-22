import os

from flask import Blueprint

_dir = os.path.dirname(os.path.abspath(__file__))
index_bp = Blueprint(
    name="index",
    import_name=__name__,
    url_prefix=None,
    template_folder=os.path.join(_dir, "templates"),
    static_folder=os.path.join(_dir, "static"),
    static_url_path="/index/static",
)
