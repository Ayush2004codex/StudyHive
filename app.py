from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, send, join_room, leave_room
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///studyhive.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'txt'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO(app)  # Initialize SocketIO

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    groups = db.relationship('Group', backref='creator', lazy=True)

# Group Model
class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unique_id = db.Column(db.String(10), unique=True, nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    members = db.relationship('User', secondary='group_members', backref='joined_groups')
    notes = db.relationship('Note', backref='group', lazy=True)

# Association Table for Group Members
group_members = db.Table('group_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('group.id'), primary_key=True)
)

# Note Model
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(120), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    created_groups = Group.query.filter_by(creator_id=current_user.id).all()
    joined_groups = current_user.joined_groups
    return render_template('dashboard.html', created_groups=created_groups, joined_groups=joined_groups)

@app.route('/group/<unique_id>', methods=['GET', 'POST'])
@login_required
def group(unique_id):
    group = Group.query.filter_by(unique_id=unique_id).first()
    if not group:
        flash('Group not found.')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        content = request.form.get('content')
        file = request.files.get('file')

        if content or file:
            note = Note(content=content, group_id=group.id)
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                note.filename = filename
            db.session.add(note)
            db.session.commit()
            flash('Note added successfully!')
        else:
            flash('Please add content or upload a file.')

    return render_template('group.html', group=group)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    name = request.form['name']
    unique_id = request.form['unique_id']
    group = Group(name=name, unique_id=unique_id, creator_id=current_user.id)
    group.members.append(current_user)
    db.session.add(group)
    db.session.commit()
    flash('Group created successfully!')
    return redirect(url_for('dashboard'))

@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    unique_id = request.form['unique_id']
    group = Group.query.filter_by(unique_id=unique_id).first()
    if group:
        if current_user not in group.members:
            group.members.append(current_user)
            db.session.commit()
            flash('Joined group successfully!')
        else:
            flash('You are already a member of this group.')
    else:
        flash('Group not found.')
    return redirect(url_for('dashboard'))

# SocketIO Events
@socketio.on('join')
def handle_join(data):
    room = data['room']
    join_room(room)
    send(f"{current_user.username} has joined the group.", room=room)

@socketio.on('leave')
def handle_leave(data):
    room = data['room']
    leave_room(room)
    send(f"{current_user.username} has left the group.", room=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    message = data['message']
    send(f"{current_user.username}: {message}", room=room)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
