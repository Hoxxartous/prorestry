from flask import Blueprint

it = Blueprint('it', __name__)

from app.it import views
