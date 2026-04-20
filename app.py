from flask import Flask, render_template, request, redirect, url_for, send_from_directory, Response, session
from functools import wraps
from secrets import token_hex
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)

# --- Configuration ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whiteboard.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov'}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
app.secret_key= "c150df3542374b09785458a888e86863e4d45b5236c71e46"
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function




class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=True)
    file_path = db.Column(db.String(200), nullable=True) # Stores filename
    file_type = db.Column(db.String(10), nullable=True)  # 'image' or 'video'
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'mp4', 'mov'}: 
      return 'video'
    return 'image'

with app.app_context():
    db.create_all()

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == "@v@$hK423":
            # --- THE MISSING LINK ---
            session['logged_in'] = True  
            # ------------------------
            return redirect(url_for('messenger'))
        return "<h1>Access Denied</h1><a href='/'>Back</a>"
    
    # Optional: If they are already logged in, don't show the login page
    if session.get('logged_in'):
        return redirect(url_for('messenger'))
        
    return render_template("login.html")


@app.route("/messenger", methods=["GET", "POST"])
@login_required
def messenger():
    if request.method == "POST":
        content = request.form.get("content")
        file = request.files.get("file")
        
        filename = None
        ftype = None

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            ftype = get_file_type(filename)

        if content or filename:
            new_post = Post(content=content, file_path=filename, file_type=ftype)
            db.session.add(new_post)
            db.session.commit()
        return redirect(url_for('messenger'))
    
    all_posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template("messenger.html", messages=all_posts)

@app.route("/check_updates")
def check_updates():
    return {"count": Post.query.count()}



if __name__ == '__main__':
    # Use threaded=True so the stream doesn't block other routes
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)