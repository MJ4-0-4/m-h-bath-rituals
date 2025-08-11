# These new lines load the .env file automatically
from dotenv import load_dotenv
load_dotenv()

import os
import json
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message

# --- Basic Flask App Setup ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = 'a-super-secret-key-for-sessions'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')

# --- Flask-Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)

# --- Admin Credentials ---
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'password123')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

# --- Constants ---
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
    price = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(255), nullable=False)
    on_sale = db.Column(db.Boolean, default=False, nullable=False)
    sale_price = db.Column(db.Integer, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    # --- NEW FIELDS ---
    ingredients = db.Column(db.Text, nullable=True)
    how_to_use = db.Column(db.Text, nullable=True)

    @property
    def current_price(self):
        if self.on_sale and self.sale_price is not None:
            return self.sale_price
        return self.price

# ... (Order Model and Login Decorator remain the same) ...
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


# --- HELPER FUNCTIONS (No changes needed) ---
def get_cart_details():
    cart_items, totals = [], {}
    subtotal = 0
    cart_ids = session.get('cart', {})
    for product_id, quantity in cart_ids.items():
        product = db.session.get(Product, int(product_id))
        if product:
            price_to_use = product.current_price
            item_total = price_to_use * quantity
            subtotal += item_total
            cart_items.append({'id': product.id, 'name': product.name, 'price': price_to_use, 'image': product.image, 'quantity': quantity, 'item_total': item_total})
    shipping = SHIPPING_COST if subtotal > 0 else 0
    tax = int(subtotal * TAX_RATE)
    total = subtotal + shipping + tax
    totals = {'subtotal': subtotal, 'shipping': shipping, 'tax': tax, 'total': total}
    return cart_items, totals

def send_order_emails(order):
    if not ADMIN_EMAIL or not app.config.get('MAIL_USERNAME'):
        print("WARN: Email features disabled.")
        return
    try:
        admin_msg = Message(subject=f"New Order Received: #{order.id}", recipients=[ADMIN_EMAIL])
        admin_msg.html = render_template('email/admin_notification.html', order=order)
        mail.send(admin_msg)
        customer_msg = Message(subject="Your M&H Bath Rituals Order Confirmation", recipients=[order.email])
        customer_msg.html = render_template('email/customer_confirmation.html', order=order)
        mail.send(customer_msg)
        print(f"Successfully sent order emails for Order #{order.id}")
    except Exception as e:
        print(f"\n--- EMAIL SENDING FAILED: {e} ---\n")
        flash("Order placed, but confirmation emails could not be sent.", "warning")

# --- FRONTEND ROUTES (UPDATED) ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/shop')
def shop():
    categories = Category.query.all()
    return render_template('shop.html', categories=categories)

# --- NEW ROUTE FOR PRODUCT DETAILS ---
# In app.py

# --- UPDATED ROUTE FOR PRODUCT DETAILS ---
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    # Get the main product the user is viewing
    product = db.session.get(Product, product_id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for('shop'))

    # --- NEW LOGIC: Find related products ---
    # Query for products that are in the same category but are NOT the current product itself.
    related_products = Product.query.filter_by(category_id=product.category_id).filter(Product.id != product_id).limit(4).all()

    # Pass both the main product AND the list of related products to the template
    return render_template('product_detail.html', product=product, related_products=related_products)

# ... (Cart and Checkout routes remain the same) ...
@app.route('/cart')
def cart():
    cart_items, totals = get_cart_details()
    return render_template('cart.html', cart_items=cart_items, totals=totals)
@app.route('/add-to-cart/<int:product_id>')
def add_to_cart(product_id):
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session['cart'] = cart
    flash('Added to cart!', 'success')
    # Redirect back to the page the user was on
    return redirect(request.referrer or url_for('shop'))
@app.route('/remove-from-cart/<int:product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    if str(product_id) in cart: del cart[str(product_id)]
    session['cart'] = cart
    return redirect(url_for('cart'))
@app.route('/clear-cart')
def clear_cart():
    session.pop('cart', None)
    return redirect(url_for('cart'))
@app.route('/checkout')
def checkout():
    cart_items, totals = get_cart_details()
    if not cart_items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for('shop'))
    return render_template('checkout.html', cart_items=cart_items, totals=totals)
@app.route('/place-order', methods=['POST'])
def place_order():
    cart_items, totals = get_cart_details()
    if not cart_items: return redirect(url_for('shop'))
    new_order = Order(
        full_name=request.form.get('fullname'), email=request.form.get('email'),
        phone=request.form.get('phone'), address1=request.form.get('address1'),
        address2=request.form.get('address2'), city=request.form.get('city'),
        state=request.form.get('state'), zipcode=request.form.get('zipcode'),
        items_json=json.dumps(cart_items), totals_json=json.dumps(totals)
    )
    db.session.add(new_order)
    db.session.commit()
    send_order_emails(new_order)
    session.pop('cart', None)
    return redirect(url_for('order_success'))
@app.route('/order-success')
def order_success():
    return render_template('order_success.html')

# --- ADMIN & AUTH ROUTES (UPDATED) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    all_products = Product.query.order_by(Product.name).all()
    all_categories = Category.query.all()
    return render_template('admin.html', products=all_products, categories=all_categories)

@app.route('/admin/orders')
@login_required
def admin_orders():
    all_orders = Order.query.order_by(Order.date_created.desc()).all()
    return render_template('admin_orders.html', orders=all_orders)

@app.route('/add-category', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name')
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name))
        db.session.commit()
        flash(f'Category "{name}" added.', 'success')
    return redirect(url_for('admin'))

