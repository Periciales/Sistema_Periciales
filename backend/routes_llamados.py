from flask import Blueprint, jsonify, request, session, render_template, redirect
from db import get_connection
from datetime import datetime

llamados_bp = Blueprint("llamados", __name__)

@llamados_bp.route("/nuevo-llamado", methods=["GET"])
def vista_nuevo_llamado():

    if "usuario_id" not in session:
        return redirect("/login")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT libro_id, nombre_libro FROM libros ORDER BY nombre_libro")
    libros = cur.fetchall()

    cur.execute("SELECT perito_id, nombre_completo FROM peritos ORDER BY nombre_completo")
    peritos = cur.fetchall()

    cur.execute("SELECT autoridad_id, nombre_autoridad FROM autoridades ORDER BY nombre_autoridad")
    autoridades = cur.fetchall()

    cur.close()
    conn.close()

    libro_actual = session.get("libro_actual")
    anio_actual = session.get("anio_actual", datetime.now().year)
    libro_nombre_actual = None

    if libro_actual:
        for l in libros:
            if l[0] == libro_actual:
                libro_nombre_actual = l[1]
                break

    return render_template(
        "nuevo_llamado.html",
        libros=libros,
        peritos=peritos,
        autoridades=autoridades,
        libro_actual=libro_actual,
        anio_actual=anio_actual,
        libro_nombre_actual=libro_nombre_actual

    )


