import os
import json
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

# --- Basic Flask App Setup ---
# Find the absolute path of the project directory
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# Secret key is needed for sessions
app.secret_key = 'a-super-secret-key-for-sessions'
# Configure the database: we will use a file named database.db in our project folder
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database extension
db = SQLAlchemy(app)

# --- Admin Credentials (from Environment Variables) ---
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'password123')

# --- Constants ---
SHIPPING_COST = 250
TAX_RATE = 0

# --- DATABASE MODELS ---
# This is the blueprint for our database tables.

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255))
    price = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(255), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Customer Info
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    address1 = db.Column(db.String(200), nullable=False)
    address2 = db.Column(db.String(200))
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    zipcode = db.Column(db.String(50), nullable=False)
    
    # Order Details (stored as JSON text)
    items_json = db.Column(db.Text, nullable=False)
    totals_json = db.Column(db.Text, nullable=False)

    # Helper properties to load JSON back into dictionaries
    @property
    def items(self):
        return json.loads(self.items_json)

    @property
    def totals(self):
        return json.loads(self.totals_json)

# --- LOGIN DECORATOR (No changes) ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- CART HELPER FUNCTION (No changes, but now uses the Product model) ---
def get_cart_details():
    cart_items, totals = [], {}
    subtotal = 0
    cart_ids = session.get('cart', {})
    for product_id, quantity in cart_ids.items():
        # Query the database for the product
        product = db.session.get(Product, int(product_id))
        if product:
            item_total = product.price * quantity
            subtotal += item_total
            cart_items.append({
                'id': product.id, 'name': product.name, 'price': product.price,
                'image': product.image, 'quantity': quantity, 'item_total': item_total
            })
    shipping = SHIPPING_COST if subtotal > 0 else 0
    tax = int(subtotal * TAX_RATE)
    total = subtotal + shipping + tax
    totals = {'subtotal': subtotal, 'shipping': shipping, 'tax': tax, 'total': total}
    return cart_items, totals

# --- FRONTEND ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/shop')
def shop():
    # Get all products from the database
    all_products = Product.query.order_by(Product.id).all()
    return render_template('shop.html', products=all_products)

@app.route('/cart')
def cart():
    cart_items, totals = get_cart_details()
    return render_template('cart.html', cart_items=cart_items, totals=totals)

@app.route('/add-to-cart/<int:product_id>')
def add_to_cart(product_id):
    cart = session.get('cart', {})
    product_id_str = str(product_id)
    cart[product_id_str] = cart.get(product_id_str, 0) + 1
    session['cart'] = cart
    flash('Added to cart!', 'success')
    return redirect(url_for('shop'))

@app.route('/remove-from-cart/<int:product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    product_id_str = str(product_id)
    if product_id_str in cart: del cart[product_id_str]
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

@app.route('/order-success')
def order_success():
    return render_template('order_success.html')

@app.route('/place-order', methods=['POST'])
def place_order():
    """Saves the order to the database, then clears the cart."""
    cart_items, totals = get_cart_details()
    if not cart_items:
        return redirect(url_for('shop'))
    
    # Create a new Order object and save it to the database
    new_order = Order(
        full_name=request.form.get('fullname'),
        email=request.form.get('email'),
        phone=request.form.get('phone'),
        address1=request.form.get('address1'),
        address2=request.form.get('address2'),
        city=request.form.get('city'),
        state=request.form.get('state'),
        zipcode=request.form.get('zipcode'),
        items_json=json.dumps(cart_items),
        totals_json=json.dumps(totals)
    )
    
    db.session.add(new_order)
    db.session.commit()
    
    session.pop('cart', None)
    return redirect(url_for('order_success'))

# --- AUTHENTICATION ROUTES (No changes) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('You were successfully logged in.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Invalid credentials. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out.', 'info')
    return redirect(url_for('login'))

# --- ADMIN ROUTES ---
@app.route('/admin')
@login_required
def admin():
    all_products = Product.query.order_by(Product.id).all()
    return render_template('admin.html', products=all_products)

@app.route('/admin/orders')
@login_required
def admin_orders():
    all_orders = Order.query.order_by(Order.date_created.desc()).all()
    return render_template('admin_orders.html', orders=all_orders)

@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    new_product = Product(
        name=request.form.get('name'),
        description=request.form.get('description'),
        price=int(request.form.get('price')),
        image=request.form.get('image')
    )
    db.session.add(new_product)
    db.session.commit()
    flash(f'Product "{new_product.name}" added successfully!', 'success')
    return redirect(url_for('admin'))

@app.route('/delete-product/<int:product_id>')
@login_required
def delete_product(product_id):
    product_to_delete = db.session.get(Product, product_id)
    if product_to_delete:
        db.session.delete(product_to_delete)
        db.session.commit()
        flash(f'Product deleted successfully!', 'success')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)