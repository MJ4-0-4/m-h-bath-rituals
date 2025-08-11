# ... (imports remain the same) ...
from dotenv import load_dotenv
load_dotenv()
import os
import json
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message

# ... (app setup and config remain the same) ...
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = 'a-super-secret-key-for-sessions'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')
db = SQLAlchemy(app)
mail = Mail(app)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'password123')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
SHIPPING_COST = 250
TAX_RATE = 0

# --- DATABASE MODELS (UPDATED) ---
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255))
    image = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    ingredients = db.Column(db.Text, nullable=True)
    how_to_use = db.Column(db.Text, nullable=True)
    # --- NEW: Relationship to Variants ---
    variants = db.relationship('Variant', backref='product', lazy=True, cascade="all, delete-orphan")

    # --- REMOVED: Price columns are now in the Variant model ---
    # price = db.Column(...)
    # on_sale = db.Column(...)
    # sale_price = db.Column(...)
    
    # Helper property to get the starting price for display
    @property
    def starting_price(self):
        if self.variants:
            return min(v.price for v in self.variants)
        return 0

# --- NEW: Variant Model ---
class Variant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    size = db.Column(db.String(100), nullable=False) # e.g., "100g", "250ml"
    price = db.Column(db.Integer, nullable=False)

# ... (Order model and login decorator are unchanged) ...
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    address1 = db.Column(db.String(200), nullable=False)
    address2 = db.Column(db.String(200))
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    zipcode = db.Column(db.String(50), nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    totals_json = db.Column(db.Text, nullable=False)
    @property
    def items(self): return json.loads(self.items_json)
    @property
    def totals(self): return json.loads(self.totals_json)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- HELPER FUNCTIONS (UPDATED) ---
def get_cart_details():
    cart_items, totals = [], {}
    subtotal = 0
    # Cart format is now {'variant_id': quantity}
    cart_ids = session.get('cart', {})
    for variant_id, quantity in cart_ids.items():
        variant = db.session.get(Variant, int(variant_id))
        if variant:
            item_total = variant.price * quantity
            subtotal += item_total
            cart_items.append({
                'product_id': variant.product.id,
                'variant_id': variant.id,
                'name': variant.product.name,
                'size': variant.size,
                'price': variant.price,
                'image': variant.product.image,
                'quantity': quantity,
                'item_total': item_total
            })
    shipping = SHIPPING_COST if subtotal > 0 else 0
    tax = int(subtotal * TAX_RATE)
    total = subtotal + shipping + tax
    totals = {'subtotal': subtotal, 'shipping': shipping, 'tax': tax, 'total': total}
    return cart_items, totals

# ... (send_order_emails is unchanged) ...

# --- FRONTEND ROUTES (UPDATED) ---
@app.route('/shop')
def shop():
    categories = Category.query.all()
    return render_template('shop.html', categories=categories)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for('shop'))
    related_products = Product.query.filter_by(category_id=product.category_id).filter(Product.id != product_id).limit(4).all()
    return render_template('product_detail.html', product=product, related_products=related_products)

# --- CART ROUTES (UPDATED) ---
@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    variant_id = request.form.get('variant_id')
    if not variant_id:
        return jsonify({'error': 'No size selected'}), 400
    
    cart = session.get('cart', {})
    cart[str(variant_id)] = cart.get(str(variant_id), 0) + 1
    session['cart'] = cart
    
    variant = Variant.query.get(variant_id)
    flash(f'Added "{variant.product.name} ({variant.size})" to cart!', 'success')
    return redirect(request.referrer or url_for('shop'))

@app.route('/remove-from-cart/<int:variant_id>')
def remove_from_cart(variant_id):
    cart = session.get('cart', {})
    if str(variant_id) in cart: del cart[str(variant_id)]
    session['cart'] = cart
    return redirect(url_for('cart'))

# ... (Other routes like checkout, place_order, home are largely unchanged but depend on the new cart logic) ...

# --- ADMIN ROUTES (UPDATED) ---
@app.route('/admin')
@login_required
def admin():
    all_products = Product.query.order_by(Product.name).all()
    all_categories = Category.query.all()
    return render_template('admin.html', products=all_products, categories=all_categories)

@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    # ... (file handling and basic product info) ...
    if 'image' not in request.files or request.files['image'].filename == '':
        flash('Product image is required.', 'danger')
        return redirect(url_for('admin'))
    file = request.files['image']
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    image_db_path = os.path.join('uploads', filename).replace('\\', '/')

    category_id = request.form.get('category_id')
    if not category_id:
        flash('You must select a category.', 'danger')
        return redirect(url_for('admin'))

    new_product = Product(
        name=request.form.get('name'),
        description=request.form.get('description'),
        image=image_db_path,
        category_id=int(category_id),
        ingredients=request.form.get('ingredients'),
        how_to_use=request.form.get('how_to_use')
    )
    db.session.add(new_product)
    
    # --- NEW: Add Variants ---
    sizes = request.form.getlist('size[]')
    prices = request.form.getlist('price[]')

    if not sizes or not prices or not sizes[0]:
        flash('At least one size and price variant is required.', 'danger')
        return redirect(url_for('admin'))

    for size, price in zip(sizes, prices):
        if size and price:
            variant = Variant(product=new_product, size=size, price=int(price))
            db.session.add(variant)

    db.session.commit()
    flash(f'Product "{new_product.name}" and its variants added.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/edit-product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = db.session.get(Product, product_id)
    if not product: return redirect(url_for('admin'))
    
    if request.method == 'POST':
        # --- UPDATE LOGIC ---
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.category_id = int(request.form.get('category_id'))
        product.ingredients = request.form.get('ingredients')
        product.how_to_use = request.form.get('how_to_use')
        
        if 'image' in request.files and request.files['image'].filename != '':
            file = request.files['image']
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            product.image = os.path.join('uploads', filename).replace('\\', '/')

        # --- UPDATE VARIANTS ---
        # Delete old variants
        for v in product.variants:
            db.session.delete(v)
        
        # Add new ones from the form
        sizes = request.form.getlist('size[]')
        prices = request.form.getlist('price[]')
        for size, price in zip(sizes, prices):
            if size and price:
                variant = Variant(product=product, size=size, price=int(price))
                db.session.add(variant)
        
        db.session.commit()
        flash(f'Product "{product.name}" updated successfully!', 'success')
        return redirect(url_for('admin'))
    
    # --- GET LOGIC ---
    categories = Category.query.all()
    return render_template('edit_product.html', product=product, categories=categories)


# ... (delete_product, init-db, and main execution block remain the same, but `delete_product` will now also delete variants because of the cascade option) ...