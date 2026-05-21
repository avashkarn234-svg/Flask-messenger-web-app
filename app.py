from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- Configuration ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whiteboard.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov'}
app.secret_key = "1a6ca5d363c97ba7e6354b8be0869632a87b0d6c7da4dfdbdb753a101a3dc39d5a3531783aab591d48a01396cb9498d7fa8c001f45e1b8f92dd0d16e67393052"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Database Schema Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='operator')
    public_key = db.Column(db.Text, nullable=True)
    encrypted_private_key = db.Column(db.Text, nullable=True)

class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

class ChannelKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    encrypted_key_block = db.Column(db.Text, nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(200), nullable=True)
    file_type = db.Column(db.String(10), nullable=True)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])
    recipient = db.relationship('User', foreign_keys=[recipient_id])

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext in {'mp4', 'mov'}: 
        return 'video'
    elif ext in {'png', 'jpg', 'jpeg', 'gif'}: 
        return 'image'
    return 'file'

with app.app_context():
    db.create_all()
    if not Channel.query.filter_by(name="general").first():
        db.session.add(Channel(name="general"))
        db.session.commit()

@app.before_request
def allow_custom_host():
    request.environ['HTTP_HOST'] = 'localhost:5000'

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def login():
    if session.get('logged_in'): 
        return redirect(url_for('messenger'))
    if request.method == "POST":
        u_name = request.form.get("username")
        p_word = request.form.get("password")
        user = User.query.filter_by(username=u_name).first()
        if user and user.password == p_word:
            session['logged_in'] = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            return redirect(url_for('messenger'))
        flash("Invalid handle credentials or access key denied.")
        return redirect(url_for('login'))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u_name = request.form.get("username")
        if User.query.filter_by(username=u_name).first():
            flash("Username handle is already provisioned.")
            return redirect(url_for('register'))
        role = 'admin' if User.query.count() == 0 else 'operator'
        new_user = User(
            username=u_name, password=request.form.get("password"), role=role,
            public_key=request.form.get("public_key"), encrypted_private_key=request.form.get("encrypted_private_key")
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Identity credentials compiled. Proceed to system sign-in.")
        return redirect(url_for('login'))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/messenger", methods=["GET", "POST"])  # <-- Fixed!
@app.route("/messenger/channel/<int:channel_id>", methods=["GET", "POST"])
@app.route("/messenger/dm/<int:recipient_id>", methods=["GET", "POST"])
@login_required
def messenger(channel_id=None, recipient_id=None):
    my_id = session['user_id']
    is_dm = (recipient_id is not None)
    
    if request.method == "POST":
        filename = None
        ftype = None
        file = request.files.get("file")
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            ftype = get_file_type(filename)

        content = request.form.get("content")
        if content or filename:
            new_post = Post(
                content=content, file_path=filename, file_type=ftype, user_id=my_id,
                channel_id=None if is_dm else (channel_id or 1), recipient_id=recipient_id if is_dm else None
            )
            db.session.add(new_post)
            db.session.commit()
            socketio.emit('db_update', {'type': 'dm' if is_dm else 'channel', 'id': recipient_id if is_dm else (channel_id or 1), 'sender': my_id, 'recipient': recipient_id})

        return redirect(url_for('messenger', recipient_id=recipient_id) if is_dm else url_for('messenger', channel_id=channel_id))

    channels = Channel.query.all()
    users = User.query.filter(User.id != my_id).all()
    search_query = request.args.get('search', '')
    current_channel, recipient = None, None

    if is_dm:
        recipient = User.query.get_or_404(recipient_id)
        msg_query = Post.query.filter(((Post.user_id == my_id) & (Post.recipient_id == recipient_id)) | ((Post.user_id == recipient_id) & (Post.recipient_id == my_id)))
    else:
        if not channel_id:
            first_ch = Channel.query.first()
            channel_id = first_ch.id if first_ch else 1
        current_channel = Channel.query.get_or_404(channel_id)
        msg_query = Post.query.filter_by(channel_id=channel_id)

    if search_query: 
        msg_query = msg_query.filter(Post.content.contains(search_query))
    messages = msg_query.order_by(Post.date_posted.asc()).all()

    return render_template("messenger.html", channels=channels, users=users, messages=messages, current_channel=current_channel, recipient=recipient, is_dm=is_dm, search_query=search_query)

@app.route("/channel/create", methods=["POST"])
@login_required
def create_channel():
    if session.get('role') not in ['admin', 'moderator']: 
        return "Access Revoked", 403
    name = secure_filename(request.form.get("name")).lower()
    if name and not Channel.query.filter_by(name=name).first():
        db.session.add(Channel(name=name))
        db.session.commit()
        socketio.emit('db_update', {'type': 'system'})
    return redirect(url_for('messenger'))

@app.route("/post/delete/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id == session['user_id'] or session['role'] in ['admin', 'moderator']:
        db.session.delete(post)
        db.session.commit()
        socketio.emit('db_update', {'type': 'system'})
    return redirect(request.referrer or url_for('messenger'))

# --- Cryptographic Helpers ---
@app.route("/api/my_private_key")
@login_required
def my_private_key():
    return jsonify({"encrypted_private_key": User.query.get(session['user_id']).encrypted_private_key})

@app.route("/api/crypto_bootstrap/<int:peer_id>")
@login_required
def crypto_bootstrap(peer_id):
    return jsonify({"public_key": User.query.get_or_404(peer_id).public_key})

@app.route("/api/channel_keys/<int:channel_id>", methods=["GET", "POST"])
@login_required
def channel_keys(channel_id):
    if request.method == "POST":
        incoming_data = request.get_json() or {}
        ChannelKey.query.filter_by(channel_id=channel_id).delete()
        for block in incoming_data.get('keys', []):
            db.session.add(ChannelKey(channel_id=channel_id, user_id=block['user_id'], encrypted_key_block=block['encrypted_key_block']))
        db.session.commit()
        return jsonify({"status": "synchronized"})

    rk = ChannelKey.query.filter_by(channel_id=channel_id).all()
    return jsonify({"users": [{"id": u.id, "username": u.username} for u in User.query.all()], "keys": {k.user_id: k.encrypted_key_block for k in rk}})

# --- Native Service Worker Header Injection Route ---
@app.route('/static/sw.js')
def serve_service_worker():
    response = send_from_directory('static', 'sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
