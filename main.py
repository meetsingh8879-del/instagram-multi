from flask import Flask, request, render_template, jsonify
from instagrapi import Client
import os
import time
import threading

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def send_messages_from_file(username, password, recipient, message_file, interval, haters_name, result_callback):
    cl = Client()
    try:

        cl.login(username, password)
        print("Logged in successfully!")

        recipient_id = None

        try:
            recipient_id = cl.user_id_from_username(recipient)
            if not recipient_id:
                raise ValueError("Recipient username not found!")
            print(f"Recipient username found: {recipient}")
        except Exception:
            try:
            	
                recipient_id = cl.chat_id_from_name(recipient)
                if not recipient_id:
                    raise ValueError("Group name not found!")
                print(f"Group found: {recipient}")
            except Exception:
                print("Neither username nor group found!")
                return "Recipient username or group not found!"

        with open(message_file, 'r') as file:
            messages = file.readlines()

        for message in messages:
            message = message.strip()
            if message:
                try:
                	
                    formatted_message = f"{haters_name} {message}"

                    if recipient_id:
                        if 'group' in recipient.lower(): 
                            cl.chat_send_message(recipient_id, formatted_message)
                            print(f"Message sent to group: {formatted_message}")
                        else:
                            cl.direct_send(formatted_message, [recipient_id])
                            print(f"Message sent to user: {formatted_message}")
                except Exception as e:
                    print(f"Failed to send message: {formatted_message}. Error: {e}")

            time.sleep(interval)

    except Exception as e:
        print(f"Error: {e}")
        return str(e)

    return "All messages sent successfully!"

def handle_user_request(username, password, recipient, message_file, interval, haters_name, result_callback):
    result = send_messages_from_file(username, password, recipient, message_file, interval, haters_name, result_callback)
    result_callback(result)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        recipient = request.form["recipient"]
        interval = int(request.form["interval"])
        haters_name = request.form["haters_name"]

        if "message_file" not in request.files:
            return "No message file uploaded!"
        
        file = request.files["message_file"]
        if file.filename == "":
            return "No selected file!"
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        def result_callback(result):
            return render_template("index.html", message=result)

        thread = threading.Thread(target=handle_user_request, args=(username, password, recipient, file_path, interval, haters_name, result_callback))
        thread.start()

        return render_template("index.html", message="Processing your request... Please wait!")

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=9000)
