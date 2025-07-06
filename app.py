import os
import json
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message  # New import

# --- Basic Flask App Setup ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = 'a-super-secret-key-for-sessions'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Flask-Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME') # Your email
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') # Your email password/app password
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app) # New mail instance

# --- Admin Credentials (from Environment Variables) ---
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'password123')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL') # Email to receive notifications

# --- Constants ---
SHIPPING_COST = 250
TAX_RATE = 0

# --- DATABASE MODELS ---
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255))
    price = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(255), nullable=False)
    # --- New Fields for Sales ---
    on_sale = db.Column(db.Boolean, default=False, nullable=False)
    sale_price = db.Column(db.Integer, nullable=True)

    # Helper property to get the current price
    @property
    def current_price(self):
        if self.on_sale and self.sale_price is not None:
            return self.sale_price
        return self.price

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

    @property
    def items(self):
        return json.loads(self.items_json)

    @property
    def totals(self):
        return json.loads(self.totals_json)

# --- LOGIN DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- CART HELPER FUNCTION (UPDATED) ---
def get_cart_details():
    """Calculates cart totals, now using sale prices if applicable."""
    cart_items, totals = [], {}
    subtotal = 0
    cart_ids = session.get('cart', {})
    for product_id, quantity in cart_ids.items():
        product = db.session.get(Product, int(product_id))
        if product:
            # Use the current_price property which handles sales
            price_to_use = product.current_price
            item_total = price_to_use * quantity
            subtotal += item_total
            cart_items.append({
                'id': product.id, 'name': product.name, 'price': price_to_use,
                'image': product.image, 'quantity': quantity, 'item_total': item_total
            })
    shipping = SHIPPING_COST if subtotal > 0 else 0
    tax = int(subtotal * TAX_RATE)
    total = subtotal + shipping + tax
    totals = {'subtotal': subtotal, 'shipping': shipping, 'tax': tax, 'total': total}
    return cart_items, totals

# --- EMAIL HELPER FUNCTION (NEW) ---
def send_order_emails(order):
    """Sends confirmation emails to admin and customer."""
    if not ADMIN_EMAIL or not app.config.get('MAIL_USERNAME'):
        print("WARN: MAIL_USERNAME or ADMIN_EMAIL not set. Skipping emails.")
        return
    try:
        # Email to Admin
        admin_msg = Message(
            subject=f"New Order Received: #{order.id}",
            recipients=[ADMIN_EMAIL]
        )
        admin_msg.html = render_template('email/admin_notification.html', order=order)
        mail.send(admin_msg)

        # Email to Customer
        customer_msg = Message(
            subject="Your M&H Bath Rituals Order Confirmation",
            recipients=[order.email]
        )
        customer_msg.html = render_template('email/customer_confirmation.html', order=order)
        mail.send(customer_msg)
        
        print(f"Order emails sent for Order #{order.id}")

    except Exception as e:
        print(f"Error sending email: {e}")
        flash("Order placed successfully, but there was an issue sending confirmation emails.", "warning")


# --- FRONTEND ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/shop')
def shop():
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
    """Saves order, sends emails, then clears cart."""
    cart_items, totals = get_cart_details()
    if not cart_items:
        return redirect(url_for('shop'))
    
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
    
    # --- Send emails after successful commit ---
    send_order_emails(new_order)
    
    session.pop('cart', None)
    return redirect(url_for('order_success'))

# --- AUTHENTICATION ROUTES ---
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
    sp = request.form.get('sale_price')
    new_product = Product(
        name=request.form.get('name'),
        description=request.form.get('description'),
        price=int(request.form.get('price')),
        image=request.form.get('image'),
        # Handle new sale fields
        on_sale=bool(request.form.get('on_sale')),
        sale_price=int(sp) if sp else None
    )
    db.session.add(new_product)
    db.session.commit()
    flash(f'Product "{new_product.name}" added successfully!', 'success')
    return redirect(url_for('admin'))

# --- NEW: Edit Product Routes ---
@app.route('/admin/edit-product/<int:product_id>', methods=['GET'])
@login_required
def edit_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash('Product not found!', 'danger')
        return redirect(url_for('admin'))
    return render_template('edit_product.html', product=product)

@app.route('/admin/update-product/<int:product_id>', methods=['POST'])
@login_required
def update_product(product_id):
    product_to_update = db.session.get(Product, product_id)
    if not product_to_update:
        flash('Product not found!', 'danger')
        return redirect(url_for('admin'))
    
    sp = request.form.get('sale_price')
    product_to_update.name = request.form.get('name')
    product_to_update.description = request.form.get('description')
    product_to_update.price = int(request.form.get('price'))
    product_to_update.image = request.form.get('image')
    product_to_update.on_sale = True if request.form.get('on_sale') == 'on' else False
    product_to_update.sale_price = int(sp) if sp and product_to_update.on_sale else None
    
    db.session.commit()
    flash(f'Product "{product_to_update.name}" updated successfully!', 'success')
    return redirect(url_for('admin'))
# --- END NEW ROUTES ---

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
    # Before running, make sure to delete database.db and run init_db.py
    # to apply the new Product model schema.
    if not all([app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'], ADMIN_EMAIL]):
        print("\nWARNING: Email environment variables not set.")
        print("Set MAIL_USERNAME, MAIL_PASSWORD, and ADMIN_EMAIL to enable email features.\n")
    
    app.run(debug=True)