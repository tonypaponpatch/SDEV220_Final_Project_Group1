import os
import io
import qrcode
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, send_file, abort)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from models import db, Admin, Category, Tag, MenuItem, QRCode

# ============================================================
# App Configuration
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///thai_diner.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Setup Login Manager for Admin accounts
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login' # Redirect here if not logged in

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# ============================================================
# Customer Routes (Menu Display)
# ============================================================

@app.route('/')
def index():
    return redirect(url_for('menu'))

@app.route('/menu')
def menu():
    """Main menu page for customers. Supports table numbers and filters."""
    table = request.args.get('table', type=int)
    tag_filter = request.args.get('filter')

    categories = Category.query.order_by(Category.display_order).all()
    menu_data = {}

    for cat in categories:
        # Show only available items
        items = cat.items.filter_by(is_available=True)

        # Apply dietary filters (e.g., Vegan, Gluten-free)
        if tag_filter:
            items = items.join(MenuItem.tags).filter(Tag.label == tag_filter)

        menu_data[cat] = items.all()

    dietary_tags = Tag.query.filter_by(tag_type='dietary').all()

    return render_template('menu.html', 
                           menu_data=menu_data, 
                           dietary_tags=dietary_tags, 
                           active_filter=tag_filter, 
                           table=table)

@app.route('/api/menu')
def api_menu():
    """Returns menu data in JSON format for the Frontend team."""
    tag_filter = request.args.get('filter')
    query = MenuItem.query.filter_by(is_available=True)

    if tag_filter:
        query = query.join(MenuItem.tags).filter(Tag.label == tag_filter)

    items = query.order_by(MenuItem.category_id, MenuItem.name).all()
    return jsonify([item.to_dict() for item in items])

# ============================================================
# Admin Routes (Authentication & Dashboard)
# ============================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()

        if admin and admin.check_password(password):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))

        flash('Invalid username or password', 'danger')

    return render_template('admin/login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    """Shows all menu items and categories to the Admin."""
    categories = Category.query.order_by(Category.display_order).all()
    items = MenuItem.query.order_by(MenuItem.category_id, MenuItem.name).all()
    return render_template('admin/dashboard.html', categories=categories, items=items)

# ============================================================
# Admin - MenuItem Management (CRUD)
# ============================================================

@app.route('/admin/items/new', methods=['GET', 'POST'])
@login_required
def admin_item_new():
    """Add a new dish to the menu."""
    categories = Category.query.order_by(Category.display_order).all()
    tags = Tag.query.all()

    if request.method == 'POST':
        # Safely handle the price input to prevent crashes
        try:
            price_val = float(request.form['price'])
        except ValueError:
            flash('Error: Price must be a number.', 'danger')
            return redirect(url_for('admin_item_new'))

        item = MenuItem(
            name = request.form['name'].strip(),
            description = request.form.get('description', '').strip(),
            price = price_val,
            image_url = request.form.get('image_url', '').strip() or None,
            category_id = int(request.form['category_id']),
            is_available = True
        )
        
        # Link selected tags to the item
        tag_ids = request.form.getlist('tag_ids', type=int)
        item.tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()

        db.session.add(item)
        db.session.commit()
        flash(f'Successfully added "{item.name}"', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/item_form.html', categories=categories, tags=tags, item=None)

@app.route('/admin/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_item_edit(item_id):
    """Edit an existing menu item."""
    item = MenuItem.query.get_or_404(item_id)
    categories = Category.query.order_by(Category.display_order).all()
    tags = Tag.query.all()

    if request.method == 'POST':
        try:
            item.price = float(request.form['price'])
        except ValueError:
            flash('Error: Price must be a number.', 'danger')
            return render_template('admin/item_form.html', categories=categories, tags=tags, item=item)

        item.name = request.form['name'].strip()
        item.description = request.form.get('description', '').strip()
        item.image_url = request.form.get('image_url', '').strip() or None
        item.category_id = int(request.form['category_id'])

        tag_ids = request.form.getlist('tag_ids', type=int)
        item.tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()

        db.session.commit()
        flash(f'Successfully updated "{item.name}"', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/item_form.html', categories=categories, tags=tags, item=item)

@app.route('/admin/items/<int:item_id>/toggle', methods=['POST'])
@login_required
def admin_item_toggle(item_id):
    """Quickly turn an item On/Off (e.g., when out of stock)."""
    item = MenuItem.query.get_or_404(item_id)
    item.toggle_available()
    db.session.commit()
    status = 'Available' if item.is_available else 'Sold Out'
    return jsonify({'is_available': item.is_available, 'status': status})

# ============================================================
# Admin - QR Code Management
# ============================================================

@app.route('/admin/qr')
@login_required
def admin_qr():
    qr_codes = QRCode.query.order_by(QRCode.table_number).all()
    return render_template('admin/qr.html', qr_codes=qr_codes)

@app.route('/admin/qr/generate', methods=['POST'])
@login_required
def admin_qr_generate():
    """Creates or updates a QR code for a specific table."""
    table_number = request.form.get('table_number', type=int)
    if not table_number:
        flash('Please enter a table number.', 'danger')
        return redirect(url_for('admin_qr'))

    base_url = request.host_url.rstrip('/')
    url = f'{base_url}/menu?table={table_number}'

    qr = QRCode.query.filter_by(table_number=table_number).first()
    if qr:
        qr.url = url
    else:
        qr = QRCode(table_number=table_number, url=url)
        db.session.add(qr)
    
    db.session.commit()
    flash(f'QR Code for Table {table_number} generated!', 'success')
    return redirect(url_for('admin_qr'))

@app.route('/admin/qr/<int:table_number>/download')
@login_required
def admin_qr_download(table_number):
    """Generates a PNG image of the QR code for download."""
    qr = QRCode.query.filter_by(table_number=table_number).first_or_404()
    img = qrcode.make(qr.url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name=f'table_{table_number}.png')

# ============================================================
# Database Initialization (Run once)
# ============================================================

@app.cli.command('init-db')
def init_db_command():
    """Command to setup the database and add starting data."""
    db.create_all()
    
    # Add default categories if empty
    if not Category.query.first():
        categories = [
            Category(name='appetizer', display_order=1),
            Category(name='main',      display_order=2),
            Category(name='drink',     display_order=3),
            Category(name='dessert',   display_order=4),
        ]
        db.session.add_all(categories)

        tags = [
            Tag(label='gluten_free', tag_type='dietary'),
            Tag(label='vegetarian',  tag_type='dietary'),
            Tag(label='spicy',       tag_type='badge'),
            Tag(label='popular',     tag_type='badge'),
        ]
        db.session.add_all(tags)
        
        # Create a default admin account
        admin = Admin(username='admin')
        admin.set_password('admin1234')
        db.session.add(admin)
        
        db.session.commit()
        print('Database initialized with default admin (admin / admin1234)')

if __name__ == '__main__':
    app.run(debug=True)