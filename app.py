import os
import io
import qrcode
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, send_file, abort)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from models import db, Admin, Category, Tag, MenuItem, QRCode, MeatOption, SpicyLevel, AddOn

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
login_manager.login_view = 'admin_login'  # Redirect here if not logged in

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
    """Main menu page for customers. Supports table numbers and dietary filters."""
    table      = request.args.get('table', type=int)
    tag_filter = request.args.get('filter')

    categories = Category.query.order_by(Category.display_order).all()
    menu_data  = {}

    for cat in categories:
        items = cat.items.filter_by(is_available=True)
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
    """
    Returns full menu data as JSON for the Frontend team.
    Each item includes meat_options and add_ons already embedded.
    Use GET /api/spicy-levels for the global spicy level list.
    """
    tag_filter = request.args.get('filter')
    query = MenuItem.query.filter_by(is_available=True)

    if tag_filter:
        query = query.join(MenuItem.tags).filter(Tag.label == tag_filter)

    items = query.order_by(MenuItem.category_id, MenuItem.name).all()
    return jsonify([item.to_dict() for item in items])


@app.route('/api/spicy-levels')
def api_spicy_levels():
    """
    Returns the global spicy level list sorted from mildest to hottest.
    Frontend uses this to build the spicy picker for items with has_spicy_option=True.
    """
    levels = SpicyLevel.query.order_by(SpicyLevel.level).all()
    return jsonify([lvl.to_dict() for lvl in levels])


# ============================================================
# Admin Routes (Authentication)
# ============================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin    = Admin.query.filter_by(username=username).first()

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
    items      = MenuItem.query.order_by(MenuItem.category_id, MenuItem.name).all()
    return render_template('admin/dashboard.html', categories=categories, items=items)


# ============================================================
# Admin - MenuItem CRUD
# ============================================================

@app.route('/admin/items/new', methods=['GET', 'POST'])
@login_required
def admin_item_new():
    """Add a new dish to the menu."""
    categories   = Category.query.order_by(Category.display_order).all()
    tags         = Tag.query.all()
    meat_options = MeatOption.query.order_by(MeatOption.name).all()
    add_ons      = AddOn.query.order_by(AddOn.name).all()

    if request.method == 'POST':
        try:
            price_val = float(request.form['price'])
        except ValueError:
            flash('Error: Price must be a number.', 'danger')
            return redirect(url_for('admin_item_new'))

        item = MenuItem(
            name             = request.form['name'].strip(),
            description      = request.form.get('description', '').strip(),
            price            = price_val,
            image_url        = request.form.get('image_url', '').strip() or None,
            category_id      = int(request.form['category_id']),
            has_spicy_option = 'has_spicy_option' in request.form,  # checkbox
            is_available     = True
        )

        tag_ids   = request.form.getlist('tag_ids',  type=int)
        meat_ids  = request.form.getlist('meat_ids',  type=int)
        addon_ids = request.form.getlist('addon_ids', type=int)

        item.tags         = Tag.query.filter(Tag.id.in_(tag_ids)).all()
        item.meat_options = MeatOption.query.filter(MeatOption.id.in_(meat_ids)).all()
        item.add_ons      = AddOn.query.filter(AddOn.id.in_(addon_ids)).all()

        db.session.add(item)
        db.session.commit()
        flash(f'Successfully added "{item.name}"', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/item_form.html',
                           categories=categories, tags=tags,
                           meat_options=meat_options, add_ons=add_ons,
                           item=None)


