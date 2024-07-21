from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from twilio.rest import Client
from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config
import os
import random
import string
import phonenumbers

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
mail = Mail(app)
bootstrap = Bootstrap(app)

from models import User, Item

def generate_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=5))

def format_phone_number(phone_number):
    try:
        parsed_number = phonenumbers.parse(phone_number, None)
        if phonenumbers.is_valid_number(parsed_number):
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        else:
            raise ValueError("Invalid phone number")
    except phonenumbers.NumberParseException:
        raise ValueError("Invalid phone number format")

@app.route('/')
def index():
    reported_items = Item.query.filter_by(reported=True).all()
    return render_template('index.html', reported_items=reported_items)

@app.route('/search', methods=['POST'])
def search():
    item_id = request.form['item_id'].strip().lower()
    item = Item.query.filter_by(id=item_id, reported=True).first()
    if item:
        return jsonify({'status': 'found', 'item': {
            'id': item.id,
            'name': item.name,
            'image': url_for('static', filename='useruploads/' + item.image)
        }})
    return jsonify({'status': 'not_found'})

@app.route('/send_message', methods=['POST'])
def send_message():
    item_id = request.form['item_id']
    message_content = request.form['message']
    item = Item.query.filter_by(id=item_id).first()
    if item:
        try:
            formatted_phone = format_phone_number(item.phone)
            # Send SMS
            client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])
            client.messages.create(
                body=f"Your item with ID {item_id} has a message: {message_content}",
                from_=app.config['TWILIO_PHONE_NUMBER'],
                to=formatted_phone
            )

            # Send Email
            msg = Message('Message regarding your missing item', sender=app.config['MAIL_USERNAME'], recipients=[item.email])
            msg.body = f"Message regarding your item with ID {item_id}: {message_content}"
            mail.send(msg)

            return jsonify({'status': 'success'})
        except ValueError as e:
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error'})

@app.route('/report_missing/<string:item_id>', methods=['POST'])
def report_missing(item_id):
    item = Item.query.filter_by(id=item_id).first()
    if item:
        item.reported = True
        db.session.commit()

        try:
            formatted_phone = format_phone_number(item.phone)
            # Send SMS
            client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])
            client.messages.create(
                body=f"Your item with ID {item_id} has been reported as missing.",
                from_=app.config['TWILIO_PHONE_NUMBER'],
                to=formatted_phone
            )

            # Send Email
            msg = Message('Item Reported as Missing', sender=app.config['MAIL_USERNAME'], recipients=[item.email])
            msg.body = f"Your item with ID {item_id} has been reported as missing."
            mail.send(msg)

            flash('The owner has been notified.')
        except ValueError as e:
            flash(f"Failed to send notification: {str(e)}")
        return redirect(url_for('index'))
    flash('Item not found')
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email == 'office@stimmungskompass.at' and password == 'OtterRitaPebble':
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template('admin_login.html')

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        image = request.files['image']
        if image:
            filename = secure_filename(image.filename)
            upload_folder = os.path.join('static', 'useruploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            image_path = os.path.join(upload_folder, filename)
            image.save(image_path)

            item_id = generate_id().lower()
            new_item = Item(id=item_id, name=name, email=email, phone=phone, image=filename, reported=True)
            db.session.add(new_item)
            db.session.commit()
            flash('Item added successfully')
    items = Item.query.all()
    return render_template('admin_dashboard.html', items=items)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form.get('email')
        phone = request.form.get('phone')
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password, email=email, phone=phone)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/user/dashboard', methods=['GET', 'POST'])
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        title = request.form['title']
        image = request.files['image']
        if image:
            filename = secure_filename(image.filename)
            upload_folder = os.path.join('static', 'useruploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            image_path = os.path.join(upload_folder, filename)
            image.save(image_path)

            item_id = generate_id().lower()
            new_item = Item(id=item_id, title=title, name=name, email=email, phone=phone, image=filename, reported=True, user_id=user.id)
            db.session.add(new_item)
            db.session.commit()
            flash('Item added successfully')
    items = Item.query.filter_by(user_id=user.id).all()
    return render_template('user_dashboard.html', items=items)

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
