from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Database setup
db = SQLAlchemy()

# ============================================================
# 1. Connection Table: menu_item_tag
# This table links Menu Items and Tags (Many-to-Many).
# For example: "Pad Thai" can have tags like 'Popular' and 'Spicy'.
# If an item or tag is deleted, it is removed here too.
# ============================================================
menu_item_tag = db.Table(
    'menu_item_tag',
    db.Column('menu_item_id', db.Integer, db.ForeignKey('menu_item.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id',       db.Integer, db.ForeignKey('tag.id',       ondelete='CASCADE'), primary_key=True)
)


# ============================================================
# 2. Admin Model
# This is for staff accounts. They can log in to manage the menu.
# - We use UserMixin for the Flask login system.
# - We do not store real passwords. We only store secret hashes for safety.
# ============================================================
class Admin(UserMixin, db.Model):
    __tablename__ = 'admin'

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)  # never store plain-text passwords

    def set_password(self, password):
        """Hash a plain-text password and store it. Call this when creating or updating a password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Return True if the given plain-text password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Admin {self.username}>'


# ============================================================
# 3. QR Code Model
# This stores QR code info for each table.
# - One table has only one QR code.
# - The 'url' is the link that customers scan to see the menu.
# ============================================================
class QRCode(db.Model):
    __tablename__ = 'qr_code'

    id           = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, unique=True, nullable=False)  # each table gets one QR
    url          = db.Column(db.String(300), nullable=False)            # URL encoded into the QR image

    def __repr__(self):
        return f'<QRCode table={self.table_number}>'


# ============================================================
# 4. Category Model
# This groups food items into sections like Appetizers or Drinks.
# - One Category can have many Menu Items.
# - 'display_order' helps us sort which category shows first.
# ============================================================
CATEGORY_NAMES = ('appetizer', 'main', 'drink', 'dessert')

class Category(db.Model):
    __tablename__ = 'category'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(50), unique=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)  # lower = shown first

    # One-to-many: one Category has many MenuItems.
    # lazy='dynamic' means items are loaded as a query object (supports .filter_by() etc.)
    # backref='category' lets MenuItem access its category via item.category
    items = db.relationship('MenuItem', backref='category', lazy='dynamic',
                            order_by='MenuItem.name')

    def __repr__(self):
        return f'<Category {self.name}>'


# ============================================================
# 5. Tag Model
# These are labels for food like 'Gluten-Free' or 'Spicy'.
# - 'dietary' tags are for healthy filters.
# - 'badge' tags are icons to show on the food picture.
# ============================================================
TAG_TYPES = ('dietary', 'badge')

class Tag(db.Model):
    __tablename__ = 'tag'

    id       = db.Column(db.Integer, primary_key=True)
    label    = db.Column(db.String(50), unique=True, nullable=False)   # e.g. 'gluten_free'
    tag_type = db.Column(db.String(20), nullable=False)                # 'dietary' or 'badge'

    def __repr__(self):
        return f'<Tag {self.label} ({self.tag_type})>'


# ============================================================
# 6. Menu Item Model
# This is the main part. It stores food name, price, and image.
# - 'is_available': Admin can hide items if they are sold out.
# - 'to_dict': This converts data for the Frontend team to use easily.
# ============================================================
class MenuItem(db.Model):
    __tablename__ = 'menu_item'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(120), nullable=False)
    description  = db.Column(db.Text)                          # optional short description
    price        = db.Column(db.Float, nullable=False)
    image_url    = db.Column(db.String(300))                   # filename inside static/img/
    is_available = db.Column(db.Boolean, default=True, nullable=False)  # False = hidden from menu
    category_id  = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)

    # Many-to-Many connection with Tags
    tags = db.relationship('Tag', secondary=menu_item_tag, lazy='subquery',
                           backref=db.backref('items', lazy=True))

    def toggle_available(self):
        """Flip the availability status. Call db.session.commit() after using this."""
        self.is_available = not self.is_available

    def get_dietary_tags(self):
        """Return only dietary tags (used for filter badges like GF, VG on the menu card)."""
        return [t for t in self.tags if t.tag_type == 'dietary']

    def get_badge_tags(self):
        """Return only badge tags (used for icon display like spicy, popular on the menu card)."""
        return [t for t in self.tags if t.tag_type == 'badge']

    def to_dict(self):
        """
        Serialize this item to a plain dictionary.
        Used by the /api/menu JSON endpoint so the frontend
        can fetch menu data without rendering a full HTML template.
        """
        return {
            'id':           self.id,
            'name':         self.name,
            'description':  self.description,
            'price':        self.price,
            'image_url':    self.image_url,
            'is_available': self.is_available,
            'category':     self.category.name,  # returns string e.g. 'main', not the id
            'tags':         [t.label for t in self.tags]
        }

    def __repr__(self):
        return f'<MenuItem {self.name} ฿{self.price}>'