@app.route('/admin/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_item_edit(item_id):
    """Edit an existing menu item."""
    item         = MenuItem.query.get_or_404(item_id)
    categories   = Category.query.order_by(Category.display_order).all()
    tags         = Tag.query.all()
    meat_options = MeatOption.query.order_by(MeatOption.name).all()
    add_ons      = AddOn.query.order_by(AddOn.name).all()

    if request.method == 'POST':
        try:
            item.price = float(request.form['price'])
        except ValueError:
            flash('Error: Price must be a number.', 'danger')
            return render_template('admin/item_form.html',
                                   categories=categories, tags=tags,
                                   meat_options=meat_options, add_ons=add_ons,
                                   item=item)

        item.name             = request.form['name'].strip()
        item.description      = request.form.get('description', '').strip()
        item.image_url        = request.form.get('image_url', '').strip() or None
        item.category_id      = int(request.form['category_id'])
        item.has_spicy_option = 'has_spicy_option' in request.form

        tag_ids   = request.form.getlist('tag_ids',  type=int)
        meat_ids  = request.form.getlist('meat_ids',  type=int)
        addon_ids = request.form.getlist('addon_ids', type=int)

        item.tags         = Tag.query.filter(Tag.id.in_(tag_ids)).all()
        item.meat_options = MeatOption.query.filter(MeatOption.id.in_(meat_ids)).all()
        item.add_ons      = AddOn.query.filter(AddOn.id.in_(addon_ids)).all()

        db.session.commit()
        flash(f'Successfully updated "{item.name}"', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/item_form.html',
                           categories=categories, tags=tags,
                           meat_options=meat_options, add_ons=add_ons,
                           item=item)


@app.route('/admin/items/<int:item_id>/delete', methods=['POST'])
@login_required
def admin_item_delete(item_id):
    """Delete a menu item permanently."""
    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash(f'Deleted "{item.name}"', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/items/<int:item_id>/toggle', methods=['POST'])
@login_required
def admin_item_toggle(item_id):
    """Quickly turn an item On/Off (e.g. when out of stock)."""
    item = MenuItem.query.get_or_404(item_id)
    item.toggle_available()
    db.session.commit()
    status = 'Available' if item.is_available else 'Sold Out'
    return jsonify({'is_available': item.is_available, 'status': status})


# ============================================================
# Admin - Meat Options CRUD
# ============================================================

@app.route('/admin/meats')
@login_required
def admin_meat_list():
    """List all meat/protein options."""
    meats = MeatOption.query.order_by(MeatOption.name).all()
    return render_template('admin/meat_list.html', meats=meats)


@app.route('/admin/meats/new', methods=['GET', 'POST'])
@login_required
def admin_meat_new():
    """Add a new meat/protein option."""
    if request.method == 'POST':
        try:
            extra = float(request.form.get('extra_price', 0))
        except ValueError:
            extra = 0.0

        meat = MeatOption(
            name        = request.form['name'].strip(),
            extra_price = extra,
            is_default  = 'is_default' in request.form
        )
        db.session.add(meat)
        db.session.commit()
        flash(f'Added meat option "{meat.name}"', 'success')
        return redirect(url_for('admin_meat_list'))

    return render_template('admin/meat_form.html', meat=None)


@app.route('/admin/meats/<int:meat_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_meat_edit(meat_id):
    """Edit an existing meat/protein option."""
    meat = MeatOption.query.get_or_404(meat_id)

    if request.method == 'POST':
        try:
            meat.extra_price = float(request.form.get('extra_price', 0))
        except ValueError:
            meat.extra_price = 0.0

        meat.name       = request.form['name'].strip()
        meat.is_default = 'is_default' in request.form
        db.session.commit()
        flash(f'Updated "{meat.name}"', 'success')
        return redirect(url_for('admin_meat_list'))

    return render_template('admin/meat_form.html', meat=meat)


@app.route('/admin/meats/<int:meat_id>/delete', methods=['POST'])
@login_required
def admin_meat_delete(meat_id):
    """Delete a meat option (also removes it from all linked menu items)."""
    meat = MeatOption.query.get_or_404(meat_id)
    db.session.delete(meat)
    db.session.commit()
    flash(f'Deleted "{meat.name}"', 'success')
    return redirect(url_for('admin_meat_list'))


# ============================================================
# Admin - Spicy Levels CRUD
# ============================================================

@app.route('/admin/spicy')
@login_required
def admin_spicy_list():
    """List all spicy levels sorted from mildest to hottest."""
    levels = SpicyLevel.query.order_by(SpicyLevel.level).all()
    return render_template('admin/spicy_list.html', levels=levels)


@app.route('/admin/spicy/new', methods=['GET', 'POST'])
@login_required
def admin_spicy_new():
    """Add a new spicy level."""
    if request.method == 'POST':
        try:
            level_val = int(request.form['level'])
        except ValueError:
            flash('Error: Level must be a whole number.', 'danger')
            return redirect(url_for('admin_spicy_new'))

        spicy = SpicyLevel(
            label      = request.form['label'].strip(),
            level      = level_val,
            is_default = 'is_default' in request.form
        )
        db.session.add(spicy)
        db.session.commit()
        flash(f'Added spicy level "{spicy.label}"', 'success')
        return redirect(url_for('admin_spicy_list'))

    return render_template('admin/spicy_form.html', spicy=None)


@app.route('/admin/spicy/<int:spicy_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_spicy_edit(spicy_id):
    """Edit an existing spicy level."""
    spicy = SpicyLevel.query.get_or_404(spicy_id)

    if request.method == 'POST':
        try:
            spicy.level = int(request.form['level'])
        except ValueError:
            flash('Error: Level must be a whole number.', 'danger')
            return render_template('admin/spicy_form.html', spicy=spicy)

        spicy.label      = request.form['label'].strip()
        spicy.is_default = 'is_default' in request.form
        db.session.commit()
        flash(f'Updated "{spicy.label}"', 'success')
        return redirect(url_for('admin_spicy_list'))

    return render_template('admin/spicy_form.html', spicy=spicy)


@app.route('/admin/spicy/<int:spicy_id>/delete', methods=['POST'])
@login_required
def admin_spicy_delete(spicy_id):
    """Delete a spicy level."""
    spicy = SpicyLevel.query.get_or_404(spicy_id)
    db.session.delete(spicy)
    db.session.commit()
    flash(f'Deleted "{spicy.label}"', 'success')
    return redirect(url_for('admin_spicy_list'))


# ============================================================
# Admin - Add-Ons CRUD
# ============================================================

@app.route('/admin/addons')
@login_required
def admin_addon_list():
    """List all available add-ons."""
    add_ons = AddOn.query.order_by(AddOn.name).all()
    return render_template('admin/addon_list.html', add_ons=add_ons)


@app.route('/admin/addons/new', methods=['GET', 'POST'])
@login_required
def admin_addon_new():
    """Add a new add-on option."""
    if request.method == 'POST':
        try:
            price_val = float(request.form['price'])
        except ValueError:
            flash('Error: Price must be a number.', 'danger')
            return redirect(url_for('admin_addon_new'))

        addon = AddOn(
            name  = request.form['name'].strip(),
            price = price_val
        )
        db.session.add(addon)
        db.session.commit()
        flash(f'Added add-on "{addon.name}"', 'success')
        return redirect(url_for('admin_addon_list'))

    return render_template('admin/addon_form.html', addon=None)


@app.route('/admin/addons/<int:addon_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_addon_edit(addon_id):
    """Edit an existing add-on."""
    addon = AddOn.query.get_or_404(addon_id)

    if request.method == 'POST':
        try:
            addon.price = float(request.form['price'])
        except ValueError:
            flash('Error: Price must be a number.', 'danger')
            return render_template('admin/addon_form.html', addon=addon)

        addon.name = request.form['name'].strip()
        db.session.commit()
        flash(f'Updated "{addon.name}"', 'success')
        return redirect(url_for('admin_addon_list'))

    return render_template('admin/addon_form.html', addon=addon)


@app.route('/admin/addons/<int:addon_id>/delete', methods=['POST'])
@login_required
def admin_addon_delete(addon_id):
    """Delete an add-on (also removes it from all linked menu items)."""
    addon = AddOn.query.get_or_404(addon_id)
    db.session.delete(addon)
    db.session.commit()
    flash(f'Deleted "{addon.name}"', 'success')
    return redirect(url_for('admin_addon_list'))


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
    url      = f'{base_url}/menu?table={table_number}'

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
    qr  = QRCode.query.filter_by(table_number=table_number).first_or_404()
    img = qrcode.make(qr.url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png', as_attachment=True,
                     download_name=f'table_{table_number}.png')


# ============================================================
# Database Initialization (Run once with: flask init-db)
# ============================================================

@app.cli.command('init-db')
def init_db_command():
    """Setup the database and add default starting data."""
    db.create_all()

    if not Category.query.first():
        db.session.add_all([
            Category(name='appetizer', display_order=1),
            Category(name='main',      display_order=2),
            Category(name='drink',     display_order=3),
            Category(name='dessert',   display_order=4),
        ])

        db.session.add_all([
            Tag(label='gluten_free', tag_type='dietary'),
            Tag(label='vegetarian',  tag_type='dietary'),
            Tag(label='spicy',       tag_type='badge'),
            Tag(label='popular',     tag_type='badge'),
        ])

        # Default meat options (Chicken pre-selected as default)
        db.session.add_all([
            MeatOption(name='Chicken', extra_price=0.0,  is_default=True),
            MeatOption(name='Pork',    extra_price=0.0,  is_default=False),
            MeatOption(name='Beef',    extra_price=20.0, is_default=False),
            MeatOption(name='Shrimp',  extra_price=30.0, is_default=False),
            MeatOption(name='Tofu',    extra_price=0.0,  is_default=False),
        ])

        # Default spicy levels (Medium pre-selected as default)
        db.session.add_all([
            SpicyLevel(label='No Spice',  level=0, is_default=False),
            SpicyLevel(label='Mild',      level=1, is_default=False),
            SpicyLevel(label='Medium',    level=2, is_default=True),
            SpicyLevel(label='Hot',       level=3, is_default=False),
            SpicyLevel(label='Extra Hot', level=4, is_default=False),
        ])

        # Default add-ons
        db.session.add_all([
            AddOn(name='Extra Egg',    price=15.0),
            AddOn(name='Extra Tofu',   price=20.0),
            AddOn(name='Extra Shrimp', price=40.0),
            AddOn(name='Extra Rice',   price=10.0),
            AddOn(name='Extra Sauce',  price=5.0),
        ])

        admin = Admin(username='admin')
        admin.set_password('admin1234')
        db.session.add(admin)

        db.session.commit()
        print('Database initialized with default data.')
        print('Admin -> username: admin | password: admin1234')
        print('!! Please change the password after first login !!')


if __name__ == '__main__':
    app.run(debug=True)