@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    # ... (file handling code is the same) ...
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

    sp = request.form.get('sale_price')
    new_product = Product(
        name=request.form.get('name'), description=request.form.get('description'),
        price=int(request.form.get('price')), image=image_db_path,
        on_sale=True if request.form.get('on_sale') else False,
        sale_price=int(sp) if sp else None, category_id=int(category_id),
        # --- ADDING NEW DATA ---
        ingredients=request.form.get('ingredients'),
        how_to_use=request.form.get('how_to_use')
    )
    db.session.add(new_product)
    db.session.commit()
    flash(f'Product "{new_product.name}" added.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/edit-product/<int:product_id>', methods=['GET'])
@login_required
def edit_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash('Product not found!', 'danger')
        return redirect(url_for('admin'))
    categories = Category.query.all()
    return render_template('edit_product.html', product=product, categories=categories)

@app.route('/admin/update-product/<int:product_id>', methods=['POST'])
@login_required
def update_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash('Product not found!', 'danger')
        return redirect(url_for('admin'))

    # ... (file handling code is the same) ...
    if 'image' in request.files and request.files['image'].filename != '':
        file = request.files['image']
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        product.image = os.path.join('uploads', filename).replace('\\', '/')

    # ... (other fields are the same) ...
    category_id = request.form.get('category_id')
    if not category_id:
        flash('You must select a category.', 'danger')
        return redirect(url_for('edit_product', product_id=product_id))

    sp = request.form.get('sale_price')
    product.name = request.form.get('name')
    product.description = request.form.get('description')
    product.price = int(request.form.get('price'))
    product.on_sale = True if request.form.get('on_sale') else False
    product.sale_price = int(sp) if sp and product.on_sale else None
    product.category_id = int(category_id)
    # --- UPDATING NEW DATA ---
    product.ingredients = request.form.get('ingredients')
    product.how_to_use = request.form.get('how_to_use')
    
    db.session.commit()
    flash(f'Product "{product.name}" updated.', 'success')
    return redirect(url_for('admin'))

# ... (delete_product, init-db, and main execution block remain the same) ...
@app.route('/delete-product/<int:product_id>')
@login_required
def delete_product(product_id):
    product = db.session.get(Product, product_id)
    if product:
        db.session.delete(product)
        db.session.commit()
        flash(f'Product deleted.', 'success')
    return redirect(url_for('admin'))
@app.cli.command("init-db")
def init_db_command():
    db.drop_all()
    db.create_all()
    default_categories = ['Soaps', 'Travel Packs', 'Bundles', 'Bottled Soap']
    for cat_name in default_categories:
        db.session.add(Category(name=cat_name))
    db.session.commit()
    print("Initialized the database and created default categories.")
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)