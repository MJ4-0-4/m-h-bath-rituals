# Import new modules: wraps from functools
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'a-super-secret-key-for-sessions' # This must be set for sessions to work

# --- NEW: Admin Credentials ---
# For a real application, use environment variables or a more secure config system.
# Do NOT commit real passwords to a public repository.
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'HIRAmaryam111'

# --- File Definitions ---
PRODUCTS_FILE = 'products.json'
ORDERS_FILE = 'orders.json'
SHIPPING_COST = 250
TAX_RATE = 0.00

# --- NEW: Login Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# --- DATA HELPER FUNCTIONS (No changes here) ---
def load_products():
    if not os.path.exists(PRODUCTS_FILE): return []
    try:
        with open(PRODUCTS_FILE, 'r') as f: return json.load(f)
    except json.JSONDecodeError: return []

def save_products(products):
    with open(PRODUCTS_FILE, 'w') as f: json.dump(products, f, indent=2)

def get_product(product_id):
    products = load_products()
    return next((p for p in products if p['id'] == product_id), None)

def load_orders():
    if not os.path.exists(ORDERS_FILE): return []
    try:
        with open(ORDERS_FILE, 'r') as f: return json.load(f)
    except json.JSONDecodeError: return []

def save_orders(orders):
    with open(ORDERS_FILE, 'w') as f: json.dump(orders, f, indent=2)


# --- CART HELPER FUNCTIONS (No changes here) ---
def get_cart_details():
    cart_items, totals = [], {}
    subtotal = 0
    cart_ids = session.get('cart', {})
    for product_id, quantity in cart_ids.items():
        product = get_product(int(product_id))
        if product:
            item_total = product['price'] * quantity
            subtotal += item_total
            cart_items.append({
                'id': product['id'], 'name': product['name'], 'price': product['price'],
                'image': product['image'], 'quantity': quantity, 'item_total': item_total
            })
    shipping = SHIPPING_COST if subtotal > 0 else 0
    tax = int(subtotal * TAX_RATE)
    total = subtotal + shipping + tax
    totals = {'subtotal': subtotal, 'shipping': shipping, 'tax': tax, 'total': total}
    return cart_items, totals

# --- FRONTEND ROUTES (No changes here) ---
@app.route('/')
def home():
    return render_template('index.html')
# ... (all other non-admin routes are unchanged) ...
@app.route('/shop')
def shop():
    products = load_products()
    return render_template('shop.html', products=products)
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
    flash(f'Added to cart!', 'success')
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
    cart_items, totals = get_cart_details()
    if not cart_items: return redirect(url_for('shop'))
    orders = load_orders()
    new_order_id = max([o.get('id', 0) for o in orders], default=0) + 1
    new_order = {
        "id": new_order_id, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "customer_info": {
            'full_name': request.form.get('fullname'), 'email': request.form.get('email'),
            'phone': request.form.get('phone'), 'address1': request.form.get('address1'),
            'address2': request.form.get('address2'), 'city': request.form.get('city'),
            'state': request.form.get('state'), 'zipcode': request.form.get('zipcode'),
        },
        "items": cart_items, "totals": totals
    }
    orders.append(new_order)
    save_orders(orders)
    session.pop('cart', None)
    return redirect(url_for('order_success'))


# --- NEW: AUTHENTICATION ROUTES ---
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


# --- PROTECTED ADMIN ROUTES ---
@app.route('/admin')
@login_required
def admin():
    products = load_products()
    return render_template('admin.html', products=products)

@app.route('/admin/orders')
@login_required
def admin_orders():
    orders = load_orders()
    sorted_orders = sorted(orders, key=lambda x: x.get('id', 0), reverse=True)
    return render_template('admin_orders.html', orders=sorted_orders)

@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    products = load_products()
    name = request.form.get('name')
    description = request.form.get('description')
    price = int(float(request.form.get('price')) * 100)
    image = request.form.get('image')
    new_id = max([p['id'] for p in products], default=0) + 1
    products.append({'id': new_id, 'name': name, 'description': description, 'price': price, 'image': image})
    save_products(products)
    flash(f'Product "{name}" added successfully!', 'success')
    return redirect(url_for('admin'))

@app.route('/delete-product/<int:product_id>')
@login_required
def delete_product(product_id):
    products = load_products()
    products = [p for p in products if p['id'] != product_id]
    save_products(products)
    flash(f'Product deleted successfully!', 'success')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)