@llamados_bp.route("/crear-llamado", methods=["POST"])
def crear_llamado():

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    data = request.json

    libro_id = int(data.get("libro_id"))
    session["libro_actual"] = libro_id
    mp_solicitante_id = int(data.get("mp_solicitante_id"))
    detenido = data.get("detenido", False)
    carpeta = data.get("carpeta_investigacion")
    detalles = data.get("detalles")
    fecha_registro = data.get("fecha_registro")
    hora_registro = data.get("hora_registro")

    if not all([libro_id, mp_solicitante_id, fecha_registro, hora_registro]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    anio = session.get("anio_actual", datetime.now().year)

    conn = get_connection()
    cur = conn.cursor()

    SUIP_ID = 1  # Ajusta si SUIP tiene otro ID

    try:

        cur.execute("SET app.usuario_id = %s", (session["usuario_id"],))

        # 🔒 Control consecutivo
        cur.execute("""
            SELECT consecutivo_actual
            FROM control_consecutivos
            WHERE libro_id = %s AND anio = %s
            FOR UPDATE
        """, (libro_id, anio))

        row = cur.fetchone()

        if row:
            numero_consecutivo = row[0] + 1
            cur.execute("""
                UPDATE control_consecutivos
                SET consecutivo_actual = %s
                WHERE libro_id = %s AND anio = %s
            """, (numero_consecutivo, libro_id, anio))
        else:
            numero_consecutivo = 1
            cur.execute("""
                INSERT INTO control_consecutivos (libro_id, anio, consecutivo_actual)
                VALUES (%s, %s, %s)
            """, (libro_id, anio, numero_consecutivo))

        # 🔹 Determinar materia principal (solo libros normales)
        materia_principal_id = None
        if libro_id != SUIP_ID:
            materia_principal_id = int(data.get("materia_id"))

        # 🔹 Obtener sigla base
        cur.execute("""
            SELECT sigla
            FROM libros
            WHERE libro_id = %s
        """, (libro_id,))

        sigla = cur.fetchone()[0]

        # 🔥 Caso especial libro Mecánica y Tránsito
        LIBRO_MECANICA_TRANSITO_ID = 4  # Ajusta si es otro

        if libro_id == LIBRO_MECANICA_TRANSITO_ID and materia_principal_id:

            MECANICA_ID = 20
            TRANSITO_ID = 25

            if materia_principal_id == MECANICA_ID:
                sigla = "FMM"
            elif materia_principal_id == TRANSITO_ID:
                sigla = "FMT"

        numero_oficial = f"{sigla}-{str(numero_consecutivo).zfill(3)}/{anio}"






        # 🧾 Insertar llamado administrativo
        cur.execute("""
            INSERT INTO llamados (
                libro_id,
                anio,
                numero_consecutivo,
                numero_oficial,
                fecha_registro,
                hora_registro,
                receptor_id,
                mp_solicitante_id,
                detenido,
                carpeta_investigacion,
                detalles
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING llamado_id
        """, (
            libro_id,
            anio,
            numero_consecutivo,
            numero_oficial,
            fecha_registro,
            hora_registro,
            session["usuario_id"],
            mp_solicitante_id,
            detenido,
            carpeta,
            detalles
        ))

        llamado_id = cur.fetchone()[0]

        # 📚 Insertar pericial(es)
        if libro_id == SUIP_ID:

            periciales = data.get("periciales")

            if not periciales or len(periciales) == 0:
                raise Exception("Debe agregar al menos una materia en SUIP")

            for p in periciales:
                cur.execute("""
                    INSERT INTO llamado_periciales (
                        llamado_id,
                        materia_id,
                        perito_id
                    )
                    VALUES (%s,%s,%s)
                """, (
                    llamado_id,
                    int(p["materia_id"]),
                    int(p["perito_id"])
                ))

        else:
            perito_id = int(data.get("perito_id"))

            if not all([materia_principal_id, perito_id]):
                raise Exception("Debe seleccionar materia y perito")

            cur.execute("""
                INSERT INTO llamado_periciales (
                    llamado_id,
                    materia_id,
                    perito_id
                )
                VALUES (%s,%s,%s)
            """, (
                llamado_id,
                materia_principal_id,
                perito_id
            ))

        conn.commit()

        return jsonify({
            "message": "Llamado creado correctamente",
            "llamado_id": llamado_id,
            "numero_oficial": numero_oficial
        })

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        conn.close()


@llamados_bp.route("/historial-libro/<int:libro_id>")
def historial_libro(libro_id):

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    anio_actual = session.get("anio_actual")
    numero_base = request.args.get("desde")

    conn = get_connection()
    cur = conn.cursor()

    try:

        filtro_numero = ""
        params = [libro_id, anio_actual]

        if numero_base:
            filtro_numero = "AND l.numero_consecutivo <= %s"
            params.append(int(numero_base))

        cur.execute(f"""
            SELECT 
                l.llamado_id,
                l.numero_oficial,
                l.fecha_registro,
                l.carpeta_investigacion,
                lp.pericial_id,
                m.nombre_materia,
                lp.tipo_documento
            FROM llamados l
            LEFT JOIN llamado_periciales lp 
                ON l.llamado_id = lp.llamado_id
            LEFT JOIN materias_periciales m
                ON lp.materia_id = m.materia_id
            WHERE l.libro_id = %s
            AND l.anio = %s
            {filtro_numero}
            ORDER BY l.numero_consecutivo DESC
            LIMIT 100
        """, params)

        rows = cur.fetchall()


        resultado = []

        for r in rows:

            resultado.append({
                "llamado_id": r[0],
                "numero": r[1],
                "fecha": r[2],
                "carpeta": r[3],
                "pericial_id": r[4],
                "materia": r[5],
                "tipo_documento": r[6],
                "cerrado": True if r[6] else False
            })


        return jsonify(resultado)

    finally:
        cur.close()
        conn.close()






@llamados_bp.route("/listar-llamados", methods=["GET"])
def listar_llamados():

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT 
                l.llamado_id,
                l.numero_oficial,
                lb.nombre_libro,
                COUNT(lp.pericial_id) as total_periciales
            FROM llamados l
            JOIN libros lb ON l.libro_id = lb.libro_id
            LEFT JOIN llamado_periciales lp ON l.llamado_id = lp.llamado_id
            GROUP BY l.llamado_id, lb.nombre_libro
            ORDER BY l.llamado_id DESC
        """)

        rows = cur.fetchall()

        resultado = []
        for r in rows:
            resultado.append({
                "llamado_id": r[0],
                "numero_oficial": r[1],
                "libro": r[2],
                "total_periciales": r[3]
            })

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        conn.close()


@llamados_bp.route("/test-masivo", methods=["GET"])
def test_masivo():

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SET app.usuario_id = %s", (session["usuario_id"],))

        resultados = []

        # Crear 3 llamados en libro 1 año 2026
        for i in range(3):

            anio = 2026

            # Bloquear fila control
            cur.execute("""
                SELECT consecutivo_actual
                FROM control_consecutivos
                WHERE libro_id = %s AND anio = %s
                FOR UPDATE
            """, (1, anio))

            row = cur.fetchone()

            if row:
                numero_consecutivo = row[0] + 1
                cur.execute("""
                    UPDATE control_consecutivos
                    SET consecutivo_actual = %s
                    WHERE libro_id = %s AND anio = %s
                """, (numero_consecutivo, 1, anio))
            else:
                numero_consecutivo = 1
                cur.execute("""
                    INSERT INTO control_consecutivos (libro_id, anio, consecutivo_actual)
                    VALUES (%s, %s, %s)
                """, (1, anio, numero_consecutivo))

            numero_oficial = f"{str(numero_consecutivo).zfill(3)}/{anio}"

            cur.execute("""
                INSERT INTO llamados (
                    libro_id,
                    materia_id,
                    anio,
                    numero_consecutivo,
                    numero_oficial,
                    fecha_registro,
                    hora_registro,
                    receptor_id,
                    mp_solicitante_id,
                    detenido
                )
                VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,CURRENT_TIME,%s,%s,%s)
                RETURNING llamado_id
            """, (1, 8, anio, numero_consecutivo, numero_oficial,
                  session["usuario_id"], 1, False))

            llamado_id = cur.fetchone()[0]

            resultados.append({
                "llamado_id": llamado_id,
                "numero": numero_oficial
            })

        conn.commit()

        return jsonify({
            "status": "Prueba masiva completada",
            "creados": resultados
        })

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        conn.close()

@llamados_bp.route("/descargar-pericial", methods=["POST"])
def descargar_pericial():

    if "usuario_id" not in session:
        return jsonify({"error": "No autenticado"}), 401

    data = request.json

    pericial_id = data.get("pericial_id")
    tipo_documento = data.get("tipo_documento")
    recibido_por = data.get("recibido_por")
    fecha_entrega_autoridad = data.get("fecha_entrega_autoridad")

    if not pericial_id or not tipo_documento:
        return jsonify({"error": "Datos incompletos"}), 400

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SET app.usuario_id = %s", (session["usuario_id"],))

        cur.execute("""
            UPDATE llamado_periciales
            SET tipo_documento = %s,
                recibido_por = %s,
                fecha_entrega_autoridad = %s
            WHERE pericial_id = %s
        """, (
            tipo_documento,
            recibido_por,
            fecha_entrega_autoridad if fecha_entrega_autoridad else None,
            pericial_id
        ))

        conn.commit()

        return jsonify({"message": "Descarga realizada correctamente"})

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        conn.close()




@llamados_bp.route("/materias-por-libro/<int:libro_id>")
def materias_por_libro(libro_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT m.materia_id, m.nombre_materia
        FROM libro_materia lm
        JOIN materias_periciales m ON lm.materia_id = m.materia_id
        WHERE lm.libro_id = %s
        ORDER BY m.nombre_materia
    """, (libro_id,))

    materias = cur.fetchall()

    cur.close()
    conn.close()

    return materias
