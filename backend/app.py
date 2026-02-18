from flask import Flask, render_template, redirect, session, jsonify, request
from routes_llamados import llamados_bp
from auth import auth_bp
from datetime import datetime
from db import get_connection

app = Flask(__name__)
app.secret_key = "super_secret_key"

@app.route("/cambiar-anio", methods=["POST"])
def cambiar_anio():

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    data = request.json
    nuevo_anio = int(data.get("anio"))

    session["anio_actual"] = nuevo_anio

    return jsonify({"status": "ok"})

# Registrar blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(llamados_bp)

# Ruta principal
@app.route("/")
def index():
    if "usuario_id" not in session:
        return redirect("/login")
    return redirect("/dashboard")

# Dashboard principal
@app.route("/dashboard")
def dashboard():
    if "usuario_id" not in session:
        return redirect("/login")

    # Siempre iniciar con año actual si no existe en sesión
    if "anio_actual" not in session:
        session["anio_actual"] = datetime.now().year

    return render_template("base.html")

@app.route("/nuevo-llamado")
def nuevo_llamado():

    if "usuario_id" not in session:
        return redirect("/login")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT libro_id, nombre_libro FROM libros ORDER BY nombre_libro")
    libros = cur.fetchall()

    cur.execute("SELECT perito_id, nombre_completo FROM peritos ORDER BY nombre_completo")
    peritos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "nuevo_llamado.html",
        libros=libros,
        peritos=peritos
    )


#if __name__ == "__main__":
#    app.run(host="0.0.0.0", port=5000, debug=True)

if __name__ == "__main__":
  app.run( debug=True)
