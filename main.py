from flask import Flask, request, render_template, jsonify, url_for
from instagrapi import Client
from werkzeug.utils import secure_filename
import os
import time
import threading
import uuid

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'txt'}

# Simple in-memory job store: { job_id: {status, message, progress} }
jobs = {}
jobs_lock = threading.Lock()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_messages_from_file(job_id, username, password, recipient, message_file, interval, haters_name):
    with jobs_lock:
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['progress'] = 0
        jobs[job_id]['message'] = 'Starting...'

    cl = Client()
    try:
        # Attempt login
        with jobs_lock:
            jobs[job_id]['message'] = 'Logging in...'
        cl.login(username, password)
        with jobs_lock:
            jobs[job_id]['message'] = 'Logged in successfully.'

        recipient_id = None
        is_group = False

        # Try username -> user id
        try:
            recipient_id = cl.user_id_from_username(recipient)
            if recipient_id:
                with jobs_lock:
                    jobs[job_id]['message'] = f"Recipient username found: {recipient}"
        except Exception:
            recipient_id = None

        # If not a username, try chat / group lookup (best-effort)
        if not recipient_id:
            try:
                # Note: chat_id_from_name may not exist depending on instagrapi version.
                # Fallback: treat recipient as a raw thread id if possible.
                recipient_id = cl.chat_id_from_name(recipient)
                is_group = True
                with jobs_lock:
                    jobs[job_id]['message'] = f"Group found: {recipient}"
            except Exception:
                # Could not resolve recipient
                with jobs_lock:
                    jobs[job_id]['status'] = 'error'
                    jobs[job_id]['message'] = 'Recipient username or group not found!'
                return

        # Read messages
        with open(message_file, 'r', encoding='utf-8') as f:
            messages = [line.strip() for line in f.readlines() if line.strip()]

        total = len(messages)
        if total == 0:
            with jobs_lock:
                jobs[job_id]['status'] = 'error'
                jobs[job_id]['message'] = 'Uploaded file contains no messages.'
            return

        for idx, message in enumerate(messages, start=1):
            formatted_message = f"{haters_name} {message}".strip()
            try:
                if is_group:
                    # send to group/chat
                    cl.chat_send_message(recipient_id, formatted_message)
                    app.logger.info(f"Message sent to group: {formatted_message}")
                else:
                    # send direct message to user id (recipient_id should be int)
                    # instagrapi expects list of user_ids
                    cl.direct_send(formatted_message, [recipient_id])
                    app.logger.info(f"Message sent to user: {formatted_message}")
                with jobs_lock:
                    jobs[job_id]['message'] = f"Sent ({idx}/{total})"
                    jobs[job_id]['progress'] = int((idx / total) * 100)
            except Exception as e:
                app.logger.exception("Failed to send message")
                with jobs_lock:
                    jobs[job_id]['message'] = f"Failed to send message ({idx}/{total}): {e}"
                # continue sending remaining messages
            time.sleep(interval)

        with jobs_lock:
            jobs[job_id]['status'] = 'done'
            jobs[job_id]['message'] = 'All messages processed.'
            jobs[job_id]['progress'] = 100

    except Exception as e:
        app.logger.exception("Error in send_messages_from_file")
        with jobs_lock:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['message'] = str(e)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        recipient = request.form.get("recipient", "").strip()
        interval = int(request.form.get("interval", 5))
        haters_name = request.form.get("haters_name", "").strip()

        if not username or not password or not recipient:
            return render_template("index.html", error="Username, password, and recipient are required.")

        if "message_file" not in request.files:
            return render_template("index.html", error="No message file uploaded!")

        file = request.files["message_file"]
        if file.filename == "":
            return render_template("index.html", error="No selected file!")

        if not allowed_file(file.filename):
            return render_template("index.html", error="Only .txt files are allowed.")

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # create job
        job_id = str(uuid.uuid4())
        with jobs_lock:
            jobs[job_id] = {
                'status': 'queued',
                'message': 'Job queued.',
                'progress': 0
            }

        thread = threading.Thread(
            target=send_messages_from_file,
            args=(job_id, username, password, recipient, file_path, interval, haters_name),
            daemon=True
        )
        thread.start()

        status_url = url_for('job_status', job_id=job_id, _external=True)
        return render_template("index.html", job_id=job_id, status_url=status_url, message="Job started. Poll the status URL for updates.")

    return render_template("index.html")

@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id):
    with jobs_lock:
        info = jobs.get(job_id)
        if not info:
            return jsonify({"error": "job not found"}), 404
        return jsonify(info)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=9000)
