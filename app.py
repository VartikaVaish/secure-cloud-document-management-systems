from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import boto3
import mimetypes
from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET")
print("Access Key:", AWS_ACCESS_KEY)
print("Secret Key:", AWS_SECRET_KEY)
print("Region:", AWS_REGION)
print("Bucket:", S3_BUCKET)

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

app = Flask(__name__)
app.secret_key = "securecloud123"

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = None

        try:
            conn = sqlite3.connect("database.db", timeout=10)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM users WHERE username=?",
                (username,)
            )

            if cursor.fetchone():
                flash("Username already exists!")
                return redirect(url_for("register"))

            hashed_password = generate_password_hash(password)

            cursor.execute(
                "INSERT INTO users(username, password) VALUES(?, ?)",
                (username, hashed_password)
            )

            conn.commit()
            flash("Registration Successful! Please Login.")
            return redirect(url_for("login"))

        except sqlite3.Error as e:
            flash(f"Database Error: {e}")
            return redirect(url_for("register"))

        finally:
            if conn:
                conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db", timeout=10)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT password FROM users WHERE username=?",
            (username,)
        )

        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[0], password):
            session.clear()
            session["username"] = username
            flash("Login Successful!")
            return redirect(url_for("dashboard"))

        flash("Invalid Username or Password")
        return redirect(url_for("login"))

    return render_template("login.html")
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    search = request.args.get("search", "")

    response = s3.list_objects_v2(Bucket=S3_BUCKET)

    if "Contents" in response:
        files = [obj["Key"] for obj in response["Contents"]]
    else:
        files = []

    total_files = len(files)

    if search:
        files = [
            file for file in files
            if search.lower() in file.lower()
        ]

    return render_template(
        "index.html",
        files=files,
        total_files=total_files,
        username=session["username"]
    )
@app.route("/upload", methods=["POST"])
def upload():
    if "username" not in session:
        return redirect(url_for("login"))

    file = request.files["document"]

    if file and file.filename != "":
        print("Bucket:", S3_BUCKET)
        print("Region:", AWS_REGION)

        content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

        s3.upload_fileobj(
            file,
            S3_BUCKET,
            file.filename,
            ExtraArgs={
                "ContentType": content_type
            }
        )

        flash("Document uploaded successfully to AWS S3!")
    else:
        flash("Please select a file.")

    return redirect(url_for("dashboard"))
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": filename,
            "ResponseContentDisposition": "inline"
        },
        ExpiresIn=3600
    )
    return redirect(url)
@app.route("/download/<path:filename>")
def download(filename):
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": filename,
            "ResponseContentDisposition": f'attachment; filename="{filename}"'
        },
        ExpiresIn=3600
    )
    return redirect(url)
@app.route("/delete/<path:filename>")
def delete(filename):
    if "username" not in session:
        return redirect(url_for("login"))

    s3.delete_object(
        Bucket=S3_BUCKET,
        Key=filename
    )

    flash("Document deleted successfully!")
    return redirect(url_for("dashboard"))
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)