# -*- coding: utf-8 -*-
"""Tela inicial — as três entradas exigidas pela especificação (item 3):
PACIENTE, ADMIN ENFERMAGEM e ADMIN HOTELARIA."""
from flask import Blueprint, render_template

portal_bp = Blueprint("portal", __name__)


@portal_bp.route("/")
def inicio():
    return render_template("portal/index.html")
