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
# 2. Connection Table: menu_item_meat
# Links which MeatOptions are available for each MenuItem.
# Example: "Green Curry" can offer Chicken, Pork, or Tofu.
# ============================================================
menu_item_meat = db.Table(
    'menu_item_meat',
    db.Column('menu_item_id',  db.Integer, db.ForeignKey('menu_item.id',  ondelete='CASCADE'), primary_key=True),
    db.Column('meat_option_id',db.Integer, db.ForeignKey('meat_option.id',ondelete='CASCADE'), primary_key=True)
)

# ============================================================
# 3. Connection Table: menu_item_addon
# Links which AddOns are available for each MenuItem.
# Example: "Pad Thai" can offer extra egg, extra shrimp, etc.
# ============================================================
menu_item_addon = db.Table(
    'menu_item_addon',
    db.Column('menu_item_id', db.Integer, db.ForeignKey('menu_item.id', ondelete='CASCADE'), primary_key=True),
    db.Column('addon_id',     db.Integer, db.ForeignKey('add_on.id',    ondelete='CASCADE'), primary_key=True)
)


# ============================================================
# 4. Admin Model
# This is for staff accounts. They can log in to manage the menu.
# - We use UserMixin for the Flask login system.
# - We do not store real passwords. We only store secret hashes for safety.
# ============================================================
class Admin(UserMixin, db.Model):
    __tablename__ = 'admin'

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        """Hash a plain-text password and store it."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Return True if the given plain-text password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Admin {self.username}>'


# ============================================================
# 5. QR Code Model
# This stores QR code info for each table.
# - One table has only one QR code.
# - The 'url' is the link that customers scan to see the menu.
# ============================================================
class QRCode(db.Model):
    __tablename__ = 'qr_code'

    id           = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, unique=True, nullable=False)
    url          = db.Column(db.String(300), nullable=False)

    def __repr__(self):
        return f'<QRCode table={self.table_number}>'


# ============================================================
# 6. Category Model
# This groups food items into sections like Appetizers or Drinks.
# - One Category can have many Menu Items.
# - 'display_order' helps us sort which category shows first.
# ============================================================
CATEGORY_NAMES = ('appetizer', 'main', 'drink', 'dessert')

class Category(db.Model):
    __tablename__ = 'category'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(50), unique=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    items = db.relationship('MenuItem', backref='category', lazy='dynamic',
                            order_by='MenuItem.name')

    def __repr__(self):
        return f'<Category {self.name}>'


# ============================================================
# 7. Tag Model
# These are labels for food like 'Gluten-Free' or 'Spicy'.
# - 'dietary' tags are for healthy filters.
# - 'badge' tags are icons to show on the food card.
# ============================================================
TAG_TYPES = ('dietary', 'badge')

class Tag(db.Model):
    __tablename__ = 'tag'

    id       = db.Column(db.Integer, primary_key=True)
    label    = db.Column(db.String(50), unique=True, nullable=False)
    tag_type = db.Column(db.String(20), nullable=False)  # 'dietary' or 'badge'

    def __repr__(self):
        return f'<Tag {self.label} ({self.tag_type})>'


# ============================================================
# 8. MeatOption Model
# Represents a protein/meat choice that can be offered on a dish.
# - 'name' is what the customer sees (e.g. "Chicken", "Tofu").
# - 'extra_price' is the additional cost for this choice.
#   Most meats will be 0.0, but premium options like shrimp may cost more.
# - 'is_default' marks one option as pre-selected in the UI.
# ============================================================
class MeatOption(db.Model):
    __tablename__ = 'meat_option'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(80), nullable=False)           # e.g. "Chicken", "Pork", "Tofu"
    extra_price = db.Column(db.Float, default=0.0, nullable=False)   # extra charge on top of base price
    is_default  = db.Column(db.Boolean, default=False, nullable=False)  # pre-selected option in UI

    def to_dict(self):
        return {
            'id':          self.id,
            'name':        self.name,
            'extra_price': self.extra_price,
            'is_default':  self.is_default,
        }

    def __repr__(self):
        return f'<MeatOption {self.name} +฿{self.extra_price}>'


# ============================================================
# 9. SpicyLevel Model
# Defines available spice levels for the restaurant (global list).
# - 'level' is a numeric rank used to sort options: 0=no spice, 3=extra hot.
# - 'label' is what the customer sees: "No Spice", "Mild", "Medium", "Hot".
# - 'is_default' marks the pre-selected level (usually "Medium").
# Note: Admin assigns spicy support per dish via MenuItem.has_spicy_option.
#       If has_spicy_option = False, the spicy picker is hidden for that dish.
# ============================================================
class SpicyLevel(db.Model):
    __tablename__ = 'spicy_level'

    id         = db.Column(db.Integer, primary_key=True)
    label      = db.Column(db.String(50), nullable=False)            # e.g. "Mild", "Hot"
    level      = db.Column(db.Integer, nullable=False, unique=True)  # sort order: 0, 1, 2, 3
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            'id':         self.id,
            'label':      self.label,
            'level':      self.level,
            'is_default': self.is_default,
        }

    def __repr__(self):
        return f'<SpicyLevel {self.label} (level={self.level})>'


# ============================================================
# 10. AddOn Model
# Represents an optional extra that can be added to a dish.
# - 'name' is what the customer sees (e.g. "Extra Egg", "Extra Shrimp").
# - 'price' is the additional cost for this add-on.
# ============================================================
class AddOn(db.Model):
    __tablename__ = 'add_on'

    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(100), nullable=False)  # e.g. "Extra Egg", "Extra Tofu"
    price = db.Column(db.Float, nullable=False)         # additional cost

    def to_dict(self):
        return {
            'id':    self.id,
            'name':  self.name,
            'price': self.price,
        }

    def __repr__(self):
        return f'<AddOn {self.name} ฿{self.price}>'


# ============================================================
# 11. Menu Item Model
# This is the main part. It stores food name, price, and image.
# - 'is_available': Admin can hide items if they are sold out.
# - 'has_spicy_option': If True, the spicy level picker shows for this dish.
# - 'meat_options': List of MeatOption choices available for this dish.
# - 'add_ons': List of AddOn extras available for this dish.
# - 'to_dict': Converts all data including options for the Frontend team.
# ============================================================
class MenuItem(db.Model):
    __tablename__ = 'menu_item'

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(120), nullable=False)
    description      = db.Column(db.Text)
    price            = db.Column(db.Float, nullable=False)
    image_url        = db.Column(db.String(300))                          # filename inside static/img/
    is_available     = db.Column(db.Boolean, default=True,  nullable=False)  # False = hidden from menu
    has_spicy_option = db.Column(db.Boolean, default=False, nullable=False)  # True = show spicy picker
    category_id      = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)

    # Many-to-Many: dietary/badge tags (existing)
    tags = db.relationship('Tag', secondary=menu_item_tag, lazy='subquery',
                           backref=db.backref('items', lazy=True))

    # Many-to-Many: available meat/protein choices for this dish
    meat_options = db.relationship('MeatOption', secondary=menu_item_meat, lazy='subquery',
                                   backref=db.backref('menu_items', lazy=True))

    # Many-to-Many: available add-ons for this dish
    add_ons = db.relationship('AddOn', secondary=menu_item_addon, lazy='subquery',
                              backref=db.backref('menu_items', lazy=True))

    def toggle_available(self):
        """Flip the availability status. Call db.session.commit() after using this."""
        self.is_available = not self.is_available

    def get_dietary_tags(self):
        """Return only dietary tags (GF, VG) for filter badges on the menu card."""
        return [t for t in self.tags if t.tag_type == 'dietary']

    def get_badge_tags(self):
        """Return only badge tags (spicy, popular) for icon display on the menu card."""
        return [t for t in self.tags if t.tag_type == 'badge']

    def get_default_meat(self):
        """Return the default MeatOption, or the first one if none is marked default."""
        default = next((m for m in self.meat_options if m.is_default), None)
        return default or (self.meat_options[0] if self.meat_options else None)

    def to_dict(self):
        """
        Serialize this item to a dictionary including all customization options.
        Used by /api/menu so the frontend can build pickers without extra requests.
        SpicyLevel list is fetched via /api/spicy-levels (global, same for all items).
        """
        return {
            'id':               self.id,
            'name':             self.name,
            'description':      self.description,
            'price':            self.price,
            'image_url':        self.image_url,
            'is_available':     self.is_available,
            'has_spicy_option': self.has_spicy_option,
            'category':         self.category.name,
            'tags':             [t.label for t in self.tags],
            'meat_options':     [m.to_dict() for m in self.meat_options],
            'add_ons':          [a.to_dict() for a in self.add_ons],
        }

    def __repr__(self):
        return f'<MenuItem {self.name} ฿{self.price}>'
