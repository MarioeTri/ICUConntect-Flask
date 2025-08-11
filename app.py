from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_socketio import SocketIO, emit
import sqlite3
import secrets
import bcrypt
import datetime
import re
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS nurse (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_nurse (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    token TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS patient (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    access_key TEXT NOT NULL,
                    condition TEXT,
                    family_member_name TEXT,
                    phone_number TEXT,
                    emergency_phone_number TEXT,
                    id_card_number TEXT,
                    address TEXT,
                    room_responsible_person TEXT,
                    room_responsible_phone TEXT,
                    doctor_name TEXT,
                    doctor_phone TEXT,
                    priority INTEGER DEFAULT 0,
                    last_updated TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS condition_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER,
                    condition TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (patient_id) REFERENCES patient(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS hospital (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL,
                    phone_number TEXT NOT NULL
                )''')
    c.execute("INSERT OR IGNORE INTO hospital (id, address, phone_number) VALUES (?, ?, ?)", 
              (1, "Jl. Kesehatan No. 88, Jakarta", "+622112345678"))
    conn.commit()
    conn.close()

init_db()

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "yha76851@gmail.com"  # Replace with your email
SMTP_PASSWORD = "miiarxcdxyywvpqv"      # Replace with your app-specific password
DOCTOR_EMAIL = "yha76851@gmail.com"

def send_confirmation_email(username, token):
    msg = MIMEMultipart()
    msg['From'] = SMTP_USERNAME
    msg['To'] = DOCTOR_EMAIL
    msg['Subject'] = "Konfirmasi Registrasi Perawat"

    confirmation_url = url_for('confirm_registration', token=token, _external=True)
    body = f"""
    Halo Dokter,

    Perawat dengan username '{username}' telah meminta registrasi. 
    Silakan konfirmasi registrasi dengan mengklik link berikut:
    {confirmation_url}

    Jika Anda tidak mengenali permintaan ini, abaikan email ini.
    Link ini valid selama 24 jam.

    Terima kasih,
    Tim Rumah Sakit Sehat Selalu
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, DOCTOR_EMAIL, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# --- WEBSOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('request_patient_list')
def handle_patient_list_request():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, name, condition, priority, last_updated FROM patient WHERE condition != '' ORDER BY priority DESC, id DESC")
    patients = c.fetchall()
    conn.close()
    socketio.emit('patient_list_update', {'patients': patients})

@socketio.on('request_patient_data')
def handle_patient_data_request(data):
    patient_id = data.get('patient_id')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM patient WHERE id=?", (patient_id,))
    patient = c.fetchone()
    c.execute("SELECT condition, timestamp FROM condition_history WHERE patient_id=? ORDER BY timestamp DESC", (patient_id,))
    history = c.fetchall()
    c.execute("SELECT address, phone_number FROM hospital WHERE id=1")
    hospital = c.fetchone()
    conn.close()
    if patient:
        socketio.emit('patient_data_update', {
            'patient': patient,
            'history': history,
            'hospital': hospital
        })

# --- HELPER FUNCTIONS ---
def validate_phone(phone):
    return re.match(r'^\+?\d{10,13}$', phone) if phone else True

def validate_id_card(id_card):
    return re.match(r'^\d{16}$', id_card) if id_card else True

def generate_pdf_report(patient, history, hospital):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=40)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleCenter', parent=styles['Title'], alignment=TA_CENTER, fontSize=16, spaceAfter=12)
    subtitle_style = ParagraphStyle('SubtitleCenter', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10, spaceAfter=20)
    normal_style = styles['Normal']
    justify_style = ParagraphStyle('Justify', parent=styles['Normal'], alignment=TA_JUSTIFY, fontSize=11)

    elements = []

    try:
        logo = Image("Assets/Hospital.png", width=1.5*inch, height=1.5*inch)
        logo.hAlign = 'CENTER'
        elements.append(logo)
    except:
        elements.append(Paragraph("<b>RUMAH SAKIT SEHAT SELALU</b>", title_style))

    elements.append(Paragraph("LAPORAN MEDIS PASIEN", title_style))
    elements.append(Paragraph(f"{hospital[0]}<br/>{hospital[1]}<br/><br/>", subtitle_style))
    elements.append(Paragraph("""
    Dengan hormat,<br/><br/>
    Dokumen ini merupakan laporan resmi yang disusun oleh tim medis Rumah Sakit Sehat Selalu sebagai bentuk pertanggungjawaban terhadap layanan dan penanganan medis yang telah diberikan kepada pasien berikut. Semua informasi yang tercantum bersumber dari pencatatan selama proses observasi dan perawatan.
    """, justify_style))
    elements.append(Spacer(1, 20))

    data_pasien = [
        ["Nama Pasien", patient[1]],
        ["Key Akses", patient[2]],
        ["Kondisi Terakhir", patient[3] or "-"],
        ["Terakhir Diperbarui", patient[14] or "-"],
        ["Nama Keluarga", patient[4] or "-"],
        ["Nomor Darurat", patient[6] or "-"],
        ["Nomor KTP", patient[7] or "-"],
        ["Alamat", patient[8] or "-"],
        ["Dokter Penanggung Jawab", patient[11] or "-"],
        ["Prioritas", ["Normal", "Sedang", "Tinggi"][patient[13]]]
    ]
    table = Table(data_pasien, colWidths=[160, 320])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica')
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Riwayat Kondisi Pasien", styles['Heading2']))
    if history:
        riwayat_data = [["Tanggal & Waktu", "Kondisi"]] + history
        history_table = Table(riwayat_data, colWidths=[200, 280])
        history_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica')
        ]))
        elements.append(history_table)
    else:
        elements.append(Paragraph("Belum terdapat riwayat kondisi yang tercatat dalam sistem.", normal_style))

    elements.append(Spacer(1, 30))
    current_date = datetime.datetime.now().strftime('%d %B %Y')
    elements.append(Paragraph(f"""
    Demikian laporan ini kami sampaikan untuk digunakan sebagaimana mestinya. Kami menyatakan bahwa informasi dalam laporan ini benar dan telah diverifikasi oleh pihak yang berwenang.<br/><br/>
    Jakarta, {current_date}<br/><br/><br/>
    Hormat kami,<br/>
    <b>Tim Medis Rumah Sakit Sehat Selalu</b>
    """, justify_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- ROUTES ---
@app.route('/')
def landing():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, name, condition, priority, last_updated FROM patient WHERE condition != '' ORDER BY priority DESC, id DESC")
    patients = c.fetchall()
    conn.close()
    return render_template('landing.html', patients=patients)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        confirm_password = request.form['confirm_password'].strip()

        if not username or not password:
            flash("Username dan password harus diisi!", "danger")
            return render_template('register.html')
        if password != confirm_password:
            flash("Password dan konfirmasi password tidak cocok!", "danger")
            return render_template('register.html')
        if len(password) < 6:
            flash("Password harus minimal 6 karakter!", "danger")
            return render_template('register.html')

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            # Check if username exists in nurse or pending_nurse
            c.execute("SELECT username FROM nurse WHERE username=?", (username,))
            if c.fetchone():
                flash("Username sudah digunakan!", "danger")
                conn.close()
                return render_template('register.html')
            c.execute("SELECT username FROM pending_nurse WHERE username=?", (username,))
            if c.fetchone():
                flash("Username ini sedang menunggu konfirmasi dokter!", "warning")
                conn.close()
                return render_template('register.html')

            # Store in pending_nurse with a unique token
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            token = secrets.token_urlsafe(32)
            created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO pending_nurse (username, password, token, created_at) VALUES (?, ?, ?, ?)",
                      (username, hashed_password, token, created_at))
            conn.commit()
            conn.close()

            # Send confirmation email
            if send_confirmation_email(username, token):
                flash("Permintaan registrasi telah dikirim ke dokter untuk konfirmasi. Silakan tunggu persetujuan.", "info")
            else:
                flash("Gagal mengirim email konfirmasi. Silakan coba lagi nanti.", "danger")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Terjadi kesalahan, silakan coba lagi.", "danger")
            conn.close()
    return render_template('register.html')

@app.route('/confirm/<token>', methods=['GET'])
def confirm_registration(token):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT username, password, created_at FROM pending_nurse WHERE token=?", (token,))
    pending = c.fetchone()

    if not pending:
        flash("Token konfirmasi tidak valid atau telah kedaluwarsa!", "danger")
        conn.close()
        return redirect(url_for('login'))

    # Check if token is within 24 hours
    created_at = datetime.datetime.strptime(pending[2], "%Y-%m-%d %H:%M:%S")
    if (datetime.datetime.now() - created_at).total_seconds() > 24 * 3600:
        c.execute("DELETE FROM pending_nurse WHERE token=?", (token,))
        conn.commit()
        flash("Token konfirmasi telah kedaluwarsa!", "danger")
        conn.close()
        return redirect(url_for('login'))

    # Move to nurse table
    try:
        c.execute("INSERT INTO nurse (username, password) VALUES (?, ?)", (pending[0], pending[1]))
        c.execute("DELETE FROM pending_nurse WHERE token=?", (token,))
        conn.commit()
        flash(f"Registrasi untuk {pending[0]} telah disetujui!", "success")
    except sqlite3.IntegrityError:
        flash("Username sudah digunakan!", "danger")
    finally:
        conn.close()
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM nurse WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user:
            try:
                stored_hash = user[2].encode('utf-8')
                input_password = password.encode('utf-8')
                if bcrypt.checkpw(input_password, stored_hash):
                    session['nurse'] = username
                    flash("Login berhasil!", "success")
                    return redirect(url_for('nurse_dashboard'))
                else:
                    flash("Username atau password salah!", "danger")
            except ValueError as e:
                flash("Terjadi kesalahan saat memverifikasi password. Silakan coba lagi atau daftar ulang.", "danger")
        else:
            flash("Username atau password salah!", "danger")
    return render_template('login.html')

@app.route('/nurse', methods=['GET', 'POST'])
def nurse_dashboard():
    if 'nurse' not in session:
        flash("Silakan login terlebih dahulu!", "warning")
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST' and 'hospital_address' in request.form:
        hospital_address = request.form['hospital_address'].strip()
        hospital_phone = request.form['hospital_phone'].strip()
        if not hospital_address:
            flash("Alamat rumah sakit harus diisi!", "danger")
        elif not validate_phone(hospital_phone):
            flash("Nomor telepon rumah sakit tidak valid! Harus berupa 10-13 digit.", "danger")
        else:
            c.execute("UPDATE hospital SET address=?, phone_number=? WHERE id=1", (hospital_address, hospital_phone))
            conn.commit()
            flash("Detail rumah sakit diperbarui!", "success")

    elif request.method == 'POST' and 'patient_name' in request.form:
        patient_name = request.form['patient_name'].strip()
        family_member_name = request.form['family_member_name'].strip()
        phone_number = request.form['phone_number'].strip()
        emergency_phone_number = request.form['emergency_phone_number'].strip()
        id_card_number = request.form['id_card_number'].strip()
        address = request.form['address'].strip()
        room_responsible_person = request.form['room_responsible_person'].strip()
        room_responsible_phone = request.form['room_responsible_phone'].strip()
        doctor_name = request.form['doctor_name'].strip()
        doctor_phone = request.form['doctor_phone'].strip()
        priority = int(request.form.get('priority', 0))

        if not patient_name:
            flash("Nama pasien harus diisi!", "danger")
        elif not validate_phone(phone_number):
            flash("Nomor telepon tidak valid! Harus berupa 10-13 digit.", "danger")
        elif not validate_phone(emergency_phone_number):
            flash("Nomor telepon darurat tidak valid! Harus berupa 10-13 digit.", "danger")
        elif not validate_phone(room_responsible_phone):
            flash("Nomor penanggung jawab ruangan tidak valid! Harus berupa 10-13 digit.", "danger")
        elif not validate_phone(doctor_phone):
            flash("Nomor telepon dokter tidak valid! Harus berupa 10-13 digit.", "danger")
        elif not validate_id_card(id_card_number):
            flash("Nomor KTP tidak valid! Harus berupa 16 digit.", "danger")
        else:
            key = secrets.token_hex(4)
            c.execute("""INSERT INTO patient (name, access_key, condition, family_member_name, phone_number, 
                        emergency_phone_number, id_card_number, address, room_responsible_person, 
                        room_responsible_phone, doctor_name, doctor_phone, priority, last_updated) 
                        VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                        (patient_name, key, family_member_name, phone_number, emergency_phone_number, 
                         id_card_number, address, room_responsible_person, room_responsible_phone, 
                         doctor_name, doctor_phone, priority, ""))
            conn.commit()
            flash(f"Pasien {patient_name} ditambahkan dengan key: {key}", "success")
            if emergency_phone_number:
                flash(f"Notifikasi telah dikirim ke nomor darurat: {emergency_phone_number}", "info")
            c.execute("SELECT id, name, condition, priority, last_updated FROM patient WHERE condition != '' ORDER BY priority DESC, id DESC")
            patients = c.fetchall()
            socketio.emit('patient_list_update', {'patients': patients})

    c.execute("SELECT address, phone_number FROM hospital WHERE id=1")
    hospital = c.fetchone()

    search_query = request.args.get('search', '').strip()
    query = "SELECT id, name, access_key, condition, priority, last_updated FROM patient"
    params = ()
    if search_query:
        query += " WHERE name LIKE ?"
        params = ('%' + search_query + '%',)
    c.execute(query + " ORDER BY priority DESC, id DESC", params)
    patients = c.fetchall()
    conn.close()
    return render_template('nurse_dashboard.html', patients=patients, search_query=search_query, hospital=hospital)

@app.route('/patient/<int:patient_id>', methods=['GET', 'POST'])
def patient_detail(patient_id):
    if 'nurse' not in session:
        flash("Hanya perawat yang dapat mengakses halaman ini!", "warning")
        return redirect(url_for('access_patient', patient_id=patient_id))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        if 'condition' in request.form:
            new_condition = request.form['condition'].strip()
            if not new_condition:
                flash("Kondisi pasien harus diisi!", "danger")
            else:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("UPDATE patient SET condition=?, last_updated=? WHERE id=?", (new_condition, timestamp, patient_id))
                c.execute("INSERT INTO condition_history (patient_id, condition, timestamp) VALUES (?, ?, ?)", 
                         (patient_id, new_condition, timestamp))
                conn.commit()
                flash("Kondisi pasien diperbarui!", "success")
                c.execute("SELECT * FROM patient WHERE id=?", (patient_id,))
                patient = c.fetchone()
                c.execute("SELECT condition, timestamp FROM condition_history WHERE patient_id=? ORDER BY timestamp DESC", (patient_id,))
                history = c.fetchall()
                c.execute("SELECT address, phone_number FROM hospital WHERE id=1")
                hospital = c.fetchone()
                socketio.emit('patient_data_update', {
                    'patient': patient,
                    'history': history,
                    'hospital': hospital
                })
                if patient[6]:
                    flash(f"Notifikasi pembaruan kondisi dikirim ke: {patient[6]}", "info")
        elif 'priority' in request.form:
            priority = int(request.form['priority'])
            c.execute("UPDATE patient SET priority=? WHERE id=?", (priority, patient_id))
            conn.commit()
            flash("Prioritas pasien diperbarui!", "success")
            c.execute("SELECT id, name, condition, priority, last_updated FROM patient WHERE condition != '' ORDER BY priority DESC, id DESC")
            patients = c.fetchall()
            socketio.emit('patient_list_update', {'patients': patients})

    c.execute("SELECT * FROM patient WHERE id=?", (patient_id,))
    patient = c.fetchone()
    c.execute("SELECT condition, timestamp FROM condition_history WHERE patient_id=? ORDER BY timestamp DESC", (patient_id,))
    history = c.fetchall()
    c.execute("SELECT address, phone_number FROM hospital WHERE id=1")
    hospital = c.fetchone()
    conn.close()

    if not patient:
        flash("Pasien tidak ditemukan!", "danger")
        return redirect(url_for('nurse_dashboard'))

    return render_template('patient_detail.html', patient=patient, history=history, hospital=hospital)

@app.route('/patient/<int:patient_id>/report')
def generate_report(patient_id):
    if 'nurse' not in session:
        flash("Hanya perawat yang dapat mengakses laporan!", "warning")
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM patient WHERE id=?", (patient_id,))
    patient = c.fetchone()
    c.execute("SELECT condition, timestamp FROM condition_history WHERE patient_id=? ORDER BY timestamp DESC", (patient_id,))
    history = c.fetchall()
    c.execute("SELECT address, phone_number FROM hospital WHERE id=1")
    hospital = c.fetchone()
    conn.close()

    if not patient:
        flash("Pasien tidak ditemukan!", "danger")
        return redirect(url_for('nurse_dashboard'))

    pdf_buffer = generate_pdf_report(patient, history, hospital)
    return send_file(pdf_buffer, as_attachment=True, download_name=f"Laporan_{patient[1]}.pdf", mimetype='application/pdf')

@app.route('/access/<int:patient_id>', methods=['GET', 'POST'])
def access_patient(patient_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM patient WHERE id=?", (patient_id,))
    patient = c.fetchone()
    conn.close()

    if not patient:
        flash("Pasien tidak ditemukan!", "danger")
        return redirect(url_for('landing'))

    if request.method == 'POST':
        key = request.form['key'].strip()
        if key == patient[2]:
            session['access_patient_id'] = patient_id
            return redirect(url_for('patient_view', patient_id=patient_id))
        else:
            flash("Key akses salah! Hubungi perawat.", "danger")

    return render_template('access_patient.html', patient=patient)

@app.route('/patient/view/<int:patient_id>')
def patient_view(patient_id):
    if 'nurse' in session:
        return redirect(url_for('patient_detail', patient_id=patient_id))

    if 'access_patient_id' not in session or session['access_patient_id'] != patient_id:
        flash("Silakan masukkan key akses terlebih dahulu!", "warning")
        return redirect(url_for('access_patient', patient_id=patient_id))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM patient WHERE id=?", (patient_id,))
    patient = c.fetchone()
    c.execute("SELECT condition, timestamp FROM condition_history WHERE patient_id=? ORDER BY timestamp DESC", (patient_id,))
    history = c.fetchall()
    c.execute("SELECT address, phone_number FROM hospital WHERE id=1")
    hospital = c.fetchone()
    conn.close()

    if not patient:
        flash("Pasien tidak ditemukan!", "danger")
        return redirect(url_for('landing'))

    return render_template('patient_view.html', patient=patient, history=history, hospital=hospital)

@app.route('/logout')
def logout():
    session.pop('nurse', None)
    session.pop('access_patient_id', None)
    flash("Anda telah logout.", "info")
    return redirect(url_for('landing'))

if __name__ == "__main__":
    socketio.run(app, debug=True)