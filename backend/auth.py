from flask import Blueprint, render_template, request, redirect, session
from db import get_connection
from datetime import datetime
import bcrypt

auth_bp = Blueprint("auth", __name__)

# ----------------------------
# LOGIN
# ----------------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT usuario_id, password_hash, rol
            FROM usuarios
            WHERE username = %s
        """, (username,))

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:
            usuario_id = user[0]
            password_hash = user[1]
            rol = user[2]

            # Verificar contraseña con bcrypt
            if bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")):
                session["usuario_id"] = usuario_id
                session["username"] = username
                session["rol"] = rol
                session["anio_actual"] = datetime.now().year
                return redirect("/dashboard")

        # Si falla login
        return render_template(
            "login.html",
            error="Credenciales incorrectas",
            year=datetime.now().year
        )

    return render_template("login.html", year=datetime.now().year)


# ----------------------------
# LOGOUT
# ----------------------------
@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
