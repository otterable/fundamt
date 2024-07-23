from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from twilio.rest import Client
from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_babel import Babel, lazy_gettext as _l, gettext as _
from config import Config
import os
import random
import string
import phonenumbers
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
mail = Mail(app)
bootstrap = Bootstrap(app)
babel = Babel()

from models import User, Item, ItemImage

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

@app.before_request
def before_request():
    g.locale = request.args.get('lang') or request.accept_languages.best_match(['en', 'de', 'fr', 'it'])
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])
    print(f"[DEBUG] Current locale set to: {g.locale}")

def get_locale():
    return g.locale

babel.init_app(app, locale_selector=get_locale)

@app.route('/')
def index():
    reported_items = Item.query.filter_by(reported=True).all()
    return render_template('index.html', reported_items=reported_items, user=g.user)

@app.route('/my_tracked_items', methods=['GET', 'POST'])
def my_tracked_items():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    items = Item.query.filter_by(user_id=user.id).all()
    message = None
    
    if request.method == 'POST':
        item_id = request.form['item_id']
        item = Item.query.get(item_id)
        action = request.form['action']
        
        if action == 'report_missing':
            item.reported = True
            item.reported_since = datetime.utcnow()  # Set reported_since
            db.session.commit()
            message = f"Item ID {item_id} reported as missing."
        elif action == 'unreport':
            item.reported = False
            item.reported_since = None  # Clear reported_since
            db.session.commit()
            message = f"Item ID {item_id} unreported as missing."
        elif action == 'delete':
            db.session.delete(item)
            db.session.commit()
            message = f"Item ID {item_id} deleted."

    return render_template('my_tracked_items.html', items=items, user=user, message=message)

@app.route('/delete_item', methods=['POST'])
def delete_item():
    item_id = request.form['delete_item_id']
    item = Item.query.get(item_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash(_('Item deleted successfully'))
    else:
        flash(_('Item not found'))
    return redirect(url_for('my_tracked_items'))

@app.route('/search', methods=['POST'])
def search():
    item_id = request.form['item_id'].strip().lower()
    item = Item.query.filter_by(id=item_id, reported=True).first()
    if item:
        return jsonify({'status': 'found', 'item': {
            'id': item.id,
            'title': item.title,
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
        item.reported_since = datetime.utcnow()  # Set reported_since
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

            flash(_('The owner has been notified.'))
        except ValueError as e:
            flash(_('Failed to send notification: ') + str(e))
        return redirect(url_for('index'))
    flash(_('Item not found'))
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email == 'office@stimmungskompass.at' and password == 'OtterRitaPebble':
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash(_('Invalid credentials'))
    return render_template('admin_login.html')

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        images = request.files.getlist('images')
        
        if images:
            image_filenames = []
            for image in images:
                filename = secure_filename(image.filename)
                upload_folder = os.path.join('static', 'useruploads')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                image_path = os.path.join(upload_folder, filename)
                image.save(image_path)
                image_filenames.append(filename)
            
            item_id = generate_id().lower()
            new_item = Item(
                id=item_id,
                title=name,
                name=name,
                email=email,
                phone=phone,
                image=image_filenames[0],  # First image is the title image
                reported=True,
                reported_since=datetime.utcnow()
            )
            db.session.add(new_item)
            db.session.commit()
            
            # Save other images if any
            for filename in image_filenames[1:]:
                additional_image = ItemImage(item_id=item_id, filename=filename)
                db.session.add(additional_image)
            db.session.commit()
            
            flash(_('Item added successfully'))
    items = Item.query.all()
    return render_template('admin_dashboard.html', items=items, user=g.user)

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
        flash(_('Registration successful'))
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
        flash(_('Invalid credentials'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/register_item_for_tracking', methods=['GET', 'POST'])
def register_item_for_tracking():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        title = request.form['title']
        images = request.files.getlist('images')
        
        if images:
            image_filenames = []
            for image in images:
                filename = secure_filename(image.filename)
                upload_folder = os.path.join('static', 'useruploads')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                image_path = os.path.join(upload_folder, filename)
                image.save(image_path)
                image_filenames.append(filename)
            
            item_id = generate_id().lower()
            user_id = session.get('user_id')
            new_item = Item(
                id=item_id,
                title=title,
                name=name,
                email=email,
                phone=phone,
                image=image_filenames[0],  # First image is the title image
                reported=False,
                user_id=user_id,
                tracked_since=datetime.utcnow()
            )
            db.session.add(new_item)
            db.session.commit()
            
            # Save other images if any
            for filename in image_filenames[1:]:
                additional_image = ItemImage(item_id=item_id, filename=filename)
                db.session.add(additional_image)
            db.session.commit()
            
            return redirect(url_for('item_registered', item_id=item_id))
    return render_template('register_item_for_tracking.html', user=g.user)

@app.route('/register_item_as_missing', methods=['GET', 'POST'])
def register_item_as_missing():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        title = request.form['title']
        images = request.files.getlist('images')
        
        if images:
            image_filenames = []
            for image in images:
                filename = secure_filename(image.filename)
                upload_folder = os.path.join('static', 'useruploads')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                image_path = os.path.join(upload_folder, filename)
                image.save(image_path)
                image_filenames.append(filename)
            
            item_id = generate_id().lower()
            new_item = Item(
                id=item_id,
                title=title,
                name=name,
                email=email,
                phone=phone,
                image=image_filenames[0],  # First image is the title image
                reported=True,
                reported_since=datetime.utcnow()
            )
            db.session.add(new_item)
            db.session.commit()
            
            # Save other images if any
            for filename in image_filenames[1:]:
                additional_image = ItemImage(item_id=item_id, filename=filename)
                db.session.add(additional_image)
            db.session.commit()
            
            return render_template('item_registered.html', item_id=item_id)
    return render_template('register_item_as_missing.html', user=g.user)

@app.route('/item_registered')
def item_registered():
    item_id = request.args.get('item_id')
    return render_template('item_registered.html', item_id=item_id)

@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == '__main__':
    db.create_all()
    print("[DEBUG] Flask app has started")
    app.run(debug=True)
