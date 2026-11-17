from app.api import app
from app.options.api import app as options_app, watchlist_db_path
from app.options.trading_import import register

register(options_app, watchlist_db_path)
